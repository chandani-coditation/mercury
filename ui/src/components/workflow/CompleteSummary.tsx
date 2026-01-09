import {
  CheckCircle,
  AlertCircle,
  Shield,
  FileText,
  ClipboardCheck,
  Download,
  FileJson,
  ListChecks,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/results/SeverityBadge";
import { EvidenceChunk } from "@/components/results/EvidenceChunk";
import { ExpandableText } from "@/components/ui/ExpandableText";
import { KeyValueDisplay } from "@/components/ui/KeyValueDisplay";
import { cn } from "@/lib/utils";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  downloadHTMLReport,
  downloadJSONReport,
  type ReportData,
} from "@/utils/reportGenerator";

interface CompleteSummaryProps {
  alertData: any;
  triageData: any;
  policyData: any;
  retrievalData: any;
  resolutionData: any;
  feedbackHistory?: any[];
  onNewTicket: () => void;
  onViewTriage?: () => void;
  onViewResolution?: () => void;
}

export const CompleteSummary = ({
  alertData,
  triageData,
  policyData,
  retrievalData,
  resolutionData,
  feedbackHistory = [],
  onNewTicket,
  onViewTriage,
  onViewResolution,
}: CompleteSummaryProps) => {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  // State for collapsible sections in evidence dialog - collapsed by default
  const [isPriorIncidentsExpanded, setIsPriorIncidentsExpanded] = useState(false);
  const [isRunbooksExpanded, setIsRunbooksExpanded] = useState(false);

  const getBandColor = (band: string | null | undefined) => {
    if (!band) {
      return "bg-primary/20 text-primary border-primary/30";
    }
    switch (band.toUpperCase()) {
      case "AUTO":
        return "bg-success/20 text-success border-success/30";
      case "PROPOSE":
        return "bg-warning/20 text-warning border-warning/30";
      case "BLOCK":
        return "bg-destructive/20 text-destructive border-destructive/30";
      default:
        return "bg-primary/20 text-primary border-primary/30";
    }
  };

  const handleDownloadReport = (format: "html" | "json") => {
    const reportData: ReportData = {
      incident_summary: {
        alert_id: alertData.alert_id,
        source: alertData.source,
        timestamp: alertData.ts || new Date().toISOString(),
        title: alertData.title,
        description: alertData.description,
      },
      triage_analysis: {
        severity: triageData.severity,
        category: triageData.category,
        routing: triageData.routing,
        impact: triageData.impact,
        urgency: triageData.urgency,
        affected_services: triageData.affected_services,
        confidence: triageData.confidence,
        summary: triageData.summary,
        likely_cause: triageData.likely_cause,
        incident_signature: triageData.incident_signature,
        matched_evidence: triageData.matched_evidence,
      },
      policy_decision: {
        policy_band: policyData.policy_band,
        requires_approval:
          policyData.policy_decision?.requires_approval || false,
        can_auto_apply: policyData.policy_decision?.can_auto_apply || false,
        policy_reason: policyData.policy_decision?.policy_reason || "",
      },
      evidence: {
        chunks_used: retrievalData.chunks_used || 0,
        sources: [...new Set(retrievalData.chunk_sources || [])],
      },
      resolution: {
        recommendations: resolutionData.recommendations || [],
        steps: resolutionData.resolution_steps || resolutionData.steps || [],
        status: "completed",
        overall_confidence:
          resolutionData.overall_confidence || resolutionData.confidence,
        reasoning: resolutionData.reasoning,
      },
    };

    if (format === "html") {
      downloadHTMLReport(reportData);
    } else {
      downloadJSONReport(reportData);
    }

    setDownloadMenuOpen(false);
  };

  const hasResolution =
    (resolutionData?.recommendations &&
      resolutionData.recommendations.length > 0) ||
    (resolutionData?.resolution_steps &&
      resolutionData.resolution_steps.length > 0) ||
    (resolutionData?.steps && resolutionData.steps.length > 0);

  return (
    <div className="space-y-2.5">
      {/* Compact Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {hasResolution ? (
            <>
              <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4 text-success" />
                Incident Resolution Complete
              </h2>
            </>
          ) : (
            <>
              <div className="w-1.5 h-1.5 rounded-full bg-warning animate-pulse" />
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-warning" />
                Incident Summary
              </h2>
            </>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {onViewTriage && (
            <Button
              variant="outline"
              size="sm"
              onClick={onViewTriage}
              className="bg-secondary hover:bg-secondary/80 text-xs py-1.5 px-3"
            >
              View Triage
            </Button>
          )}
          {onViewResolution && hasResolution && (
            <Button
              variant="outline"
              size="sm"
              onClick={onViewResolution}
              className="bg-secondary hover:bg-secondary/80 text-xs py-1.5 px-3"
            >
              View Resolution
            </Button>
          )}
          <Button
            size="sm"
            onClick={onNewTicket}
            className="bg-primary hover:bg-primary/90 text-primary-foreground text-xs py-1.5 px-3"
          >
            Triage New Ticket
          </Button>
        </div>
      </div>

      {/* Complete Summary Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        {/* Original Alert Details - Compact */}
        <Card className="p-2.5 glass-card">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">Original Alert</h3>
            </div>
            {/* Key fields in compact grid */}
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              <div>
                <span className="text-muted-foreground text-xs">Alert ID:</span>
                <div className="font-mono text-foreground text-xs mt-0.5">
                  <ExpandableText text={alertData.alert_id} charLimit={20} />
                </div>
              </div>
              <div>
                <span className="text-muted-foreground text-xs">Source:</span>
                <div className="text-foreground text-xs mt-0.5">
                  {alertData.source}
                </div>
              </div>
              <div className="col-span-2">
                <span className="text-muted-foreground text-xs">Service:</span>
                <div className="text-foreground text-xs mt-0.5">
                  {alertData.labels?.service || alertData.service || "N/A"}
                </div>
              </div>
            </div>
            {/* Title and Description - Compact */}
            {alertData.title && (
              <div className="pt-1 border-t border-border/30">
                <span className="text-muted-foreground text-xs">Title:</span>
                <div className="text-foreground text-xs mt-0.5 leading-relaxed">
                  <ExpandableText text={alertData.title} lineLimit={2} />
                </div>
              </div>
            )}
            {alertData.description && (
              <div className="pt-1">
                <span className="text-muted-foreground text-xs">Description:</span>
                <div className="text-foreground text-xs mt-0.5 leading-relaxed">
                  <ExpandableText text={alertData.description} lineLimit={4} />
                </div>
              </div>
            )}
          </div>
        </Card>

        {/* Triage Results Summary - Compact and Reorganized */}
        <Card className="p-2.5 glass-card">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <FileText className="w-3.5 h-3.5 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">Triage Analysis</h3>
            </div>
            
            {/* TOP PRIORITY: Severity, Routing, Affected Services - Consistent Format */}
            <div className="grid grid-cols-3 gap-1.5">
              {/* Severity - Using KeyValueDisplay */}
              {triageData.severity ? (
                <KeyValueDisplay
                  label="Severity"
                  value={
                    <div className="flex items-center gap-1 flex-wrap">
                      <SeverityBadge severity={triageData.severity} />
                      {triageData.category && (
                        <span className="px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-semibold font-sans">
                          {triageData.category}
                        </span>
                      )}
                    </div>
                  }
                  valueType="severity"
                />
              ) : (
                <KeyValueDisplay label="Severity" value="N/A" />
              )}

              {/* Routing - Using KeyValueDisplay */}
              <KeyValueDisplay
                label="Routing"
                value={triageData.routing || "N/A"}
                valueType="routing"
              />

              {/* Affected Services - Using KeyValueDisplay */}
              <KeyValueDisplay
                label="Affected Services"
                value={
                  triageData.affected_services && triageData.affected_services.length > 0
                    ? triageData.affected_services.join(", ")
                    : "N/A"
                }
              />
            </div>

            {/* SECOND ROW: Impact, Urgency, Confidence - Consistent Format */}
            <div className="grid grid-cols-3 gap-1.5">
              {/* Impact - Using KeyValueDisplay */}
              <KeyValueDisplay
                label="Impact"
                value={triageData.impact || "N/A"}
                valueType="impact"
              />

              {/* Urgency - Using KeyValueDisplay */}
              <KeyValueDisplay
                label="Urgency"
                value={triageData.urgency || "N/A"}
                valueType="urgency"
              />

              {/* AI Confidence - Using KeyValueDisplay */}
              <KeyValueDisplay
                label="AI Confidence"
                value={
                  triageData.confidence !== undefined && triageData.confidence !== null
                    ? triageData.confidence
                    : 0
                }
                valueType="confidence"
              />
            </div>

            {/* Incident Signature - Standardized Format */}
            {triageData.incident_signature && (
              <div className="glass-card p-1.5 space-y-0.5 pt-1 border-t border-border/30">
                <span className="text-xs font-semibold text-muted-foreground">Incident Signature</span>
                {triageData.incident_signature.failure_type || triageData.incident_signature.error_class ? (
                  <div className="space-y-0.5">
                    {triageData.incident_signature.failure_type && (
                      <div className="text-xs">
                        <span className="text-muted-foreground">Failure: </span>
                        <span className="font-semibold text-primary font-mono">
                          {triageData.incident_signature.failure_type}
                        </span>
                      </div>
                    )}
                    {triageData.incident_signature.error_class && (
                      <div className="text-xs">
                        <span className="text-muted-foreground">Error: </span>
                        <span className="font-semibold text-primary font-mono">
                          {triageData.incident_signature.error_class}
                        </span>
                      </div>
                    )}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">N/A</span>
                )}
              </div>
            )}
          </div>
        </Card>

        {/* Policy Decision Summary - Compact */}
        <Card className="p-2.5 glass-card">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">Policy Decision</h3>
            </div>
            <div className="space-y-1">
              <div>
                <span className="text-xs text-muted-foreground mb-0.5 block">
                  Policy Band
                </span>
                <div
                  className={cn(
                    "inline-flex items-center px-2 py-1 rounded-lg border text-xs font-bold font-mono",
                    getBandColor(policyData.policy_band),
                  )}
                >
                  {policyData.policy_band || "N/A"}
                </div>
              </div>
              <div className="flex items-center justify-between p-1.5 bg-secondary/30 rounded text-xs">
                <span className="text-muted-foreground">Requires Approval</span>
                <span
                  className={
                    policyData.policy_decision?.requires_approval
                      ? "text-warning font-semibold"
                      : "text-success font-semibold"
                  }
                >
                  {policyData.policy_decision?.requires_approval ? "Yes" : "No"}
                </span>
              </div>
              <div className="flex items-center justify-between p-1.5 bg-secondary/30 rounded text-xs">
                <span className="text-muted-foreground">Can Auto-Apply</span>
                <span
                  className={
                    policyData.policy_decision?.can_auto_apply
                      ? "text-success font-semibold"
                      : "text-muted-foreground"
                  }
                >
                  {policyData.policy_decision?.can_auto_apply ? "Yes" : "No"}
                </span>
              </div>
            </div>
            {policyData.policy_decision?.policy_reason && (
              <div className="text-xs text-muted-foreground pt-1 border-t border-border/50 leading-relaxed">
                <strong className="text-foreground">Reason:</strong>{" "}
                <ExpandableText
                  text={policyData.policy_decision.policy_reason}
                  lineLimit={2}
                  className="inline"
                />
              </div>
            )}
          </div>
        </Card>

        {/* Evidence Summary - Compact */}
        <Card className="p-2.5 glass-card">
          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <ClipboardCheck className="w-3.5 h-3.5 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">
                Knowledge Base Evidence
              </h3>
            </div>
            <div className="space-y-1.5">
              <div className="flex gap-2">
                <Dialog open={evidenceOpen} onOpenChange={setEvidenceOpen}>
                  <DialogTrigger asChild>
                    <button className="flex-1 p-2 bg-primary/10 border border-primary/20 rounded-lg text-center hover:bg-primary/20 transition-colors cursor-pointer group">
                      <div className="text-lg font-bold text-primary group-hover:scale-110 transition-transform">
                        {retrievalData.chunks_used || 0}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5 group-hover:text-primary transition-colors">
                        Chunks Used
                      </div>
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-7xl max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <ClipboardCheck className="w-5 h-5 text-primary" />
                        Knowledge Base Evidence
                      </DialogTitle>
                      <DialogDescription>
                        Detailed evidence chunks retrieved from the knowledge
                        base to inform the resolution
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 mt-3">
                      {/* Evidence Stats */}
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-2.5 bg-primary/10 border border-primary/20 rounded-lg">
                          <div className="text-xl font-bold text-primary">
                            {retrievalData.chunks_used || 0}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            Chunks Used
                          </div>
                        </div>
                        <div className="p-2.5 bg-primary/10 border border-primary/20 rounded-lg">
                          <div className="text-xl font-bold text-primary">
                            {new Set(retrievalData.chunk_sources || []).size}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            Unique Sources
                          </div>
                        </div>
                      </div>

                      {/* Sources */}
                      <div>
                        <div className="text-xs font-semibold text-foreground mb-2">
                          Sources:
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {[...new Set(retrievalData.chunk_sources || [])].map(
                            (source: string, idx: number) => (
                              <span
                                key={idx}
                                className="px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
                              >
                                {source}
                              </span>
                            ),
                          )}
                        </div>
                      </div>

                      {/* Evidence Chunks - Separated by Type */}
                      {retrievalData.chunks &&
                        retrievalData.chunks.length > 0 && (
                          <div>
                            <div className="text-xs font-semibold text-foreground mb-4">
                              Evidence Details:
                            </div>
                            {(() => {
                              const allPriorIncidents = retrievalData.chunks.filter(
                                (chunk: any) =>
                                  chunk.provenance?.source_type ===
                                    "incident_signature" ||
                                  chunk.metadata?.doc_type ===
                                    "incident_signature",
                              );
                              const allRunbooks = retrievalData.chunks.filter(
                                (chunk: any) =>
                                  chunk.provenance?.source_type === "runbook" ||
                                  chunk.provenance?.source_type ===
                                    "runbook_step" ||
                                  chunk.metadata?.doc_type === "runbook",
                              );
                              // Limit to top 5 for each category
                              const priorIncidents = allPriorIncidents.slice(0, 5);
                              const runbooks = allRunbooks.slice(0, 5);

                              return (
                                <div className="space-y-3">
                                  {/* Prior Incidents Section */}
                                  {priorIncidents.length > 0 && (
                                    <div className="space-y-2">
                                      <div
                                        className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2 cursor-pointer hover:text-foreground transition-colors"
                                        onClick={() => setIsPriorIncidentsExpanded(!isPriorIncidentsExpanded)}
                                      >
                                        {isPriorIncidentsExpanded ? (
                                          <ChevronDown className="w-4 h-4 text-primary" />
                                        ) : (
                                          <ChevronRight className="w-4 h-4 text-primary" />
                                        )}
                                        <span className="w-1 h-4 bg-primary rounded-full" />
                                        Prior Incidents ({priorIncidents.length}
                                        {allPriorIncidents.length > 5
                                          ? ` of ${allPriorIncidents.length}`
                                          : ""}
                                        )
                                      </div>
                                      {isPriorIncidentsExpanded && (
                                        <div className="space-y-3">
                                          {priorIncidents.map(
                                            (chunk: any, index: number) => (
                                              <EvidenceChunk
                                                key={chunk.chunk_id || index}
                                                chunk={chunk}
                                                index={index}
                                              />
                                            ),
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  {/* Runbooks Section */}
                                  {runbooks.length > 0 && (
                                    <div className="space-y-3">
                                      <div
                                        className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2 cursor-pointer hover:text-foreground transition-colors"
                                        onClick={() => setIsRunbooksExpanded(!isRunbooksExpanded)}
                                      >
                                        {isRunbooksExpanded ? (
                                          <ChevronDown className="w-4 h-4 text-primary" />
                                        ) : (
                                          <ChevronRight className="w-4 h-4 text-primary" />
                                        )}
                                        <span className="w-1 h-4 bg-primary rounded-full" />
                                        Runbooks ({runbooks.length}
                                        {allRunbooks.length > 5
                                          ? ` of ${allRunbooks.length}`
                                          : ""}
                                        )
                                      </div>
                                      {isRunbooksExpanded && (
                                        <div className="space-y-3">
                                          {runbooks.map(
                                            (chunk: any, index: number) => (
                                              <EvidenceChunk
                                                key={chunk.chunk_id || index}
                                                chunk={chunk}
                                                index={
                                                  priorIncidents.length + index
                                                }
                                              />
                                            ),
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })()}
                          </div>
                        )}

                      {(!retrievalData.chunks ||
                        retrievalData.chunks.length === 0) && (
                        <div className="text-center py-4 text-muted-foreground">
                          <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
                          <p>No detailed chunk content available</p>
                          <p className="text-xs mt-1">
                            Evidence was used but detailed content was not
                            stored
                          </p>
                        </div>
                      )}
                    </div>
                  </DialogContent>
                </Dialog>

                <div className="flex-1 p-2 bg-primary/10 border border-primary/20 rounded-lg text-center">
                  <div className="text-lg font-bold text-primary">
                    {new Set(retrievalData.chunk_sources || []).size}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    Unique Sources
                  </div>
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">
                  Sources:
                </div>
                <div className="flex flex-wrap gap-2">
                  {[...new Set(retrievalData.chunk_sources || [])].map(
                    (source: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-2 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
                      >
                        {source}
                      </span>
                    ),
                  )}
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Resolution Steps - Full Width */}
      {resolutionData &&
      resolutionData.resolution_steps &&
      resolutionData.resolution_steps.length > 0 ? (
        <Card className="p-4 glass-card glow-border">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-success" />
              <h3 className="text-xs font-semibold text-foreground">
                Resolution Steps Executed
              </h3>
            </div>
            <div className="bg-background/50 border border-border/30 rounded-lg p-4">
              <div className="space-y-2">
                {resolutionData.resolution_steps.map(
                  (step: string, index: number) => (
                    <div key={index} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-success/20 text-success flex items-center justify-center text-xs font-bold">
                        {index + 1}
                      </span>
                      <span className="text-xs text-foreground leading-relaxed pt-0.5">
                        {step}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </div>
          </div>
        </Card>
      ) : (
        <Card className="p-4 glass-card glow-border">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-warning" />
              <h3 className="text-xs font-semibold text-foreground">
                Resolution Status
              </h3>
            </div>
            <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
              <p className="text-xs text-muted-foreground text-center py-4 leading-relaxed">
                Resolution has not been proposed yet for this incident.
                {policyData?.policy_band && (
                  <span className="block mt-2">
                    Current Policy Band:{" "}
                    <span
                      className={cn(
                        "font-semibold",
                        policyData.policy_band === "AUTO"
                          ? "text-success"
                          : policyData.policy_band === "PROPOSE"
                            ? "text-warning"
                            : policyData.policy_band === "REVIEW"
                              ? "text-warning"
                              : policyData.policy_band === "BLOCK"
                                ? "text-destructive"
                                : "text-foreground",
                      )}
                    >
                      {policyData.policy_band || "N/A"}
                    </span>
                    {policyData.policy_band === "AUTO" && (
                      <span className="block mt-1 text-xs">
                        Resolution can be auto-generated when approved.
                      </span>
                    )}
                    {(policyData.policy_band === "PROPOSE" ||
                      policyData.policy_band === "REVIEW") && (
                      <span className="block mt-1 text-xs">
                        Approval required before resolution can be generated.
                      </span>
                    )}
                    {policyData.policy_band === "BLOCK" && (
                      <span className="block mt-1 text-xs">
                        Resolution is currently blocked.
                      </span>
                    )}
                  </span>
                )}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Feedback History */}
      {feedbackHistory && feedbackHistory.length > 0 && (
        <Card className="p-4 glass-card glow-border">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <ListChecks className="w-5 h-5 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">Feedback History</h3>
            </div>
            <div className="space-y-2">
              {feedbackHistory.map((fb, index) => (
                <div
                  key={fb.id || index}
                  className="flex items-center justify-between bg-background/50 border border-border/30 rounded-lg px-3 py-2"
                >
                  <div className="flex flex-col">
                    <span className="text-xs font-semibold text-foreground">
                      {fb.feedback_type === "triage" ? "Triage" : "Resolution"}
                    </span>
                    {fb.notes && (
                      <span className="text-xs text-muted-foreground">
                        {fb.notes}
                      </span>
                    )}
                    {fb.created_at && (
                      <span className="text-[11px] text-muted-foreground mt-0.5">
                        {new Date(fb.created_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {fb.rating === "thumbs_up" && <span>👍</span>}
                    {fb.rating === "thumbs_down" && <span>👎</span>}
                    {!fb.rating && (
                      <span className="text-xs text-muted-foreground">
                        No rating
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Action Summary */}
      <Card
                    className={`p-4 ${hasResolution ? "bg-success/10 border-success/30" : "bg-warning/10 border-warning/30"}`}
      >
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-foreground mb-1">
              {hasResolution
                ? "Incident Resolved Successfully"
                : "Incident Summary"}
            </h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {hasResolution
                ? "All resolution steps have been executed. The incident has been marked as complete."
                : "This incident has been triaged and analyzed. Resolution has not been generated yet."}
            </p>
          </div>
          <div className="flex gap-3">
            {/* Download Report Dropdown */}
            <Dialog open={downloadMenuOpen} onOpenChange={setDownloadMenuOpen}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="bg-secondary hover:bg-secondary/80"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Download Report
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <Download className="w-5 h-5 text-primary" />
                    Download Incident Report
                  </DialogTitle>
                  <DialogDescription>
                    Choose your preferred report format
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-3 py-4">
                  <Button
                    onClick={() => handleDownloadReport("html")}
                    className="w-full h-auto py-3 px-4 bg-primary hover:bg-primary/90 text-left justify-start gap-3"
                  >
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-white/20">
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-semibold text-foreground">HTML Report</div>
                      <div className="text-xs text-muted-foreground">
                        Beautiful, printable report with all details
                      </div>
                    </div>
                  </Button>

                  <Button
                    onClick={() => handleDownloadReport("json")}
                    variant="outline"
                    className="w-full h-auto py-3 px-4 text-left justify-start gap-3 hover:bg-secondary/50"
                  >
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-secondary">
                      <FileJson className="w-5 h-5 text-foreground" />
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-semibold text-foreground">JSON Data</div>
                      <div className="text-xs text-muted-foreground">
                        Raw data for API integration
                      </div>
                    </div>
                  </Button>
                </div>
              </DialogContent>
            </Dialog>

            <Button
              onClick={onNewTicket}
              className="bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              Triage New Ticket
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};
