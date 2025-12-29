import { Shield, MessageSquare } from "lucide-react";
import { PolicyIndicator } from "./PolicyIndicator";
import { InfoCard } from "./InfoCard";
import { cn } from "@/lib/utils";

interface PolicyDecision {
  policy_band: string;
  can_auto_apply: boolean;
  requires_approval: boolean;
  notification_required: boolean;
  rollback_required: boolean;
  policy_reason: string;
}

interface PolicyData {
  policy_band: string;
  policy_decision: PolicyDecision;
}

interface PolicyTabProps {
  data: PolicyData;
}

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

export const PolicyTab = ({ data }: PolicyTabProps) => {
  const decision = data.policy_decision;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Policy Band Badge - Highlighted for Demo */}
      <div className="flex items-center gap-4 relative">
        <div className="p-3 rounded-xl bg-primary/10">
          <Shield className="w-6 h-6 text-primary" />
        </div>
        <div className="relative">
          <p className="text-sm text-muted-foreground mb-1">Policy Band</p>
          <div
            className={cn(
              "inline-flex items-center px-4 py-2 rounded-lg border-2 text-lg font-bold font-mono relative shadow-lg",
              getBandColor(data.policy_band)
            )}
          >
            <div className="absolute -inset-1 rounded-lg blur-sm opacity-50 animate-pulse" 
                 style={{ backgroundColor: data.policy_band === "PROPOSE" ? "rgba(251, 191, 36, 0.3)" : 
                                        data.policy_band === "AUTO" ? "rgba(34, 197, 94, 0.3)" : 
                                        "rgba(239, 68, 68, 0.3)" }} />
            <span className="relative z-10">{data.policy_band}</span>
          </div>
        </div>
      </div>

      {/* Decision Indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <PolicyIndicator 
          label="Can Auto-Apply" 
          value={decision.can_auto_apply} 
        />
        <div className="relative">
          <div className="absolute -inset-0.5 bg-warning/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          <div className="relative">
            <PolicyIndicator 
              label="Requires Approval" 
              value={decision.requires_approval} 
            />
          </div>
        </div>
        <PolicyIndicator 
          label="Notification Required" 
          value={decision.notification_required} 
        />
        <PolicyIndicator 
          label="Rollback Required" 
          value={decision.rollback_required} 
        />
      </div>

      {/* Policy Reason */}
      <InfoCard icon={MessageSquare} title="Policy Reason" variant="highlighted">
        {decision.policy_reason}
      </InfoCard>
    </div>
  );
};
