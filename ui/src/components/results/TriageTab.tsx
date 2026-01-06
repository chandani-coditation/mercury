import {
  FileText,
  Lightbulb,
  Route,
  Server,
  ListChecks,
  AlertCircle,
  Target,
  TrendingUp,
  Info,
} from "lucide-react";
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
  incidentId?: string;
  triageRatings?: {
    severity?: string | null;
    impact?: string | null;
    urgency?: string | null;
  };
  ratingStatus?: {
    severity?: string;
    impact?: string;
    urgency?: string;
  };
  onRatingChange?: (
    field: "severity" | "impact" | "urgency",
    rating: "thumbs_up" | "thumbs_down"
  ) => void;
}

// Rating buttons component
const RatingButtons = ({
  field,
  rating,
  ratingStatus,
  onRatingChange,
  disabled,
}: {
  field: "severity" | "impact" | "urgency";
  rating?: string | null;
  ratingStatus?: string;
  onRatingChange?: (field: "severity" | "impact" | "urgency", rating: "thumbs_up" | "thumbs_down") => void;
  disabled?: boolean;
}) => {
  if (!onRatingChange) return null;

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => onRatingChange(field, "thumbs_up")}
        disabled={disabled || ratingStatus === "loading"}
        className={`flex items-center justify-center w-7 h-7 rounded-md border transition-all ${
          rating === "thumbs_up"
            ? "border-success bg-success/20 text-success"
            : "border-border/50 bg-background/50 hover:bg-secondary/50 text-muted-foreground"
        } ${ratingStatus === "loading" || disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        title="Thumbs up"
      >
        <span className="text-sm">👍</span>
      </button>
      <button
        type="button"
        onClick={() => onRatingChange(field, "thumbs_down")}
        disabled={disabled || ratingStatus === "loading"}
        className={`flex items-center justify-center w-7 h-7 rounded-md border transition-all ${
          rating === "thumbs_down"
            ? "border-destructive bg-destructive/20 text-destructive"
            : "border-border/50 bg-background/50 hover:bg-secondary/50 text-muted-foreground"
        } ${ratingStatus === "loading" || disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        title="Thumbs down"
      >
        <span className="text-sm">👎</span>
      </button>
      {ratingStatus === "success" && (
        <span className="text-xs text-success">✓</span>
      )}
    </div>
  );
};

