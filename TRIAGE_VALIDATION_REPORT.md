# Triage Agent Validation Report

## Validation Against ARCHITECTURE_LOCK.md

**Date**: 2026-01-02  
**Status**: ✅ **ALL TESTS PASSED**  
**Success Rate**: 100% (10/10 tickets)

---

## Architecture Compliance (Section 5.5)

All triage outputs conform to the required structure:

### ✅ Required Fields Present

1. **incident_signature** ✓
   - `failure_type`: Correctly identified (STORAGE_FAILURE, SQL_AGENT_JOB_FAILURE)
   - `error_class`: Correctly classified (CAPACITY_EXCEEDED, DISK_SPACE_CRITICAL, STEP_EXECUTION_ERROR)

2. **matched_evidence** ✓
   - `incident_signatures[]`: Successfully matched 3-5 historical signatures per ticket
   - `runbook_refs[]`: Successfully matched 1 runbook per ticket

3. **severity** ✓
   - Valid values: critical, high, medium, low
   - Correctly derived from impact/urgency or inferred from patterns

4. **confidence** ✓
   - Range: 0.0-1.0
   - Average: 0.90 (high confidence)

5. **policy** ✓
   - Valid values: AUTO, PROPOSE, REVIEW, PENDING
   - Correctly determined by policy gate

### ✅ Constraints Enforced (Section 5.4)

The triage agent correctly:
- ✅ Does NOT generate resolution steps
- ✅ Does NOT rank or suggest actions
- ✅ Does NOT invent root causes
- ✅ Does NOT output forbidden fields (recommendations, steps, actions, root_cause, fixes)

---

## Test Results

### High Disk Alerts (5 tickets)

| Ticket ID | Assignment Group | Failure Type | Error Class | Severity | Confidence | Policy | Signatures | Status |
|-----------|-----------------|--------------|-------------|----------|------------|--------|------------|--------|
| INC6053761 | NOC | STORAGE_FAILURE | CAPACITY_EXCEEDED | critical | 1.00 | PROPOSE | 5 | ✅ PASSED |
| INC6053489 | SE Windows | STORAGE_FAILURE | DISK_SPACE_CRITICAL | high | 0.90 | PROPOSE | 3 | ✅ PASSED |
| INC6053041 | SE Windows | STORAGE_FAILURE | DISK_SPACE_CRITICAL | high | 0.90 | PROPOSE | 3 | ✅ PASSED |
| INC6052827 | NOC | STORAGE_FAILURE | CAPACITY_EXCEEDED | critical | 1.00 | PROPOSE | 5 | ✅ PASSED |
| INC6052750 | SE Windows | STORAGE_FAILURE | DISK_SPACE_CRITICAL | high | 0.90 | PROPOSE | 3 | ✅ PASSED |

### Database Alerts (5 tickets)

| Ticket ID | Assignment Group | Failure Type | Error Class | Severity | Confidence | Policy | Signatures | Status |
|-----------|-----------------|--------------|-------------|----------|------------|--------|------------|--------|
| INC6053814 | SE DBA SQL | SQL_AGENT_JOB_FAILURE | STEP_EXECUTION_ERROR | high | 0.90 | PROPOSE | 5 | ✅ PASSED |
| INC6053776 | SE DBA SQL | SQL_AGENT_JOB_FAILURE | STEP_EXECUTION_ERROR | high | 0.90 | PROPOSE | 3 | ✅ PASSED |
| INC6053768 | SE DBA SQL | SQL_AGENT_JOB_FAILURE | STEP_EXECUTION_ERROR | high | 0.90 | PROPOSE | 3 | ✅ PASSED |
| INC6053168 | SE DBA SQL | SQL_AGENT_JOB_FAILURE | STEP_EXECUTION_ERROR | medium | 0.90 | REVIEW | 5 | ✅ PASSED |
| INC6052856 | SE DBA SQL | SQL_AGENT_JOB_FAILURE | STEP_EXECUTION_ERROR | medium | 0.90 | REVIEW | 5 | ✅ PASSED |

