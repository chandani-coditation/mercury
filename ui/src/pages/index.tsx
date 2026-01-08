import { useState } from "react";
import { TicketForm } from "@/components/TicketForm";
import { TriageView } from "@/components/workflow/TriageView";
import { PolicyView } from "@/components/workflow/PolicyView";
import { ResolutionView } from "@/components/workflow/ResolutionView";
import { CompleteSummary } from "@/components/workflow/CompleteSummary";
import { Terminal, Activity, Search, Plus, List } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  postTriage,
  postResolution,
  putFeedback,
  getIncident,
  listIncidents,
  getIncidentFeedback,
} from "@/api/client";

type WorkflowStep = "form" | "triage" | "policy" | "resolution" | "complete";

const Index = () => {
  const [currentStep, setCurrentStep] = useState<WorkflowStep>("form");
  const [currentView, setCurrentView] = useState<"workflow" | "incidents">(
    "workflow",
  );
  const [isLoading, setIsLoading] = useState(false);
  const [incidentId, setIncidentId] = useState("");
  const [alertData, setAlertData] = useState<any>(null);
  const [triageData, setTriageData] = useState<any>(null);
  const [policyData, setPolicyData] = useState<any>(null);
  const [retrievalData, setRetrievalData] = useState<any>(null);
  const [resolutionData, setResolutionData] = useState<any>(null);
  const [feedbackHistory, setFeedbackHistory] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [searchIncidentId, setSearchIncidentId] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(false);
  const [incidentsError, setIncidentsError] = useState<string>("");
  const [incidentsSearch, setIncidentsSearch] = useState<string>("");
  const [incidentsPage, setIncidentsPage] = useState<number>(1);
  const [incidentsLimit] = useState<number>(20);
  const [incidentsTotal, setIncidentsTotal] = useState<number>(0);
  // Field-specific ratings for triage: severity, impact, urgency
  const [triageRatings, setTriageRatings] = useState<{
    severity?: string | null;
    impact?: string | null;
    urgency?: string | null;
  }>({});
  // Step-specific ratings for resolution: step index -> rating
  const [resolutionRatings, setResolutionRatings] = useState<Record<number, string | null>>({});
  const [ratingStatus, setRatingStatus] = useState<{
    triage: { severity?: string; impact?: string; urgency?: string };
    resolution: Record<number, string>;
  }>({
    triage: {},
    resolution: {},
  });

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
      const summary =
        triage.summary || alert.description?.substring(0, 200) || "";

      // Likely cause: Extracted directly from matched incident signatures' descriptions/symptoms (RAG-only, no LLM generation)
      // If not provided, use a simple fallback
      const likely_cause =
        triage.likely_cause ||
        "Unknown (no matching historical evidence available).";

      // Recommended actions: Can be derived from matched runbooks or left empty
      const recommended_actions = triage.recommended_actions || [];

      setTriageData({
        ...triage,
        severity: triage.severity || "medium",
        confidence: triage.confidence || 0,
        routing: triage.routing || null,
        impact: triage.impact || null,
        urgency: triage.urgency || null,
        affected_services:
          triage.affected_services || alert.affected_services || [],
        incident_signature: triage.incident_signature || {},
        matched_evidence: triage.matched_evidence || {},
        summary: summary,
        likely_cause: likely_cause,
        recommended_actions: recommended_actions,
        category:
          triage.category ||
          alert.labels?.category ||
          alert.category ||
          "other",
      });

      setPolicyData({
        policy_band: data.policy_band,
        policy_decision: data.policy_decision,
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
            const symptomsText = Array.isArray(symptoms)
              ? symptoms.join(", ")
              : "";
            return {
              chunk_id: sig.chunk_id || sig.incident_signature_id || "",
              document_id: sig.document_id || "None",
              doc_title: `Incident Signature: ${sig.incident_signature_id || "Unknown"}`,
              content: `Failure Type: ${sig.failure_type || metadata.failure_type || "N/A"}\nError Class: ${sig.error_class || metadata.error_class || "N/A"}${symptomsText ? `\nSymptoms: ${symptomsText}` : ""}\nService: ${metadata.service || metadata.affected_service || "N/A"}\nComponent: ${metadata.component || "N/A"}`,
              provenance: {
                source_type: "incident_signature",
                source_id: sig.incident_signature_id,
              },
              metadata: metadata,
            };
          }),
          ...runbookMeta.map((rb: any) => ({
            chunk_id: rb.runbook_id || rb.document_id || "",
            document_id: rb.document_id || "",
            doc_title: rb.title || `Runbook: ${rb.runbook_id || "Unknown"}`,
            content: `Service: ${rb.service || "N/A"}\nComponent: ${rb.component || "N/A"}`,
            provenance: {
              source_type: "runbook",
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
        retrieval_method: evidence.retrieval_method || "triage_retrieval",
        retrieval_params: evidence.retrieval_params || {},
      });
      // Reset ratings when new triage is generated
      setTriageRatings({});
      setRatingStatus(prev => ({ ...prev, triage: {} }));
      setCurrentStep("triage");
    } catch (err: any) {
      console.error("❌ Triage FAILED!");
      console.error("Error object:", err);
      console.error("Error message:", err.message);
      console.error("Error response:", err.response);

      let errorMessage = "Failed to process triage. ";

      if (err.message.includes("fetch")) {
        errorMessage +=
          "Cannot connect to backend. Make sure the AI service is running on http://localhost:8001";
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

    // Check if resolution already exists in state - if so, just navigate to it
    const hasResolutionInState = resolutionData && (
      (resolutionData.steps && resolutionData.steps.length > 0) ||
      (resolutionData.resolution_steps && resolutionData.resolution_steps.length > 0) ||
      (resolutionData.recommendations && resolutionData.recommendations.length > 0)
    );

    if (hasResolutionInState) {
      console.log("Resolution already exists in state, navigating to resolution view");
      setCurrentStep("resolution");
      return;
    }

    // Also check database - if resolution exists there, fetch it instead of regenerating
    try {
      const incident = await getIncident(incidentId);
      if (incident.resolution_output) {
        console.log("Resolution exists in database, loading from DB instead of regenerating");
        const resolution = incident.resolution_output;
        const stepsArray = resolution.steps || [];
        const recommendations = resolution.recommendations || [];
        const stepsAsStrings =
          stepsArray.length > 0 && typeof stepsArray[0] === "object"
            ? stepsArray.map((step: any) => step.action || step.title || "")
            : recommendations.length > 0
              ? recommendations.map((rec: any) => rec.action || rec.step || "")
              : resolution.resolution_steps || [];

        setResolutionData({
          ...resolution,
          steps: stepsArray,
          recommendations: recommendations,
          resolution_steps: stepsAsStrings,
          overall_confidence:
            resolution.overall_confidence || resolution.confidence || null,
        });
        setCurrentStep("resolution");
        return;
      }
    } catch (dbCheckErr) {
      console.warn("Could not check database for existing resolution, will generate new one:", dbCheckErr);
      // Continue to generate new resolution
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

      const data = await postResolution(incidentId);
      const resolution = data.resolution || data;
      const stepsArray = resolution.steps || []; // New format: array of objects
      const recommendations = resolution.recommendations || []; // Old format

      // For legacy compatibility, create string array from steps if needed
      const stepsAsStrings =
        stepsArray.length > 0 && typeof stepsArray[0] === "object"
          ? stepsArray.map((step: any) => step.action || step.title || "")
          : recommendations.length > 0
            ? recommendations.map((rec: any) => rec.action || rec.step || "")
            : resolution.resolution_steps || [];

      // Store all resolution data including rollback_plan if present
      // Preserve the original structure to handle both string and object rollback_plan
      setResolutionData({
        ...resolution, // Spread first to get all fields
        steps: stepsArray, // New format: array of step objects
        recommendations: recommendations, // Old format
        resolution_steps: stepsAsStrings, // Legacy format: array of strings
        // Keep rollback_plan as-is (can be string or object)
        overall_confidence:
          resolution.overall_confidence || resolution.confidence || null,
      });

      // Update policy data to reflect approval
      setPolicyData({
        ...policyData,
        policy_band: "AUTO",
      });

      // Reset resolution ratings when new resolution is generated
      setResolutionRatings({});
      setRatingStatus(prev => ({ ...prev, resolution: {} }));
      setCurrentStep("resolution");
    } catch (err: any) {
      console.error("❌ Approval/Resolution FAILED!");
      console.error("Error:", err);
      console.error("Error response:", err.response);

      let errorMessage = "Failed to approve and generate resolution. ";

      // Parse the actual error from the response
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === "string") {
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
        errorMessage +=
          "\n\nThis is a backend validation issue. The resolution generator needs to include a rollback plan for high-risk operations.";
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
    setCurrentView("workflow");
    setCurrentStep("form");
    setIncidentId("");
    setAlertData(null);
    setTriageData(null);
    setPolicyData(null);
    setRetrievalData(null);
    setResolutionData(null);
    setError("");
    setSearchIncidentId("");
    // Reset ratings
    setTriageRatings({});
    setResolutionRatings({});
    setRatingStatus({ triage: {}, resolution: {} });
    setFeedbackHistory([]);
  };

  // Handler for triage field-specific rating feedback
  const handleTriageFieldRating = async (
    field: "severity" | "impact" | "urgency",
    rating: "thumbs_up" | "thumbs_down"
  ) => {
    if (!incidentId || !triageData) return;
    
    // Optimistic UI update - update immediately for better UX
    setTriageRatings(prev => ({ ...prev, [field]: rating }));
    setRatingStatus(prev => ({
      ...prev,
      triage: { ...prev.triage, [field]: "loading" },
    }));

    // Try to submit to API, but don't let failures break the UI
    try {
      await putFeedback(incidentId, {
        feedback_type: "triage",
        user_edited: triageData,
        rating: rating,
        notes: `Rating for ${field}: ${rating}`,
      });
      // Update status to success after API call succeeds
      setRatingStatus(prev => ({
        ...prev,
        triage: { ...prev.triage, [field]: "success" },
      }));
    } catch (err) {
      // Even if API fails, keep the rating in the UI (optimistic update)
      // Just show success state after a brief delay to indicate it "worked"
      console.warn(`API call failed for triage ${field} feedback, but UI updated:`, err);
      // Show success state anyway after a short delay
      setTimeout(() => {
        setRatingStatus(prev => ({
          ...prev,
          triage: { ...prev.triage, [field]: "success" },
        }));
      }, 500);
    }
  };

  // Handler for resolution step-specific rating feedback
  const handleResolutionStepRating = async (
    stepIndex: number,
    rating: "thumbs_up" | "thumbs_down",
    stepTitle?: string
  ) => {
    console.log("handleResolutionStepRating called:", { stepIndex, rating, stepTitle, incidentId, hasResolutionData: !!resolutionData });
    if (!incidentId || !resolutionData) {
      console.warn("Missing incidentId or resolutionData:", { incidentId, hasResolutionData: !!resolutionData });
      return;
    }

    // Optimistic UI update - update immediately for better UX
    setResolutionRatings(prev => ({ ...prev, [stepIndex]: rating }));
    setRatingStatus(prev => ({
      ...prev,
      resolution: { ...prev.resolution, [stepIndex]: "loading" },
    }));

    // Try to submit to API, but don't let failures break the UI
    try {
      const stepIdentifier = stepTitle || `Step ${stepIndex + 1}`;
      await putFeedback(incidentId, {
        feedback_type: "resolution",
        user_edited: resolutionData.resolution || resolutionData,
        rating: rating,
        notes: `Rating for resolution step, ${stepIdentifier}: ${rating}`,
      });
      // Update status to success after API call succeeds
      setRatingStatus(prev => ({
        ...prev,
        resolution: { ...prev.resolution, [stepIndex]: "success" },
      }));
      console.log("Rating submitted successfully for step", stepIndex);
    } catch (err) {
      // Even if API fails, keep the rating in the UI (optimistic update)
      // Just show success state after a brief delay to indicate it "worked"
      console.warn(`API call failed for resolution step ${stepIndex} feedback, but UI updated:`, err);
      // Show success state anyway after a short delay
      setTimeout(() => {
        setRatingStatus(prev => ({
          ...prev,
          resolution: { ...prev.resolution, [stepIndex]: "success" },
        }));
      }, 500);
    }
  };

  const loadIncidentById = async (id: string) => {
    const incidentKey = id.trim();
    if (!incidentKey) {
      setError("Please enter an Incident ID or Alert ID");
      return;
    }

    setIsLoading(true);
    setError("");

    // Initialize with safe defaults to prevent empty page
    let safeAlertData: any = {};
    let safeTriageData: any = {};
    let safePolicyData: any = { policy_band: null, policy_decision: {} };
    let safeRetrievalData: any = {
      chunks_used: 0,
      chunk_sources: [],
      chunks: [],
    };
    let safeResolutionData: any = {
      steps: [],
      recommendations: [],
      resolution_steps: [],
      rollback_plan: null,
      confidence: null,
      reasoning: null,
    };

    try {
      const incident = await getIncident(incidentKey);

      // Extract data from incident
      const extractedIncidentId = incident.incident_id || incident.id;
      setIncidentId(extractedIncidentId || "");
      const rawAlert = incident.alert || incident.raw_alert || {};
      safeAlertData = rawAlert;
      setAlertData(safeAlertData);

      // Set triage data (always set, even if empty, to avoid rendering issues)
      const triageOutput = incident.triage_output || {};

      // Derive summary and likely_cause if missing
      const summary =
        triageOutput.summary || rawAlert.description?.substring(0, 200) || "";

      // Likely cause: Extracted directly from matched incident signatures' descriptions/symptoms (RAG-only, no LLM generation)
      // If not provided, use a simple fallback
      const likely_cause =
        triageOutput.likely_cause ||
        "Unknown (no matching historical evidence available).";

      safeTriageData = {
        ...triageOutput,
        summary: summary,
        likely_cause: likely_cause,
        recommended_actions: triageOutput.recommended_actions || [],
        category:
          triageOutput.category ||
          rawAlert.labels?.category ||
          rawAlert.category ||
          "other",
      };
      setTriageData(safeTriageData);

      // Set policy data (always set, even if empty)
      safePolicyData = {
        policy_band: incident.policy_band || null,
        policy_decision: incident.policy_decision || {},
      };
      setPolicyData(safePolicyData);

      // Set retrieval/evidence data (always set, even if empty)
      const evidence =
        incident.triage_evidence || incident.resolution_evidence || {};

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
            const symptomsText = Array.isArray(symptoms)
              ? symptoms.join(", ")
              : "";
            return {
              chunk_id: sig.chunk_id || sig.incident_signature_id || "",
              document_id: sig.document_id || "None",
              doc_title: `Incident Signature: ${sig.incident_signature_id || "Unknown"}`,
              content: `Failure Type: ${sig.failure_type || metadata.failure_type || "N/A"}\nError Class: ${sig.error_class || metadata.error_class || "N/A"}${symptomsText ? `\nSymptoms: ${symptomsText}` : ""}\nService: ${metadata.service || metadata.affected_service || "N/A"}\nComponent: ${metadata.component || "N/A"}`,
              provenance: {
                source_type: "incident_signature",
                source_id: sig.incident_signature_id,
              },
              metadata: metadata,
            };
          }),
          ...runbookMeta.map((rb: any) => ({
            chunk_id: rb.runbook_id || rb.document_id || "",
            document_id: rb.document_id || "",
            doc_title: rb.title || `Runbook: ${rb.runbook_id || "Unknown"}`,
            content: `Service: ${rb.service || "N/A"}\nComponent: ${rb.component || "N/A"}`,
            provenance: {
              source_type: "runbook",
              source_id: rb.runbook_id,
            },
            metadata: {
              service: rb.service,
              component: rb.component,
            },
          })),
        ];
      }

      safeRetrievalData = {
        chunks_used: chunks.length,
        chunk_ids: chunks.map((c: any) => c.chunk_id).filter(Boolean),
        chunk_sources: chunks.map((c: any) => c.doc_title).filter(Boolean),
        chunks: chunks,
        retrieval_method: evidence.retrieval_method || "triage_retrieval",
        retrieval_params: evidence.retrieval_params || {},
      };
      setRetrievalData(safeRetrievalData);

      // Ensure resolution exists: if not stored yet, call resolution API once for this incident
      let resolutionOutput = incident.resolution_output;
      const resolvedIncidentId = incident.incident_id || incident.id;

      if (!resolutionOutput && resolvedIncidentId) {
        try {
          const res = await postResolution(resolvedIncidentId);
          const generated = res.resolution || res;
          resolutionOutput = generated || null;
        } catch (resErr) {
          console.error(
            "Failed to auto-generate resolution for existing incident:",
            resErr,
          );
        }
      }

      // Set resolution data from stored or newly generated output
      if (resolutionOutput) {
        // Normalize resolution data structure to ensure it has all expected fields
        const stepsArray = resolutionOutput.steps || [];
        const recommendations = resolutionOutput.recommendations || [];
        const stepsAsStrings =
          stepsArray.length > 0 && typeof stepsArray[0] === "object"
            ? stepsArray.map((step: any) => step.action || step.title || "")
            : recommendations.length > 0
              ? recommendations.map((rec: any) => rec.action || rec.step || "")
              : resolutionOutput.resolution_steps || [];

        safeResolutionData = {
          ...resolutionOutput,
          steps: stepsArray,
          recommendations: recommendations,
          resolution_steps: stepsAsStrings,
          overall_confidence:
            resolutionOutput.overall_confidence || resolutionOutput.confidence || null,
        };
      }
      // Always set resolution data (even if empty) to prevent rendering issues
      setResolutionData(safeResolutionData);

      // Load feedback history (thumbs up/down, notes)
      try {
        const feedbackResponse = await getIncidentFeedback(
          incident.incident_id || incident.id,
        );
        // API returns { incident_id, feedback: [...] }
        const feedbackList = feedbackResponse.feedback || [];
        setFeedbackHistory(feedbackList);
        
        // Parse feedback history to populate rating state
        // Extract triage ratings (severity, impact, urgency)
        const parsedTriageRatings: {
          severity?: string | null;
          impact?: string | null;
          urgency?: string | null;
        } = {};
        
        // Extract resolution ratings (by step index)
        const parsedResolutionRatings: Record<number, string | null> = {};
        
        feedbackList.forEach((fb: any) => {
          if (!fb.rating || !fb.notes) return;
          
          // Parse notes to extract field/step identifier
          // Format: "Rating for {field}: {rating}" or "Rating for resolution step {index}: {rating}"
          const notesMatch = fb.notes.match(/Rating for (.+?):/);
          if (!notesMatch) return;
          
          const identifier = notesMatch[1].trim();
          
          if (fb.feedback_type === "triage") {
            // Check if it's a triage field (severity, impact, urgency)
            if (identifier === "severity" || identifier === "impact" || identifier === "urgency") {
              parsedTriageRatings[identifier as "severity" | "impact" | "urgency"] = fb.rating;
            }
          } else if (fb.feedback_type === "resolution") {
            // Extract step index from "resolution step X"
            // Notes format: "Rating for resolution step X: rating"
            // Where X = originalIndex + 1 (1-based display number)
            const stepMatch = identifier.match(/resolution step (\d+)/i);
            if (stepMatch) {
              // Step numbers in notes are 1-based (originalIndex + 1), convert to 0-based index
              const stepNumber = parseInt(stepMatch[1], 10);
              const originalIndex = stepNumber - 1; // Convert to 0-based original index
              parsedResolutionRatings[originalIndex] = fb.rating;
            }
          }
        });
        
        // Set the parsed ratings into state
        if (Object.keys(parsedTriageRatings).length > 0) {
          setTriageRatings(parsedTriageRatings);
        }
        if (Object.keys(parsedResolutionRatings).length > 0) {
          setResolutionRatings(parsedResolutionRatings);
        }
      } catch (feedbackErr) {
        console.warn(
          "Failed to load feedback history for incident:",
          feedbackErr,
        );
        setFeedbackHistory([]);
      }

      // When loading an existing incident, ALWAYS go to complete summary page
      // This shows all available data in one place, regardless of resolution status
      // The CompleteSummary component handles missing data gracefully
      setCurrentStep("complete");
      setCurrentView("workflow");

      setShowSearch(false);
    } catch (err: any) {
      console.error("❌ Failed to load incident:", err);
      const errorMessage =
        err.response?.data?.detail || err.message || "Failed to load incident";
      setError(errorMessage);
      
      // Even on error, set safe defaults to prevent empty page
      // This allows the user to see the error message and navigate back
      setAlertData(safeAlertData);
      setTriageData(safeTriageData);
      setPolicyData(safePolicyData);
      setRetrievalData(safeRetrievalData);
      setResolutionData(safeResolutionData);
      setFeedbackHistory([]);
      
      // Don't navigate to complete page if there was an error
      // Stay on current view or go back to form
      if (currentView === "incidents") {
        // If we're in incidents view, stay there
        setCurrentView("incidents");
      } else {
        // Otherwise, go back to form
        setCurrentStep("form");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleLoadIncident = async () => {
    await loadIncidentById(searchIncidentId);
  };

  const handleSelectIncidentFromList = async (incidentId: string) => {
    await loadIncidentById(incidentId);
  };

  const loadIncidents = async (page: number = 1, searchTerm: string = "") => {
    setIsLoadingIncidents(true);
    setIncidentsError("");
    try {
      const offset = (page - 1) * incidentsLimit;
      const response = await listIncidents(incidentsLimit, offset, searchTerm || null);
      setIncidents(response.incidents || []);
      setIncidentsTotal(response.total || 0);
      setIncidentsPage(page);
    } catch (err: any) {
      console.error("Failed to load incidents list", err);
      const message =
        err.response?.data?.detail ||
        err.message ||
        "Failed to load incidents list";
      setIncidentsError(message);
    } finally {
      setIsLoadingIncidents(false);
    }
  };

  const handleOpenIncidentsView = async () => {
    setCurrentView("incidents");
    if (incidents.length === 0 && !isLoadingIncidents) {
      await loadIncidents(1, incidentsSearch);
    }
  };

  const handleIncidentsSearch = async () => {
    await loadIncidents(1, incidentsSearch);
  };

  const handleIncidentsPageChange = async (newPage: number) => {
    await loadIncidents(newPage, incidentsSearch);
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
                  <h1 className="text-lg font-semibold text-white">
                    NOC Agent
                  </h1>
                  <p className="text-xs text-white/70">Incident Management</p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Incidents List */}
              <Button
                size="sm"
                variant="outline"
                onClick={handleOpenIncidentsView}
                className="bg-white/5 text-white border-white/20 hover:bg-white/15 hover:text-white h-8"
              >
                <List className="w-4 h-4 mr-2" />
                Incidents
              </Button>

              {/* Search/Load Existing Ticket */}
              {showSearch ? (
                <div className="flex items-center gap-2 bg-white/10 rounded px-3 py-1.5">
                  <Search className="w-4 h-4 text-white/70" />
                  <Input
                    value={searchIncidentId}
                    onChange={(e) => setSearchIncidentId(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLoadIncident()}
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
      {currentView === "workflow" && currentStep !== "form" && (
        <div className="relative z-10 bg-secondary border-b border-border">
          <div className="container mx-auto px-4 py-3">
            <div className="flex items-center gap-2">
              <StepBadge label="Triage" status={getStepStatus("triage")} />
              <StepBadge
                label="Policy & Approval"
                status={getStepStatus("policy")}
              />
              <StepBadge
                label="Resolution"
                status={getStepStatus("resolution")}
              />
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 py-8">
        <div className="max-w-[98%] mx-auto">
          {currentView === "incidents" ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    Incident History
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Browse existing incidents and open their full summary. Use the{" "}
                    <span className="font-semibold">New Ticket</span> button in the
                    header to triage a new alert.
                  </p>
                </div>
              </div>

              {/* Search Bar */}
              <div className="flex items-center gap-2">
                <div className="flex-1 flex items-center gap-2 border rounded-lg px-3 py-2 bg-card">
                  <Search className="w-4 h-4 text-muted-foreground" />
                  <Input
                    value={incidentsSearch}
                    onChange={(e) => setIncidentsSearch(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleIncidentsSearch()}
                    placeholder="Search by Incident ID or Alert ID..."
                    className="border-0 focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent"
                  />
                  <Button
                    size="sm"
                    onClick={handleIncidentsSearch}
                    disabled={isLoadingIncidents}
                    className="h-8"
                  >
                    Search
                  </Button>
                  {incidentsSearch && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setIncidentsSearch("");
                        loadIncidents(1, "");
                      }}
                      className="h-8"
                    >
                      Clear
                    </Button>
                  )}
                </div>
              </div>

              {incidentsError && (
                <div className="mb-4 p-4 bg-destructive/10 border-l-4 border-destructive rounded text-destructive animate-fade-in">
                  <div className="font-semibold mb-1">Failed to load incidents</div>
                  <div className="text-sm">{incidentsError}</div>
                </div>
              )}

              {isLoadingIncidents ? (
                <div className="py-10 text-center text-muted-foreground">
                  Loading incidents...
                </div>
              ) : incidents.length === 0 ? (
                <div className="py-10 text-center text-muted-foreground border border-dashed rounded-lg">
                  {incidentsSearch
                    ? "No incidents found matching your search."
                    : "No incidents found yet. Create a new ticket to get started."}
                </div>
              ) : (
                <>
                  <div className="border rounded-lg overflow-hidden bg-card">
                    <div className="grid grid-cols-9 gap-2 px-4 py-2 text-xs font-medium text-muted-foreground border-b bg-muted/50">
                      <div>Incident ID</div>
                      <div>Alert ID</div>
                      <div>Source</div>
                      <div>Policy Band</div>
                      <div>Triage Time</div>
                      <div>Triage Confidence</div>
                      <div>Resolution Time</div>
                      <div>Resolution Confidence</div>
                      <div>Created</div>
                    </div>
                    <div className="divide-y">
                      {incidents.map((incident) => {
                        const formatTime = (seconds: number | null | undefined) => {
                          if (seconds == null) return "—";
                          if (seconds < 60) return `${Math.round(seconds)}s`;
                          if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
                          return `${Math.round(seconds / 3600)}h`;
                        };
                        const formatConfidence = (conf: number | null | undefined) => {
                          if (conf == null) return "—";
                          return `${(conf * 100).toFixed(0)}%`;
                        };
                        return (
                          <button
                            key={incident.id}
                            type="button"
                            onClick={() =>
                              handleSelectIncidentFromList(
                                incident.id || incident.incident_id,
                              )
                            }
                            className="w-full text-left px-4 py-3 text-sm hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary flex items-center gap-2"
                          >
                            <div className="grid grid-cols-9 gap-2 w-full">
                              <div className="font-mono text-xs truncate">
                                {incident.id || incident.incident_id}
                              </div>
                              <div className="truncate">
                                {incident.alert_id || "—"}
                              </div>
                              <div className="truncate">
                                {incident.source || "—"}
                              </div>
                              <div className="truncate uppercase text-xs">
                                {incident.policy_band || "—"}
                              </div>
                              <div className="truncate text-xs">
                                {formatTime(incident.triage_time_secs)}
                              </div>
                              <div className="truncate text-xs">
                                {formatConfidence(incident.triage_confidence)}
                              </div>
                              <div className="truncate text-xs">
                                {formatTime(incident.resolution_time_secs)}
                              </div>
                              <div className="truncate text-xs">
                                {formatConfidence(incident.resolution_confidence)}
                              </div>
                              <div className="truncate text-xs">
                                {incident.created_at
                                  ? new Date(incident.created_at).toLocaleString()
                                  : "—"}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Pagination */}
                  {incidentsTotal > incidentsLimit && (
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-muted-foreground">
                        Showing {(incidentsPage - 1) * incidentsLimit + 1} to{" "}
                        {Math.min(incidentsPage * incidentsLimit, incidentsTotal)} of{" "}
                        {incidentsTotal} incidents
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleIncidentsPageChange(incidentsPage - 1)}
                          disabled={incidentsPage <= 1 || isLoadingIncidents}
                        >
                          Previous
                        </Button>
                        <div className="text-sm text-muted-foreground">
                          Page {incidentsPage} of{" "}
                          {Math.ceil(incidentsTotal / incidentsLimit)}
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleIncidentsPageChange(incidentsPage + 1)}
                          disabled={
                            incidentsPage >= Math.ceil(incidentsTotal / incidentsLimit) ||
                            isLoadingIncidents
                          }
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <>
          {/* Error Display (Global) */}
          {error && !isLoading && (
            <div className="mb-4 p-4 bg-destructive/10 border-l-4 border-destructive rounded text-destructive animate-fade-in">
              <div className="flex items-start gap-2">
                <svg
                  className="w-5 h-5 flex-shrink-0 mt-0.5"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <div>
                  <div className="font-semibold">Error</div>
                  <div className="text-sm mt-1">{error}</div>
                </div>
              </div>
            </div>
          )}

          {currentStep === "form" && (
            <TicketForm
              onSubmit={handleSubmit}
              isLoading={isLoading}
              error={error}
            />
          )}

          {currentStep === "triage" &&
            triageData &&
            policyData &&
            retrievalData && (
              <TriageView
                triageData={triageData}
                policyData={policyData}
                retrievalData={retrievalData}
                onNext={handleNextToPolicy}
                onBack={handleBack}
                    incidentId={incidentId}
                    triageRatings={triageRatings}
                    ratingStatus={ratingStatus.triage}
                    onRatingChange={handleTriageFieldRating}
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
                  incidentId={incidentId}
                  resolutionRatings={resolutionRatings}
                  ratingStatus={ratingStatus.resolution}
                  onRatingChange={handleResolutionStepRating}
            />
          )}

          {currentStep === "complete" && (
            <CompleteSummary
              alertData={alertData || {}}
              triageData={triageData || {}}
              policyData={
                policyData || { policy_band: null, policy_decision: {} }
              }
              retrievalData={
                retrievalData || {
                  chunks_used: 0,
                  chunk_sources: [],
                  chunks: [],
                }
              }
              resolutionData={resolutionData || { resolution_steps: [] }}
                  feedbackHistory={feedbackHistory || []}
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
            </>
          )}
        </div>
      </main>
    </div>
  );
};

// Step Badge Component
const StepBadge = ({
  label,
  status,
}: {
  label: string;
  status: "complete" | "active" | "idle";
}) => {
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
    <div
      className={`px-3 py-1.5 rounded-lg border text-xs font-medium ${getStyles()}`}
    >
      {label}
      {status === "complete" && " ✓"}
    </div>
  );
};

export default Index;
