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
}

export const ResultsPanel = ({
  triageData,
  policyData,
  retrievalData,
  onHide,
}: ResultsPanelProps) => {
  const [activeTab, setActiveTab] = useState("triage");

  return (
    <div className="w-full mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <h2 className="text-xl font-semibold text-foreground">
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
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="w-full grid grid-cols-3 bg-secondary/50 border border-border/50 p-1 rounded-xl mb-6">
          <TabsTrigger
            value="triage"
            className={cn(
              "flex items-center gap-2 rounded-lg py-3 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Zap className="w-4 h-4" />
            Triage
          </TabsTrigger>
          <TabsTrigger
            value="policy"
            className={cn(
              "flex items-center gap-2 rounded-lg py-3 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Shield className="w-4 h-4" />
            Policy
          </TabsTrigger>
          <TabsTrigger
            value="retrieval"
            className={cn(
              "flex items-center gap-2 rounded-lg py-3 text-sm font-medium transition-all data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-lg",
            )}
          >
            <Database className="w-4 h-4" />
            Retrieval
          </TabsTrigger>
        </TabsList>

        <div className="glass-card p-6 glow-border">
          <TabsContent value="triage" className="mt-0">
            <TriageTab data={triageData} />
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
