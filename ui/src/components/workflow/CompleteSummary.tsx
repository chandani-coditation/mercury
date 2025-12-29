import { CheckCircle, AlertCircle, Shield, FileText, ClipboardCheck, Download, FileJson } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/results/SeverityBadge";
import { EvidenceChunk } from "@/components/results/EvidenceChunk";
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
import { downloadHTMLReport, downloadJSONReport, type ReportData } from "@/utils/reportGenerator";

interface CompleteSummaryProps {
  alertData: any;
  triageData: any;
  policyData: any;
  retrievalData: any;
  resolutionData: any;
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
  onNewTicket,
  onViewTriage,
  onViewResolution,
}: CompleteSummaryProps) => {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  
  const getBandColor = (band: string) => {
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

  const handleDownloadReport = (format: 'html' | 'json') => {
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
        affected_services: triageData.affected_services,
        confidence: triageData.confidence,
        summary: triageData.summary,
        likely_cause: triageData.likely_cause,
      },
      policy_decision: {
        policy_band: policyData.policy_band,
        requires_approval: policyData.policy_decision?.requires_approval || false,
        can_auto_apply: policyData.policy_decision?.can_auto_apply || false,
        policy_reason: policyData.policy_decision?.policy_reason || "",
      },
      evidence: {
        chunks_used: retrievalData.chunks_used || 0,
        sources: [...new Set(retrievalData.chunk_sources || [])],
      },
      resolution: {
        steps: resolutionData.resolution_steps || [],
        status: "completed",
        risk_level: resolutionData.risk_level,
        estimated_time: resolutionData.estimated_time_minutes || resolutionData.estimated_duration,
        reasoning: resolutionData.reasoning,
      },
    };

    if (format === 'html') {
      downloadHTMLReport(reportData);
    } else {
      downloadJSONReport(reportData);
    }
    
    setDownloadMenuOpen(false);
  };

  const hasResolution = resolutionData?.resolution_steps && resolutionData.resolution_steps.length > 0;

  return (
    <div className="space-y-6">
      {/* Success Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {hasResolution ? (
            <>
              <div className="w-3 h-3 rounded-full bg-success animate-pulse" />
              <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                <CheckCircle className="w-6 h-6 text-success" />
                Incident Resolution Complete
              </h2>
            </>
          ) : (
            <>
              <div className="w-3 h-3 rounded-full bg-warning animate-pulse" />
              <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
                <AlertCircle className="w-6 h-6 text-warning" />
                Incident Summary
              </h2>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {onViewTriage && (
            <Button
              variant="outline"
              onClick={onViewTriage}
              className="bg-secondary hover:bg-secondary/80"
            >
              View Triage
            </Button>
          )}
          {onViewResolution && hasResolution && (
            <Button
              variant="outline"
              onClick={onViewResolution}
              className="bg-secondary hover:bg-secondary/80"
            >
              View Resolution
            </Button>
          )}
          <Button
            onClick={onNewTicket}
            className="bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            Triage New Ticket
          </Button>
        </div>
      </div>

      {/* Complete Summary Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Original Alert Details */}
        <Card className="p-6 glass-card">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">Original Alert</h3>
            </div>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-muted-foreground">Alert ID:</span>
                <span className="ml-2 font-mono text-foreground">{alertData.alert_id}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Source:</span>
                <span className="ml-2 text-foreground">{alertData.source}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Service:</span>
                <span className="ml-2 text-foreground">{alertData.labels?.service || alertData.service || "N/A"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Title:</span>
                <div className="mt-1 text-foreground">{alertData.title}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Description:</span>
                <div className="mt-1 text-foreground leading-relaxed">{alertData.description}</div>
              </div>
            </div>
          </div>
        </Card>

        {/* Triage Results Summary */}
        <Card className="p-6 glass-card">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">Triage Analysis</h3>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <SeverityBadge severity={triageData.severity} />
                <span className="px-3 py-1 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-medium">
                  {triageData.category}
                </span>
              </div>
              <div className="text-sm">
                <span className="text-muted-foreground">Routing:</span>
                <span className="ml-2 font-mono text-primary font-semibold">{triageData.routing}</span>
              </div>
              <div className="text-sm">
                <span className="text-muted-foreground">Affected Services:</span>
                <div className="mt-1 flex flex-wrap gap-2">
                  {(triageData.affected_services || []).map((service: string, idx: number) => (
                    <span key={idx} className="px-2 py-1 bg-secondary/50 border border-border/50 rounded text-xs">
                      {service}
                    </span>
                  ))}
                </div>
              </div>
              <div className="text-sm">
                <span className="text-muted-foreground">AI Confidence:</span>
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-success rounded-full transition-all duration-500"
                      style={{ width: `${triageData.confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono font-semibold">{Math.round(triageData.confidence * 100)}%</span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Policy Decision Summary */}
        <Card className="p-6 glass-card">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">Policy Decision</h3>
            </div>
            <div className="space-y-3">
              <div>
                <span className="text-xs text-muted-foreground mb-2 block">Policy Band</span>
                <div
                  className={cn(
                    "inline-flex items-center px-4 py-2 rounded-lg border text-sm font-bold font-mono",
                    getBandColor(policyData.policy_band)
                  )}
                >
                  {policyData.policy_band}
                </div>
              </div>
              <div className="text-sm space-y-2">
                <div className="flex items-center justify-between p-2 bg-secondary/30 rounded">
                  <span className="text-muted-foreground">Requires Approval</span>
                  <span className={policyData.policy_decision?.requires_approval ? "text-warning" : "text-success"}>
                    {policyData.policy_decision?.requires_approval ? "Yes" : "No"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-2 bg-secondary/30 rounded">
                  <span className="text-muted-foreground">Can Auto-Apply</span>
                  <span className={policyData.policy_decision?.can_auto_apply ? "text-success" : "text-muted-foreground"}>
                    {policyData.policy_decision?.can_auto_apply ? "Yes" : "No"}
                  </span>
                </div>
              </div>
              {policyData.policy_decision?.policy_reason && (
                <div className="text-xs text-muted-foreground pt-2 border-t border-border/50">
                  <strong className="text-foreground">Reason:</strong> {policyData.policy_decision.policy_reason}
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Evidence Summary */}
        <Card className="p-6 glass-card">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <ClipboardCheck className="w-5 h-5 text-primary" />
              <h3 className="font-semibold text-foreground">Knowledge Base Evidence</h3>
            </div>
            <div className="space-y-3">
              <div className="flex gap-4">
                <Dialog open={evidenceOpen} onOpenChange={setEvidenceOpen}>
                  <DialogTrigger asChild>
                    <button className="flex-1 p-3 bg-primary/10 border border-primary/20 rounded-lg text-center hover:bg-primary/20 transition-colors cursor-pointer group">
                      <div className="text-2xl font-bold text-primary group-hover:scale-110 transition-transform">
                        {retrievalData.chunks_used || 0}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 group-hover:text-primary transition-colors">
                        Chunks Used (Click to view)
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
                        Detailed evidence chunks retrieved from the knowledge base to inform the resolution
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 mt-4">
                      {/* Evidence Stats */}
                      <div className="grid grid-cols-2 gap-4">
                        <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg">
                          <div className="text-2xl font-bold text-primary">{retrievalData.chunks_used || 0}</div>
                          <div className="text-xs text-muted-foreground mt-1">Chunks Used</div>
                        </div>
                        <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg">
                          <div className="text-2xl font-bold text-primary">
                            {new Set(retrievalData.chunk_sources || []).size}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">Unique Sources</div>
                        </div>
                      </div>

                      {/* Sources */}
                      <div>
                        <div className="text-sm font-semibold text-foreground mb-2">Sources:</div>
                        <div className="flex flex-wrap gap-2">
                          {[...new Set(retrievalData.chunk_sources || [])].map((source: string, idx: number) => (
                            <span
                              key={idx}
                              className="px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
                            >
                              {source}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Evidence Chunks */}
                      {retrievalData.chunks && retrievalData.chunks.length > 0 && (
                        <div>
                          <div className="text-sm font-semibold text-foreground mb-3">Evidence Chunks:</div>
                          <div className="space-y-3">
                            {retrievalData.chunks.map((chunk: any, index: number) => (
                              <EvidenceChunk key={index} chunk={chunk} index={index} />
                            ))}
                          </div>
                        </div>
                      )}

                      {(!retrievalData.chunks || retrievalData.chunks.length === 0) && (
                        <div className="text-center py-8 text-muted-foreground">
                          <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                          <p>No detailed chunk content available</p>
                          <p className="text-xs mt-1">Evidence was used but detailed content was not stored</p>
                        </div>
                      )}
                    </div>
                  </DialogContent>
                </Dialog>

                <div className="flex-1 p-3 bg-primary/10 border border-primary/20 rounded-lg text-center">
                  <div className="text-2xl font-bold text-primary">
                    {new Set(retrievalData.chunk_sources || []).size}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Unique Sources</div>
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-2">Sources:</div>
                <div className="flex flex-wrap gap-2">
                  {[...new Set(retrievalData.chunk_sources || [])].map((source: string, idx: number) => (
                    <span
                      key={idx}
                      className="px-2 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
                    >
                      {source}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Resolution Steps - Full Width */}
      {resolutionData && resolutionData.resolution_steps && resolutionData.resolution_steps.length > 0 ? (
        <Card className="p-6 glass-card glow-border">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-success" />
              <h3 className="font-semibold text-foreground">Resolution Steps Executed</h3>
            </div>
            <div className="bg-background/50 border border-border/30 rounded-lg p-4">
              <div className="space-y-2">
                {resolutionData.resolution_steps.map((step: string, index: number) => (
                  <div key={index} className="flex items-start gap-3 text-sm">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-success/20 text-success flex items-center justify-center text-xs font-bold">
                      {index + 1}
                    </span>
                    <span className="text-muted-foreground leading-relaxed pt-0.5">{step}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      ) : (
        <Card className="p-6 glass-card glow-border">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-warning" />
              <h3 className="font-semibold text-foreground">Resolution Status</h3>
            </div>
            <div className="bg-warning/10 border border-warning/30 rounded-lg p-4">
              <p className="text-muted-foreground text-sm text-center py-4">
                Resolution has not been proposed yet for this incident.
                {policyData?.policy_band && (
                  <span className="block mt-2">
                    Current Policy Band: <span className={cn("font-semibold", 
                      policyData.policy_band === "AUTO" ? "text-success" :
                      policyData.policy_band === "PROPOSE" ? "text-warning" :
                      policyData.policy_band === "REVIEW" ? "text-warning" :
                      policyData.policy_band === "BLOCK" ? "text-destructive" :
                      "text-foreground"
                    )}>{policyData.policy_band}</span>
                    {policyData.policy_band === "AUTO" && (
                      <span className="block mt-1 text-xs">Resolution can be auto-generated when approved.</span>
                    )}
                    {(policyData.policy_band === "PROPOSE" || policyData.policy_band === "REVIEW") && (
                      <span className="block mt-1 text-xs">Approval required before resolution can be generated.</span>
                    )}
                    {policyData.policy_band === "BLOCK" && (
                      <span className="block mt-1 text-xs">Resolution is currently blocked.</span>
                    )}
                  </span>
                )}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Action Summary */}
      <Card className={`p-6 ${hasResolution ? 'bg-success/10 border-success/30' : 'bg-warning/10 border-warning/30'}`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-foreground mb-1">
              {hasResolution ? "Incident Resolved Successfully" : "Incident Summary"}
            </h3>
            <p className="text-sm text-muted-foreground">
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
                    onClick={() => handleDownloadReport('html')}
                    className="w-full h-auto py-4 px-6 bg-primary hover:bg-primary/90 text-left justify-start gap-4"
                  >
                    <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-white/20">
                      <FileText className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-base">HTML Report</div>
                      <div className="text-sm opacity-90">Beautiful, printable report with all details</div>
                    </div>
                  </Button>
                  
                  <Button
                    onClick={() => handleDownloadReport('json')}
                    variant="outline"
                    className="w-full h-auto py-4 px-6 text-left justify-start gap-4 hover:bg-secondary/50"
                  >
                    <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-secondary">
                      <FileJson className="w-6 h-6 text-foreground" />
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-base">JSON Data</div>
                      <div className="text-sm text-muted-foreground">Raw data for API integration</div>
                    </div>
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            
            <Button onClick={onNewTicket} className="bg-primary hover:bg-primary/90 text-primary-foreground">
              Triage New Ticket
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

