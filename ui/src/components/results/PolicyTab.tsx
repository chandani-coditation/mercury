import { Shield, MessageSquare, Info } from "lucide-react";
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
    <div className="space-y-2.5 animate-fade-in">
      {/* TOP PRIORITY: Policy Band */}
      <div className="glass-card p-2.5 border-2 border-primary/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Shield className="w-4 h-4 text-primary" />
            <span className="text-xs font-semibold text-muted-foreground">Policy Band</span>
          </div>
          <div
            className={cn(
              "inline-flex items-center px-3 py-1.5 rounded-lg border text-base font-bold font-mono",
              getBandColor(data.policy_band),
            )}
          >
            {data.policy_band}
          </div>
        </div>
      </div>

      {/* Decision Indicators - Compact 2x2 Grid */}
      <div className="grid grid-cols-2 gap-2">
        <PolicyIndicator
          label="Can Auto-Apply"
          value={decision.can_auto_apply}
        />
        <PolicyIndicator
          label="Requires Approval"
          value={decision.requires_approval}
        />
        <PolicyIndicator
          label="Notification Required"
          value={decision.notification_required}
        />
        <PolicyIndicator
          label="Rollback Required"
          value={decision.rollback_required}
        />
      </div>

      {/* Policy Reason - Compact */}
      <div className="glass-card p-2.5 space-y-1.5">
        <div className="flex items-center gap-1.5">
          <MessageSquare className="w-3.5 h-3.5 text-primary" />
          <h4 className="text-xs font-semibold text-foreground">Policy Reason</h4>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {decision.policy_reason}
        </p>
      </div>
    </div>
  );
};
