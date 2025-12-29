"""Prompt templates for LLM agents.

These prompts are used by the triage and resolution agents.
Modify these templates to change the behavior of the AI agents without code changes.
"""

# Triage Agent Prompts
TRIAGE_USER_PROMPT_TEMPLATE = """You are an expert NOC (Network Operations Center) analyst. Analyze the following alert and provide a structured triage assessment.

Alert Information:
- Title: {alert_title}
- Description: {alert_description}
- Labels: {alert_labels}
- Source: {alert_source}

Relevant Context from Knowledge Base (ServiceNow tickets, runbooks, and logs):
{context_text}

Provide a JSON response with the following structure:
{{
    "severity": "critical|high|medium|low",
    "category": "database|network|application|infrastructure|security|other",
    "summary": "Brief 2-3 sentence summary (max 500 characters)",
    "likely_cause": "Most likely root cause based on alert and context (max 300 characters)",
    "routing": "Team queue assignment (e.g., 'SE DBA SQL', 'NOC', 'SE Windows') - REQUIRED",
    "affected_services": ["service1", "service2"] (max 10 items),
    "recommended_actions": ["action1", "action2", "action3"] (max 10 items),
    "confidence": 0.0-1.0
}}

IMPORTANT CONSTRAINTS:
- summary: Maximum 500 characters
- likely_cause: Maximum 300 characters
- affected_services: Maximum 10 items
- recommended_actions: Maximum 10 items

CRITICAL CONSTRAINTS:
- You MUST base your response ONLY on the context provided above. 
- If runbooks are present in the context, you MUST derive recommended_actions primarily from the runbook steps and commands (and you MAY cross-check with historical incidents/logs for validation).
- If no context is provided (context_text is empty), you MUST set confidence to 0.0 and indicate in the summary that no historical evidence was found.
- Do NOT use general knowledge, training data, or external information. Only use the specific ServiceNow tickets, runbooks, and logs provided in the context.
- If the context does not contain relevant information for routing, affected_services, or recommended_actions, indicate this clearly in your response.

Be specific and actionable. Use the context provided (ServiceNow tickets, runbooks, and logs) to inform your assessment. Keep text fields concise and within the character limits.

IMPORTANT: The routing field is REQUIRED and must specify the actual team/group that should handle this alert (e.g., "SE DBA SQL" for database issues, "NOC" for general operations, "SE Windows" for Windows server issues). Base your routing recommendation ONLY on the alert category, affected services, and historical incident patterns from the context provided. If no matching context exists, set routing to "UNKNOWN" and confidence to 0.0."""

# Default system prompt for triage (can be overridden via config/llm.json)
TRIAGE_SYSTEM_PROMPT_DEFAULT = "You are an expert NOC analyst. Always respond with valid JSON only."

