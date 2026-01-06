import { useEffect, useMemo, useState } from "react";
import {
  postTriage,
  getIncident,
  putFeedback,
  postResolution,
} from "./api/client";

const allowedCategories = [
  "database",
  "network",
  "application",
  "infrastructure",
  "security",
  "other",
];

const emptyLabels = {
  service: "Database",
  component: "Alerts",
  cmdb_ci: "Database-SQL",
  category: "database",
};

// Initial dummy alert matching tests/sample_alerts_for_ui.json (lines 2–14)
// This alert should match runbooks/tickets in KB (Database Alerts runbook).
const makeInitialAlert = () => ({
  alert_id: "sample-match-1",
  title: "MATCHES_KB__Database_Alerts_High_Disk",
  description:
    "Database disk usage on primary SQL server has exceeded 90% for the last 20 minutes. Multiple I/O wait alerts observed on the database volume.",
  source: "prometheus",
  category: emptyLabels.category,
  labels: {
    ...emptyLabels,
    environment: "production",
    severity: "high",
    alertname: "DatabaseDiskUsageHigh",
  },
  ts: new Date().toISOString(),
});

const statusPill = (status) => {
  if (status === "success") return "pill success";
  if (status === "warn" || status === "needs-approval" || status === "pending")
    return "pill warn";
  if (status === "error" || status === "blocked") return "pill error";
  return "pill";
};

