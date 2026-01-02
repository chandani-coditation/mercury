"""Step transformation and classification for Resolution Agent.

This module handles:
- Step type classification (investigation, mitigation, resolution, verification, etc.)
- Step filtering (remove documentation/context steps)
- Step ordering by logical flow
- Step transformation (generate titles, clean actions)
"""

from typing import List, Dict, Optional
import re
from ai_service.core import get_logger

logger = get_logger(__name__)

# Step type order for logical flow
STEP_TYPE_ORDER = {
    "investigation": 1,
    "mitigation": 2,
    "resolution": 3,
    "verification": 4,
    "rollback": 5,
    "documentation": 99,  # Should be filtered out
    "context": 99,  # Should be filtered out
}


def classify_step_type(step: Dict) -> str:
    """
    Classify a runbook step by analyzing its action text.
    
    Args:
        step: Step dictionary with 'action' field
        
    Returns:
        Step type: 'investigation', 'mitigation', 'resolution', 'verification', 
                   'documentation', 'context', or 'unknown'
    """
    action = (step.get("action") or "").lower()
    condition = (step.get("condition") or "").lower()
    combined = f"{action} {condition}".lower()
    
    # Documentation/Context steps (should be filtered out)
    doc_keywords = [
        "document", "record", "log", "note", "track", "update ticket",
        "identify context", "gather context", "collect context"
    ]
    if any(keyword in combined for keyword in doc_keywords):
        # Check if it's just documentation or if it has actionable content
        if any(word in action for word in ["document", "record", "log", "note", "track"]):
            if not any(word in action for word in ["check", "verify", "analyze", "review", "identify", "gather"]):
                return "documentation"
    
    # Investigation steps
    investigation_keywords = [
        "check", "verify", "review", "examine", "analyze", "identify",
        "inspect", "assess", "evaluate", "gather evidence", "collect data",
        "monitor", "observe", "trace", "diagnose"
    ]
    if any(keyword in combined for keyword in investigation_keywords):
        return "investigation"
    
    # Mitigation steps (quick relief)
    mitigation_keywords = [
        "reduce", "decrease", "lower", "minimize", "alleviate", "ease",
        "temporary", "quick fix", "stop", "pause", "suspend", "disable",
        "clean up", "free up", "release", "terminate", "kill"
    ]
    if any(keyword in combined for keyword in mitigation_keywords):
        return "mitigation"
    
    # Resolution steps (root fix)
    resolution_keywords = [
        "fix", "resolve", "repair", "correct", "restore", "recover",
        "reconfigure", "restart", "reboot", "reinstall", "update",
        "upgrade", "patch", "apply", "implement", "deploy"
    ]
    if any(keyword in combined for keyword in resolution_keywords):
        return "resolution"
    
    # Verification steps
    verification_keywords = [
        "confirm", "validate", "test", "ensure", "verify success",
        "check status", "monitor stability", "observe results"
    ]
    if any(keyword in combined for keyword in verification_keywords):
        return "verification"
    
    # Rollback steps
    rollback_keywords = [
        "rollback", "revert", "undo", "restore previous", "roll back"
    ]
    if any(keyword in combined for keyword in rollback_keywords):
        return "rollback"
    
    # Default: classify as investigation if unclear
    return "investigation"


def filter_steps(steps: List[Dict]) -> List[Dict]:
    """
    Filter out documentation and context steps.
    
    Args:
        steps: List of step dictionaries
        
    Returns:
        Filtered list with documentation/context steps removed
    """
    filtered = []
    for step in steps:
        step_type = classify_step_type(step)
        if step_type not in ["documentation", "context"]:
            step["_inferred_step_type"] = step_type
            filtered.append(step)
        else:
            logger.debug(f"Filtered out {step_type} step: {step.get('step_id')}")
    
    logger.info(f"Filtered {len(steps)} steps to {len(filtered)} actionable steps")
    return filtered


def order_steps_by_type(steps: List[Dict]) -> List[Dict]:
    """
    Order steps by logical flow: investigation → mitigation → resolution → verification.
    
    Within each type, order by relevance score if available.
    
    Args:
        steps: List of step dictionaries with '_inferred_step_type'
        
    Returns:
        Ordered list of steps
    """
    # Group by type
    by_type = {}
    for step in steps:
        step_type = step.get("_inferred_step_type", "unknown")
        if step_type not in by_type:
            by_type[step_type] = []
        by_type[step_type].append(step)
    
    # Sort each group by relevance (if available) or confidence
    for step_type, group in by_type.items():
        group.sort(
            key=lambda s: (
                s.get("similarity_score", 0),
                s.get("combined_score", 0),
                s.get("confidence", 0)
            ),
            reverse=True
        )
    
    # Order by type priority
    ordered = []
    for step_type in ["investigation", "mitigation", "resolution", "verification", "rollback"]:
        if step_type in by_type:
            ordered.extend(by_type[step_type])
    
    # Add any unknown types at the end
    if "unknown" in by_type:
        ordered.extend(by_type["unknown"])
    
    logger.info(f"Ordered {len(ordered)} steps by type")
    return ordered


