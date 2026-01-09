import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { X, Zap, Shield, Database } from "lucide-react";
import { TriageTab } from "./TriageTab";
import { PolicyTab } from "./PolicyTab";
import { RetrievalTab } from "./RetrievalTab";
import { cn } from "@/lib/utils";

interface ResultsPanelProps {
  triageData: any;
  policyData: any;
  retrievalData: any;
  onHide?: () => void;
  incidentId?: string;
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  triageRatings?: {
    severity?: string | null;
    impact?: string | null;
    urgency?: string | null;
  };
  ratingStatus?: {
    severity?: string;
    impact?: string;
    urgency?: string;
  };
  onRatingChange?: (
    field: "severity" | "impact" | "urgency",
    rating: "thumbs_up" | "thumbs_down"
  ) => void;
}

export const ResultsPanel = ({
  triageData,
  policyData,
  retrievalData,
  onHide,
  incidentId,
  activeTab: controlledActiveTab,
  onTabChange,
  triageRatings,
  ratingStatus,
  onRatingChange,
}: ResultsPanelProps) => {
  const [internalActiveTab, setInternalActiveTab] = useState("triage");
  const activeTab = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab;
  
  const handleTabChange = (tab: string) => {
    if (onTabChange) {
      onTabChange(tab);
    } else {
      setInternalActiveTab(tab);
    }
  };

  return (
    <div className="w-full mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          <h2 className="text-base font-semibold text-foreground">
            Analysis Results
          </h2>
        </div>
        {onHide && (
          <button
            onClick={onHide}
            className="px-4 py-2 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-sm font-medium transition-colors flex items-center gap-2"
          >
            <X className="w-4 h-4" />
            Hide
          </button>
        )}
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="w-full grid grid-cols-3 bg-secondary/50 border border-border/50 p-1 rounded-xl mb-3">
          <TabsTrigger
            value="triage"
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Zap className="w-3.5 h-3.5" />
            Triage
          </TabsTrigger>
          <TabsTrigger
            value="policy"
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Shield className="w-3.5 h-3.5" />
            Policy
          </TabsTrigger>
          <TabsTrigger
            value="retrieval"
            className={cn(
              "flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Database className="w-3.5 h-3.5" />
            Retrieval
          </TabsTrigger>
        </TabsList>

        <div className="glass-card p-3 glow-border">
          <TabsContent value="triage" className="mt-0">
            <TriageTab
              data={triageData}
              incidentId={incidentId}
              triageRatings={triageRatings}
              ratingStatus={ratingStatus}
              onRatingChange={onRatingChange}
            />
          </TabsContent>
          <TabsContent value="policy" className="mt-0">
            <PolicyTab data={policyData} />
          </TabsContent>
          <TabsContent value="retrieval" className="mt-0">
            <RetrievalTab data={retrievalData} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
};
