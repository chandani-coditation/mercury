import { cn } from "@/lib/utils";
import { componentClasses } from "@/design-system";

export interface KeyValueDisplayProps {
  label: string;
  value: string | number | React.ReactNode;
  valueType?: "severity" | "impact" | "urgency" | "confidence" | "routing" | "default";
  className?: string;
  labelClassName?: string;
  valueClassName?: string;
  inline?: boolean; // If true, label and value on same line
  borderless?: boolean; // If true, remove border for cleaner grid layouts
}

/**
 * Centralized component for displaying key-value pairs with consistent styling
 * and automatic color coding based on value type
 */
export const KeyValueDisplay = ({
  label,
  value,
  valueType = "default",
  className = "",
  labelClassName = "",
  valueClassName = "",
  inline = false,
  borderless = false, // Default to bordered - label and value in one box
}: KeyValueDisplayProps) => {
  // Get color classes based on value type and value
  const getValueColor = (): string => {
    if (typeof value === "string") {
      const valueLower = value.toLowerCase();

      switch (valueType) {
        case "severity":
          if (valueLower.includes("critical") || valueLower.includes("high")) {
            return "text-destructive font-semibold";
          } else if (valueLower.includes("medium")) {
            return "text-warning font-semibold";
          } else if (valueLower.includes("low")) {
            return "text-success font-semibold";
          }
          return "text-primary font-semibold";

        case "impact":
          if (valueLower.includes("impact1") || valueLower.includes("high")) {
            return "text-destructive font-semibold";
          } else if (valueLower.includes("impact2") || valueLower.includes("medium")) {
            return "text-warning font-semibold";
          } else if (valueLower.includes("impact3") || valueLower.includes("low")) {
            return "text-success font-semibold";
          }
          return "text-primary font-semibold";

        case "urgency":
          if (valueLower.includes("urgency1") || valueLower.includes("high")) {
            return "text-destructive font-semibold";
          } else if (valueLower.includes("urgency2") || valueLower.includes("medium")) {
            return "text-warning font-semibold";
          } else if (valueLower.includes("urgency3") || valueLower.includes("low")) {
            return "text-success font-semibold";
          }
          return "text-primary font-semibold";

        case "confidence":
          // Confidence is typically a number, but handle string percentages
          const percentMatch = valueLower.match(/(\d+)%/);
          if (percentMatch) {
            const percent = parseInt(percentMatch[1], 10);
            if (percent >= 80) {
              return "text-success font-semibold";
            } else if (percent >= 60) {
              return "text-warning font-semibold";
            } else {
              return "text-destructive font-semibold";
            }
          }
          return "text-primary font-semibold";

        case "routing":
          return "text-primary font-semibold font-sans"; // Use sans-serif for consistency

        default:
          return "text-primary font-semibold";
      }
    } else if (typeof value === "number") {
      // For numeric confidence values (0-1 scale)
      if (valueType === "confidence") {
        const percent = value * 100;
        if (percent >= 80) {
          return "text-success font-semibold";
        } else if (percent >= 60) {
          return "text-warning font-semibold";
        } else {
          return "text-destructive font-semibold";
        }
      }
      return "text-primary font-semibold";
    }

    return "text-primary font-semibold";
  };

  const valueColorClass = getValueColor();

  // Format confidence number to percentage string
  const displayValue =
    typeof value === "number" && valueType === "confidence"
      ? `${Math.round(value * 100)}%`
      : value;

  // Choose card class based on borderless prop
  const cardClass = borderless 
    ? componentClasses.cardSmallBorderless 
    : componentClasses.cardSmall;

  if (inline) {
    // Inline layout: label and value on same line, both inside border
    return (
      <div className={cn(cardClass, "flex items-center justify-between gap-2", className)}>
        <span className={cn(componentClasses.label, labelClassName)}>
          {label}
        </span>
        <div className={cn(componentClasses.flexRow, "flex-wrap")}>
          {typeof displayValue === "string" || typeof displayValue === "number" ? (
            <span className={cn("text-xs font-semibold font-sans", valueColorClass, valueClassName)}>
              {displayValue}
            </span>
          ) : (
            <div className={cn("text-xs font-semibold font-sans", valueColorClass, valueClassName)}>{displayValue}</div>
          )}
        </div>
      </div>
    );
  }

  // Stacked layout: label on top, value below, both inside border
  return (
    <div className={cn(cardClass, className)}>
      <span className={cn(componentClasses.label, labelClassName)}>
        {label}
      </span>
      <div className={cn(componentClasses.flexRow, "flex-wrap")}>
        {typeof displayValue === "string" || typeof displayValue === "number" ? (
          <span className={cn("text-xs font-semibold font-sans", valueColorClass, valueClassName)}>
            {displayValue}
          </span>
        ) : (
          <div className={cn("text-xs font-semibold font-sans", valueColorClass, valueClassName)}>{displayValue}</div>
        )}
      </div>
    </div>
  );
};
