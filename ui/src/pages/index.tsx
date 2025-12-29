import { useState } from "react";
import { TicketForm } from "@/components/TicketForm";
import { TriageView } from "@/components/workflow/TriageView";
import { PolicyView } from "@/components/workflow/PolicyView";
import { ResolutionView } from "@/components/workflow/ResolutionView";
import { CompleteSummary } from "@/components/workflow/CompleteSummary";
import { Terminal, Activity } from "lucide-react";
import { postTriage, postResolution, putFeedback } from "@/api/client";

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

  const handleSubmit = async (alert: any) => {
    setIsLoading(true);
    setAlertData(alert);
    setError("");
    
    console.log("=== Submitting Triage ===");
    console.log("Alert data:", JSON.stringify(alert, null, 2));
    console.log("API endpoint:", "http://localhost:8001/api/v1/triage");
    
    try {
      const data = await postTriage(alert);
      console.log("✅ Triage SUCCESS!");
      console.log("Response:", JSON.stringify(data, null, 2));
      
      setIncidentId(data.incident_id);
      setTriageData(data.triage);
      setPolicyData({
        policy_band: data.policy_band,
        policy_decision: data.policy_decision
      });
      setRetrievalData(data.evidence_chunks || {
        chunks_used: 0,
        chunk_ids: [],
        chunk_sources: [],
        chunks: []
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
    
    console.log("=== Approving Policy ===");
    console.log("Incident ID:", incidentId);
    
    try {
      // Step 1: Submit approval feedback
      console.log("Step 1: Submitting approval feedback...");
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
      console.log("✅ Resolution generated successfully");
      console.log("Resolution response:", JSON.stringify(data, null, 2));
      
      // Extract resolution steps from the response
      const resolution = data.resolution || data;
      const steps = resolution.resolution_steps || resolution.steps || [];
      
      // Store all resolution data including rollback_plan if present
      setResolutionData({
        resolution_steps: steps,
        rollback_plan: resolution.rollback_plan || null,
        risk_level: resolution.risk_level || null,
        estimated_duration: resolution.estimated_duration || null,
        ...resolution
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
  };

  const handleMarkComplete = () => {
    // Simply navigate to complete page - no API call needed
    // The resolution is already stored in the database from when it was generated
    console.log("=== Marking Resolution Complete ===");
    console.log("Navigating to complete summary page");
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
      {/* Background gradient effect */}
      <div className="fixed inset-0 bg-gradient-to-br from-primary/5 via-background to-background pointer-events-none" />
      
      {/* Header */}
      <header className="relative z-10 border-b border-border/50 bg-card/50 backdrop-blur-xl">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Terminal className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-foreground">
                NOC Agent UI — 
                <span className="text-primary"> Triage</span> → 
                <span className={policyData ? "text-primary" : "text-muted-foreground"}> Policy</span> → 
                <span className={resolutionData ? "text-primary" : "text-muted-foreground"}> Resolution</span>
              </h1>
              <p className="text-xs text-muted-foreground">AI-Powered Incident Resolution</p>
            </div>
            <div className="ml-auto flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-success animate-pulse" />
                <span className="text-xs text-muted-foreground">System Active</span>
              </div>
              {currentStep !== "form" && (
                <button
                  onClick={handleNewTicket}
                  className="px-3 py-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-sm font-medium transition-colors"
                >
                  Triage New Ticket
                </button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Progress Steps */}
      {currentStep !== "form" && (
        <div className="relative z-10 bg-card/30 border-b border-border/50">
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

          {currentStep === "complete" && alertData && triageData && policyData && retrievalData && resolutionData && (
            <CompleteSummary
              alertData={alertData}
              triageData={triageData}
              policyData={policyData}
              retrievalData={retrievalData}
              resolutionData={resolutionData}
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
