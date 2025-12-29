import { useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

interface ActionItemProps {
  action: string;
  index: number;
}

export const ActionItem = ({ action, index }: ActionItemProps) => {
  const [checked, setChecked] = useState(false);

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-4 rounded-lg border border-border/50 bg-secondary/30 transition-all duration-200 hover:bg-secondary/50",
        checked && "opacity-60"
      )}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <Checkbox
        id={`action-${index}`}
        checked={checked}
        onCheckedChange={(value) => setChecked(value as boolean)}
        className="mt-0.5 border-primary data-[state=checked]:bg-primary data-[state=checked]:border-primary"
      />
      <label
        htmlFor={`action-${index}`}
        className={cn(
          "text-sm leading-relaxed cursor-pointer transition-all",
          checked ? "line-through text-muted-foreground" : "text-foreground"
        )}
      >
        {action}
      </label>
    </div>
  );
};
