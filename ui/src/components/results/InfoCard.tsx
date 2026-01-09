import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface InfoCardProps {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "highlighted";
}

export const InfoCard = ({
  icon: Icon,
  title,
  children,
  className,
  variant = "default",
}: InfoCardProps) => {
  return (
    <div
      className={cn(
        "glass-card p-3 space-y-2 animate-slide-up",
        variant === "highlighted" && "glow-border",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-lg bg-primary/10">
          <Icon className="w-3.5 h-3.5 text-primary" />
        </div>
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
      </div>
      <div className="text-sm text-foreground leading-relaxed">{children}</div>
    </div>
  );
};
