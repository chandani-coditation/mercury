import React, { useState, useEffect, useMemo, useRef } from "react";
import "./App.css";
import IncidentList from "./components/IncidentList";
import IncidentDetail from "./components/IncidentDetail";
import { AgentStateProvider } from "./context/AgentStateContext";
import { ToastProvider, useToast } from "./context/ToastContext";
import ToastContainer from "./components/common/ToastContainer";
import apiClient from "./services/api";
import Sidebar from "./components/layout/Sidebar";
import TopBar from "./components/layout/TopBar";
import TriageForm from "./components/TriageForm";
import RunbooksList from "./components/RunbooksList";
import Button from "./components/common/Button";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";

function AppContent() {
  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showTriageForm, setShowTriageForm] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [policyFilter, setPolicyFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [workspaceTab, setWorkspaceTab] = useState("incidents");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const toast = useToast();

  useEffect(() => {
    if (workspaceTab === "incidents") {
      loadIncidents();
    }
  }, [workspaceTab]);

  // Auto-refresh insights when state updates (polling every 30 seconds)
  useEffect(() => {
    if (workspaceTab !== "incidents") return;
    
    const refreshInterval = setInterval(() => {
      // Only refresh if we're not currently loading and have incidents
      if (!loading && incidents.length > 0) {
        loadIncidents();
      }
    }, 30000); // Refresh every 30 seconds

    return () => clearInterval(refreshInterval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceTab, loading, incidents.length]);

  const loadIncidents = async (pageNum = page) => {
    setLoading(true);
    setError(null);
    try {
      const offset = (pageNum - 1) * pageSize;
      const response = await apiClient.get(
        `/incidents?limit=${pageSize}&offset=${offset}`
      );
      setIncidents(response.data.incidents || []);
      // Update page if we got results
      if (response.data.incidents?.length > 0 || pageNum === 1) {
        setPage(pageNum);
      }
    } catch (err) {
      const errorMsg = `Failed to load incidents: ${err.message}`;
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleIncidentSelect = (incident) => {
    setSelectedIncident(incident);
  };

  const handleBack = () => {
    setSelectedIncident(null);
    loadIncidents();
  };

  const handleTriage = async (alertData) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.post(`/triage`, alertData);
      await loadIncidents();
      // Fetch the full incident and merge policy_decision and warning from triage response
      // The triage response has the fresh policy_decision, which is more reliable than DB fetch
      const incidentResponse = await apiClient.get(
        `/incidents/${response.data.incident_id}`
      );
      const incidentWithPolicy = { 
        ...incidentResponse.data, 
        // Merge policy_decision from triage response (more reliable, fresh from agent)
        policy_decision: response.data.policy_decision || incidentResponse.data.policy_decision,
        policy_band: response.data.policy_band || incidentResponse.data.policy_band,
        warning: response.data.warning || null
      };
      console.log('[App] Triage completed, policy:', {
        policy_band: incidentWithPolicy.policy_band,
        can_auto_apply: incidentWithPolicy.policy_decision?.can_auto_apply,
        requires_approval: incidentWithPolicy.policy_decision?.requires_approval
      });
      setSelectedIncident(incidentWithPolicy);
      toast.success("Triage completed successfully");
      return incidentWithPolicy;
    } catch (err) {
      const errorDetail = err.response?.data?.detail;
      let errorMessage = 'Triage failed';
      
      if (typeof errorDetail === 'string') {
        errorMessage = errorDetail;
      } else if (errorDetail) {
        errorMessage = JSON.stringify(errorDetail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      // Make error message more user-friendly
      if (errorMessage.includes('No matching evidence') || errorMessage.includes('No historical data')) {
        errorMessage = `⚠️ No matching evidence found in knowledge base. The system needs relevant historical data to perform triage. Please ensure similar alerts, incidents, or runbooks are ingested first.`;
      }
      
      setError(errorMessage);
      toast.error(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const handleResolution = async (incidentId) => {
    console.log('[App] Generating resolution for incident:', incidentId);
    setLoading(true);
    setError(null);
    const startTime = Date.now();
    try {
      const response = await apiClient.post(
        `/resolution?incident_id=${incidentId}`
      );
      const duration = Date.now() - startTime;
      console.log(`[App] Resolution generated in ${duration}ms`);
      // Wait a moment for database to update
      await new Promise(resolve => setTimeout(resolve, 300));
      await loadIncidents();
      // Fetch the full incident and merge warning from response
      const incidentResponse = await apiClient.get(
        `/incidents/${incidentId}`
      );
      const incidentWithWarning = { 
        ...incidentResponse.data, 
        warning: response.data.warning || null,
        resolution_output: response.data.resolution || incidentResponse.data.resolution_output
      };
      if (selectedIncident?.id === incidentId) {
        setSelectedIncident(incidentWithWarning);
      }
      toast.success("Resolution generated successfully");
      return incidentWithWarning;
    } catch (err) {
      const duration = Date.now() - startTime;
      console.error(`[App] Resolution failed after ${duration}ms:`, err);
      const errorDetail = err.response?.data?.detail;
      let errorMessage = 'Resolution failed';
      
      if (err.response?.status === 403) {
        console.log('[App] Approval required (403)');
        errorMessage = 'Approval required. Please approve via feedback first.';
      } else if (typeof errorDetail === 'string') {
        errorMessage = errorDetail;
      } else if (errorDetail) {
        errorMessage = JSON.stringify(errorDetail);
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      // Make error message more user-friendly
      if (errorMessage.includes('No matching evidence') || errorMessage.includes('No historical data')) {
        errorMessage = `⚠️ No matching evidence found in knowledge base. The system needs relevant historical data to generate resolution. Please ensure similar runbooks or incidents are ingested first.`;
      }
      
      setError(errorMessage);
      toast.error(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const handleFeedback = async (incidentId, feedbackData) => {
    // Optimistic update
    const originalIncident = selectedIncident;
    if (selectedIncident?.id === incidentId) {
      setSelectedIncident((prev) => ({
        ...prev,
        ...feedbackData,
        updated_at: new Date().toISOString(),
      }));
    }
    
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.put(
        `/incidents/${incidentId}/feedback`,
        feedbackData
      );
      await loadIncidents();
      if (selectedIncident?.id === incidentId) {
        const updated = await apiClient.get(`/incidents/${incidentId}`);
        setSelectedIncident(updated.data);
      }
      toast.success("Feedback submitted successfully");
      return response.data;
    } catch (err) {
      // Rollback optimistic update
      if (originalIncident) {
        setSelectedIncident(originalIncident);
      }
      const errorMsg = `Feedback failed: ${err.response?.data?.detail || err.message}`;
      setError(errorMsg);
      toast.error(errorMsg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const respondToPendingAction = async (
    incidentId,
    actionName,
    actionPayload
  ) => {
    setLoading(true);
    setError(null);
    try {
      await apiClient.post(
        `/agents/${incidentId}/actions/${actionName}/respond`,
        {
          action_name: actionName,
          incident_id: incidentId,
          approved:
            actionPayload.approved !== undefined
              ? actionPayload.approved
              : true,
          user_edited:
            actionPayload.user_edited || actionPayload.userEdited || null,
          notes: actionPayload.notes || "",
          policy_band:
            actionPayload.policy_band || actionPayload.policyBand || "AUTO",
        }
      );
      await loadIncidents();
      if (selectedIncident?.id === incidentId) {
        const updated = await apiClient.get(`/incidents/${incidentId}`);
        setSelectedIncident(updated.data);
      }
      toast.success("Action response submitted successfully");
    } catch (err) {
      const errorDetail = err.response?.data?.detail;
      const errorMsg = `Action response failed: ${
        typeof errorDetail === "string"
          ? errorDetail
          : err.message || "unknown error"
      }`;
      setError(errorMsg);
      toast.error(errorMsg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const filteredIncidents = useMemo(() => {
    return (
      incidents
        .filter((incident) => {
          if (!searchTerm) return true;
          const haystack = [
            incident.raw_alert?.title,
            incident.raw_alert?.labels?.service,
            incident.id,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return haystack.includes(searchTerm.toLowerCase());
        })
        .filter((incident) => {
          if (policyFilter === "all") return true;
          return (incident.policy_band || "").toUpperCase() === policyFilter;
        })
        .filter((incident) => {
          if (severityFilter === "all") return true;
          const severity = incident.triage_output?.severity?.toLowerCase();
          return severity === severityFilter;
        })
        .sort((a, b) => {
          const aTime = new Date(a.alert_received_at || a.created_at || 0).getTime();
          const bTime = new Date(b.alert_received_at || b.created_at || 0).getTime();
          return bTime - aTime;
        })
    );
  }, [incidents, searchTerm, policyFilter, severityFilter]);

  const insightData = useMemo(() => {
    const total = incidents.length;
    const awaitingApproval = incidents.filter(
      (incident) =>
        incident.policy_decision?.requires_approval && !incident.resolution_output
    ).length;
    const autoReady = incidents.filter(
      (incident) => incident.policy_decision?.can_auto_apply
    ).length;

    return [
      { label: "Total Incidents", value: total, helper: "live" },
      { label: "Awaiting Approval", value: awaitingApproval, helper: "policy holds" },
      { label: "Auto-Ready", value: autoReady, helper: "safe to apply" },
    ];
  }, [incidents]);

  const incidentStats = useMemo(() => {
    const total = incidents.length;
    const awaitingApproval = incidents.filter(
      (incident) =>
        incident.policy_decision?.requires_approval && !incident.resolution_output
    ).length;
    // Count incidents that likely have pending actions (requires approval but no resolution)
    const pendingActions = awaitingApproval;
    
    return {
      total,
      awaitingApproval,
      pendingActions,
    };
  }, [incidents]);

  const openTriageForm = () => setShowTriageForm(true);
  const closeTriageForm = () => setShowTriageForm(false);
  const searchInputRef = useRef(null);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    "ctrl+k": (e) => {
      e.preventDefault();
      searchInputRef.current?.focus();
    },
    "ctrl+n": (e) => {
      e.preventDefault();
      if (!showTriageForm) {
        openTriageForm();
      }
    },
    "escape": (e) => {
      if (showTriageForm) {
        closeTriageForm();
      } else if (selectedIncident) {
        handleBack();
      }
    },
    "ctrl+r": (e) => {
      e.preventDefault();
      loadIncidents();
    },
  }, true);

  const workspaceMeta = {
    runbooks: {
      title: "Runbooks Library",
      description:
        "Organize human playbooks and AI-assisted workflows. Configure guardrails and escalation paths.",
      cta: "Create Runbook",
    },
    analytics: {
      title: "Operations Analytics",
      description:
        "Monitor AI adoption, policy performance, and HITL workload trends. Dashboards coming soon.",
      cta: "View Dashboard",
    },
  };

  const handleTriageSubmit = async (data) => {
    await handleTriage(data);
    closeTriageForm();
  };

  const handleBulkAction = async (incidentIds, action) => {
    // Optimistic update
    const originalIncidents = [...incidents];
    setIncidents((prev) =>
      prev.map((incident) =>
        incidentIds.includes(incident.id)
          ? {
              ...incident,
              policy_decision: {
                ...incident.policy_decision,
                requires_approval: false,
                can_auto_apply: action === "approve",
              },
              updated_at: new Date().toISOString(),
            }
          : incident
      )
    );

    setLoading(true);
    setError(null);
    try {
      if (action === "approve") {
        // Approve all selected incidents
        await Promise.all(
          incidentIds.map((id) =>
            apiClient.put(`/incidents/${id}/feedback`, {
              approved: true,
              notes: "Bulk approved",
            })
          )
        );
        toast.success(`Approved ${incidentIds.length} incident(s)`);
      } else if (action === "dismiss") {
        // Dismiss all selected incidents
        await Promise.all(
          incidentIds.map((id) =>
            apiClient.put(`/incidents/${id}/feedback`, {
              approved: false,
              notes: "Bulk dismissed",
            })
          )
        );
        toast.success(`Dismissed ${incidentIds.length} incident(s)`);
      }
      await loadIncidents();
    } catch (err) {
      // Rollback optimistic update
      setIncidents(originalIncidents);
      const errorMsg = `Bulk action failed: ${err.response?.data?.detail || err.message}`;
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar 
        onNewIncident={openTriageForm} 
        onRefresh={loadIncidents}
        incidentStats={incidentStats}
      />

      <div className="content-shell">
        <TopBar
          selectedIncident={workspaceTab === "incidents" ? selectedIncident : null}
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          policyFilter={policyFilter}
          onPolicyFilterChange={setPolicyFilter}
          severityFilter={severityFilter}
          onSeverityFilterChange={setSeverityFilter}
          onNewIncident={openTriageForm}
          onRefresh={loadIncidents}
          workspaceTab={workspaceTab}
          onWorkspaceTabChange={setWorkspaceTab}
          searchInputRef={searchInputRef}
        />

        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        <div className="insights-row">
          {insightData.map((insight) => (
            <div key={insight.label} className="insight-card">
              <h4>{insight.label}</h4>
              <strong>{insight.value}</strong>
              <span>{insight.helper}</span>
            </div>
          ))}
        </div>

        <div className="content-body">
          {workspaceTab === "incidents" ? (
            <div className="pane-grid">
              <div className="pane">
                <IncidentList
                  incidents={filteredIncidents}
                  onSelect={handleIncidentSelect}
                  onNewTriage={openTriageForm}
                  onResolveIncident={handleResolution}
                  onBulkAction={handleBulkAction}
                  loading={loading}
                  selectedIncidentId={selectedIncident?.id}
                  page={page}
                  pageSize={pageSize}
                  onPageChange={(newPage) => loadIncidents(newPage)}
                />
              </div>
              <div className="pane">
                {selectedIncident ? (
                  <AgentStateProvider incidentId={selectedIncident.id}>
                    <IncidentDetail
                      incident={selectedIncident}
                      onBack={handleBack}
                      onResolution={handleResolution}
                      onFeedback={handleFeedback}
                      onRespondPendingAction={respondToPendingAction}
                      loading={loading}
                    />
                  </AgentStateProvider>
                ) : (
                  <div className="pane-placeholder">
                    Select an incident to view live workflow state.
                  </div>
                )}
              </div>
            </div>
          ) : workspaceTab === "runbooks" ? (
            <RunbooksList />
          ) : (
            <div className="workspace-placeholder">
              <h2>{workspaceMeta[workspaceTab]?.title}</h2>
              <p>{workspaceMeta[workspaceTab]?.description}</p>
              <div className="placeholder-actions">
                <Button
                  variant="primary"
                  onClick={() => toast.info("Coming soon!")}
                >
                  {workspaceMeta[workspaceTab]?.cta || "Coming Soon"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {showTriageForm && (
        <div className="modal-overlay">
          <div className="modal-panel">
            <TriageForm
              onSubmit={handleTriageSubmit}
              onCancel={closeTriageForm}
              loading={loading}
            />
          </div>
        </div>
      )}

      <ToastContainer />
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

export default App;