function App() {
  const [alert, setAlert] = useState(() => makeInitialAlert());
  const [incidentId, setIncidentId] = useState("");
  const [triage, setTriage] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [resolutionError, setResolutionError] = useState(null);
  const [retrieval, setRetrieval] = useState(null);
  const [triageStatus, setTriageStatus] = useState("idle");
  const [policyStatus, setPolicyStatus] = useState("idle");
  const [resolutionStatus, setResolutionStatus] = useState("idle");
  const [error, setError] = useState("");
  const [sideOpen, setSideOpen] = useState(true);
  const [resultTab, setResultTab] = useState("triage");
  const [acknowledgeNoEvidence, setAcknowledgeNoEvidence] = useState(false);
  const [triageRating, setTriageRating] = useState(null); // 'thumbs_up' or 'thumbs_down'
  const [resolutionRating, setResolutionRating] = useState(null); // 'thumbs_up' or 'thumbs_down'
  const [ratingStatus, setRatingStatus] = useState({ triage: "idle", resolution: "idle" });
  const hasResults =
    triage || policy || retrieval || resolution || resolutionError;

  const needsApproval = useMemo(() => {
    const band =
      policy?.policy_band || policy?.policy?.policy_band || triage?.policy_band;
    const canAutoApply =
      policy?.policy_decision?.can_auto_apply ?? policy?.policy?.can_auto_apply;
    const requiresApproval =
      policy?.policy_decision?.requires_approval ??
      policy?.policy?.requires_approval;
    const hasEvidence = (retrieval?.chunks_used ?? 0) > 0;
    // Require approval if: PROPOSE/REVIEW band, or AUTO band but no evidence (safety)
    return (
      band === "PROPOSE" ||
      band === "REVIEW" ||
      requiresApproval === true ||
      canAutoApply === false ||
      (band === "AUTO" && !hasEvidence) // AUTO but no evidence requires approval
    );
  }, [policy, triage, retrieval]);

  const canAutoProceed = useMemo(() => {
    const band =
      policy?.policy_band || policy?.policy?.policy_band || triage?.policy_band;
    const canAutoApply =
      policy?.policy_decision?.can_auto_apply ?? policy?.policy?.can_auto_apply;
    const requiresApproval =
      policy?.policy_decision?.requires_approval ??
      policy?.policy?.requires_approval;
    const hasEvidence = (retrieval?.chunks_used ?? 0) > 0;
    // Only auto-proceed if AUTO band AND has evidence (safety check)
    return (
      band === "AUTO" &&
      canAutoApply === true &&
      requiresApproval === false &&
      hasEvidence
    );
  }, [policy, triage, retrieval]);

  // Compute policy details for display
  const policyDetails = useMemo(() => {
    const band =
      policy?.policy_band || policy?.policy?.policy_band || triage?.policy_band;
    const canAutoApply =
      policy?.policy_decision?.can_auto_apply ?? policy?.policy?.can_auto_apply;
    const requiresApproval =
      policy?.policy_decision?.requires_approval ??
      policy?.policy?.requires_approval;
    const confidence = triage?.confidence ?? 0;
    const severity = triage?.severity ?? "unknown";
    const evidenceCount = retrieval?.chunks_used ?? 0;
    const hasEvidence = evidenceCount > 0;

    let reason = "";
    if (band === "AUTO") {
      reason = `Low severity (${severity}), high confidence (${confidence.toFixed(2)})`;
    } else if (band === "PROPOSE") {
      reason = `Medium/high severity (${severity}), confidence ${confidence.toFixed(2)}`;
    } else if (band === "REVIEW") {
      reason = `Critical severity or low confidence (${confidence.toFixed(2)})`;
    }

    return {
      band,
      reason,
      confidence,
      severity,
      evidenceCount,
      hasEvidence,
      canAutoApply,
      requiresApproval,
    };
  }, [policy, triage, retrieval]);

  // Auto-open results drawer the first time new results arrive (triage/policy/retrieval/resolution/error),
  // but still respect manual user toggling afterwards.
  useEffect(() => {
    if (triage || policy || retrieval || resolution || resolutionError) {
      setSideOpen(true);
    } else {
      setSideOpen(false);
    }
  }, [triage, policy, retrieval, resolution, resolutionError]);

  // Pick the first available tab when results change, prioritizing resolution/error
  useEffect(() => {
    if (resolutionError) return setResultTab("error");
    if (resolution) return setResultTab("resolution");
    if (triage) return setResultTab("triage");
    if (policy) return setResultTab("policy");
    if (retrieval) return setResultTab("retrieval");
  }, [triage, policy, retrieval, resolution, resolutionError]);

  // Auto-generate resolution when policy band is AUTO (high confidence, low severity) AND has evidence
  useEffect(() => {
    if (
      canAutoProceed &&
      policyDetails.hasEvidence &&
      incidentId &&
      triageStatus === "success" &&
      policyStatus === "success" &&
      resolutionStatus === "idle" &&
      !resolution &&
      !resolutionError
    ) {
      // Small delay to ensure UI has updated before triggering resolution
      const timer = setTimeout(async () => {
        if (!incidentId) return;
        setError("");
        setResolutionError(null);
        setResolutionStatus("loading");
        try {
          const data = await postResolution(incidentId);
          if (data.detail?.error === "approval_required") {
            setResolutionStatus("blocked");
            setError(
              data.detail?.message || "Approval required before resolution.",
            );
            return;
          }
          setResolution(data.resolution || data);
          setResolutionStatus("success");
        } catch (err) {
          // Capture error detail for display in right panel
          const errorDetail = err.response?.data || {
            detail: err.message || String(err),
          };
          setResolutionError(errorDetail);
          setError(err.message || String(err));
          setResolutionStatus("error");
        }
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [
    canAutoProceed,
    incidentId,
    triageStatus,
    policyStatus,
    resolutionStatus,
    resolution,
    resolutionError,
  ]);

  const handleAlertChange = (field, value) => {
    setAlert((prev) => ({ ...prev, [field]: value }));
  };

  const handleLabelChange = (field, value) => {
    setAlert((prev) => {
      const nextLabels = { ...prev.labels, [field]: value };
      if (field === "category") {
        return { ...prev, category: value, labels: nextLabels };
      }
      return { ...prev, labels: nextLabels };
    });
  };

  // Keep category and labels.category in sync if any drift occurs
  useEffect(() => {
    setAlert((prev) => {
      if (prev.category === prev.labels.category) return prev;
      const nextCategory =
        prev.category || prev.labels.category || emptyLabels.category;
      return {
        ...prev,
        category: nextCategory,
        labels: { ...prev.labels, category: nextCategory },
      };
    });
  }, []);

  const handleSubmitTriage = async (e) => {
    e.preventDefault();
    setError("");
    setIncidentId("");
    setTriage(null);
    setPolicy(null);
    setResolution(null);
    setResolutionError(null);
    setRetrieval(null);
    setAcknowledgeNoEvidence(false);
    setTriageStatus("loading");
    setPolicyStatus("pending");
    setResolutionStatus("idle");
    try {
      const data = await postTriage(alert);
      setIncidentId(data.incident_id);
      setTriage(data.triage);
      setPolicy({
        policy_band: data.policy_band,
        policy_decision: data.policy_decision,
      });
      setRetrieval(data.evidence_chunks);
      setTriageStatus("success");
      setPolicyStatus("success");
    } catch (err) {
      setError(err.message || String(err));
      setTriageStatus("error");
      setPolicyStatus("error");
    }
  };

  const handleApprove = async () => {
    if (!incidentId || !triage) return;
    if (!policyDetails.hasEvidence && !acknowledgeNoEvidence) {
      setError(
        "Please acknowledge that resolution will be generated without evidence",
      );
      return;
    }
    setError("");
    setPolicyStatus("loading");
    try {
      const payload = {
        feedback_type: "triage",
        user_edited: triage,
        notes: policyDetails.hasEvidence
          ? "Approved via UI"
          : "Approved via UI - acknowledged no evidence",
        policy_band: "AUTO",
      };
      await putFeedback(incidentId, payload);
      const refreshed = await getIncident(incidentId);
      setTriage(refreshed.triage_output || triage);
      setPolicy({
        policy_band: refreshed.policy_band,
        policy_decision: refreshed.policy_decision,
      });
      setPolicyStatus("success");
      setAcknowledgeNoEvidence(false); // Reset after approval

      // Automatically trigger resolution generation after approval
      setResolutionError(null);
      setResolutionStatus("loading");
      try {
        const data = await postResolution(incidentId);
        if (data.detail?.error === "approval_required") {
          setResolutionStatus("blocked");
          setError(
            data.detail?.message || "Approval required before resolution.",
          );
          return;
        }
        setResolution(data.resolution || data);
        setResolutionStatus("success");
      } catch (err) {
        // Capture error detail for display in right panel
        const errorDetail = err.response?.data || {
          detail: err.message || String(err),
        };
        setResolutionError(errorDetail);
        setError(err.message || String(err));
        setResolutionStatus("error");
      }
    } catch (err) {
      setError(err.message || String(err));
      setPolicyStatus("error");
    }
  };

  const handleResolution = async () => {
    if (!incidentId) return;
    setError("");
    setResolutionError(null);
    setResolutionStatus("loading");
    try {
      const data = await postResolution(incidentId);
      if (data.detail?.error === "approval_required") {
        setResolutionStatus("blocked");
        setError(
          data.detail?.message || "Approval required before resolution.",
        );
        return;
      }
      setResolution(data.resolution || data);
      setResolutionStatus("success");
      // Reset resolution rating when new resolution is generated
      setResolutionRating(null);
      setRatingStatus(prev => ({ ...prev, resolution: "idle" }));
    } catch (err) {
      // Capture error detail for display in right panel
      const errorDetail = err.response?.data || {
        detail: err.message || String(err),
      };
      setResolutionError(errorDetail);
      setError(err.message || String(err));
      setResolutionStatus("error");
    }
  };

  const stepState = (done, active, blocked) => {
    if (blocked) return "step blocked";
    if (done) return "step complete";
    if (active) return "step active";
    return "step";
  };

  return (
    <div className="app">
      <h2 className="page-title">
        NOC Agent UI — Triage → Policy → Resolution
      </h2>

      <div className="stepper">
        <div
          className={stepState(
            triageStatus === "success",
            triageStatus === "loading",
          )}
        >
          <div className="dot" />
          <div className="text">
            <div className="title">Triage</div>
            <div className="subtitle">
              {incidentId
                ? `Incident: ${incidentId}`
                : "Create incident from alert"}
            </div>
          </div>
        </div>
        <div
          className={stepState(
            policyStatus === "success" && !needsApproval,
            policyStatus === "loading" || (needsApproval && !canAutoProceed),
            policyStatus === "error",
          )}
        >
          <div className="dot" />
          <div className="text">
            <div className="title">Policy & Approval</div>
            <div className="subtitle">
              {canAutoProceed
                ? `AUTO band - Auto-proceeding to resolution...`
                : needsApproval
                  ? `${policyDetails.band || "PROPOSE/REVIEW"} band - Requires approval`
                  : policy?.policy_band || "Awaiting decision"}
            </div>
          </div>
        </div>
        <div
          className={stepState(
            resolutionStatus === "success",
            resolutionStatus === "loading",
            resolutionStatus === "blocked",
          )}
        >
          <div className="dot" />
          <div className="text">
            <div className="title">Resolution</div>
            <div className="subtitle">
              {resolutionStatus === "success"
                ? "Complete"
                : resolutionStatus === "blocked"
                  ? "Approval required"
                  : "Pending"}
            </div>
          </div>
        </div>
      </div>

      <div className="layout">
        <div>
          <div className="progress-strip">
            {(triageStatus === "loading" ||
              policyStatus === "loading" ||
              resolutionStatus === "loading") && (
              <div className="spinner" aria-label="loading" />
            )}
            <div className="progress-chip">
              <span>Triage</span>
              <span className={statusPill(triageStatus)}>{triageStatus}</span>
            </div>
            <div className="progress-chip">
              <span>Policy</span>
              <span className={statusPill(policyStatus)}>{policyStatus}</span>
            </div>
            <div className="progress-chip">
              <span>Resolution</span>
              <span className={statusPill(resolutionStatus)}>
                {resolutionStatus}
              </span>
            </div>
            <div className="progress-note-inline">
              {triageStatus === "loading"
                ? "Submitting triage…"
                : policyStatus === "loading"
                  ? "Evaluating policy…"
                  : resolutionStatus === "loading"
                    ? "Generating resolution…"
                    : "Idle"}
            </div>
          </div>
          <div className="card">
            <div className="section-title">New Ticket</div>
            <form onSubmit={handleSubmitTriage} className="form-grid">
              <div>
                <div className="label">Alert ID</div>
                <input
                  className="input"
                  value={alert.alert_id}
                  onChange={(e) =>
                    handleAlertChange("alert_id", e.target.value)
                  }
                  required
                />
              </div>
              <div>
                <div className="label">Source</div>
                <input
                  className="input"
                  value={alert.source}
                  onChange={(e) => handleAlertChange("source", e.target.value)}
                  required
                />
              </div>
              <div className="form-grid-half">
                <div>
                  <div className="label">Service</div>
                  <input
                    className="input"
                    value={alert.labels.service}
                    onChange={(e) =>
                      handleLabelChange("service", e.target.value)
                    }
                    placeholder="database"
                    required
                  />
                </div>
                <div>
                  <div className="label">Component</div>
                  <input
                    className="input"
                    value={alert.labels.component}
                    onChange={(e) =>
                      handleLabelChange("component", e.target.value)
                    }
                    placeholder="sql-server"
                    required
                  />
                </div>
              </div>
              <div className="form-grid-half">
                <div>
                  <div className="label">CMDB CI</div>
                  <input
                    className="input"
                    value={alert.labels.cmdb_ci}
                    onChange={(e) =>
                      handleLabelChange("cmdb_ci", e.target.value)
                    }
                    placeholder="Database-SQL"
                  />
                </div>
                <div>
                  <div className="label">Category</div>
                  <select
                    className="select"
                    value={alert.category || alert.labels.category}
                    onChange={(e) =>
                      handleLabelChange("category", e.target.value)
                    }
                    required
                  >
                    {allowedCategories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="full-width">
                <div className="label">Title</div>
                <input
                  className="input"
                  value={alert.title}
                  onChange={(e) => handleAlertChange("title", e.target.value)}
                  required
                />
              </div>
              <div className="full-width">
                <div className="label">Description</div>
                <textarea
                  className="textarea"
                  value={alert.description}
                  onChange={(e) =>
                    handleAlertChange("description", e.target.value)
                  }
                  required
                />
              </div>
              <div className="full-width">
                <div className="label">Timestamp (ts)</div>
                <input
                  className="input"
                  value={alert.ts}
                  onChange={(e) => handleAlertChange("ts", e.target.value)}
                  placeholder={new Date().toISOString()}
                />
              </div>
              <div
                className="full-width"
                style={{ display: "flex", alignItems: "flex-end", gap: 12 }}
              >
                <button
                  className="button"
                  type="submit"
                  disabled={triageStatus === "loading"}
                >
                  {triageStatus === "loading"
                    ? "Submitting..."
                    : "Submit & Triage"}
                </button>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setAlert(makeInitialAlert())}
                >
                  Reset Form
                </button>
              </div>
            </form>
          </div>

          {(incidentId || triage || policy || retrieval || resolution) && (
            <div className="card">
              <div className="section-title">Controls & Status</div>

              {/* Policy Details Section */}
              {policy && triage && (
                <>
                  <div className="divider" />
                  <div
                    className="section-title"
                    style={{ fontSize: "0.9em", marginBottom: "8px" }}
                  >
                    Policy Decision
                  </div>
                  <div
                    style={{
                      marginBottom: "12px",
                      fontSize: "0.85em",
                      lineHeight: "1.5",
                    }}
                  >
                    <div>
                      <strong>Policy Band:</strong> {policyDetails.band}
                    </div>
                    <div>
                      <strong>Reason:</strong> {policyDetails.reason}
                    </div>
                    <div>
                      <strong>Evidence Found:</strong>{" "}
                      {policyDetails.evidenceCount} chunk(s)
                    </div>
                    <div>
                      <strong>Action:</strong>{" "}
                      {canAutoProceed
                        ? "Auto-proceeding (AUTO band with evidence)"
                        : needsApproval
                          ? policyDetails.band === "AUTO" &&
                            !policyDetails.hasEvidence
                            ? "Requires approval (AUTO band but no evidence found)"
                            : `Requires approval (${policyDetails.band} band)`
                          : "Awaiting decision"}
                    </div>
                  </div>

                  {/* Warning when no evidence */}
                  {!policyDetails.hasEvidence && (
                    <div
                      style={{
                        padding: "12px",
                        backgroundColor: "rgba(255, 193, 7, 0.15)",
                        border: "1px solid #ffc107",
                        borderRadius: "4px",
                        marginBottom: "12px",
                        fontSize: "0.85em",
                        color: "#ffc107",
                      }}
                    >
                      <strong style={{ color: "#ffc107" }}>
                        ⚠️ No Evidence Found:
                      </strong>{" "}
                      <span style={{ color: "#e2e8f0" }}>
                        No matching runbooks or historical incidents found in
                        knowledge base. Resolution will be generated without
                        historical context. Quality may be limited.
                      </span>
                    </div>
                  )}
                </>
              )}

              <div className="row">
                <div>
                  <div className="label">Approval</div>
                  <button
                    className="button secondary"
                    onClick={handleApprove}
                    disabled={
                      !incidentId ||
                      !needsApproval ||
                      policyStatus === "loading" ||
                      (!policyDetails.hasEvidence && !acknowledgeNoEvidence)
                    }
                  >
                    {policyStatus === "loading"
                      ? "Approving..."
                      : !policyDetails.hasEvidence
                        ? "Approve & Generate (No Evidence)"
                        : "Approve & Generate Resolution"}
                  </button>
                </div>
                <div>
                  <div className="label">Resolution</div>
                  <button
                    className="button"
                    onClick={handleResolution}
                    disabled={
                      !incidentId ||
                      resolutionStatus === "loading" ||
                      (needsApproval && !canAutoProceed)
                    }
                  >
                    {resolutionStatus === "loading"
                      ? "Requesting..."
                      : "Generate Resolution"}
                  </button>
                </div>
              </div>

              {/* Checkbox for acknowledging no evidence */}
              {!policyDetails.hasEvidence && needsApproval && (
                <div style={{ marginTop: "12px" }}>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      fontSize: "0.85em",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={acknowledgeNoEvidence}
                      onChange={(e) =>
                        setAcknowledgeNoEvidence(e.target.checked)
                      }
                    />
                    I understand resolution will be generated without historical
                    context
                  </label>
                </div>
              )}

              {error ? (
                <>
                  <div className="divider" />
                  <div className="pill error">Error</div>
                  <div className="json-box">{error}</div>
                </>
              ) : null}
            </div>
          )}
        </div>

        <div
          className={`side-panel ${hasResults ? "active" : ""} ${sideOpen ? "open" : "closed"}`}
        >
          <div className="side-panel-header">
            <div className="side-panel-title">Results</div>
            {hasResults ? (
              <button
                className="icon-button"
                type="button"
                onClick={() => setSideOpen((v) => !v)}
              >
                {sideOpen ? "Hide" : "Show"}
              </button>
            ) : null}
          </div>
          {hasResults ? (
            <>
              <div className="side-tabs">
                {triage ? (
                  <button
                    type="button"
                    className={`side-tab ${resultTab === "triage" ? "active" : ""}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setResultTab("triage")}
                  >
                    Triage
                  </button>
                ) : null}
                {policy ? (
                  <button
                    type="button"
                    className={`side-tab ${resultTab === "policy" ? "active" : ""}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setResultTab("policy")}
                  >
                    Policy
                  </button>
                ) : null}
                {retrieval ? (
                  <button
                    type="button"
                    className={`side-tab ${resultTab === "retrieval" ? "active" : ""}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setResultTab("retrieval")}
                  >
                    Retrieval
                  </button>
                ) : null}
                {resolutionError ? (
                  <button
                    type="button"
                    className={`side-tab ${resultTab === "error" ? "active" : ""}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setResultTab("error")}
                  >
                    Error
                  </button>
                ) : null}
                {resolution ? (
                  <button
                    type="button"
                    className={`side-tab ${resultTab === "resolution" ? "active" : ""}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => setResultTab("resolution")}
                  >
                    Resolution
                  </button>
                ) : null}
              </div>

              <div className="card result-card fill">
                {resultTab === "triage" && triage ? (
                  <>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                      <div className="section-title">Triage Output</div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <span style={{ fontSize: "0.85em", color: "#666" }}>Was this helpful?</span>
                        <button
                          type="button"
                          className={`icon-button ${triageRating === "thumbs_up" ? "active" : ""}`}
                          onClick={async () => {
                            if (!incidentId) return;
                            setRatingStatus(prev => ({ ...prev, triage: "loading" }));
                            try {
                              await putFeedback(incidentId, {
                                feedback_type: "triage",
                                user_edited: triage,
                                rating: "thumbs_up",
                              });
                              setTriageRating("thumbs_up");
                              setRatingStatus(prev => ({ ...prev, triage: "success" }));
                            } catch (err) {
                              setRatingStatus(prev => ({ ...prev, triage: "error" }));
                              console.error("Failed to submit feedback:", err);
                            }
                          }}
                          disabled={ratingStatus.triage === "loading"}
                          style={{
                            fontSize: "1.2em",
                            padding: "4px 8px",
                            border: triageRating === "thumbs_up" ? "2px solid #4CAF50" : "1px solid #ddd",
                            backgroundColor: triageRating === "thumbs_up" ? "#e8f5e9" : "transparent",
                            cursor: "pointer",
                          }}
                          title="Thumbs up"
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          className={`icon-button ${triageRating === "thumbs_down" ? "active" : ""}`}
                          onClick={async () => {
                            if (!incidentId) return;
                            setRatingStatus(prev => ({ ...prev, triage: "loading" }));
                            try {
                              await putFeedback(incidentId, {
                                feedback_type: "triage",
                                user_edited: triage,
                                rating: "thumbs_down",
                              });
                              setTriageRating("thumbs_down");
                              setRatingStatus(prev => ({ ...prev, triage: "success" }));
                            } catch (err) {
                              setRatingStatus(prev => ({ ...prev, triage: "error" }));
                              console.error("Failed to submit feedback:", err);
                            }
                          }}
                          disabled={ratingStatus.triage === "loading"}
                          style={{
                            fontSize: "1.2em",
                            padding: "4px 8px",
                            border: triageRating === "thumbs_down" ? "2px solid #f44336" : "1px solid #ddd",
                            backgroundColor: triageRating === "thumbs_down" ? "#ffebee" : "transparent",
                            cursor: "pointer",
                          }}
                          title="Thumbs down"
                        >
                          👎
                        </button>
                        {ratingStatus.triage === "success" && (
                          <span style={{ fontSize: "0.75em", color: "#4CAF50" }}>✓</span>
                        )}
                      </div>
                    </div>
                    <div className="json-box fill">
                      {JSON.stringify(triage, null, 2)}
                    </div>
                  </>
                ) : null}
                {resultTab === "policy" && policy ? (
                  <>
                    <div className="section-title">Policy Decision</div>
                    <div className="json-box fill">
                      {JSON.stringify(policy, null, 2)}
                    </div>
                  </>
                ) : null}
                {resultTab === "retrieval" && retrieval ? (
                  <>
                    <div className="section-title">Retrieval Evidence</div>
                    <div className="json-box fill">
                      {JSON.stringify(retrieval, null, 2)}
                    </div>
                  </>
                ) : null}
                {resultTab === "error" && resolutionError ? (
                  <>
                    <div className="section-title">Resolution Error</div>
                    <div className="json-box fill">
                      {JSON.stringify(resolutionError, null, 2)}
                    </div>
                  </>
                ) : null}
                {resultTab === "resolution" && resolution ? (
                  <>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                      <div className="section-title">Resolution</div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <span style={{ fontSize: "0.85em", color: "#666" }}>Was this helpful?</span>
                        <button
                          type="button"
                          className={`icon-button ${resolutionRating === "thumbs_up" ? "active" : ""}`}
                          onClick={async () => {
                            if (!incidentId) return;
                            setRatingStatus(prev => ({ ...prev, resolution: "loading" }));
                            try {
                              await putFeedback(incidentId, {
                                feedback_type: "resolution",
                                user_edited: resolution.resolution || resolution,
                                rating: "thumbs_up",
                              });
                              setResolutionRating("thumbs_up");
                              setRatingStatus(prev => ({ ...prev, resolution: "success" }));
                            } catch (err) {
                              setRatingStatus(prev => ({ ...prev, resolution: "error" }));
                              console.error("Failed to submit feedback:", err);
                            }
                          }}
                          disabled={ratingStatus.resolution === "loading"}
                          style={{
                            fontSize: "1.2em",
                            padding: "4px 8px",
                            border: resolutionRating === "thumbs_up" ? "2px solid #4CAF50" : "1px solid #ddd",
                            backgroundColor: resolutionRating === "thumbs_up" ? "#e8f5e9" : "transparent",
                            cursor: "pointer",
                          }}
                          title="Thumbs up"
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          className={`icon-button ${resolutionRating === "thumbs_down" ? "active" : ""}`}
                          onClick={async () => {
                            if (!incidentId) return;
                            setRatingStatus(prev => ({ ...prev, resolution: "loading" }));
                            try {
                              await putFeedback(incidentId, {
                                feedback_type: "resolution",
                                user_edited: resolution.resolution || resolution,
                                rating: "thumbs_down",
                              });
                              setResolutionRating("thumbs_down");
                              setRatingStatus(prev => ({ ...prev, resolution: "success" }));
                            } catch (err) {
                              setRatingStatus(prev => ({ ...prev, resolution: "error" }));
                              console.error("Failed to submit feedback:", err);
                            }
                          }}
                          disabled={ratingStatus.resolution === "loading"}
                          style={{
                            fontSize: "1.2em",
                            padding: "4px 8px",
                            border: resolutionRating === "thumbs_down" ? "2px solid #f44336" : "1px solid #ddd",
                            backgroundColor: resolutionRating === "thumbs_down" ? "#ffebee" : "transparent",
                            cursor: "pointer",
                          }}
                          title="Thumbs down"
                        >
                          👎
                        </button>
                        {ratingStatus.resolution === "success" && (
                          <span style={{ fontSize: "0.75em", color: "#4CAF50" }}>✓</span>
                        )}
                      </div>
                    </div>
                    <div className="json-box fill">
                      {JSON.stringify(resolution, null, 2)}
                    </div>
                  </>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </div>

      {hasResults && !sideOpen ? (
        <button
          className="floating-open-button"
          type="button"
          onClick={() => setSideOpen(true)}
        >
          Open Results
        </button>
      ) : null}

      {hasResults && sideOpen ? <div className="result-overlay" /> : null}
    </div>
  );
}

export default App;

