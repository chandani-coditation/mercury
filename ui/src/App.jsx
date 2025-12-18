import { useEffect, useMemo, useRef, useState } from "react";
import { postTriage, getIncident, putFeedback, postResolution } from "./api/client";

const allowedCategories = ["database", "network", "application", "infrastructure", "security", "other"];

const emptyLabels = {
  service: "database",
  component: "sql-server",
  cmdb_ci: "Database-SQL",
  category: "database",
};

const makeInitialAlert = () => ({
  alert_id: "test-alert-001",
  title: "Database connection pool exhausted",
  description: "Application unable to connect to database. Error: connection pool exhausted.",
  source: "monitoring",
  category: emptyLabels.category,
  labels: { ...emptyLabels },
  ts: new Date().toISOString(),
});

const statusPill = (status) => {
  if (status === "success") return "pill success";
  if (status === "warn" || status === "needs-approval" || status === "pending") return "pill warn";
  if (status === "error" || status === "blocked") return "pill error";
  return "pill";
};

function App() {
  const [alert, setAlert] = useState(() => makeInitialAlert());
  const [incidentId, setIncidentId] = useState("");
  const [triage, setTriage] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [resolution, setResolution] = useState(null);
  const [retrieval, setRetrieval] = useState(null);
  const [triageStatus, setTriageStatus] = useState("idle");
  const [policyStatus, setPolicyStatus] = useState("idle");
  const [resolutionStatus, setResolutionStatus] = useState("idle");
  const [error, setError] = useState("");
  const [polling, setPolling] = useState(false);
  const [sideOpen, setSideOpen] = useState(true);
  const [resultTab, setResultTab] = useState("triage");
  const hasResults = triage || policy || retrieval || resolution;
  const autoOpened = useRef(false);

  const needsApproval = useMemo(() => {
    const band = policy?.policy_band || policy?.policy?.policy_band || triage?.policy_band;
    const canAutoApply = policy?.policy_decision?.can_auto_apply ?? policy?.policy?.can_auto_apply;
    const requiresApproval =
      policy?.policy_decision?.requires_approval ?? policy?.policy?.requires_approval;
    return band === "PROPOSE" || band === "REVIEW" || requiresApproval === true || canAutoApply === false;
  }, [policy, triage]);

  // Poll incident status when enabled
  useEffect(() => {
    if (!incidentId || !polling) return;
    const id = setInterval(() => {
      getIncident(incidentId)
        .then((data) => {
          setTriage(data.triage_output || triage);
          setPolicy({ policy_band: data.policy_band, policy_decision: data.policy_decision });
        })
        .catch((err) => setError(err.message || String(err)));
    }, 5000);
    return () => clearInterval(id);
  }, [incidentId, polling, triage]);

  // Auto-open results drawer when new data arrives
  useEffect(() => {
    if (hasResults && !autoOpened.current) {
      setSideOpen(true);
      autoOpened.current = true;
    }
    if (!hasResults) {
      setSideOpen(false);
      autoOpened.current = false;
    }
  }, [hasResults]);

  // Pick the first available tab when results change
  useEffect(() => {
    if (triage) return setResultTab("triage");
    if (policy) return setResultTab("policy");
    if (retrieval) return setResultTab("retrieval");
    if (resolution) return setResultTab("resolution");
  }, [triage, policy, retrieval, resolution]);

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
      const nextCategory = prev.category || prev.labels.category || emptyLabels.category;
      return { ...prev, category: nextCategory, labels: { ...prev.labels, category: nextCategory } };
    });
  }, []);

  const handleSubmitTriage = async (e) => {
    e.preventDefault();
    setError("");
    setIncidentId("");
    setTriage(null);
    setPolicy(null);
    setResolution(null);
    setRetrieval(null);
    setTriageStatus("loading");
    setPolicyStatus("pending");
    setResolutionStatus("idle");
    try {
      const data = await postTriage(alert);
      setIncidentId(data.incident_id);
      setTriage(data.triage);
      setPolicy({ policy_band: data.policy_band, policy_decision: data.policy_decision });
      setRetrieval(data.evidence_chunks);
      setTriageStatus("success");
      setPolicyStatus("success");
      setPolling(true);
    } catch (err) {
      setError(err.message || String(err));
      setTriageStatus("error");
      setPolicyStatus("error");
      setPolling(false);
    }
  };

  const handleApprove = async () => {
    if (!incidentId || !triage) return;
    setError("");
    setPolicyStatus("loading");
    try {
      const payload = {
        feedback_type: "triage",
        user_edited: triage,
        notes: "Approved via UI",
        policy_band: "AUTO",
      };
      await putFeedback(incidentId, payload);
      const refreshed = await getIncident(incidentId);
      setTriage(refreshed.triage_output || triage);
      setPolicy({ policy_band: refreshed.policy_band, policy_decision: refreshed.policy_decision });
      setPolicyStatus("success");
      setPolling(true);
    } catch (err) {
      setError(err.message || String(err));
      setPolicyStatus("error");
    }
  };

  const handleResolution = async () => {
    if (!incidentId) return;
    setError("");
    setResolutionStatus("loading");
    try {
      const data = await postResolution(incidentId);
      if (data.detail?.error === "approval_required") {
        setResolutionStatus("blocked");
        setError(data.detail?.message || "Approval required before resolution.");
        return;
      }
      setResolution(data.resolution || data);
      setResolutionStatus("success");
      setPolling(false);
    } catch (err) {
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
      <h2 className="page-title">NOC Agent UI — Triage → Policy → Resolution</h2>

      <div className="stepper">
        <div className={stepState(triageStatus === "success", triageStatus === "loading")}>
          <div className="dot" />
          <div className="text">
            <div className="title">Triage</div>
            <div className="subtitle">
              {incidentId ? `Incident: ${incidentId}` : "Create incident from alert"}
            </div>
          </div>
        </div>
        <div
          className={stepState(
            policyStatus === "success" && !needsApproval,
            policyStatus === "loading" || needsApproval,
            policyStatus === "error"
          )}
        >
          <div className="dot" />
          <div className="text">
            <div className="title">Policy & Approval</div>
            <div className="subtitle">
              {needsApproval
                ? "Needs approval (PROPOSE/REVIEW)"
                : policy?.policy_band || "Awaiting decision"}
            </div>
          </div>
        </div>
        <div
          className={stepState(
            resolutionStatus === "success",
            resolutionStatus === "loading",
            resolutionStatus === "blocked"
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
              resolutionStatus === "loading" ||
              polling) && <div className="spinner" aria-label="loading" />}
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
              <span className={statusPill(resolutionStatus)}>{resolutionStatus}</span>
            </div>
            <div className="progress-chip">
              <span>Polling</span>
              <span className={statusPill(polling ? "loading" : "idle")}>
                {polling ? "running" : "idle"}
              </span>
            </div>
            <div className="progress-note-inline">
              {triageStatus === "loading"
                ? "Submitting triage…"
                : policyStatus === "loading"
                ? "Evaluating policy…"
                : resolutionStatus === "loading"
                ? "Generating resolution…"
                : polling
                ? "Polling every 5s…"
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
                  onChange={(e) => handleAlertChange("alert_id", e.target.value)}
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
                    onChange={(e) => handleLabelChange("service", e.target.value)}
                    placeholder="database"
                    required
                  />
                </div>
                <div>
                  <div className="label">Component</div>
                  <input
                    className="input"
                    value={alert.labels.component}
                    onChange={(e) => handleLabelChange("component", e.target.value)}
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
                    onChange={(e) => handleLabelChange("cmdb_ci", e.target.value)}
                    placeholder="Database-SQL"
                  />
                </div>
                <div>
                  <div className="label">Category</div>
                  <select
                    className="select"
                    value={alert.category || alert.labels.category}
                    onChange={(e) => handleLabelChange("category", e.target.value)}
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
                  onChange={(e) => handleAlertChange("description", e.target.value)}
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
              <div className="full-width" style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
                <button className="button" type="submit" disabled={triageStatus === "loading"}>
                  {triageStatus === "loading" ? "Submitting..." : "Submit & Triage"}
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
              <div className="row">
                <div>
                  <div className="label">Polling</div>
                  <button
                    className="button secondary"
                    onClick={() => setPolling((p) => !p)}
                    disabled={!incidentId}
                  >
                    {polling ? "Stop polling" : "Start polling"}
                  </button>
                </div>
                <div>
                  <div className="label">Approval</div>
                  <button
                    className="button secondary"
                    onClick={handleApprove}
                    disabled={!incidentId || !needsApproval || policyStatus === "loading"}
                  >
                    {policyStatus === "loading" ? "Approving..." : "Approve (set AUTO)"}
                  </button>
                </div>
                <div>
                  <div className="label">Resolution</div>
                  <button
                    className="button"
                    onClick={handleResolution}
                    disabled={!incidentId || resolutionStatus === "loading"}
                  >
                    {resolutionStatus === "loading" ? "Requesting..." : "Generate Resolution"}
                  </button>
                </div>
              </div>
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

        <div className={`side-panel ${hasResults ? "active" : ""} ${sideOpen ? "open" : "closed"}`}>
          <div className="side-panel-header">
            <div className="side-panel-title">Results</div>
            {hasResults ? (
              <button className="icon-button" type="button" onClick={() => setSideOpen((v) => !v)}>
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
                    <div className="section-title">Triage Output</div>
                    <div className="json-box fill">{JSON.stringify(triage, null, 2)}</div>
                  </>
                ) : null}
                {resultTab === "policy" && policy ? (
                  <>
                    <div className="section-title">Policy Decision</div>
                    <div className="json-box fill">{JSON.stringify(policy, null, 2)}</div>
                  </>
                ) : null}
                {resultTab === "retrieval" && retrieval ? (
                  <>
                    <div className="section-title">Retrieval Evidence</div>
                    <div className="json-box fill">{JSON.stringify(retrieval, null, 2)}</div>
                  </>
                ) : null}
                {resultTab === "resolution" && resolution ? (
                  <>
                    <div className="section-title">Resolution</div>
                    <div className="json-box fill">{JSON.stringify(resolution, null, 2)}</div>
                  </>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </div>

      {hasResults && !sideOpen ? (
        <button className="floating-open-button" type="button" onClick={() => setSideOpen(true)}>
          Open Results
        </button>
      ) : null}

      {hasResults && sideOpen ? <div className="result-overlay" /> : null}
    </div>
  );
}

export default App;
