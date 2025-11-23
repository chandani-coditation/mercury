import React, { useMemo, useState, useEffect, useRef } from "react";
import "./IncidentDetail.css";
import { useAgentStateContext } from "../context/AgentStateContext";
import { useToast } from "../context/ToastContext";
import ProgressStepper from "./hitl/ProgressStepper";
import PendingActionCard from "./hitl/PendingActionCard";
import TriageReviewForm from "./hitl/TriageReviewForm";

const getPolicyBandDescription = (band) => {
  switch (band) {
    case "AUTO":
      return {
        description: "Automatically approved - within safe thresholds",
        conditions: "Low severity OR confidence > 90%",
        action: "Resolution will be generated automatically",
      };
    case "PROPOSE":
      return {
        description: "Requires approval - medium to high risk",
        conditions: "Medium/High severity AND confidence ≥ 70%",
        action: "Review triage and approve before resolution",
      };
    case "REVIEW":
      return {
        description: "Requires review - critical or low confidence",
        conditions: "Critical severity OR confidence < 70%",
        action: "Manual review and approval required",
      };
    default:
      return {
        description: "Policy evaluation pending",
        conditions: "N/A",
        action: "Awaiting policy evaluation",
      };
  }
};

function IncidentDetail({
  incident,
  onBack,
  onResolution,
  onFeedback,
  onRespondPendingAction = async () => {},
  loading,
}) {
  const { state: liveState, connectionStatus } = useAgentStateContext();
  const toast = useToast();
  const [legacyReviewMode, setLegacyReviewMode] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const lastPendingActionRef = useRef(null);

  const triage = liveState?.triage_output || incident.triage_output || {};
  const resolution =
    liveState?.resolution_output || incident.resolution_output || {};
  const policyBand =
    liveState?.policy_band || incident.policy_band || "PENDING";
  const policyDecision =
    liveState?.policy_decision || incident.policy_decision || {};
  const warning = liveState?.warning ?? incident.warning ?? null;
  const pendingAction = liveState?.pending_action;

  // Derive canAutoApply and requiresApproval from policy_decision if available,
  // otherwise fall back to policy_band
  const canAutoApply = policyDecision.can_auto_apply === true || 
    (policyDecision.can_auto_apply === undefined && policyBand === "AUTO");
  const requiresApproval = policyDecision.requires_approval === true ||
    (policyDecision.requires_approval === undefined && 
     (policyBand === "PROPOSE" || policyBand === "REVIEW"));

  const tabs = useMemo(
    () => [
      { id: "overview", label: "Overview" },
      { id: "triage", label: "Triage" },
      { id: "resolution", label: "Resolution" },
      { id: "evidence", label: "Evidence" },
      { id: "timeline", label: "Timeline" },
    ],
    []
  );

  // Show toast and sound/visual alert when pending action appears
  useEffect(() => {
    if (pendingAction && pendingAction.action_name !== lastPendingActionRef.current) {
      lastPendingActionRef.current = pendingAction.action_name;
      const actionTypeLabel =
        pendingAction.action_type === "review_triage"
          ? "Triage Review"
          : pendingAction.action_type === "review_resolution"
          ? "Resolution Review"
          : pendingAction.action_type;
      toast.warning(`Action required: ${actionTypeLabel}`, 8000);
      
      // Visual alert - flash the browser tab title
      const originalTitle = document.title;
      let flashCount = 0;
      const flashInterval = setInterval(() => {
        document.title = flashCount % 2 === 0 
          ? `⚠️ ${actionTypeLabel} - ${originalTitle}`
          : originalTitle;
        flashCount++;
        if (flashCount >= 10) {
          clearInterval(flashInterval);
          document.title = originalTitle;
        }
      }, 500);
      
      // Sound alert (if user has interacted with page)
      try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800;
        oscillator.type = 'sine';
        
        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.3);
      } catch (e) {
        // Audio not supported or user hasn't interacted
        console.debug("Audio alert not available:", e);
      }
      
      return () => {
        clearInterval(flashInterval);
        document.title = originalTitle;
      };
    } else if (!pendingAction && lastPendingActionRef.current) {
      lastPendingActionRef.current = null;
      document.title = document.title.replace(/⚠️ .*? - /, '');
    }
  }, [pendingAction, toast]);

  // Show toast when state step changes significantly
  useEffect(() => {
    if (liveState?.current_step) {
      const step = liveState.current_step;
      if (step === "completed") {
        toast.success("Workflow completed successfully");
      } else if (step === "policy_evaluated" && !pendingAction) {
        toast.info("Policy evaluation complete");
      }
    }
  }, [liveState?.current_step, pendingAction, toast]);

  const currentStepLabel = useMemo(() => {
    if (pendingAction) return "awaiting_review";
    if (liveState?.current_step) return liveState.current_step;
    if (resolution.resolution_steps) return "completed";
    if (triage.severity) return "policy_evaluated";
    return "initialized";
  }, [pendingAction, liveState?.current_step, resolution.resolution_steps, triage.severity]);

  const timelineEvents = useMemo(() => {
    const events = [];
    
    // Add state transitions from logs
    if (liveState?.logs && Array.isArray(liveState.logs)) {
      liveState.logs.forEach((log) => {
        if (log.step || log.message) {
          events.push({
            type: "state_transition",
            step: log.step,
            label: log.message || log.step?.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()) || "State Change",
            timestamp: log.timestamp || log.created_at,
            level: log.level || "info",
            status: "completed",
          });
        }
      });
    }
    
    // Add pending action events
    if (pendingAction) {
      events.push({
        type: "action",
        step: "paused_for_review",
        label: `Action Required: ${pendingAction.action_type?.replace(/_/g, " ") || "Review"}`,
        timestamp: pendingAction.created_at || liveState?.updated_at,
        status: "current",
        actionType: pendingAction.action_type,
        description: pendingAction.description,
      });
    }
    
    // Add key milestones
    if (liveState?.started_at) {
      events.push({
        type: "milestone",
        step: "initialized",
        label: "Workflow Started",
        timestamp: liveState.started_at,
        status: "completed",
      });
    }
    
    if (triage?.severity && !events.find(e => e.step === "policy_evaluated")) {
      events.push({
        type: "milestone",
        step: "policy_evaluated",
        label: "Triage Completed",
        timestamp: liveState?.updated_at,
        status: "completed",
      });
    }
    
    if (resolution?.resolution_steps && !events.find(e => e.step === "completed")) {
      events.push({
        type: "milestone",
        step: "completed",
        label: "Resolution Generated",
        timestamp: liveState?.completed_at || liveState?.updated_at,
        status: "completed",
      });
    }
    
    // Sort by timestamp
    events.sort((a, b) => {
      const aTime = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const bTime = b.timestamp ? new Date(b.timestamp).getTime() : 0;
      return aTime - bTime;
    });
    
    // Add current step if not in events
    if (liveState?.current_step && !events.find(e => e.step === liveState.current_step)) {
      const currentIdx = events.length;
      events.push({
        type: "state_transition",
        step: liveState.current_step,
        label: liveState.current_step.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()),
        timestamp: liveState.updated_at,
        status: "current",
      });
    }
    
    return events;
  }, [liveState, pendingAction, triage, resolution]);

  const normalizedPolicyBand = (policyBand || "UNKNOWN").toLowerCase();
  const policyInfo = getPolicyBandDescription(policyBand || "UNKNOWN");

  const handleGetResolution = async () => {
    if (requiresApproval || warning) return;
    await onResolution(incident.id);
  };

  const handleLegacyReviewSubmit = async (payload) => {
    await onFeedback(incident.id, {
      feedback_type: "triage",
      user_edited: payload.user_edited || triage,
      notes: payload.notes,
      policy_band: payload.policy_band || "AUTO",
    });
    setLegacyReviewMode(false);
  };

  const handlePendingActionSubmit = async (payload) => {
    if (!pendingAction || !onRespondPendingAction) return;
    await onRespondPendingAction(
      incident.id,
      pendingAction.action_name,
      payload
    );
  };

  return (
    <div className="incident-detail">
      <div className="workflow-hero">
        <div>
          <button className="btn-back" onClick={onBack}>
            ← Back to List
          </button>
          <h2>{incident.raw_alert?.title || "Incident Detail"}</h2>
          <p className="hero-subtitle">
            {incident.raw_alert?.description ||
              "Review AI triage, policy decisions, and resolution recommendations."}
          </p>
          <div className="hero-meta">
            <span className={`policy-badge badge-${normalizedPolicyBand}`}>
              {policyBand || "UNKNOWN"}
            </span>
            <span className="hero-pill">
              Severity: <strong>{triage.severity || "N/A"}</strong>
            </span>
            <span className="hero-pill">
              Confidence:{" "}
              <strong>
                {triage.confidence !== undefined
                  ? `${Math.round(triage.confidence * 100)}%`
                  : "N/A"}
              </strong>
            </span>
            {pendingAction && (
              <span className="hero-pill hero-pill-warning">
                Pending Action: {pendingAction.action_type}
              </span>
            )}
          </div>
        </div>
        <div className="hero-actions">
          {!resolution.resolution_steps &&
            !pendingAction &&
            !legacyReviewMode && (
              <>
                {/* Show both buttons when AUTO policy - user can get resolution or provide feedback */}
                {canAutoApply && !requiresApproval && !warning && (
                  <>
                    <button
                      className="btn-primary"
                      onClick={handleGetResolution}
                      disabled={loading}
                    >
                      {loading ? "Generating..." : "Get Resolution"}
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => setLegacyReviewMode(true)}
                      disabled={loading}
                      title="Review triage output manually and provide feedback"
                    >
                      Provide Feedback
                    </button>
                  </>
                )}
                {/* Show only feedback button for non-AUTO bands */}
                {(!canAutoApply || requiresApproval || policyBand === "PROPOSE" || policyBand === "REVIEW") && (
                  <button
                    className="btn-secondary"
                    onClick={() => setLegacyReviewMode(true)}
                    disabled={loading}
                    title="Review triage output manually and provide feedback"
                  >
                    Provide Feedback
                  </button>
                )}
              </>
            )}
        </div>
      </div>

      {liveState && (
        <ProgressStepper
          currentStep={liveState.current_step}
          connectionStatus={connectionStatus}
        />
      )}

      <div className="detail-content">
        {pendingAction && (
          <PendingActionCard
            action={pendingAction}
            onRespond={handlePendingActionSubmit}
            loading={loading}
          />
        )}

        {legacyReviewMode && !pendingAction && (
          <section className="detail-section hitl-action-card">
            <div className="hitl-action-header">
              <div>
                <h2>Manual Approval</h2>
                <p>
                  This incident was created without a live HITL action. Review
                  the triage output and submit approval to continue.
                </p>
              </div>
            </div>
            <TriageReviewForm
              triage={triage}
              onSubmit={handleLegacyReviewSubmit}
              loading={loading}
              onCancel={() => setLegacyReviewMode(false)}
            />
          </section>
        )}


        {warning && (
          <section className="detail-section warning-section">
            <h2>⚠️ Notice</h2>
            <p>{warning}</p>
          </section>
        )}

        <section className="detail-section policy-section">
          <h2>Policy Decision</h2>
          <div className="policy-header">
            <div className="policy-band-display">
              <span className={`policy-badge badge-${policyBand.toLowerCase()}`}>
                {policyBand}
              </span>
              <span className="policy-description">{policyInfo.description}</span>
            </div>
            <div className="policy-flags">
              <div className={`policy-flag ${canAutoApply ? "flag-auto" : "flag-manual"}`}>
                <span className="flag-label">Auto Apply:</span>
                <span className="flag-value">{canAutoApply ? "Yes" : "No"}</span>
              </div>
              <div className={`policy-flag ${requiresApproval ? "flag-required" : "flag-not-required"}`}>
                <span className="flag-label">Requires Approval:</span>
                <span className="flag-value">{requiresApproval ? "Yes" : "No"}</span>
              </div>
            </div>
          </div>
          <div className="policy-details">
            <div className="policy-detail-item">
              <strong>Conditions:</strong> {policyInfo.conditions}
            </div>
            <div className="policy-detail-item">
              <strong>Action:</strong> {policyInfo.action}
            </div>
          </div>
        </section>

        <section className="detail-section">
          <h2>Alert Information</h2>
          <div className="info-grid">
            <div className="info-item">
              <span className="info-label">Alert ID:</span>
              <span className="info-value">{incident.alert_id || "N/A"}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Received:</span>
              <span className="info-value">
                {incident.alert_received_at
                  ? new Date(incident.alert_received_at).toLocaleString()
                  : "N/A"}
              </span>
            </div>
          </div>
          {incident.raw_alert && (
            <div className="alert-details">
              <h3>{incident.raw_alert.title}</h3>
              <p>{incident.raw_alert.description}</p>
            </div>
          )}
        </section>

        <div className="detail-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`detail-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "overview" && (
          <section className="detail-section grid-two">
            <div>
              <h2>Policy Decision</h2>
              <div className="policy-header">
                <div className="policy-band-display">
                  <span className={`policy-badge badge-${normalizedPolicyBand}`}>
                    {policyBand || "UNKNOWN"}
                  </span>
                  <span className="policy-description">
                    {policyInfo.description}
                  </span>
                </div>
                <div className="policy-flags">
                  <div className={`policy-flag ${canAutoApply ? "flag-auto" : "flag-manual"}`}>
                    <span className="flag-label">Auto Apply</span>
                    <span className="flag-value">{canAutoApply ? "Yes" : "No"}</span>
                  </div>
                  <div className={`policy-flag ${requiresApproval ? "flag-required" : "flag-not-required"}`}>
                    <span className="flag-label">Approval Needed</span>
                    <span className="flag-value">{requiresApproval ? "Yes" : "No"}</span>
                  </div>
                </div>
              </div>
              <div className="policy-details">
                <div className="policy-detail-item">
                  <strong>Conditions:</strong> {policyInfo.conditions}
                </div>
                <div className="policy-detail-item">
                  <strong>Action:</strong> {policyInfo.action}
                </div>
              </div>
            </div>
            <div>
              <h2>Alert Information</h2>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Alert ID</span>
                  <span className="info-value">{incident.alert_id || "N/A"}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Received</span>
                  <span className="info-value">
                    {incident.alert_received_at
                      ? new Date(incident.alert_received_at).toLocaleString()
                      : "N/A"}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Service</span>
                  <span className="info-value">
                    {incident.raw_alert?.labels?.service || "N/A"}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Component</span>
                  <span className="info-value">
                    {incident.raw_alert?.labels?.component || "N/A"}
                  </span>
                </div>
              </div>
              {incident.raw_alert && (
                <div className="alert-details">
                  <h3>{incident.raw_alert.title}</h3>
                  <p>{incident.raw_alert.description}</p>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "triage" && (
          <section className="detail-section">
            <div className="triage-grid">
              <div className="triage-item">
                <span className="triage-label">Severity</span>
                <span className={`severity severity-${triage.severity}`}>
                  {triage.severity}
                </span>
              </div>
              <div className="triage-item">
                <span className="triage-label">Category</span>
                <span>{triage.category}</span>
              </div>
              <div className="triage-item">
                <span className="triage-label">Confidence</span>
                <span>
                  {triage.confidence !== undefined
                    ? `${(triage.confidence * 100).toFixed(0)}%`
                    : "N/A"}
                </span>
              </div>
            </div>
            <div className="triage-content">
              <div className="content-block">
                <h4>Summary</h4>
                <p>{triage.summary}</p>
              </div>
              <div className="content-block">
                <h4>Likely Cause</h4>
                <p>{triage.likely_cause}</p>
              </div>
              {triage.affected_services?.length > 0 && (
                <div className="content-block">
                  <h4>Affected Services</h4>
                  <ul>
                    {triage.affected_services.map((service, idx) => (
                      <li key={service + idx}>{service}</li>
                    ))}
                  </ul>
                </div>
              )}
              {triage.recommended_actions?.length > 0 && (
                <div className="content-block">
                  <h4>Recommended Actions</h4>
                  <ul>
                    {triage.recommended_actions.map((action, idx) => (
                      <li key={action + idx}>{action}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "resolution" && resolution.resolution_steps && (
          <section className="detail-section">
            <div className="resolution-meta">
              <div className="meta-item">
                <span className="meta-label">Risk Level</span>
                <span className={`risk risk-${resolution.risk_level}`}>
                  {resolution.risk_level}
                </span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Estimated Time</span>
                <span>{resolution.estimated_time_minutes} minutes</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Requires Approval</span>
                <span>{resolution.requires_approval ? "Yes" : "No"}</span>
              </div>
            </div>
            <div className="resolution-content">
              <div className="content-block">
                <h4>Resolution Steps</h4>
                <ol className="steps-list">
                  {resolution.resolution_steps.map((step, i) => (
                    <li key={step + i}>{step}</li>
                  ))}
                </ol>
              </div>
              {resolution.commands && (
                <div className="content-block">
                  <h4>Commands</h4>
                  <ul className="commands-list">
                    {resolution.commands.map((cmd, i) => (
                      <li key={cmd + i}>
                        <code>{cmd}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {resolution.rollback_plan && (
                <div className="content-block">
                  <h4>Rollback Plan</h4>
                  <ol className="steps-list">
                    {resolution.rollback_plan.map((step, i) => (
                      <li key={step + i}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "evidence" && (
          <section className="detail-section grid-two">
            <div>
              <h2>Triage Evidence</h2>
              {incident.triage_evidence ? (
                <>
                  <p className="evidence-count">
                    {incident.triage_evidence.chunks_used || 0} chunks
                  </p>
                  <div className="evidence-sources">
                    {incident.triage_evidence.chunk_sources?.map((source, i) => (
                      <span key={source + i} className="evidence-tag">
                        {source}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="muted">No triage evidence stored.</p>
              )}
            </div>
            <div>
              <h2>Resolution Evidence</h2>
              {incident.resolution_evidence ? (
                <>
                  <p className="evidence-count">
                    {incident.resolution_evidence.chunks_used || 0} chunks
                  </p>
                  <div className="evidence-sources">
                    {incident.resolution_evidence.chunk_sources?.map((source, i) => (
                      <span key={source + i} className="evidence-tag">
                        {source}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="muted">Resolution evidence will appear here once generated.</p>
              )}
            </div>
          </section>
        )}

        {activeTab === "timeline" && (
          <section className="detail-section">
            <h2>Workflow Timeline</h2>
            <div className="timeline-header">
              <p className="timeline-description">
                Complete history of state transitions, actions, and milestones
              </p>
            </div>
            <div className="timeline">
              {timelineEvents.length === 0 ? (
                <div className="timeline-empty">
                  <p>No timeline events yet. Timeline will populate as the workflow progresses.</p>
                </div>
              ) : (
                timelineEvents.map((event, idx) => (
                  <div
                    key={`${event.step}-${idx}-${event.timestamp || idx}`}
                    className={`timeline-item timeline-${event.status} timeline-${event.type}`}
                  >
                    <div className="timeline-node" />
                    <div className="timeline-content">
                      <div className="timeline-header-row">
                        <p className="timeline-label">{event.label}</p>
                        {event.type === "action" && (
                          <span className="timeline-badge timeline-badge-action">Action</span>
                        )}
                        {event.type === "milestone" && (
                          <span className="timeline-badge timeline-badge-milestone">Milestone</span>
                        )}
                      </div>
                      {event.description && (
                        <p className="timeline-description-text">{event.description}</p>
                      )}
                      <p className="timeline-meta">
                        {event.timestamp
                          ? new Date(event.timestamp).toLocaleString()
                          : "Just now"}
                        {event.level && event.level !== "info" && (
                          <span className={`timeline-level timeline-level-${event.level}`}>
                            {event.level}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

export default IncidentDetail;