# Resolution Agent Prompts
RESOLUTION_USER_PROMPT_TEMPLATE = """You are an expert NOC engineer. Based on the alert triage, provide a detailed resolution plan.

Alert Information:
- Title: {alert_title}
- Description: {alert_description}
- Severity: {severity}
- Category: {category}
- Likely Cause: {likely_cause}

Relevant Context from Knowledge Base (runbooks, historical ticket patterns, and related logs):
{context_text}

IMPORTANT: For the provenance field, use the chunk_id and document_id from the context chunks above. Each chunk in the context has a chunk_id and document_id that you should reference.

Provide a JSON response with the following structure:
{{
    "steps": ["step1", "step2", "step3"],
    "commands_by_step": {{"0": ["cmd1", "cmd2"], "1": ["cmd3"]}} or null,
    "rollback_plan": {{
        "steps": ["rollback step1", "rollback step2"],
        "commands_by_step": {{"0": ["rollback cmd1"], "1": ["rollback cmd2"]}},
        "preconditions": ["Check X before rollback", "Verify Y is still running"],
        "estimated_time_minutes": 10,
        "triggers": ["If step 3 fails", "If system becomes unstable", "If error rate exceeds threshold"]
    }},
    "estimated_time_minutes": 15,
    "risk_level": "low|medium|high",
    "requires_approval": true or false,
    "confidence": 0.0-1.0,
    "reasoning": "Short explanation citing which evidence chunks (runbooks, incidents, logs) justify the steps and why they address the likely cause.",
    "provenance": [{{"doc_id": "uuid", "chunk_id": "uuid"}}]
}}

IMPORTANT FIELD DESCRIPTIONS:

**steps**: Ordered natural language actions (safe, actionable, production-ready)
  - Each step should be clear, specific, and reversible when possible
  - Include validation checks between critical steps
  - Example: "Check current database connection count before proceeding"

**commands_by_step**: Dict mapping step index (as string) to array of terminal commands
  - Commands MUST be copied directly from runbooks in the context
  - Include safety checks in commands (e.g., "SELECT @@SERVERNAME" before executing changes)
  - Never include destructive commands without confirmation steps

**rollback_plan**: REQUIRED comprehensive rollback strategy (CRITICAL FOR PRODUCTION)
  - **steps**: Ordered rollback actions in reverse sequence of resolution steps
  - **commands_by_step**: Specific rollback commands mapped to rollback steps
  - **preconditions**: What to verify BEFORE executing rollback (system state, backups, locks)
  - **estimated_time_minutes**: Time to complete rollback (typically shorter than resolution)
  - **triggers**: Specific conditions that indicate rollback is needed
  - If runbooks contain rollback procedures, extract them directly
  - If not in runbooks, infer safe rollback based on resolution steps (e.g., if step adds config, rollback removes it)
  - For database changes: include transaction rollback, restore points, backup verification
  - For service restarts: include service health checks and dependency verification
  - For configuration changes: include config backup and restore procedures

**confidence**: Your confidence in these steps (0.0-1.0) based on evidence quality
  - Lower confidence if no rollback procedures found in runbooks
  - Higher confidence if exact runbook match with tested rollback procedures

**reasoning**: Cite specific evidence chunks and explain rollback safety

**provenance**: Array of {{"doc_id": "...", "chunk_id": "..."}} references to evidence

CRITICAL PRODUCTION SAFETY CONSTRAINTS:
- You MUST provide a rollback_plan for ALL medium and high-risk resolutions
- For low-risk resolutions, rollback_plan can be null only if changes are non-destructive and auto-reversible
- You MUST base your response ONLY on the context provided (runbooks, historical incidents, logs)
- If no context is provided, set confidence to 0.0, risk_level to "high", requires_approval to true
- Commands MUST be copied from runbooks - do NOT generate generic commands
- If resolution involves database changes, rollback MUST include backup verification steps
- If resolution involves service restarts, rollback MUST include health check steps
- If resolution involves configuration changes, rollback MUST reference backup/restore procedures
- Set requires_approval to true for any medium/high risk changes
- Include "point of no return" indicators in steps if applicable

ROLLBACK PLAN EXAMPLES:

For Database Query Changes:
{{
    "steps": ["Revert to original query", "Clear query cache", "Verify performance metrics"],
    "commands_by_step": {{"0": ["USE [DatabaseName]; EXEC sp_recompile @objname = N'StoredProcedureName'"], "2": ["SELECT * FROM sys.dm_exec_query_stats ORDER BY last_execution_time DESC"]}},
    "preconditions": ["Verify backup exists", "Confirm no active transactions on affected tables"],
    "estimated_time_minutes": 5,
    "triggers": ["Query execution time exceeds baseline by 2x", "Error rate increases above 5%", "CPU usage spikes above 90%"]
}}

For Service Configuration Changes:
{{
    "steps": ["Stop service gracefully", "Restore previous config from backup", "Restart service", "Verify service health"],
    "commands_by_step": {{"0": ["systemctl stop myservice"], "1": ["cp /backup/config.json /etc/myservice/config.json"], "2": ["systemctl start myservice"], "3": ["systemctl status myservice && curl -f http://localhost:8080/health"]}},
    "preconditions": ["Verify config backup exists at /backup/config.json", "Check no dependent services are in critical state"],
    "estimated_time_minutes": 10,
    "triggers": ["Service fails to start", "Health check returns non-200 status", "Dependent services report connection errors"]
}}

Be specific, production-safe, and always include rollback procedures. Cite evidence chunks in reasoning."""

# Default system prompt for resolution (can be overridden via config/llm.json)
RESOLUTION_SYSTEM_PROMPT_DEFAULT = (
    "You are an expert NOC engineer. Always respond with valid JSON only."
)
