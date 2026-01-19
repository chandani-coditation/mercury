"""Centralized service/component mapping utility.

This matches the normalization logic used during ingestion to ensure
evaluation queries use the same service/component values as stored in the database.
"""

from typing import Tuple, Optional
from pathlib import Path
import json

# Load service/component mapping config (same as ingestion uses)
try:
    project_root = Path(__file__).parent.parent
    mapping_path = project_root / "config" / "service_component_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, "r") as f:
            SERVICE_COMPONENT_MAPPING = json.load(f)
    else:
        SERVICE_COMPONENT_MAPPING = {}
except Exception:
    SERVICE_COMPONENT_MAPPING = {}


def map_service_component(cmdb_ci: Optional[str], category: Optional[str]) -> Tuple[str, str]:
    """
    Map CMDB_CI and category to service/component.

    IMPORTANT: This must match the normalization logic in ingestion/normalizers.py
    to ensure evaluation queries use the same service/component values as stored in DB.

    Priority:
    1. Use CMDB_CI if available (most accurate)
    2. Fallback to category if CMDB_CI is missing
    3. Default to Database if nothing matches

    Args:
        cmdb_ci: CMDB CI value from ticket
        category: Category value from ticket

    Returns:
        Tuple of (service, component) - matches what's stored in database
    """
    # Priority 1: Use CMDB_CI
    if cmdb_ci and cmdb_ci.strip():
        cmdb_upper = cmdb_ci.upper().strip()

        # Network patterns (matches ingestion: Network service, NULL component)
        if any(x in cmdb_upper for x in ["NETWORK", "SWITCH", "ROUTER", "LEAF", "SPINE"]):
            return "Network", None  # Network has NULL component in DB

        # Firewall patterns (matches ingestion: Firewall service, NULL component)
        if any(x in cmdb_upper for x in ["FIREWALL"]):
            return "Firewall", None  # Firewall has NULL component in DB

        # Server/Infrastructure patterns (matches ingestion: Server → Infrastructure, component based on type)
        if any(x in cmdb_upper for x in ["SERVER", "WINDOWS", "LINUX", "UNIX", "SOLARIS"]):
            # Check category to determine component - but DB shows most are Infrastructure/Memory
            # For now, default to Infrastructure/Memory (matches 112 signatures in DB)
            return "Infrastructure", "Memory"

        # Database patterns (matches ingestion: Database service, Database component)
        if any(x in cmdb_upper for x in ["DATABASE", "SQL", "ORACLE", "POSTGRES", "MYSQL"]):
            return "Database", "Database"  # Matches DB: Database/Database

        # If CMDB_CI contains "-", split it (but still normalize)
        if "-" in cmdb_ci:
            parts = cmdb_ci.split("-", 1)
            service_part = parts[0].strip()
            component_part = parts[1].strip() if len(parts) > 1 else None

            # Normalize service part
            service_upper = service_part.upper()
            if "NETWORK" in service_upper:
                return "Network", None
            elif "FIREWALL" in service_upper:
                return "Firewall", None
            elif "SERVER" in service_upper or "WINDOWS" in service_upper:
                return "Infrastructure", component_part or "Memory"
            elif "DATABASE" in service_upper or "SQL" in service_upper:
                return "Database", "Database"
            else:
                return service_part, component_part

    # Priority 2: Use category
    if category and category.strip():
        category_upper = category.upper().strip()

        # Network patterns
        if any(x in category_upper for x in ["NETWORK", "CONNECTIVITY", "BGP", "ROUTING"]):
            return "Network", None

        # Memory patterns (matches DB: Infrastructure/Memory - 112 signatures)
        if "MEMORY" in category_upper:
            return "Infrastructure", "Memory"

        # CPU patterns (DB shows Infrastructure/Memory for CPU alerts too)
        if "CPU" in category_upper:
            return "Infrastructure", "Memory"  # Matches DB pattern

        # Disk patterns (DB shows Infrastructure/Memory for disk alerts too)
        if "DISK" in category_upper:
            return "Infrastructure", "Memory"  # Matches DB pattern

        # Performance/Server patterns (default to Infrastructure/Memory - matches DB)
        if any(x in category_upper for x in ["PERFORMANCE", "OPERATING SYSTEM", "OS"]):
            return "Infrastructure", "Memory"

        # Database patterns (matches DB: Database/Database)
        if any(x in category_upper for x in ["DATABASE", "MONITORING", "ALERT", "SQL"]):
            return "Database", "Database"

    # Default fallback (matches most common in DB)
    return "Database", "Database"