def generate_step_title(action: str, step_type: str) -> str:
    """
    Generate a short, UI-friendly title from action text.
    
    Args:
        action: Action text
        step_type: Inferred step type
        
    Returns:
        Short title (3-6 words)
    """
    if not action:
        return "Execute step"
    
    # Remove common prefixes
    action_clean = action.strip()
    prefixes = [
        "when", "if", "step", "action:", "condition:", 
        "record", "document", "check", "verify"
    ]
    for prefix in prefixes:
        if action_clean.lower().startswith(prefix):
            action_clean = action_clean[len(prefix):].strip()
            if action_clean.startswith(":"):
                action_clean = action_clean[1:].strip()
    
    # Extract key phrases
    # Look for imperative verbs at the start
    imperative_patterns = [
        r"^(check|verify|review|examine|analyze|identify|fix|resolve|repair|restore|reduce|decrease|clean|monitor|confirm|validate)\s+([^.]{0,60})",
        r"^([A-Z][^.]{0,60})",  # Capitalized sentence start
    ]
    
    for pattern in imperative_patterns:
        match = re.match(pattern, action_clean, re.IGNORECASE)
        if match:
            title = match.group(1 if len(match.groups()) == 1 else 2)
            # Clean up title
            title = title.strip()
            # Capitalize first letter
            title = title[0].upper() + title[1:] if title else title
            # Limit length
            if len(title) > 60:
                title = title[:57] + "..."
            return title
    
    # Fallback: use first 50 characters
    title = action_clean[:50].strip()
    if len(action_clean) > 50:
        title += "..."
    return title


def clean_action_for_ui(action: str) -> str:
    """
    Clean action text to be UI-ready: remove SQL, commands, make it plain English.
    
    Args:
        action: Raw action text
        
    Returns:
        Cleaned, plain English action
    """
    if not action:
        return action
    
    # Remove SQL queries
    lines = action.split('\n')
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        # Skip SQL statements
        if re.match(r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXEC|EXECUTE|USE|DECLARE)\s+', line_stripped, re.IGNORECASE):
            continue
        # Skip command-line commands
        if re.match(r'^\s*[$#]|^\s*(sudo|systemctl|kubectl|docker|psql|mysql)', line_stripped, re.IGNORECASE):
            continue
        # Skip code blocks
        if line_stripped.startswith('```') or line_stripped.endswith('```'):
            continue
        cleaned_lines.append(line)
    
    cleaned = '\n'.join(cleaned_lines).strip()
    
    # Remove inline SQL patterns
    cleaned = re.sub(r'\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXEC|EXECUTE|USE|DECLARE)\s+[^.]*\.', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)  # Remove code blocks
    cleaned = re.sub(r'\$[^\s]+', '', cleaned)  # Remove command-line patterns
    
    # Remove generic prefixes
    cleaned = re.sub(r'^(step\s+\d+\s*:?\s*|action:\s*|condition:\s*)', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


def transform_step_for_ui(step: Dict, step_number: int) -> Dict:
    """
    Transform a runbook step into UI-ready format.
    
    Args:
        step: Step dictionary with action, condition, etc.
        step_number: Step number in the ordered sequence
        
    Returns:
        Transformed step with step_number, title, action, expected_outcome, risk_level
    """
    action = step.get("action", "")
    step_type = step.get("_inferred_step_type", "investigation")
    
    # Clean action
    cleaned_action = clean_action_for_ui(action)
    
    # Generate title
    title = generate_step_title(cleaned_action, step_type)
    
    # Get expected outcome
    expected_outcome = step.get("expected_outcome")
    if not expected_outcome:
        # Generate from action
        if "check" in cleaned_action.lower() or "verify" in cleaned_action.lower():
            expected_outcome = "Issue identified and understood"
        elif "fix" in cleaned_action.lower() or "resolve" in cleaned_action.lower():
            expected_outcome = "Issue resolved"
        elif "reduce" in cleaned_action.lower() or "decrease" in cleaned_action.lower():
            expected_outcome = "Issue severity reduced"
        elif "monitor" in cleaned_action.lower():
            expected_outcome = "System stability confirmed"
        else:
            expected_outcome = "Step completed successfully"
    
    # Get risk level
    risk_level = step.get("risk_level", "medium")
    if not risk_level or risk_level.lower() not in ["low", "medium", "high"]:
        # Infer from action
        action_lower = cleaned_action.lower()
        if any(word in action_lower for word in ["kill", "delete", "drop", "remove", "stop", "restart"]):
            risk_level = "high"
        elif any(word in action_lower for word in ["update", "modify", "change", "alter"]):
            risk_level = "medium"
        else:
            risk_level = "low"
    
    return {
        "step_number": step_number,
        "title": title,
        "action": cleaned_action,
        "expected_outcome": expected_outcome,
        "risk_level": risk_level.lower(),
        "confidence": step.get("confidence", step.get("combined_score", 0.7)),
        "provenance": {
            "runbook_id": step.get("runbook_id"),
            "step_id": step.get("step_id"),
            "chunk_id": step.get("chunk_id"),
            "document_id": step.get("document_id"),
        }
    }


def calculate_estimated_time(steps: List[Dict]) -> int:
    """
    Calculate estimated time in minutes based on step types and count.
    
    Args:
        steps: List of transformed steps
        
    Returns:
        Estimated time in minutes
    """
    if not steps:
        return 0
    
    # Base time per step type (minutes)
    time_per_type = {
        "investigation": 5,
        "mitigation": 10,
        "resolution": 15,
        "verification": 5,
        "rollback": 10,
    }
    
    total_time = 0
    for step in steps:
        step_type = step.get("_inferred_step_type", "investigation")
        base_time = time_per_type.get(step_type, 10)
        # Adjust for risk level
        risk_level_raw = step.get("risk_level", "medium")
        risk_level = risk_level_raw.lower() if risk_level_raw else "medium"
        if risk_level == "high":
            base_time = int(base_time * 1.5)
        elif risk_level == "low":
            base_time = int(base_time * 0.8)
        total_time += base_time
    
    return total_time

