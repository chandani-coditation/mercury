"""Database connection utilities with connection pooling and retries."""

import os
import time
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

# Import logger (with fallback if ai_service not available)
try:
    from ai_service.core import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Global connection pool
_db_pool: ConnectionPool = None

# Retry configuration (can be overridden via environment variables)
DB_CONN_RETRIES = int(os.getenv("DB_CONN_RETRIES", "3"))
DB_CONN_RETRY_BASE_DELAY = float(os.getenv("DB_CONN_RETRY_BASE_DELAY", "1.0"))
DB_CONN_RETRY_MAX_DELAY = float(os.getenv("DB_CONN_RETRY_MAX_DELAY", "5.0"))


def init_db_pool(min_size: int = 2, max_size: int = 10, timeout: int = 30):
    """
    Initialize the database connection pool.

    Validates database password strength in production environments to ensure security.

    Args:
        min_size: Minimum number of connections in pool (default: 2)
        max_size: Maximum number of connections in pool (default: 10)
        timeout: Connection timeout in seconds (default: 30)

    Raises:
        ValueError: If password validation fails in production
    """
    global _db_pool
    if _db_pool is not None:
        logger.warning("Database pool already initialized")
        return

    # Validate database password in production
    try:
        from ai_service.core.password_validator import validate_database_password

        is_valid, errors = validate_database_password()
        if not is_valid:
            error_msg = "Database password validation failed:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
    except ImportError:
        # If password validator is not available, log warning but continue
        logger.warning(
            "Password validator not available. Skipping password validation. "
            "Ensure POSTGRES_PASSWORD is set to a strong password in production."
        )

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "nocdb")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")

    # Increase connect_timeout and add wait timeout for pool connections
    wait_timeout = int(
        os.getenv("DB_POOL_WAIT_TIMEOUT", "10")
    )  # Wait up to 10s for available connection

    conninfo = f"host={host} port={port} dbname={dbname} user={user} password={password} connect_timeout={timeout}"

    try:
        _db_pool = ConnectionPool(
            conninfo,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=False,
            timeout=wait_timeout,  # Wait timeout for getting connection from pool
        )
        _db_pool.open()
        logger.info(
            f"Database connection pool initialized: min={min_size}, max={max_size}, connect_timeout={timeout}s, wait_timeout={wait_timeout}s"
        )

        # Test the pool with a quick connection
        try:
            with get_db_connection_context() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.close()
            logger.debug("Database pool connection test successful")
        except Exception as test_error:
            logger.warning(f"Database pool connection test failed: {test_error}")
            # Don't raise - pool might still work, just log the warning
    except Exception as e:
        logger.error("Failed to initialize database pool", exc_info=True)
        raise


def close_db_pool():
    """Close the database connection pool."""
    global _db_pool
    if _db_pool is not None:
        _db_pool.close()
        _db_pool = None
        logger.info("Database connection pool closed")


def _create_direct_connection():
    """
    Create a direct database connection (bypassing connection pool).

    This is used as a fallback when the connection pool is not initialized.
    Should only be used in exceptional circumstances.

    Returns:
        psycopg.Connection: Database connection object
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "nocdb")
    logger.debug(f"Connecting to database directly: {host}:{port}/{dbname}")
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "nocdb"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        row_factory=dict_row,
    )


def _get_db_connection():
    """
    Internal function to get a database connection from the pool.
    Falls back to direct connection if pool is not initialized.
    Includes retry logic for transient failures.

    NOTE: This function should NOT be used directly. Use get_db_connection_context() instead
    to ensure connections are properly returned to the pool.
    """
    last_error = None
    for attempt in range(DB_CONN_RETRIES):
        try:
            if _db_pool is not None:
                # Use getconn() with timeout handling - if pool is exhausted, it will raise PoolTimeout
                try:
                    return _db_pool.getconn()
                except Exception as pool_exc:
                    # If pool timeout or other pool error, log and retry
                    if (
                        "timeout" in str(pool_exc).lower()
                        or "pool" in str(pool_exc).lower()
                    ):
                        logger.warning(
                            f"Connection pool timeout/error (attempt {attempt + 1}/{DB_CONN_RETRIES}): {pool_exc}. "
                            f"Pool may be exhausted. Retrying..."
                        )
                        last_error = pool_exc
                        if attempt < DB_CONN_RETRIES - 1:
                            delay = min(
                                DB_CONN_RETRY_BASE_DELAY * (2**attempt),
                                DB_CONN_RETRY_MAX_DELAY,
                            )
                            time.sleep(delay)
                            continue
                    raise  # Re-raise if not a timeout/pool issue
            return _create_direct_connection()
        except psycopg.OperationalError as exc:
            last_error = exc
            delay = min(
                DB_CONN_RETRY_BASE_DELAY * (2**attempt),
                DB_CONN_RETRY_MAX_DELAY,
            )
            # Only log as warning if it's not a timeout (timeouts are expected when pool is busy)
            if "timeout" not in str(exc).lower():
                logger.warning(
                    "Database connection attempt %s/%s failed: %s. Retrying in %.2fs",
                    attempt + 1,
                    DB_CONN_RETRIES,
                    exc,
                    delay,
                )
            else:
                logger.debug(
                    "Database connection timeout (attempt %s/%s): %s. Retrying in %.2fs",
                    attempt + 1,
                    DB_CONN_RETRIES,
                    exc,
                    delay,
                )
            time.sleep(delay)
        except Exception as exc:  # pragma: no cover - unexpected path
            last_error = exc
            logger.error("Database connection error: %s", exc, exc_info=True)
            break
    if last_error:
        raise last_error


@contextmanager
def get_db_connection_context():
    """
    Context manager for database connections.
    Automatically returns connection to pool when done.
    Handles connection errors gracefully.
    """
    conn = None
    try:
        conn = _get_db_connection()
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}", exc_info=True)
        # If connection is bad, don't return it to pool
        if conn and _db_pool is not None:
            try:
                _db_pool.putconn(conn, close=True)  # Close bad connection
            except Exception:
                pass  # Ignore errors when closing bad connection
            finally:
                conn = None
        raise
    finally:
        if conn is not None:
            if _db_pool is not None:
                try:
                    _db_pool.putconn(conn)
                except Exception as e:
                    logger.warning(f"Error returning connection to pool: {e}")
                    # Try to close the connection if returning to pool fails
                    try:
                        conn.close()
                    except Exception:
                        pass
                finally:
                    conn = None
            else:
                try:
                    conn.close()
                except Exception:
                    pass
                finally:
                    conn = None


# Removed get_db_cursor() - use get_db_connection_context() instead
# This function was removed to prevent connection leaks.
# Always use: with get_db_connection_context() as conn: cur = conn.cursor()
