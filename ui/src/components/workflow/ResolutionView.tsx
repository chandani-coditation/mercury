import {
  ArrowLeft,
  CheckCircle,
  AlertTriangle,
  Brain,
  Info,
  Terminal,
  Shield,
  Check,
  ThumbsUp,
  ThumbsDown,
  Edit,
  Save,
  X,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ExpandableText } from "@/components/ui/ExpandableText";

interface ResolutionViewProps {
  data: any;
  onBack: () => void;
  onMarkComplete: () => void;
  incidentId?: string;
  resolutionRatings?: Record<number, string | null>;
  ratingStatus?: Record<number, string>;
  onRatingChange?: (stepIndex: number, rating: "thumbs_up" | "thumbs_down", stepTitle?: string) => void;
  onStepEdit?: (stepIndex: number, editedStep: any, originalStep: any) => Promise<void>;
  stepEditStatus?: Record<number, "idle" | "loading" | "success" | "error">;
}

// Rating buttons component for resolution steps
const StepRatingButtons = ({
  stepIndex,
  rating,
  ratingStatus,
  onRatingChange,
  disabled,
  stepTitle,
}: {
  stepIndex: number;
  rating?: string | null;
  ratingStatus?: string;
  onRatingChange?: (stepIndex: number, rating: "thumbs_up" | "thumbs_down", stepTitle?: string) => void;
  disabled?: boolean;
  stepTitle?: string;
}) => {
  if (!onRatingChange) {
    console.warn("StepRatingButtons: onRatingChange is not provided for step", stepIndex);
    return null;
  }

  const handleClick = (ratingType: "thumbs_up" | "thumbs_down") => {
    console.log(`🔥 Button clicked: ${ratingType} for step ${stepIndex}`, stepTitle);
    if (onRatingChange) {
      // Call the handler - it will handle optimistic updates and API calls
      onRatingChange(stepIndex, ratingType, stepTitle);
      console.log("✅ onRatingChange called successfully");
    } else {
      console.warn("❌ onRatingChange is not available");
    }
  };

  return (
    <div 
      className="flex items-center gap-1" 
      style={{ 
        position: "relative", 
        zIndex: 9999,
        pointerEvents: "auto",
      }}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log("🔥 Button element clicked - thumbs_up");
          handleClick("thumbs_up");
        }}
        disabled={disabled || ratingStatus === "loading"}
        className={`h-7 w-7 p-0 ${
          rating === "thumbs_up"
            ? "bg-success/20 text-success border border-success"
            : "hover:bg-secondary/50"
        }`}
        title="Thumbs up - Rate this step"
        style={{ 
          pointerEvents: "auto", 
          zIndex: 9999,
          position: "relative",
        }}
      >
        <span style={{ fontSize: "14px" }}>👍</span>
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log("🔥 Button element clicked - thumbs_down");
          handleClick("thumbs_down");
        }}
        disabled={disabled || ratingStatus === "loading"}
        className={`h-7 w-7 p-0 ${
          rating === "thumbs_down"
            ? "bg-destructive/20 text-destructive border border-destructive"
            : "hover:bg-secondary/50"
        }`}
        title="Thumbs down - Rate this step"
        style={{ 
          pointerEvents: "auto", 
          zIndex: 9999,
          position: "relative",
        }}
      >
        <span style={{ fontSize: "14px" }}>👎</span>
      </Button>
      {ratingStatus === "success" && rating === "thumbs_up" && (
        <span className="text-xs text-success ml-1">✓</span>
      )}
      {ratingStatus === "success" && rating === "thumbs_down" && (
        <span className="text-xs text-destructive ml-1">✕</span>
      )}
    </div>
  );
};

