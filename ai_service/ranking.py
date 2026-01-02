"""Ranking logic for Resolution Agent.

Per architecture: Steps are ranked by:
- Historical success
- Risk level
- Relevance to incident signature
"""

from typing import List, Dict, Optional
from ai_service.core import get_logger

logger = get_logger(__name__)


def rank_steps(
    steps: List[Dict],
    incident_signature: Dict,
    historical_resolutions: List[Dict],
    step_success_stats: Dict[str, Dict],
) -> List[Dict]:
    """
    Rank runbook steps by relevance, historical success, and risk.
    
    Per architecture: Steps are ranked, not invented.
    
    Args:
        steps: List of runbook step chunks
        incident_signature: Incident signature from triage output
        historical_resolutions: Historical resolution records
        step_success_stats: Success statistics per step_id
        
    Returns:
        List of ranked steps with scores and provenance
    """
    if not steps:
        return []
    
    failure_type = incident_signature.get("failure_type", "").lower()
    error_class = incident_signature.get("error_class", "").lower()
    
    # Score each step
    scored_steps = []
    
    for step in steps:
        step_id = step.get("step_id", "")
        action = (step.get("action") or "").lower() if step.get("action") else ""
        condition = (step.get("condition") or "").lower() if step.get("condition") else ""
        risk_level = (step.get("risk_level") or "medium").lower() if step.get("risk_level") else "medium"
        content = (step.get("content") or "").lower() if step.get("content") else ""
        
        # Initialize scores
        relevance_score = 0.0
        success_score = 0.0
        risk_score = 0.0
        
        # 1. Relevance score (0.0 - 1.0)
        # Check if step condition/action matches failure_type or error_class
        if failure_type and failure_type in condition:
            relevance_score += 0.4
        if failure_type and failure_type in action:
            relevance_score += 0.3
        if error_class and error_class in condition:
            relevance_score += 0.2
        if error_class and error_class in action:
            relevance_score += 0.1
        
        # Check content relevance
        if failure_type and failure_type in content:
            relevance_score += 0.2
        if error_class and error_class in content:
            relevance_score += 0.1
        
        # Cap relevance at 1.0
        relevance_score = min(relevance_score, 1.0)
        
        # If no explicit match, give base relevance based on runbook match
        if relevance_score == 0.0:
            relevance_score = 0.3  # Base relevance if step is from matched runbook
        
        # 2. Historical success score (0.0 - 1.0)
        if step_id in step_success_stats:
            stats = step_success_stats[step_id]
            success_score = stats.get("success_rate", 0.5)
            
            # Boost for frequently used steps (more data = more reliable)
            if stats.get("total_uses", 0) > 3:
                success_score = min(success_score * 1.1, 1.0)
        else:
            # No history = neutral score
            success_score = 0.5
        
        # Check historical resolutions for step usage patterns
        step_mentioned_count = 0
        step_successful_count = 0
        
        for hist_res in historical_resolutions:
            resolution_output = hist_res.get("resolution_output", {})
            steps_list = resolution_output.get("steps", [])
            
            # Check if this step is mentioned in historical resolution
            step_found = any(
                step_id in str(step_text) or 
                action in str(step_text).lower() or
                step.get("chunk_id") in str(resolution_output.get("provenance", []))
                for step_text in steps_list
            )
            
            if step_found:
                step_mentioned_count += 1
                if hist_res.get("is_successful", False):
                    step_successful_count += 1
        
        # Update success score based on historical resolutions
        if step_mentioned_count > 0:
            hist_success_rate = step_successful_count / step_mentioned_count
            # Blend with existing success score
            success_score = (success_score * 0.6) + (hist_success_rate * 0.4)
        
        # 3. Risk score (inverted: lower risk = higher score)
        risk_map = {"low": 1.0, "medium": 0.7, "high": 0.4}
        risk_score = risk_map.get(risk_level, 0.7)
        
        # Combined score (weighted)
        # Relevance: 40%, Success: 40%, Risk: 20%
        combined_score = (
            relevance_score * 0.4 +
            success_score * 0.4 +
            risk_score * 0.2
        )
        
        scored_steps.append({
            **step,
            "relevance_score": relevance_score,
            "success_score": success_score,
            "risk_score": risk_score,
            "combined_score": combined_score,
        })
    
    # Sort by combined score (descending)
    ranked_steps = sorted(scored_steps, key=lambda x: x["combined_score"], reverse=True)
    
    top_scores = [f"{s['combined_score']:.3f}" for s in ranked_steps[:3]]
    logger.debug(
        f"Ranked {len(ranked_steps)} steps. Top 3 scores: {top_scores}"
    )
    
    return ranked_steps


def assemble_recommendations(
    ranked_steps: List[Dict],
    min_confidence: float = 0.6,
    max_steps: int = 10
) -> List[Dict]:
    """
    Assemble ordered recommendations from ranked steps.
    
    Per architecture: Recommendations must have provenance.
    
    Args:
        ranked_steps: List of ranked steps with scores
        min_confidence: Minimum confidence threshold
        max_steps: Maximum number of steps to include
        
    Returns:
        List of recommendation objects with provenance
    """
    recommendations = []
    
    for step in ranked_steps[:max_steps]:
        # Only include steps above confidence threshold
        if step["combined_score"] < min_confidence:
            continue
        
        # Build a more descriptive action from condition and action
        action_text = step.get("action", "")
        condition_text = step.get("condition", "")
        
        # Create a natural language action description
        if action_text and condition_text:
            # Combine condition and action into a more descriptive step
            if condition_text.lower() not in ["step applies", "n/a", ""]:
                enhanced_action = f"{condition_text}. {action_text}"
            else:
                enhanced_action = action_text
        elif action_text:
            enhanced_action = action_text
        elif condition_text:
            enhanced_action = condition_text
        else:
            enhanced_action = f"Execute step {step.get('step_id', 'unknown')}"
        
        # Ensure we have expected_outcome, rollback, and risk_level
        expected_outcome = step.get("expected_outcome")
        if not expected_outcome and action_text:
            # Generate a reasonable expected outcome from the action
            expected_outcome = f"Complete {action_text.lower()}"
        
        rollback = step.get("rollback")
        if not rollback:
            rollback = "Revert any changes made in this step"
        
        risk_level = step.get("risk_level")
        if not risk_level:
            # Infer risk level from action content
            action_lower = enhanced_action.lower()
            if any(word in action_lower for word in ["kill", "delete", "drop", "remove", "stop", "restart"]):
                risk_level = "high"
            elif any(word in action_lower for word in ["update", "modify", "change", "alter"]):
                risk_level = "medium"
            else:
                risk_level = "low"
        
        recommendation = {
            "step_id": step.get("step_id"),
            "action": enhanced_action,
            "condition": condition_text if condition_text and condition_text.lower() not in ["step applies", "n/a"] else None,
            "expected_outcome": expected_outcome,
            "rollback": rollback,
            "risk_level": risk_level,
            "confidence": step["combined_score"],
            "provenance": {
                "runbook_id": step.get("runbook_id"),
                "chunk_id": step.get("chunk_id"),
                "document_id": step.get("document_id"),
                "step_id": step.get("step_id"),
            },
            "scores": {
                "relevance": step["relevance_score"],
                "success": step["success_score"],
                "risk": step["risk_score"],
            }
        }
        
        recommendations.append(recommendation)
    
    logger.debug(f"Assembled {len(recommendations)} recommendations")
    return recommendations

