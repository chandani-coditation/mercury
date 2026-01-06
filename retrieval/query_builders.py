"""Query builder utilities for hybrid search queries.

Centralizes common query patterns, scoring formulas, and parameter building
to ensure consistency across all retrieval queries.
"""

from typing import Optional, List, Tuple


class HybridSearchQueryBuilder:
    """Builds hybrid search queries with RRF fusion and soft filter boosts."""

    # RRF configuration
    DEFAULT_RRF_K = 60
    
    # Soft filter boost values
    SERVICE_EXACT_MATCH_BOOST = 0.15
    SERVICE_PARTIAL_MATCH_BOOST = 0.10
    COMPONENT_EXACT_MATCH_BOOST = 0.10
    COMPONENT_PARTIAL_MATCH_BOOST = 0.05
    COMPONENT_NULL_BOOST = 0.05  # For incident signatures when component is NULL
    
    # Limit multipliers for RRF fusion
    # Higher multiplier = more candidates for better fusion results
    RRF_CANDIDATE_MULTIPLIER = 3  # Changed from 2 to 3 for better results

    @staticmethod
    def build_rrf_score_formula(
        vector_weight: float, fulltext_weight: float, rrf_k: int = DEFAULT_RRF_K
    ) -> str:
        """
        Returns RRF score calculation SQL fragment.
        
        RRF (Reciprocal Rank Fusion) formula:
        score = (1/(k + vector_rank) * vector_weight) + (1/(k + fulltext_rank) * fulltext_weight)
        
        Args:
            vector_weight: Weight for vector search results (0-1)
            fulltext_weight: Weight for full-text search results (0-1)
            rrf_k: RRF constant (default 60, higher = less aggressive ranking)
        
        Returns:
            SQL fragment for RRF score calculation
        """
        return f"""
            (1.0 / ({rrf_k}.0 + COALESCE(v.vector_rank, 999))) * {vector_weight} +
            (1.0 / ({rrf_k}.0 + COALESCE(f.fulltext_rank, 999))) * {fulltext_weight}
        """

    @staticmethod
    def build_service_boost_case(
        metadata_alias: str = "COALESCE(v.metadata->>'service', f.metadata->>'service', '')"
    ) -> str:
        """
        Returns service match boost CASE statement.
        
        Args:
            metadata_alias: SQL expression to access service field in metadata
        
        Returns:
            SQL CASE statement for service match boost
        """
        return f"""
            CASE 
                WHEN COALESCE(%s, '') = '' THEN 0.0
                WHEN LOWER({metadata_alias}) = LOWER(%s) THEN {HybridSearchQueryBuilder.SERVICE_EXACT_MATCH_BOOST}
                WHEN LOWER({metadata_alias}) LIKE LOWER(%s) THEN {HybridSearchQueryBuilder.SERVICE_PARTIAL_MATCH_BOOST}
                ELSE 0.0
            END
        """

    @staticmethod
    def build_component_boost_case(
        metadata_alias: str = "COALESCE(v.metadata->>'component', f.metadata->>'component', '')",
        allow_null_boost: bool = False,
    ) -> str:
        """
        Returns component match boost CASE statement.
        """
        null_boost_clause = ""
        if allow_null_boost:
            null_boost_clause = f"""
                WHEN {metadata_alias} = '' THEN {HybridSearchQueryBuilder.COMPONENT_NULL_BOOST}
            """

        return f"""
            CASE 
                WHEN COALESCE(%s, '') = '' THEN 0.0{null_boost_clause}
                WHEN LOWER({metadata_alias}) = LOWER(%s)
                    THEN {HybridSearchQueryBuilder.COMPONENT_EXACT_MATCH_BOOST}
                WHEN LOWER({metadata_alias}) LIKE LOWER(%s)
                    THEN {HybridSearchQueryBuilder.COMPONENT_PARTIAL_MATCH_BOOST}
                ELSE 0.0
            END
        """

    @staticmethod
    def build_service_boost_case_dual(
        service_alias: str = "COALESCE(v.metadata->>'service', f.metadata->>'service', '')",
        affected_service_alias: str = "COALESCE(v.metadata->>'affected_service', f.metadata->>'affected_service', '')",
    ) -> str:
        """
        Returns service match boost CASE statement that checks both service and affected_service.
        """
        return f"""
            CASE 
                WHEN COALESCE(%s, '') = '' THEN 0.0
                WHEN LOWER({service_alias}) = LOWER(%s)
                    OR LOWER({affected_service_alias}) = LOWER(%s)
                    THEN {HybridSearchQueryBuilder.SERVICE_EXACT_MATCH_BOOST}
                WHEN LOWER({service_alias}) LIKE LOWER(%s)
                    OR LOWER({affected_service_alias}) LIKE LOWER(%s)
                    THEN {HybridSearchQueryBuilder.SERVICE_PARTIAL_MATCH_BOOST}
                ELSE 0.0
            END
        """

    @staticmethod
    def build_soft_filter_boost_params(
        service_val: Optional[str], component_val: Optional[str]
    ) -> List[Optional[str]]:
        """
        Builds standardized parameter list for soft filter boosts.
        
        Returns parameters in order:
        - service_val (for IS NULL check)
        - service_val (for exact match)
        - service_val with % (for partial match)
        - component_val (for IS NULL check)
        - component_val (for exact match)
        - component_val with % (for partial match)
        
        Args:
            service_val: Service value to match (can be None)
            component_val: Component value to match (can be None)
        
        Returns:
            List of 6 parameters for soft filter boosts
        
        Note: For PostgreSQL type inference, None values are kept as None for IS NULL checks,
        but converted to empty strings for text comparisons to avoid IndeterminateDatatype errors.
        """
        params = []
        # Service params (3 params)
        # Keep None for IS NULL check (no type cast needed in SQL)
        params.append(service_val)  # IS NULL check
        # Use empty string instead of None for text comparisons to avoid type inference issues
        params.append(service_val if service_val else "")  # Exact match
        params.append(f"%{service_val}%" if service_val else "")  # Partial match
        # Component params (3 params)
        params.append(component_val)  # IS NULL check
        params.append(component_val if component_val else "")  # Exact match
        params.append(f"%{component_val}%" if component_val else "")  # Partial match
        return params

    @staticmethod
    def build_soft_filter_boost_params_dual_service(
        service_val: Optional[str], component_val: Optional[str]
    ) -> List[Optional[str]]:
        """
        Builds parameter list for soft filter boosts with dual service matching.
        
        Used for incident signatures which check both service and affected_service.
        Returns 8 parameters (6 for service + 2 extra for affected_service).
        
        Args:
            service_val: Service value to match (can be None)
            component_val: Component value to match (can be None)
        
        Returns:
            List of 8 parameters for dual service soft filter boosts
        
        Note: For PostgreSQL type inference, None values are kept as None for IS NULL checks,
        but converted to empty strings for text comparisons to avoid IndeterminateDatatype errors.
        """
        params = []
        # Service params (5 params: check, exact x2, partial x2)
        # Keep None for IS NULL check (no type cast needed in SQL)
        params.append(service_val)  # IS NULL check
        # Use empty string instead of None for text comparisons to avoid type inference issues
        params.append(service_val if service_val else "")  # Exact match (service field)
        params.append(service_val if service_val else "")  # Exact match (affected_service field)
        params.append(f"%{service_val}%" if service_val else "")  # Partial match (service field)
        params.append(f"%{service_val}%" if service_val else "")  # Partial match (affected_service field)
        # Component params (3 params)
        params.append(component_val)  # IS NULL check
        params.append(component_val if component_val else "")  # Exact match
        params.append(f"%{component_val}%" if component_val else "")  # Partial match
        return params

    @staticmethod
    def build_soft_filter_boost_params_for_order_by(
        service_val: Optional[str], component_val: Optional[str]
    ) -> List[Optional[str]]:
        """
        Builds parameter list for soft filter boosts used in ORDER BY clause.
        
        Returns parameters in order (duplicated for SELECT and ORDER BY):
        - Service params (3) for SELECT
        - Component params (3) for SELECT
        - Service params (3) for ORDER BY
        - Component params (3) for ORDER BY
        
        Used for runbook metadata query which calculates boosts in both SELECT and ORDER BY.
        
        Args:
            service_val: Service value to match (can be None)
            component_val: Component value to match (can be None)
        
        Returns:
            List of 12 parameters (6 for SELECT + 6 for ORDER BY)
        """
        # Build base params (6 params)
        base_params = HybridSearchQueryBuilder.build_soft_filter_boost_params(
            service_val, component_val
        )
        # Duplicate for ORDER BY (another 6 params)
        return base_params + base_params

    @staticmethod
    def calculate_rrf_candidate_limit(final_limit: int) -> int:
        """
        Calculates the limit for RRF candidate collection (vector and fulltext CTEs).
        
        For better RRF fusion results, we need more candidates than the final limit.
        Higher multiplier = better fusion quality but slower queries.
        
        Args:
            final_limit: Desired final number of results
        
        Returns:
            Limit to use for vector and fulltext candidate collection
        """
        return max(final_limit * HybridSearchQueryBuilder.RRF_CANDIDATE_MULTIPLIER, 20)

    @staticmethod
    def validate_parameter_count(
        query: str, params: List, expected_count: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Validates that parameter count matches query placeholders.
        
        Args:
            query: SQL query string with %s placeholders
            params: List of parameters
            expected_count: Expected parameter count (if None, counts placeholders)
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        placeholder_count = query.count("%s")
        param_count = len(params)
        
        if expected_count is not None:
            if param_count != expected_count:
                return (
                    False,
                    f"Parameter count mismatch: expected {expected_count} but got {param_count}",
                )
        else:
            if param_count != placeholder_count:
                return (
                    False,
                    f"Parameter count mismatch: query has {placeholder_count} placeholders "
                    f"but {param_count} parameters provided",
                )
        
        return (True, "")

