import { useState } from "react";
import { TicketForm } from "@/components/TicketForm";
import { TriageView } from "@/components/workflow/TriageView";
import { PolicyView } from "@/components/workflow/PolicyView";
import { ResolutionView } from "@/components/workflow/ResolutionView";
import { CompleteSummary } from "@/components/workflow/CompleteSummary";
import { Terminal, Activity, Search, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { postTriage, postResolution, putFeedback, putResolutionComplete, getIncident } from "@/api/client";

// Sample data
const sampleTriageData = {
  severity: "high" as const,
  category: "database",
  summary: "The alert indicates a failure in executing a database step due to an inability to open the step output file. This is critical as it affects the database operation in the production environment.",
  likely_cause: "The failure may be due to insufficient disk space or permission issues preventing access to the step output file.",
  routing: "SE DBA SQL",
  affected_services: ["Database-SQL"],
  recommended_actions: [
    "Check disk space on the database server.",
    "Verify permissions for the user INT\\ClustAgtSrvc on the output file location.",
    "Review recent changes or scheduled jobs that could have impacted database performance."
  ],
  confidence: 0.9
};

const samplePolicyData = {
  policy_band: "PROPOSE",
  policy_decision: {
    policy_band: "PROPOSE",
    can_auto_apply: false,
    requires_approval: true,
    notification_required: false,
    rollback_required: false,
    policy_reason: "Matched PROPOSE band based on severity=high and confidence=0.9"
  }
};

const sampleRetrievalData = {
  chunks_used: 5,
  chunk_ids: [
    "4b72cdc8-4537-4fda-a2eb-6fcc768789f6",
    "c431a520-b806-47be-a9aa-76a7c97acec0",
  ],
  chunk_sources: [
    "Runbook - Database Alerts",
    "Runbook - Database Alerts",
  ],
  chunks: []
};

const sampleResolutionData = {
  resolution_steps: [
    "SSH into the database server (Database-SQL)",
    "Check disk space: df -h",
    "Verify permissions: ls -la /path/to/output",
    "Review SQL Agent job history",
    "Restart affected services if needed",
    "Validate database connectivity"
  ]
};

type WorkflowStep = "form" | "triage" | "policy" | "resolution" | "complete";

const Index = () => {
  const [currentStep, setCurrentStep] = useState<WorkflowStep>("form");
  const [isLoading, setIsLoading] = useState(false);
  const [incidentId, setIncidentId] = useState("");
  const [alertData, setAlertData] = useState<any>(null);
  const [triageData, setTriageData] = useState<any>(null);
  const [policyData, setPolicyData] = useState<any>(null);
  const [retrievalData, setRetrievalData] = useState<any>(null);
  const [resolutionData, setResolutionData] = useState<any>(null);
  const [error, setError] = useState("");
  const [searchIncidentId, setSearchIncidentId] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  const handleSubmit = async (alert: any) => {
    setIsLoading(true);
    setAlertData(alert);
    setError("");
    
    
    try {
      const data = await postTriage(alert);
      
      setIncidentId(data.incident_id);
      
      // Extract triage data with new fields
      const triage = data.triage || {};
      
      // Derive summary and likely_cause from alert if not in triage output
      // Summary: Use alert description (first 200 chars) if no summary in triage
      const summary = triage.summary || alert.description?.substring(0, 200) || "";
      
      // Likely cause: Use LLM-generated value from triage output (based on evidence)
      // If not provided, use a simple fallback
      const likely_cause = triage.likely_cause || "Analysis based on alert description and historical patterns.";
      
      // Recommended actions: Can be derived from matched runbooks or left empty
      const recommended_actions = triage.recommended_actions || [];
      
      setTriageData({
        ...triage,
        severity: triage.severity || "medium",
        confidence: triage.confidence || 0,
        routing: triage.routing || null,
        impact: triage.impact || null,
        urgency: triage.urgency || null,
        affected_services: triage.affected_services || alert.affected_services || [],
        incident_signature: triage.incident_signature || {},
        matched_evidence: triage.matched_evidence || {},
        summary: summary,
        likely_cause: likely_cause,
        recommended_actions: recommended_actions,
        category: triage.category || alert.labels?.category || alert.category || "other",
      });
      
      setPolicyData({
        policy_band: data.policy_band,
        policy_decision: data.policy_decision
      });
      // Transform evidence structure for RetrievalTab
      const evidence = data.evidence || data.evidence_chunks || {};
      
      // Use chunks from evidence if available (full content), otherwise build from incident_signatures/runbook_metadata
      let chunks = evidence.chunks || [];
      
      if (chunks.length === 0) {
        // Fallback: build chunks from incident_signatures and runbook_metadata
        const incidentSigs = evidence.incident_signatures || [];
        const runbookMeta = evidence.runbook_metadata || [];
        
        chunks = [
          ...incidentSigs.map((sig: any) => {
            const metadata = sig.metadata || {};
            const symptoms = metadata.symptoms || [];
            const symptomsText = Array.isArray(symptoms) ? symptoms.join(', ') : '';
            return {
              chunk_id: sig.chunk_id || sig.incident_signature_id || '',
              document_id: sig.document_id || 'None',
              doc_title: `Incident Signature: ${sig.incident_signature_id || 'Unknown'}`,
              content: `Failure Type: ${sig.failure_type || metadata.failure_type || 'N/A'}\nError Class: ${sig.error_class || metadata.error_class || 'N/A'}${symptomsText ? `\nSymptoms: ${symptomsText}` : ''}\nService: ${metadata.service || metadata.affected_service || 'N/A'}\nComponent: ${metadata.component || 'N/A'}`,
              provenance: {
                source_type: 'incident_signature',
                source_id: sig.incident_signature_id,
              },
              metadata: metadata,
            };
          }),
          ...runbookMeta.map((rb: any) => ({
            chunk_id: rb.runbook_id || rb.document_id || '',
            document_id: rb.document_id || '',
            doc_title: rb.title || `Runbook: ${rb.runbook_id || 'Unknown'}`,
            content: `Service: ${rb.service || 'N/A'}\nComponent: ${rb.component || 'N/A'}`,
            provenance: {
              source_type: 'runbook',
              source_id: rb.runbook_id,
            },
            metadata: {
              service: rb.service,
              component: rb.component,
            },
          })),
        ];
      }
      
      setRetrievalData({
        chunks_used: chunks.length,
        chunk_ids: chunks.map((c: any) => c.chunk_id).filter(Boolean),
        chunk_sources: chunks.map((c: any) => c.doc_title).filter(Boolean),
        chunks: chunks,
        retrieval_method: evidence.retrieval_method || 'triage_retrieval',
        retrieval_params: evidence.retrieval_params || {},
      });
      setCurrentStep("triage");
    } catch (err: any) {
      console.error("❌ Triage FAILED!");
      console.error("Error object:", err);
      console.error("Error message:", err.message);
      console.error("Error response:", err.response);
      
      let errorMessage = "Failed to process triage. ";
      
      if (err.message.includes("fetch")) {
        errorMessage += "Cannot connect to backend. Make sure the AI service is running on http://localhost:8001";
      } else if (err.response?.data?.detail) {
        errorMessage += err.response.data.detail;
      } else if (err.message) {
        errorMessage += err.message;
      } else {
        errorMessage += "Unknown error occurred.";
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNextToPolicy = () => {
    setCurrentStep("policy");
  };

  const handleApproveAndContinue = async () => {
    if (!incidentId) {
      setError("No incident ID found");
      return;
    }
    
    setIsLoading(true);
    setError("");
    
    
    try {
      // Step 1: Submit approval feedback
      const feedbackPayload = {
        feedback_type: "triage",
        user_edited: triageData,
        notes: "Approved via UI",
        policy_band: "AUTO", // Override to AUTO to allow resolution
      };
      
      await putFeedback(incidentId, feedbackPayload);
      console.log("✅ Approval submitted successfully");
      
      // Step 2: Generate resolution
      console.log("Step 2: Generating resolution...");
      
      // No body needed - incident_id is in the query string
      const data = await postResolution(incidentId);
      
      // Extract resolution from the response
      // New structure: { resolution: { steps: [{ step_number, title, action, expected_outcome, risk_level }], ... }, ... }
      // Old structure: { resolution: { recommendations: [...], overall_confidence, risk_level, reasoning }, ... }
      // Legacy structure: { resolution: { steps: [...], ... }, ... }
      const resolution = data.resolution || data;
      const stepsArray = resolution.steps || []; // New format: array of objects
      const recommendations = resolution.recommendations || []; // Old format
      
      // For legacy compatibility, create string array from steps if needed
      const stepsAsStrings = stepsArray.length > 0 && typeof stepsArray[0] === 'object'
        ? stepsArray.map((step: any) => step.action || step.title || "")
        : (recommendations.length > 0 
          ? recommendations.map((rec: any) => rec.action || rec.step || "")
          : (resolution.resolution_steps || []));
      
      // Store all resolution data including rollback_plan if present
      // Preserve the original structure to handle both string and object rollback_plan
      setResolutionData({
        ...resolution, // Spread first to get all fields
        steps: stepsArray, // New format: array of step objects
        recommendations: recommendations, // Old format
        resolution_steps: stepsAsStrings, // Legacy format: array of strings
        // Keep rollback_plan as-is (can be string or object)
        risk_level: resolution.risk_level || data.risk_level || null,
        overall_confidence: resolution.overall_confidence || resolution.confidence || null,
        estimated_time_minutes: resolution.estimated_time_minutes || resolution.estimated_duration || null,
        estimated_duration: resolution.estimated_duration || resolution.estimated_time_minutes || null,
      });
      
      // Update policy data to reflect approval
      setPolicyData({
        ...policyData,
        policy_band: "AUTO"
      });
      
      setCurrentStep("resolution");
    } catch (err: any) {
      console.error("❌ Approval/Resolution FAILED!");
      console.error("Error:", err);
      console.error("Error response:", err.response);
      
      let errorMessage = "Failed to approve and generate resolution. ";
      
      // Parse the actual error from the response
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') {
          errorMessage += detail;
        } else if (detail.message) {
          errorMessage += detail.message;
        } else {
          errorMessage += JSON.stringify(detail);
        }
      } else if (err.message) {
        errorMessage += err.message;
      }
      
      // Add helpful context
      if (errorMessage.includes("rollback_plan")) {
        errorMessage += "\n\nThis is a backend validation issue. The resolution generator needs to include a rollback plan for high-risk operations.";
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBack = () => {
    if (currentStep === "complete") {
      setCurrentStep("resolution");
    } else if (currentStep === "resolution") {
      setCurrentStep("policy");
    } else if (currentStep === "policy") {
      setCurrentStep("triage");
    } else if (currentStep === "triage") {
      setCurrentStep("form");
    }
  };

  const handleNewTicket = () => {
    setCurrentStep("form");
    setIncidentId("");
    setAlertData(null);
    setTriageData(null);
    setPolicyData(null);
    setRetrievalData(null);
    setResolutionData(null);
    setError("");
    setSearchIncidentId("");
  };

  const handleLoadIncident = async () => {
    if (!searchIncidentId.trim()) {
      setError("Please enter an Incident ID or Alert ID");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      const incident = await getIncident(searchIncidentId);

      // Extract data from incident
      setIncidentId(incident.incident_id || incident.id);
      const rawAlert = incident.alert || incident.raw_alert || {};
      setAlertData(rawAlert);
      
      // Set triage data (always set, even if empty, to avoid rendering issues)
      const triageOutput = incident.triage_output || {};
      
      // Derive summary and likely_cause if missing
      const summary = triageOutput.summary || rawAlert.description?.substring(0, 200) || "";
      
      // Likely cause: Use LLM-generated value from triage output (based on evidence)
      // If not provided, use a simple fallback
      const likely_cause = triageOutput.likely_cause || "Analysis based on alert description and historical patterns.";
      
      setTriageData({
        ...triageOutput,
        summary: summary,
        likely_cause: likely_cause,
        recommended_actions: triageOutput.recommended_actions || [],
        category: triageOutput.category || rawAlert.labels?.category || rawAlert.category || "other",
      });

      // Set policy data (always set, even if empty)
      setPolicyData({
        policy_band: incident.policy_band || null,
        policy_decision: incident.policy_decision || {}
      });

      // Set retrieval/evidence data (always set, even if empty)
      const evidence = incident.triage_evidence || incident.resolution_evidence || {};
      
      // Use chunks from evidence if available (full content), otherwise build from incident_signatures/runbook_metadata
      let chunks = evidence.chunks || [];
      
      if (chunks.length === 0) {
        // Fallback: build chunks from incident_signatures and runbook_metadata
        const incidentSigs = evidence.incident_signatures || [];
        const runbookMeta = evidence.runbook_metadata || [];
        
        chunks = [
          ...incidentSigs.map((sig: any) => {
            const metadata = sig.metadata || {};
            const symptoms = metadata.symptoms || [];
            const symptomsText = Array.isArray(symptoms) ? symptoms.join(', ') : '';
            return {
              chunk_id: sig.chunk_id || sig.incident_signature_id || '',
              document_id: sig.document_id || 'None',
              doc_title: `Incident Signature: ${sig.incident_signature_id || 'Unknown'}`,
              content: `Failure Type: ${sig.failure_type || metadata.failure_type || 'N/A'}\nError Class: ${sig.error_class || metadata.error_class || 'N/A'}${symptomsText ? `\nSymptoms: ${symptomsText}` : ''}\nService: ${metadata.service || metadata.affected_service || 'N/A'}\nComponent: ${metadata.component || 'N/A'}`,
              provenance: {
                source_type: 'incident_signature',
                source_id: sig.incident_signature_id,
              },
              metadata: metadata,
            };
          }),
          ...runbookMeta.map((rb: any) => ({
            chunk_id: rb.runbook_id || rb.document_id || '',
            document_id: rb.document_id || '',
            doc_title: rb.title || `Runbook: ${rb.runbook_id || 'Unknown'}`,
            content: `Service: ${rb.service || 'N/A'}\nComponent: ${rb.component || 'N/A'}`,
            provenance: {
              source_type: 'runbook',
              source_id: rb.runbook_id,
            },
            metadata: {
              service: rb.service,
              component: rb.component,
            },
          })),
        ];
      }
      
      setRetrievalData({
        chunks_used: chunks.length,
        chunk_ids: chunks.map((c: any) => c.chunk_id).filter(Boolean),
        chunk_sources: chunks.map((c: any) => c.doc_title).filter(Boolean),
        chunks: chunks,
        retrieval_method: evidence.retrieval_method || 'triage_retrieval',
        retrieval_params: evidence.retrieval_params || {},
      });

      // Set resolution data if exists
      if (incident.resolution_output) {
        setResolutionData(incident.resolution_output);
      } else {
        // Set empty resolution data to avoid undefined errors
        setResolutionData({
          resolution_steps: [],
          rollback_plan: null,
          risk_level: null,
          estimated_time_minutes: null,
          confidence: null,
          reasoning: null
        });
      }

      // When loading an existing incident, ALWAYS go to complete summary page
      // This shows all available data in one place, regardless of resolution status
      // The CompleteSummary component handles missing data gracefully
      setCurrentStep("complete");

      setShowSearch(false);
    } catch (err: any) {
      console.error("❌ Failed to load incident:", err);
      setError(err.response?.data?.detail || err.message || "Failed to load incident");
    } finally {
      setIsLoading(false);
    }
  };

  const handleMarkComplete = () => {
    // Simply navigate to complete page - no API call needed
    // The resolution is already stored in the database from when it was generated
    setCurrentStep("complete");
  };

  const getStepStatus = (step: WorkflowStep) => {
    const steps = ["form", "triage", "policy", "resolution"];
    const currentIndex = steps.indexOf(currentStep);
    const stepIndex = steps.indexOf(step);
    
    if (stepIndex < currentIndex) return "complete";
    if (stepIndex === currentIndex) return "active";
    return "idle";
  };

  return (
    <div className="min-h-screen bg-background">
      {/* ServiceNow Style Header - Dark Navy */}
      <header className="relative z-10 bg-[#2c3e50] text-white shadow-md">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded bg-white/10">
                  <Terminal className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-white">NOC Agent</h1>
                  <p className="text-xs text-white/70">Incident Management</p>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              {/* Search/Load Existing Ticket */}
              {showSearch ? (
                <div className="flex items-center gap-2 bg-white/10 rounded px-3 py-1.5">
                  <Search className="w-4 h-4 text-white/70" />
                  <Input
                    value={searchIncidentId}
                    onChange={(e) => setSearchIncidentId(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleLoadIncident()}
                    placeholder="Incident ID or Alert ID..."
                    className="bg-transparent border-none text-white placeholder:text-white/50 focus-visible:ring-0 focus-visible:ring-offset-0 h-7 w-64"
                    disabled={isLoading}
                  />
                  <Button
                    size="sm"
                    onClick={handleLoadIncident}
                    disabled={isLoading}
                    className="bg-primary hover:bg-primary/90 h-7 px-3"
                  >
                    {isLoading ? "Loading..." : "Load"}
                  </Button>
                  <button
                    onClick={() => {
                      setShowSearch(false);
                      setSearchIncidentId("");
                      setError("");
                    }}
                    className="text-white/70 hover:text-white"
                  >
                    ✕
                  </button>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowSearch(true)}
                  className="bg-white/10 text-white border-white/20 hover:bg-white/20 hover:text-white h-8"
                >
                  <Search className="w-4 h-4 mr-2" />
                  Load Existing
                </Button>
              )}
              
              <div className="h-6 w-px bg-white/20" />
              
              <div className="flex items-center gap-2 text-sm">
                <Activity className="w-4 h-4 text-green-400" />
                <span className="text-white/90">Active</span>
              </div>
              
              <Button
                size="sm"
                onClick={handleNewTicket}
                className="bg-primary hover:bg-primary/90 text-white h-8"
              >
                <Plus className="w-4 h-4 mr-1" />
                New Ticket
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Progress Steps - ServiceNow Style */}
      {currentStep !== "form" && (
        <div className="relative z-10 bg-secondary border-b border-border">
          <div className="container mx-auto px-4 py-3">
            <div className="flex items-center gap-2">
              <StepBadge label="Triage" status={getStepStatus("triage")} />
              <StepBadge label="Policy & Approval" status={getStepStatus("policy")} />
              <StepBadge label="Resolution" status={getStepStatus("resolution")} />
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 py-8">
        <div className="max-w-[98%] mx-auto">
          {/* Error Display (Global) */}
          {error && !isLoading && (
            <div className="mb-4 p-4 bg-destructive/10 border-l-4 border-destructive rounded text-destructive animate-fade-in">
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <div>
                  <div className="font-semibold">Error</div>
                  <div className="text-sm mt-1">{error}</div>
                </div>
              </div>
            </div>
          )}
          
          {currentStep === "form" && (
            <TicketForm onSubmit={handleSubmit} isLoading={isLoading} error={error} />
          )}

          {currentStep === "triage" && triageData && policyData && retrievalData && (
            <TriageView
              triageData={triageData}
              policyData={policyData}
              retrievalData={retrievalData}
              onNext={handleNextToPolicy}
              onBack={handleBack}
            />
          )}

          {currentStep === "policy" && policyData && (
            <PolicyView
              data={policyData}
              retrievalData={retrievalData}
              onApprove={handleApproveAndContinue}
              onBack={handleBack}
              isLoading={isLoading}
              error={error}
            />
          )}

          {currentStep === "resolution" && resolutionData && (
            <ResolutionView
              data={resolutionData}
              onBack={handleBack}
              onMarkComplete={handleMarkComplete}
            />
          )}

          {currentStep === "complete" && alertData && resolutionData && (
            <CompleteSummary
              alertData={alertData || {}}
              triageData={triageData || {}}
              policyData={policyData || { policy_band: null, policy_decision: {} }}
              retrievalData={retrievalData || { chunks_used: 0, chunk_sources: [], chunks: [] }}
              resolutionData={resolutionData || { resolution_steps: [] }}
              onNewTicket={handleNewTicket}
              onViewTriage={() => {
                // Just navigate - use existing state data, no API calls
                setCurrentStep("triage");
              }}
              onViewResolution={() => {
                // Just navigate - use existing state data, no API calls
                setCurrentStep("resolution");
              }}
            />
          )}
        </div>
      </main>
    </div>
  );
};

// Step Badge Component
const StepBadge = ({ label, status }: { label: string; status: "complete" | "active" | "idle" }) => {
  const getStyles = () => {
    if (status === "complete") {
      return "bg-success/20 text-success border-success/30";
    }
    if (status === "active") {
      return "bg-warning/20 text-warning border-warning/30";
    }
    return "bg-secondary/50 text-muted-foreground border-border/30";
  };

  return (
    <div className={`px-3 py-1.5 rounded-lg border text-xs font-medium ${getStyles()}`}>
      {label}
      {status === "complete" && " ✓"}
    </div>
  );
};

export default Index;
