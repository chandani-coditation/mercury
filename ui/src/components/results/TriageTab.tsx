import { FileText, Lightbulb, Route, Server, ListChecks } from "lucide-react";
import { SeverityBadge } from "./SeverityBadge";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { InfoCard } from "./InfoCard";
import { ServiceTag } from "./ServiceTag";
import { ActionItem } from "./ActionItem";

interface TriageData {
  severity: "high" | "medium" | "low";
  category: string;
  summary: string;
  likely_cause: string;
  routing: string;
  affected_services: string[];
  recommended_actions: string[];
  confidence: number;
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
        <div className="px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-sm font-medium">
          {data.category}
        </div>
      </div>

      {/* Summary */}
      <InfoCard icon={FileText} title="Summary" variant="highlighted">
        {data.summary}
      </InfoCard>

      {/* Likely Cause */}
      <InfoCard icon={Lightbulb} title="Likely Cause">
        {data.likely_cause}
      </InfoCard>

      {/* Routing - Highlighted for Demo */}
      <InfoCard icon={Route} title="Routing Assignment" variant="highlighted">
        <div className="relative">
          <span className="font-mono text-primary font-semibold text-lg">{data.routing}</span>
          <div className="absolute -inset-1 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
        </div>
      </InfoCard>

      {/* Affected Services */}
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

      {/* Recommended Actions */}
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