export const TriageTab = ({
  data,
  incidentId,
  triageRatings,
  ratingStatus,
  onRatingChange,
}: TriageTabProps) => {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header with Severity and Category */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={data.severity} />
          {incidentId && onRatingChange && (
            <RatingButtons
              field="severity"
              rating={triageRatings?.severity}
              ratingStatus={ratingStatus?.severity}
              onRatingChange={onRatingChange}
            />
          )}
        </div>
        {data.category && (
          <div className="px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-sm font-medium">
            {data.category}
          </div>
        )}
      </div>

      {/* Summary */}
      {data.summary && (
        <div className="space-y-2">
          <InfoCard icon={FileText} title="Summary" variant="highlighted">
            {data.summary}
          </InfoCard>
          <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
            <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
            <span>
              This is the AI's analysis of your alert. It summarizes what the
              problem is, when it started, and what impact it might have on your
              systems.
            </span>
          </p>
        </div>
      )}

      {/* Likely Cause */}
      {data.likely_cause && (
        <div className="space-y-2">
          <InfoCard icon={Lightbulb} title="Likely Cause">
            {data.likely_cause}
          </InfoCard>
          <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
            <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
            <span>
              Based on the alert details and knowledge base, the AI has
              identified the most probable root cause. This helps you understand
              why the problem occurred and where to focus your investigation.
            </span>
          </p>
        </div>
      )}

      {/* Impact and Urgency - New fields added (between Likely Cause and Routing) */}
      {(data.impact || data.urgency) && (
        <div className="grid grid-cols-2 gap-3">
          {data.impact && (
            <div className="space-y-2">
              <div className="glass-card p-5 space-y-3 animate-slide-up">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-lg bg-primary/10">
                      <TrendingUp className="w-4 h-4 text-primary" />
                    </div>
                    <h4 className="font-semibold text-foreground">Impact</h4>
                  </div>
                  {incidentId && onRatingChange && (
                    <RatingButtons
                      field="impact"
                      rating={triageRatings?.impact}
                      ratingStatus={ratingStatus?.impact}
                      onRatingChange={onRatingChange}
                    />
                  )}
                </div>
                <div className="text-sm text-foreground leading-relaxed">
                  <span className="text-sm font-semibold text-primary">
                    {data.impact}
                  </span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
                <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
                <span>
                  The extent of the impact on business operations. Higher impact
                  means more users or critical systems are affected.
                </span>
              </p>
            </div>
          )}
          {data.urgency && (
            <div className="space-y-2">
              <div className="glass-card p-5 space-y-3 animate-slide-up">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-lg bg-primary/10">
                      <TrendingUp className="w-4 h-4 text-primary" />
                    </div>
                    <h4 className="font-semibold text-foreground">Urgency</h4>
                  </div>
                  {incidentId && onRatingChange && (
                    <RatingButtons
                      field="urgency"
                      rating={triageRatings?.urgency}
                      ratingStatus={ratingStatus?.urgency}
                      onRatingChange={onRatingChange}
                    />
                  )}
                </div>
                <div className="text-sm text-foreground leading-relaxed">
                  <span className="text-sm font-semibold text-primary">
                    {data.urgency}
                  </span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
                <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
                <span>
                  How quickly the issue needs to be resolved. Higher urgency
                  means immediate action is required.
                </span>
              </p>
            </div>
          )}
        </div>
      )}

      {/* Routing - Highlighted for Demo */}
      {data.routing && (
        <div className="space-y-2">
          <InfoCard
            icon={Route}
            title="Routing Assignment"
            variant="highlighted"
          >
            <div className="relative">
              <span className="font-mono text-primary font-semibold text-lg">
                {data.routing}
              </span>
              <div className="absolute -inset-1 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
            </div>
          </InfoCard>
          <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
            <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
            <span>
              This is the team or person who should handle this incident. The AI
              automatically routes tickets based on the type of issue, affected
              services, and your organization's routing rules. This ensures the
              right experts get the ticket.
            </span>
          </p>
        </div>
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
          <div className="flex flex-wrap gap-2 mb-2">
            {data.affected_services.map((service, index) => (
              <ServiceTag key={index} service={service} />
            ))}
          </div>
          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
            <span>
              These are the services, databases, or systems that are impacted by
              this alert. Knowing which services are affected helps you
              understand the scope of the issue and who might need to be
              notified.
            </span>
          </p>
        </div>
      )}

      {/* Recommended Actions */}
      {data.recommended_actions && data.recommended_actions.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <ListChecks className="w-4 h-4 text-primary" />
            </div>
            <h4 className="font-semibold text-foreground">
              Recommended Actions
            </h4>
          </div>
          <div className="space-y-2">
            {data.recommended_actions.map((action, index) => (
              <ActionItem key={index} action={action} index={index} />
            ))}
          </div>
        </div>
      )}

      {/* Confidence Meter - Highlighted for Demo */}
      <div className="space-y-2">
        <div className="glass-card p-5 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
          <div className="absolute -inset-0.5 bg-primary/10 rounded-lg blur opacity-30" />
          <div className="relative">
            <ConfidenceMeter confidence={data.confidence} />
          </div>
        </div>
        <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
          <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          <span>
            This shows how confident the AI is in its analysis. Higher
            confidence (80%+) means the AI found strong matches in the knowledge
            base and is very sure about its assessment. Lower confidence means
            you should review the analysis more carefully, as the AI may need
            more information or the issue might be unusual.
          </span>
        </p>
      </div>
    </div>
  );
};