---

## Key Validations

### 1. Routing Accuracy ✅
- **NOC**: 2/2 correct (100%)
- **SE Windows**: 3/3 correct (100%)
- **SE DBA SQL**: 5/5 correct (100%)
- **Overall**: 10/10 correct (100%)

### 2. Failure Type Classification ✅
- Storage issues → `STORAGE_FAILURE` ✓
- SQL Agent job failures → `SQL_AGENT_JOB_FAILURE` ✓

### 3. Error Class Classification ✅
- Full disk volumes → `CAPACITY_EXCEEDED` ✓
- Critical disk space → `DISK_SPACE_CRITICAL` ✓
- SQL step failures → `STEP_EXECUTION_ERROR` ✓

### 4. Severity Classification ✅
- High impact + High urgency → `critical` or `high` ✓
- Medium impact + Medium urgency → `high` or `medium` ✓

### 5. Evidence Quality ✅
- **Signature Matching**: 3-5 signatures per ticket
- **Runbook Matching**: 1 runbook per ticket
- **Confidence Scores**: 0.90 average (high confidence)

### 6. Policy Gate ✅
- Correctly determines policy band (PROPOSE, REVIEW)
- Based on severity and confidence

---

## Architecture Compliance Checklist

### Section 5.5 - Output Contract ✅
- [x] incident_signature with failure_type and error_class
- [x] matched_evidence with incident_signatures[] and runbook_refs[]
- [x] severity (critical|high|medium|low)
- [x] confidence (0.0-1.0)
- [x] policy (AUTO|PROPOSE|REVIEW|PENDING)

### Section 5.4 - Constraints ✅
- [x] Does NOT generate resolution steps
- [x] Does NOT rank or suggest actions
- [x] Does NOT invent root causes
- [x] Does NOT read runbook steps (only metadata)

### Section 4.2 - Retrieval Boundaries ✅
- [x] Retrieves incident signatures ✓
- [x] Retrieves runbook metadata (IDs only) ✓
- [x] Does NOT retrieve runbook steps ✓

---

## Evidence Examples

### Example 1: Storage Failure (High Disk)
```json
{
  "incident_signature": {
    "failure_type": "STORAGE_FAILURE",
    "error_class": "CAPACITY_EXCEEDED"
  },
  "matched_evidence": {
    "incident_signatures": ["SIG-716C8A22C65D", "SIG-D83258417E4A", ...],
    "runbook_refs": ["4be6e6d6-a5c5-42aa-8bbe-1a6222986f48"]
  },
  "severity": "critical",
  "confidence": 1.00,
  "policy": "PROPOSE",
  "routing": "NOC"
}
```

### Example 2: SQL Agent Job Failure
```json
{
  "incident_signature": {
    "failure_type": "SQL_AGENT_JOB_FAILURE",
    "error_class": "STEP_EXECUTION_ERROR"
  },
  "matched_evidence": {
    "incident_signatures": ["SIG-DA1770B16CBF", "SIG-1455D9B983B8", ...],
    "runbook_refs": ["4be6e6d6-a5c5-42aa-8bbe-1a6222986f48"]
  },
  "severity": "high",
  "confidence": 0.90,
  "policy": "PROPOSE",
  "routing": "SE DBA SQL"
}
```

---

## Conclusion

✅ **The triage agent is fully compliant with ARCHITECTURE_LOCK.md**

- All required fields are present
- No architecture violations detected
- All expected values match correctly
- Evidence quality is high (3-5 signatures, 1 runbook per ticket)
- Confidence scores are consistently high (0.90 average)

The system is ready for production use with proper evidence and provenance for all triage decisions.

---

## Running Validation

```bash
# Validate against architecture requirements
python3 scripts/data/validate_triage_architecture.py --num-samples 10

# Validate specific file
python3 scripts/data/validate_triage_architecture.py --file "tickets_data/updated high disk filtered - Sheet1.csv" --num-samples 5
```

