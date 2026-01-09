import { useState } from "react";
import {
  FileText,
  Lightbulb,
  ListChecks,
  Route,
  Server,
  TrendingUp,
} from "lucide-react";
import { ActionItem } from "./ActionItem";
import { ServiceTag } from "./ServiceTag";
import { SeverityBadge } from "./SeverityBadge";
import { cn } from "@/lib/utils";
import { ExpandableText } from "@/components/ui/ExpandableText";
import { KeyValueDisplay } from "@/components/ui/KeyValueDisplay";

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

// Using shared ExpandableText component from ui/ExpandableText

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
  onRatingChange?: (
    field: "severity" | "impact" | "urgency",
    rating: "thumbs_up" | "thumbs_down"
  ) => void;
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
        } ${
          ratingStatus === "loading" || disabled
            ? "opacity-50 cursor-not-allowed"
            : "cursor-pointer"
        }`}
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
        } ${
          ratingStatus === "loading" || disabled
            ? "opacity-50 cursor-not-allowed"
            : "cursor-pointer"
        }`}
        title="Thumbs down"
      >
        <span className="text-sm">👎</span>
      </button>
      {ratingStatus === "success" && rating === "thumbs_up" && (
        <span className="text-xs text-success">✓</span>
      )}
      {ratingStatus === "success" && rating === "thumbs_down" && (
        <span className="text-xs text-destructive">✕</span>
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
    <div className="space-y-2.5 animate-fade-in">
      {/* TOP PRIORITY: Severity, Routing, Affected Services - Consistent Format */}
      <div className="grid grid-cols-3 gap-1.5">
        {/* Severity - Using KeyValueDisplay with rating buttons */}
        <div className="relative">
          <KeyValueDisplay
            label="Severity"
            value={
              <div className="flex items-center gap-1 flex-wrap">
                <SeverityBadge severity={data.severity} />
                {data.category && (
                  <span className="px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-semibold font-sans">
                    {data.category}
                  </span>
                )}
              </div>
            }
            valueType="severity"
          />
          {incidentId && onRatingChange && (
            <div className="absolute top-1 right-1">
              <RatingButtons
                field="severity"
                rating={triageRatings?.severity}
                ratingStatus={ratingStatus?.severity}
                onRatingChange={onRatingChange}
              />
            </div>
          )}
        </div>

        {/* Routing - Using KeyValueDisplay */}
        {data.routing ? (
          <KeyValueDisplay
            label="Routing"
            value={data.routing}
            valueType="routing"
          />
        ) : (
          <KeyValueDisplay label="Routing" value="N/A" valueType="routing" />
        )}

        {/* Affected Services - Using KeyValueDisplay */}
        <KeyValueDisplay
          label="Affected Services"
          value={
            data.affected_services && data.affected_services.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {data.affected_services.map((service, index) => (
                  <ServiceTag key={index} service={service} />
                ))}
              </div>
            ) : (
              "N/A"
            )
          }
        />
      </div>

      {/* SECOND ROW: Impact, Urgency, Confidence - Consistent Format */}
      <div className="grid grid-cols-3 gap-1.5">
        {/* Impact - Using KeyValueDisplay with rating buttons */}
        {data.impact ? (
          <div className="relative">
            <KeyValueDisplay
              label="Impact"
              value={data.impact}
              valueType="impact"
            />
            {incidentId && onRatingChange && (
              <div className="absolute top-1 right-1">
                <RatingButtons
                  field="impact"
                  rating={triageRatings?.impact}
                  ratingStatus={ratingStatus?.impact}
                  onRatingChange={onRatingChange}
                />
              </div>
            )}
          </div>
        ) : (
          <KeyValueDisplay label="Impact" value="N/A" valueType="impact" />
        )}

        {/* Urgency - Using KeyValueDisplay with rating buttons */}
        {data.urgency ? (
          <div className="relative">
            <KeyValueDisplay
              label="Urgency"
              value={data.urgency}
              valueType="urgency"
            />
            {incidentId && onRatingChange && (
              <div className="absolute top-1 right-1">
                <RatingButtons
                  field="urgency"
                  rating={triageRatings?.urgency}
                  ratingStatus={ratingStatus?.urgency}
                  onRatingChange={onRatingChange}
                />
              </div>
            )}
          </div>
        ) : (
          <KeyValueDisplay label="Urgency" value="N/A" valueType="urgency" />
        )}

        {/* AI Confidence - Using KeyValueDisplay */}
        <KeyValueDisplay
          label="AI Confidence"
          value={data.confidence !== undefined && data.confidence !== null ? data.confidence : 0}
          valueType="confidence"
        />
      </div>

      {/* Likely Cause - Full Width */}
      {data.likely_cause && (
        <div className="glass-card p-2.5 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Lightbulb className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Likely Cause</span>
          </div>
          <ExpandableText
            text={data.likely_cause}
            lineLimit={3}
            className="text-xs font-semibold font-sans text-foreground leading-relaxed"
          />
        </div>
      )}

      {/* Summary - Full Width */}
      {data.summary && (
        <div className="glass-card p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs font-semibold text-foreground">Summary</span>
            </div>
            {/* Compact Confidence Display */}
            <KeyValueDisplay
              label="Confidence"
              value={data.confidence}
              valueType="confidence"
              inline={true}
              className="p-0 border-0 shadow-none bg-transparent"
            />
          </div>
          <ExpandableText
            text={data.summary}
            charLimit={200}
            className="text-xs font-semibold font-sans text-foreground leading-relaxed"
            showButtonText={{ more: "Read more", less: "Read less" }}
          />
        </div>
      )}

      {/* Recommended Actions */}
      {data.recommended_actions && data.recommended_actions.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <ListChecks className="w-3.5 h-3.5 text-primary" />
            <h4 className="text-xs font-semibold text-foreground">
              Recommended Actions
            </h4>
          </div>
          <div className="space-y-1.5">
            {data.recommended_actions.map((action, index) => (
              <ActionItem key={index} action={action} index={index} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
