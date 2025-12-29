import { cn } from "@/lib/utils";
import { AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";

interface SeverityBadgeProps {
  severity: "high" | "medium" | "low";
  className?: string;
}

const severityConfig = {
  high: {
    icon: AlertTriangle,
    label: "High",
    className: "severity-high",
  },
  medium: {
    icon: AlertCircle,
    label: "Medium",
    className: "severity-medium",
  },
  low: {
    icon: CheckCircle,
    label: "Low",
    className: "severity-low",
  },
};

export const SeverityBadge = ({ severity, className }: SeverityBadgeProps) => {
  const config = severityConfig[severity] || severityConfig.medium;
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border font-medium text-sm",
        config.className,
        className
      )}
    >
      <Icon className="w-4 h-4" />
      <span>{config.label} Severity</span>
    </div>
  );
};
