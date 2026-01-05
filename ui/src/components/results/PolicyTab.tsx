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
    <div className="space-y-6 animate-fade-in">
      {/* Policy Band Badge - Highlighted for Demo */}
      <div className="space-y-2">
        <div className="flex items-center gap-4 relative">
          <div className="p-3 rounded-xl bg-primary/10">
            <Shield className="w-6 h-6 text-primary" />
          </div>
          <div className="relative">
            <p className="text-sm text-muted-foreground mb-1">Policy Band</p>
            <div
              className={cn(
                "inline-flex items-center px-4 py-2 rounded-lg border-2 text-lg font-bold font-mono relative shadow-lg",
                getBandColor(data.policy_band),
              )}
            >
              <div
                className="absolute -inset-1 rounded-lg blur-sm opacity-50 animate-pulse"
                style={{
                  backgroundColor:
                    data.policy_band === "PROPOSE"
                      ? "rgba(251, 191, 36, 0.3)"
                      : data.policy_band === "AUTO"
                        ? "rgba(34, 197, 94, 0.3)"
                        : "rgba(239, 68, 68, 0.3)",
                }}
              />
              <span className="relative z-10">{data.policy_band}</span>
            </div>
          </div>
        </div>
        <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
          <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          <span>
            The Policy Band determines how the system handles this incident:{" "}
            <strong>AUTO (Green):</strong> The system can automatically generate
            and apply a resolution. Low risk, safe to proceed automatically.{" "}
            <strong>PROPOSE (Orange):</strong> The system will propose a
            resolution, but you need to review and approve it before it's
            applied. Medium risk, requires human oversight.{" "}
            <strong>REVIEW (Red):</strong> The system blocks automatic
            resolution. High risk or unusual situation - requires manual
            investigation and resolution.
          </span>
        </p>
      </div>

      {/* Decision Indicators */}
      <div className="space-y-2">
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
        <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
          <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          <span>
            <strong>Can Auto-Apply:</strong> Whether the resolution can be
            automatically executed without human intervention.{" "}
            <strong>Requires Approval:</strong> Whether a human must review and
            approve before the resolution is applied.{" "}
            <strong>Notification Required:</strong> Whether stakeholders need to
            be notified about this incident. <strong>Rollback Required:</strong>{" "}
            Whether a rollback plan is needed in case the resolution causes
            issues.
          </span>
        </p>
      </div>

      {/* Policy Reason */}
      <div className="space-y-2">
        <InfoCard
          icon={MessageSquare}
          title="Policy Reason"
          variant="highlighted"
        >
          {decision.policy_reason}
        </InfoCard>
        <p className="text-xs text-muted-foreground px-1 flex items-start gap-1.5">
          <Info className="w-3 h-3 text-muted-foreground flex-shrink-0 mt-0.5" />
          <span>
            This explains why the system assigned this particular policy band.
            It shows the factors considered (like severity, confidence, risk
            level) and how they influenced the decision. This helps you
            understand the reasoning behind the policy assignment.
          </span>
        </p>
      </div>
    </div>
  );
};
