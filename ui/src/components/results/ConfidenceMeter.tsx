import { cn } from "@/lib/utils";

interface ConfidenceMeterProps {
  confidence: number;
  className?: string;
}

export const ConfidenceMeter = ({ confidence, className }: ConfidenceMeterProps) => {
  const percentage = Math.round(confidence * 100);
  
  const getColorClass = () => {
    if (percentage >= 80) return "bg-success";
    if (percentage >= 60) return "bg-warning";
    return "bg-destructive";
  };

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">AI Confidence</span>
        <span className="text-sm font-mono font-semibold text-foreground">
          {percentage}%
        </span>
      </div>
      <div className="h-2 bg-secondary rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500 ease-out", getColorClass())}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};