export const ResolutionView = ({
  data,
  onBack,
  onMarkComplete,
  incidentId,
  resolutionRatings,
  ratingStatus,
  onRatingChange,
  onStepEdit,
  stepEditStatus,
}: ResolutionViewProps) => {
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  // Track which step is being edited and its edited content
  const [editingStepIndex, setEditingStepIndex] = useState<number | null>(null);
  const [editedStepContent, setEditedStepContent] = useState<string>("");

  const resolution = data.resolution || data;

  // New structure: steps array with objects (new format)
  // Format: [{ step_number, title, action, expected_outcome }, ...]
  // Filter out steps with empty/null/missing actions and renumber sequentially
  const allSteps = resolution.steps || [];
  
  // Filter out steps with empty/null/missing actions
  const validStepsWithOriginalIndex = allSteps
    .map((step: any, originalIndex: number) => ({ step, originalIndex }))
    .filter(({ step }: { step: any }) => {
      const action = step.action || "";
      return action.trim().length > 0;
    });
  
  // Renumber the valid steps sequentially starting from 1, but keep original index for rating lookup
  const stepsArray = validStepsWithOriginalIndex.map(({ step, originalIndex }: { step: any; originalIndex: number }, displayIndex: number) => ({
    ...step,
    step_number: displayIndex + 1, // Sequential numbering starting from 1
    originalIndex, // Keep original index for rating lookup
    displayIndex, // Display index (0-based for filtered array)
  }));

  // Debug logging - remove in production
  if (process.env.NODE_ENV === "development") {
    console.log("ResolutionView props:", {
      incidentId,
      hasOnRatingChange: !!onRatingChange,
      resolutionRatings,
      ratingStatus,
      stepsCount: stepsArray.length,
    });
  }

  const overallConfidence =
    resolution.overall_confidence || resolution.confidence;
  const reasoning = resolution.reasoning;
  const rollbackPlan = resolution.rollback_plan;
  const commands = resolution.commands_by_step || {};

  // Handle rollback_plan - it can be a string or an object
  const rollbackPlanSteps =
    typeof rollbackPlan === "object" && rollbackPlan !== null
      ? rollbackPlan.steps || []
      : null;
  const rollbackPlanCommands =
    typeof rollbackPlan === "object" && rollbackPlan !== null
      ? rollbackPlan.commands_by_step || {}
      : {};
  const rollbackPlanText =
    typeof rollbackPlan === "string" ? rollbackPlan : null;
  const hasRollbackPlan = rollbackPlan !== null && rollbackPlan !== undefined;

  const handleMarkCompleteClick = () => {
    setConfirmDialogOpen(true);
  };

  const handleConfirmComplete = () => {
    setConfirmDialogOpen(false);
    onMarkComplete();
  };

  // Edit handlers
  const handleEditClick = (stepIndex: number, currentAction: string) => {
    setEditingStepIndex(stepIndex);
    setEditedStepContent(currentAction);
  };

  const handleCancelEdit = () => {
    setEditingStepIndex(null);
    setEditedStepContent("");
  };

  const handleSaveEdit = async (stepIndex: number, originalStep: any) => {
    if (!onStepEdit) {
      console.warn("onStepEdit handler not provided");
      return;
    }

    const editedStep = {
      ...originalStep,
      action: editedStepContent.trim(),
    };

    try {
      await onStepEdit(stepIndex, editedStep, originalStep);
      // Only close edit mode if save was successful
      setEditingStepIndex(null);
      setEditedStepContent("");
    } catch (error) {
      console.error("Failed to save edited step:", error);
      // Keep edit mode open on error so user can retry
    }
  };

  return (
    <div className="space-y-2.5">
      {/* Compact Header with Confidence */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          <h2 className="text-base font-semibold text-foreground flex items-center gap-1.5">
            <CheckCircle className="w-4 h-4 text-success" />
            Resolution Generated
          </h2>
          {overallConfidence && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-success/10 border border-success/20">
              <Brain className="w-3 h-3 text-success" />
              <span className="text-xs font-semibold text-success">
                {Math.round(overallConfidence * 100)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Summary - Compact, only if meaningful */}
      {reasoning && reasoning.trim() && (
        <Card className="p-2 bg-primary/5 border-primary/20">
          <div className="flex items-start gap-1">
            <Info className="w-3 h-3 text-primary flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <ExpandableText
                text={reasoning}
                charLimit={200}
                className="text-xs text-muted-foreground leading-relaxed"
                showButtonText={{ more: "Read more", less: "Read less" }}
              />
            </div>
          </div>
        </Card>
      )}

      {/* Resolution Recommendations - Prioritized */}
      <Card className="p-2.5 glass-card glow-border" style={{ position: "relative", pointerEvents: "auto" }}>
        <div className="space-y-1.5" style={{ position: "relative", pointerEvents: "auto" }}>
          <h3 className="text-xs font-semibold text-foreground flex items-center gap-1">
            <CheckCircle className="w-3 h-3 text-success" />
            Resolution Recommendations
          </h3>
          <div className="space-y-1" style={{ position: "relative", pointerEvents: "auto" }}>
            {stepsArray.length > 0 ? (
              // New format: steps array with objects (already filtered and renumbered)
              stepsArray.map((step: any, displayIndex: number) => {
                const stepNumber = step.step_number || displayIndex + 1;
                const stepTitle = step.title || "";
                const stepAction = step.action || "";
                // Use originalIndex for rating lookup to match the original step position in the array
                const ratingIndex = step.originalIndex !== undefined ? step.originalIndex : displayIndex;
                const stepCommands =
                  commands[stepNumber - 1] ||
                  commands[(stepNumber - 1).toString()] ||
                  [];
                const hasCommands = stepCommands && stepCommands.length > 0;

                return (
                  <div
                    key={`step-${stepNumber}-${displayIndex}`}
                    className="bg-background/50 border border-border/30 rounded-lg p-2 hover:border-primary/30 transition-colors"
                    style={{ position: "relative" }}
                  >
                    <div className="flex items-start gap-1.5">
                      <span className="flex-shrink-0 w-4 h-4 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold">
                        {stepNumber}
                      </span>
                      <div className="flex-1 space-y-1">
                        <div className="flex items-start justify-between gap-1.5" style={{ position: "relative" }}>
                          <div className="flex-1">
                            {/* Show action as main content - editable if in edit mode */}
                            {editingStepIndex === ratingIndex ? (
                              <Textarea
                                value={editedStepContent}
                                onChange={(e) => setEditedStepContent(e.target.value)}
                                className="text-xs min-h-[60px] resize-none"
                                placeholder="Edit the step description..."
                                autoFocus
                              />
                            ) : (
                              stepAction && (
                                <p className="text-xs text-foreground leading-relaxed">
                                  {stepAction}
                                </p>
                              )
                            )}
                          </div>
                          <div 
                            className="flex items-center gap-1"
                            style={{ 
                              position: "relative", 
                              zIndex: 9999, 
                              pointerEvents: "auto",
                              flexShrink: 0
                            }}
                          >
                            {editingStepIndex === ratingIndex ? (
                              // Save/Cancel buttons when editing
                              <>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleSaveEdit(ratingIndex, step)}
                                  disabled={stepEditStatus?.[ratingIndex] === "loading"}
                                  className="h-7 w-7 p-0 hover:bg-success/20 text-success"
                                  title="Save changes"
                                >
                                  <Save className="w-3.5 h-3.5" />
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  onClick={handleCancelEdit}
                                  disabled={stepEditStatus?.[ratingIndex] === "loading"}
                                  className="h-7 w-7 p-0 hover:bg-destructive/20 text-destructive"
                                  title="Cancel editing"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </Button>
                                {stepEditStatus?.[ratingIndex] === "loading" && (
                                  <span className="text-xs text-muted-foreground">Saving...</span>
                                )}
                                {stepEditStatus?.[ratingIndex] === "success" && (
                                  <span className="text-xs text-success">✓ Saved</span>
                                )}
                                {stepEditStatus?.[ratingIndex] === "error" && (
                                  <span className="text-xs text-destructive">✕ Error</span>
                                )}
                              </>
                            ) : (
                              // Edit button and rating buttons when not editing
                              <>
                                {incidentId && onStepEdit && (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => handleEditClick(ratingIndex, stepAction)}
                                    className="h-7 w-7 p-0 hover:bg-primary/20 text-primary"
                                    title="Edit this step"
                                  >
                                    <Edit className="w-3.5 h-3.5" />
                                  </Button>
                                )}
                                {incidentId && onRatingChange && (
                                  <StepRatingButtons
                                    stepIndex={ratingIndex}
                                    rating={resolutionRatings?.[ratingIndex] ?? null}
                                    ratingStatus={ratingStatus?.[ratingIndex]}
                                    onRatingChange={onRatingChange}
                                    stepTitle={stepAction || stepTitle}
                                  />
                                )}
                              </>
                            )}
                          </div>
                        </div>
                        {hasCommands && (
                          <div className="mt-1 space-y-1">
                            <div className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Terminal className="w-2.5 h-2.5" />
                              <span>Commands:</span>
                            </div>
                            {stepCommands.map((cmd: string, cmdIdx: number) => (
                              <pre
                                key={cmdIdx}
                                className="text-xs bg-black/20 border border-border/30 rounded p-1.5 overflow-x-auto"
                              >
                                <code className="text-primary">{cmd}</code>
                              </pre>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-3 text-muted-foreground">
                <AlertTriangle className="w-6 h-6 mx-auto mb-1.5 opacity-50" />
                <p className="text-xs">No resolution recommendations available</p>
                <p className="text-xs mt-0.5">
                  Resolution data may be incomplete
                </p>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Rollback Plan - Compact */}
      {hasRollbackPlan && (
        <Card className="p-2.5 bg-warning/5 border-warning/20">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-warning" />
              Rollback Plan
            </h3>

            {/* If rollback_plan is a string */}
            {rollbackPlanText && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {rollbackPlanText}
              </p>
            )}

            {/* If rollback_plan is an object with steps */}
            {rollbackPlanSteps && rollbackPlanSteps.length > 0 && (
              <>
                <div className="space-y-1.5">
                  {rollbackPlanSteps.map((step: string, index: number) => {
                    const stepCommands =
                      rollbackPlanCommands[index] ||
                      rollbackPlanCommands[index.toString()] ||
                      [];
                    const hasCommands = stepCommands && stepCommands.length > 0;

                    return (
                      <div
                        key={index}
                        className="bg-background/50 border border-warning/30 rounded-lg p-2"
                      >
                        <div className="flex items-start gap-1.5">
                          <span className="flex-shrink-0 w-4 h-4 rounded-full bg-warning/20 text-warning flex items-center justify-center text-xs font-bold">
                            {index + 1}
                          </span>
                          <div className="flex-1">
                            <p className="text-xs text-foreground leading-relaxed">
                              {step}
                            </p>
                            {hasCommands && (
                              <div className="mt-1 space-y-1">
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                  <Terminal className="w-2.5 h-2.5" />
                                  <span>Rollback Commands:</span>
                                </div>
                                {stepCommands.map(
                                  (cmd: string, cmdIdx: number) => (
                                    <pre
                                      key={cmdIdx}
                                      className="text-xs bg-black/20 border border-border/30 rounded p-1.5 overflow-x-auto"
                                    >
                                      <code className="text-warning">
                                        {cmd}
                                      </code>
                                    </pre>
                                  ),
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Show additional rollback plan metadata if available */}
                {typeof rollbackPlan === "object" && rollbackPlan !== null && (
                  <div className="space-y-1.5 pt-1.5 border-t border-warning/20">
                    {rollbackPlan.preconditions &&
                      rollbackPlan.preconditions.length > 0 && (
                        <div className="text-xs text-muted-foreground">
                          <span className="font-semibold">Preconditions: </span>
                          <span>{rollbackPlan.preconditions.join(", ")}</span>
                        </div>
                      )}
                    {rollbackPlan.triggers &&
                      rollbackPlan.triggers.length > 0 && (
                        <div className="text-xs text-muted-foreground">
                          <span className="font-semibold">Triggers: </span>
                          <span>{rollbackPlan.triggers.join(", ")}</span>
                        </div>
                      )}
                  </div>
                )}
              </>
            )}
          </div>
        </Card>
      )}

      {/* Navigation Buttons - Compact */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          onClick={onBack}
          className="bg-secondary hover:bg-secondary/80 text-xs py-1.5 px-3"
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
          Back
        </Button>
        <Button
          size="sm"
          onClick={handleMarkCompleteClick}
          className="bg-success hover:bg-success/90 text-success-foreground text-xs py-1.5 px-3"
        >
          Mark as Complete
          <CheckCircle className="w-3.5 h-3.5 ml-1.5" />
        </Button>
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialogOpen} onOpenChange={setConfirmDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-success" />
              Confirm Resolution Completion
            </DialogTitle>
            <DialogDescription>
              Confirm that all resolution steps have been executed successfully.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="p-4 bg-success/10 border border-success/30 rounded-lg">
              <div className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold text-foreground mb-1">
                    Ready to Mark Complete
                  </div>
                  <div className="text-sm text-muted-foreground">
                    You have reviewed {stepsArray.length} resolution step
                    {stepsArray.length !== 1 ? "s" : ""}.
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold text-sm text-foreground">
                Before marking complete, ensure:
              </h4>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                  <span>All resolution steps have been executed</span>
                </li>
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                  <span>The alert condition has been resolved</span>
                </li>
                <li className="flex items-start gap-2">
                  <Check className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                  <span>System is stable and monitoring confirms recovery</span>
                </li>
                {rollbackPlan && (
                  <li className="flex items-start gap-2">
                    <Check className="w-4 h-4 text-success flex-shrink-0 mt-0.5" />
                    <span>Rollback plan has been noted for potential use</span>
                  </li>
                )}
              </ul>
            </div>

            {/* Removed: Risk level warning in confirmation dialog (deprecated field) */}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => setConfirmDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmComplete}
              className="bg-success hover:bg-success/90"
            >
              <CheckCircle className="w-4 h-4 mr-2" />
              Confirm Complete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
