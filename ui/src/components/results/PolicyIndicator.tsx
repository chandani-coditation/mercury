import { cn } from "@/lib/utils";
import { Check, X } from "lucide-react";

interface PolicyIndicatorProps {
  label: string;
  value: boolean;
  className?: string;
}

export const PolicyIndicator = ({
  label,
  value,
  className,
}: PolicyIndicatorProps) => {
  return (
    <div
      className={cn(
        "flex items-center justify-between p-4 rounded-lg border",
        value
          ? "bg-success/10 border-success/30"
          : "bg-secondary/30 border-border/50",
        className,
      )}
    >
      <span className="text-sm text-foreground">{label}</span>
      <div
        className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center",
          value ? "bg-success" : "bg-muted",
        )}
      >
        {value ? (
          <Check className="w-3.5 h-3.5 text-success-foreground" />
        ) : (
          <X className="w-3.5 h-3.5 text-muted-foreground" />
        )}
      </div>
    </div>
  );
};
