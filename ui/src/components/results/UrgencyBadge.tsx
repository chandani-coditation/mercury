import { cn } from "@/lib/utils";
import { AlertTriangle, AlertCircle, CheckCircle } from "lucide-react";

interface UrgencyBadgeProps {
  urgency: string;
  className?: string;
}

const parseUrgencyLevel = (urgency: string): "high" | "medium" | "low" => {
  const urgencyLower = urgency.toLowerCase();
  
  // First, check for explicit text indicators (prioritize text over numbers)
  if (urgencyLower.includes("high") || urgencyLower.includes("critical")) {
    return "high";
  }
  if (urgencyLower.includes("medium")) {
    return "medium";
  }
  if (urgencyLower.includes("low")) {
    return "low";
  }
  
  // If no text indicator found, check for numeric values (1-5 scale, where 1-2 = high, 3 = medium, 4-5 = low)
  const numericMatch = urgencyLower.match(/(\d+)/);
  if (numericMatch) {
    const num = parseInt(numericMatch[1], 10);
    if (num <= 2) return "high";
    if (num === 3) return "medium";
    return "low";
  }
  
  // Default to medium
  return "medium";
};

const urgencyConfig = {
  high: {
    icon: AlertTriangle,
    className: "severity-high",
  },
  medium: {
    icon: AlertCircle,
    className: "severity-medium",
  },
  low: {
    icon: CheckCircle,
    className: "severity-low",
  },
};

export const UrgencyBadge = ({ urgency, className }: UrgencyBadgeProps) => {
  const level = parseUrgencyLevel(urgency);
  const config = urgencyConfig[level];
  const Icon = config.icon;

  // Preserve the original display text
  const displayText = urgency;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border font-semibold text-xs font-sans",
        config.className,
        className,
      )}
    >
      <Icon className="w-4 h-4" />
      <span>{displayText}</span>
    </div>
  );
};
