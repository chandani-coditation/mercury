import {
  ArrowRight,
  ArrowLeft,
  Shield,
  Check,
  X,
  AlertCircle,
  AlertTriangle,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface PolicyViewProps {
  data: any;
  retrievalData?: any;
  onApprove: () => void;
  onBack: () => void;
  isLoading: boolean;
  error?: string;
}

const getBandColor = (band: string) => {
  switch (band.toUpperCase()) {
    case "AUTO":
      return "bg-success/20 text-success border-success/30";
    case "PROPOSE":
      return "bg-warning/20 text-warning border-warning/30";
    case "BLOCK":
      return "bg-destructive/20 text-destructive border-destructive/30";
    default:
      return "bg-primary/20 text-primary border-primary/30";
  }
};

export const PolicyView = ({
  data,
  retrievalData: _retrievalData,
  onApprove,
  onBack,
  isLoading,
  error,
}: PolicyViewProps) => {
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const decision = data.policy_decision;
  const policyBand = data.policy_band;

  // Only require confirmation for PROPOSE and BLOCK, not for AUTO
  const requiresConfirmation =
    policyBand === "PROPOSE" || policyBand === "BLOCK";

  const handleApproveClick = () => {
    if (requiresConfirmation) {
      setConfirmDialogOpen(true);
    } else {
      // AUTO - proceed directly without confirmation
      onApprove();
    }
  };

  const handleConfirmApprove = () => {
    setConfirmDialogOpen(false);
    onApprove();
  };

  return (
    <div className="space-y-2.5">
      {/* Analysis Results Header */}
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
        <h2 className="text-base font-semibold text-foreground">
          Analysis Results
        </h2>
      </div>

      {/* TOP PRIORITY: Policy Band */}
      <Card className="p-3 glass-card glow-border border-2 border-primary/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" />
            <span className="text-xs font-semibold text-muted-foreground">Policy Band</span>
          </div>
          <div
            className={cn(
              "inline-flex items-center px-3 py-1.5 rounded-lg border text-base font-bold font-mono",
              getBandColor(policyBand),
            )}
          >
            {policyBand}
          </div>
        </div>
      </Card>

      {/* Decision Indicators Grid - Compact 2x2 */}
      <div className="grid grid-cols-2 gap-2">
        <DecisionIndicator
          label="Can Auto-Apply"
          value={decision.can_auto_apply}
        />
        <DecisionIndicator
          label="Requires Approval"
          value={decision.requires_approval}
          highlight
        />
        <DecisionIndicator
          label="Notification Required"
          value={decision.notification_required}
        />
        <DecisionIndicator
          label="Rollback Required"
          value={decision.rollback_required}
        />
      </div>

      {/* Policy Reason - Compact */}
      <div className="glass-card p-2.5 space-y-1.5">
        <div className="flex items-center gap-1.5">
          <div className="w-1 h-3 bg-primary rounded-full" />
          <h4 className="font-semibold text-xs text-foreground">
            Policy Reason
          </h4>
        </div>
        <p className="text-xs text-muted-foreground pl-2.5 leading-relaxed">
          {decision.policy_reason}
        </p>
      </div>

      {/* Approval Message - Compact */}
      {requiresConfirmation && (
        <Card className="p-2.5 bg-warning/10 border-warning/30">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-foreground">
              Policy Decision Required
            </h3>
            <p className="text-xs text-muted-foreground">
              Review the policy band and approve to proceed with resolution
            </p>
          </div>
        </Card>
      )}

      {!requiresConfirmation && (
        <Card className="p-2.5 bg-success/10 border-success/30">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-foreground">
              Auto-Approved Policy
            </h3>
            <p className="text-xs text-muted-foreground">
              This policy band allows automatic progression to resolution
            </p>
          </div>
        </Card>
      )}

      {/* Error Display - Compact */}
      {error && (
        <Card className="p-2.5 bg-destructive/10 border-destructive/30">
          <div className="flex items-start gap-1.5">
            <AlertCircle className="w-4 h-4 text-destructive flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-destructive text-xs">Error</div>
              <div className="text-xs text-destructive/90 mt-0.5 whitespace-pre-wrap">
                {error}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={onBack}
          disabled={isLoading}
          className="bg-secondary hover:bg-secondary/80"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <Button
          onClick={handleApproveClick}
          disabled={isLoading}
          className="bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2" />
              Generating...
            </>
          ) : requiresConfirmation ? (
            <>
              Approve & Continue
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          ) : (
            <>
              Continue to Resolution
              <ArrowRight className="w-4 h-4 ml-2" />
            </>
          )}
        </Button>
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialogOpen} onOpenChange={setConfirmDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-warning" />
              Confirm Policy Approval
            </DialogTitle>
            <DialogDescription>
              You are about to approve this policy and proceed with resolution
              generation.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="p-4 bg-warning/10 border border-warning/30 rounded-lg">
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold text-foreground mb-1">
                    Policy Band: {policyBand}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {decision.policy_reason}
                  </div>
                </div>
              </div>
            </div>

            {policyBand === "BLOCK" && (
              <div className="p-4 bg-destructive/10 border border-destructive/30 rounded-lg">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-destructive mb-1">
                      Warning
                    </div>
                    <div className="text-sm text-destructive/90">
                      This policy is marked as BLOCK. Proceeding requires
                      careful review.
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between py-2 px-3 bg-secondary/30 rounded">
                <span className="text-muted-foreground">Requires Approval</span>
                <span
                  className={
                    decision.requires_approval
                      ? "text-warning font-semibold"
                      : "text-muted-foreground"
                  }
                >
                  {decision.requires_approval ? "Yes" : "No"}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 px-3 bg-secondary/30 rounded">
                <span className="text-muted-foreground">Can Auto-Apply</span>
                <span
                  className={
                    decision.can_auto_apply
                      ? "text-success font-semibold"
                      : "text-muted-foreground"
                  }
                >
                  {decision.can_auto_apply ? "Yes" : "No"}
                </span>
              </div>
            </div>

            <p className="text-sm text-muted-foreground">
              By approving, you confirm that you have reviewed the policy
              decision and agree to proceed with AI-generated resolution steps.
            </p>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setConfirmDialogOpen(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmApprove}
              disabled={isLoading}
              className="bg-primary hover:bg-primary/90"
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2" />
                  Generating...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Confirm & Proceed
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

// Decision Indicator Component
const DecisionIndicator = ({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: boolean;
  highlight?: boolean;
}) => {
  return (
    <div
      className={cn(
        "flex items-center justify-between p-2 rounded-lg border",
        value && highlight
          ? "bg-success/10 border-success/30"
          : value
            ? "bg-secondary/30 border-border/50"
            : "bg-secondary/20 border-border/30",
      )}
    >
      <span className="text-xs text-foreground">{label}</span>
      <div
        className={cn(
          "w-4 h-4 rounded-full flex items-center justify-center",
          value ? "bg-success" : "bg-muted",
        )}
      >
        {value ? (
          <Check className="w-2.5 h-2.5 text-success-foreground" />
        ) : (
          <X className="w-2.5 h-2.5 text-muted-foreground" />
        )}
      </div>
    </div>
  );
};
