import { FileText, Lightbulb, Route, Server, ListChecks, AlertCircle, Target, TrendingUp } from "lucide-react";
import { SeverityBadge } from "./SeverityBadge";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { InfoCard } from "./InfoCard";
import { ServiceTag } from "./ServiceTag";
import { ActionItem } from "./ActionItem";

interface TriageData {
  severity: "high" | "medium" | "low";
  category?: string;
  summary?: string;
  likely_cause?: string;
  routing?: string;
  impact?: string;
  urgency?: string;
  affected_services?: string[];
  recommended_actions?: string[];
  confidence: number;
  incident_signature?: {
    failure_type?: string;
    error_class?: string;
  };
  matched_evidence?: {
    incident_signatures?: string[];
    runbook_refs?: string[];
  };
}

interface TriageTabProps {
  data: TriageData;
}

export const TriageTab = ({ data }: TriageTabProps) => {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header with Severity and Category */}
      <div className="flex flex-wrap items-center gap-3">
        <SeverityBadge severity={data.severity} />
        {data.category && (
          <div className="px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-sm font-medium">
            {data.category}
          </div>
        )}
      </div>

      {/* Summary */}
      {data.summary && (
        <InfoCard icon={FileText} title="Summary" variant="highlighted">
          {data.summary}
        </InfoCard>
      )}

      {/* Likely Cause */}
      {data.likely_cause && (
        <InfoCard icon={Lightbulb} title="Likely Cause">
          {data.likely_cause}
        </InfoCard>
      )}

      {/* Impact and Urgency - New fields added (between Likely Cause and Routing) */}
      {(data.impact || data.urgency) && (
        <div className="grid grid-cols-2 gap-3">
          {data.impact && (
            <InfoCard icon={TrendingUp} title="Impact">
              <span className="font-semibold text-primary text-lg">{data.impact}</span>
            </InfoCard>
          )}
          {data.urgency && (
            <InfoCard icon={TrendingUp} title="Urgency">
              <span className="font-semibold text-primary text-lg">{data.urgency}</span>
            </InfoCard>
          )}
        </div>
      )}

      {/* Routing - Highlighted for Demo */}
      {data.routing && (
        <InfoCard icon={Route} title="Routing Assignment" variant="highlighted">
          <div className="relative">
            <span className="font-mono text-primary font-semibold text-lg">{data.routing}</span>
            <div className="absolute -inset-1 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          </div>
        </InfoCard>
      )}

      {/* Affected Services */}
      {data.affected_services && data.affected_services.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <Server className="w-4 h-4 text-primary" />
            </div>
            <h4 className="font-semibold text-foreground">Affected Services</h4>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.affected_services.map((service, index) => (
              <ServiceTag key={index} service={service} />
            ))}
          </div>
        </div>
      )}

      {/* Recommended Actions */}
      {data.recommended_actions && data.recommended_actions.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <ListChecks className="w-4 h-4 text-primary" />
            </div>
            <h4 className="font-semibold text-foreground">Recommended Actions</h4>
          </div>
          <div className="space-y-2">
            {data.recommended_actions.map((action, index) => (
              <ActionItem key={index} action={action} index={index} />
            ))}
          </div>
        </div>
      )}

      {/* Incident Classification - Collapsible/Expandable section for technical details */}
      {data.incident_signature && (data.incident_signature.failure_type || data.incident_signature.error_class) && (
        <details className="space-y-3">
          <summary className="flex items-center gap-2 cursor-pointer text-sm text-muted-foreground hover:text-foreground transition-colors">
            <Target className="w-4 h-4" />
            <span>Incident Classification (Technical Details)</span>
          </summary>
          <div className="grid grid-cols-2 gap-3 mt-3">
            {data.incident_signature.failure_type && (
              <InfoCard icon={AlertCircle} title="Failure Type">
                <span className="font-mono text-sm">{data.incident_signature.failure_type}</span>
              </InfoCard>
            )}
            {data.incident_signature.error_class && (
              <InfoCard icon={AlertCircle} title="Error Class">
                <span className="font-mono text-sm">{data.incident_signature.error_class}</span>
              </InfoCard>
            )}
          </div>
        </details>
      )}

      {/* Matched Evidence - Collapsible/Expandable section for technical details */}
      {data.matched_evidence && (
        <details className="space-y-3">
          <summary className="flex items-center gap-2 cursor-pointer text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ListChecks className="w-4 h-4" />
            <span>Matched Evidence (Technical Details)</span>
          </summary>
          <div className="space-y-3 mt-3">
            {data.matched_evidence.incident_signatures && data.matched_evidence.incident_signatures.length > 0 && (
              <InfoCard icon={FileText} title="Historical Incidents">
                <div className="flex flex-wrap gap-2">
                  {data.matched_evidence.incident_signatures.slice(0, 5).map((sig, index) => (
                    <span key={index} className="px-2 py-1 rounded bg-secondary text-xs font-mono">
                      {sig}
                    </span>
                  ))}
                  {data.matched_evidence.incident_signatures.length > 5 && (
                    <span className="px-2 py-1 rounded bg-secondary text-xs text-muted-foreground">
                      +{data.matched_evidence.incident_signatures.length - 5} more
                    </span>
                  )}
                </div>
              </InfoCard>
            )}
            {data.matched_evidence.runbook_refs && data.matched_evidence.runbook_refs.length > 0 && (
              <InfoCard icon={FileText} title="Matched Runbooks">
                <div className="flex flex-wrap gap-2">
                  {data.matched_evidence.runbook_refs.map((ref, index) => (
                    <span key={index} className="px-2 py-1 rounded bg-secondary text-xs font-mono">
                      {ref.substring(0, 8)}...
                    </span>
                  ))}
                </div>
              </InfoCard>
            )}
          </div>
        </details>
      )}

      {/* Confidence Meter - Highlighted for Demo */}
      <div className="glass-card p-5 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
        <div className="absolute -inset-0.5 bg-primary/10 rounded-lg blur opacity-30" />
        <div className="relative">
          <ConfidenceMeter confidence={data.confidence} />
        </div>
      </div>
    </div>
  );
};
