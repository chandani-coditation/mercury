import { Server } from "lucide-react";
import { cn } from "@/lib/utils";

interface ServiceTagProps {
  service: string;
  className?: string;
}

export const ServiceTag = ({ service, className }: ServiceTagProps) => {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary/50 border border-border/50 text-sm font-mono",
        className,
      )}
    >
      <Server className="w-3.5 h-3.5 text-primary" />
      <span className="text-foreground">{service}</span>
    </div>
  );
};
