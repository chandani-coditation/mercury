import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface InfoCardProps {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "highlighted";
}

export const InfoCard = ({ icon: Icon, title, children, className, variant = "default" }: InfoCardProps) => {
  return (
    <div
      className={cn(
        "glass-card p-5 space-y-3 animate-slide-up",
        variant === "highlighted" && "glow-border",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <div className="p-2 rounded-lg bg-primary/10">
          <Icon className="w-4 h-4 text-primary" />
        </div>
        <h4 className="font-semibold text-foreground">{title}</h4>
      </div>
      <div className="text-sm text-muted-foreground leading-relaxed">
        {children}
      </div>
    </div>
  );
};
