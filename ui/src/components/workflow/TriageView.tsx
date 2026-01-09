import { ArrowRight, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ResultsPanel } from "@/components/results/ResultsPanel";

interface TriageViewProps {
  triageData: any;
  policyData: any;
  retrievalData: any;
  onNext: () => void;
  onBack: () => void;
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

export const TriageView = ({
  triageData,
  policyData,
  retrievalData,
  onNext,
  onBack,
  incidentId,
  activeTab,
  onTabChange,
  triageRatings,
  ratingStatus,
  onRatingChange,
}: TriageViewProps) => {
  return (
    <div className="space-y-3">
      {/* Results Panel with 3 Tabs */}
      <ResultsPanel
        triageData={triageData}
        policyData={policyData}
        retrievalData={retrievalData}
        incidentId={incidentId}
        activeTab={activeTab}
        onTabChange={onTabChange}
        triageRatings={triageRatings}
        ratingStatus={ratingStatus}
        onRatingChange={onRatingChange}
      />

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={onBack}
          className="bg-secondary hover:bg-secondary/80"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <Button
          onClick={onNext}
          className="bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          Next
          <ArrowRight className="w-4 h-4 ml-2" />
        </Button>
      </div>
    </div>
  );
};
