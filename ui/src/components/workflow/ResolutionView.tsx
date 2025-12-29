import { ArrowLeft, CheckCircle, ArrowRight, Clock, AlertTriangle, Brain, Info, Terminal, Shield, Check } from "lucide-react";
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

interface ResolutionViewProps {
  data: any;
  onBack: () => void;
  onMarkComplete: () => void;
}

export const ResolutionView = ({ data, onBack, onMarkComplete }: ResolutionViewProps) => {
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  
  // Debug logging
  console.log("ResolutionView - Received data:", data);
  
  const resolution = data.resolution || data;
  const steps = resolution.resolution_steps || resolution.steps || data.resolution_steps || [];
  const riskLevel = resolution.risk_level || "unknown";
  const estimatedTime = resolution.estimated_time_minutes || resolution.estimated_duration;
  const confidence = resolution.confidence;
  const reasoning = resolution.reasoning;
  const rollbackPlan = resolution.rollback_plan;
  const commands = resolution.commands_by_step || {};
  
  console.log("ResolutionView - Extracted:", {
    stepsCount: steps.length,
    steps: steps,
    riskLevel,
    estimatedTime,
    confidence,
    hasRollbackPlan: !!rollbackPlan,
    rollbackPlanType: typeof rollbackPlan
  });
  
  // Handle rollback_plan - it can be a string or an object
  const rollbackPlanSteps = typeof rollbackPlan === 'object' && rollbackPlan !== null 
    ? (rollbackPlan.steps || [])
    : null;
  const rollbackPlanCommands = typeof rollbackPlan === 'object' && rollbackPlan !== null
    ? (rollbackPlan.commands_by_step || {})
    : {};
  const rollbackPlanText = typeof rollbackPlan === 'string' ? rollbackPlan : null;
  const hasRollbackPlan = rollbackPlan !== null && rollbackPlan !== undefined;
  
  const handleMarkCompleteClick = () => {
    setConfirmDialogOpen(true);
  };

  const handleConfirmComplete = () => {
    setConfirmDialogOpen(false);
    onMarkComplete();
  };
  
  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case "low":
        return "text-success border-success/30 bg-success/10";
      case "medium":
        return "text-warning border-warning/30 bg-warning/10";
      case "high":
        return "text-destructive border-destructive/30 bg-destructive/10";
      default:
        return "text-muted-foreground border-border/30 bg-secondary/10";
    }
  };

  return (
    <div className="space-y-6">
      {/* Success Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-success" />
            Resolution Generated
          </h2>
        </div>
        
        {/* Key Metrics */}
        <div className="flex gap-4">
          {estimatedTime && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/10 border border-primary/20">
              <Clock className="w-4 h-4 text-primary" />
              <span className="text-sm">
                <span className="font-semibold text-primary">{estimatedTime}</span>
                <span className="text-muted-foreground ml-1">min</span>
              </span>
            </div>
          )}
          
          {riskLevel && riskLevel !== "unknown" && (
            <div className={cn("flex items-center gap-2 px-3 py-2 rounded-lg border", getRiskColor(riskLevel))}>
              <AlertTriangle className="w-4 h-4" />
              <span className="text-sm font-semibold uppercase">{riskLevel} Risk</span>
            </div>
          )}
          
          {confidence && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-success/10 border border-success/20">
              <Brain className="w-4 h-4 text-success" />
              <span className="text-sm">
                <span className="font-semibold text-success">{Math.round(confidence * 100)}%</span>
                <span className="text-muted-foreground ml-1">Confidence</span>
              </span>
            </div>
          )}
        </div>
      </div>

      {/* AI Reasoning */}
      {reasoning && (
        <Card className="p-4 bg-primary/5 border-primary/20">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-foreground mb-1">AI Reasoning</h4>
              <p className="text-sm text-muted-foreground leading-relaxed">{reasoning}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Resolution Steps */}
      <Card className="p-6 glass-card glow-border">
        <div className="space-y-4">
          <h3 className="font-semibold text-foreground flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-success" />
            Resolution Steps
          </h3>
          <div className="space-y-3">
            {steps && steps.length > 0 ? (
              steps.map((step: string, index: number) => {
              const stepCommands = commands[index] || commands[index.toString()] || [];
              const hasCommands = stepCommands && stepCommands.length > 0;
              
              return (
                <div key={index} className="bg-background/50 border border-border/30 rounded-lg p-4 hover:border-primary/30 transition-colors">
                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold">
                      {index + 1}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm text-foreground leading-relaxed">{step}</p>
                      
                      {hasCommands && (
                        <div className="mt-3 space-y-2">
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Terminal className="w-3 h-3" />
                            <span>Commands:</span>
                          </div>
                          {stepCommands.map((cmd: string, cmdIdx: number) => (
                            <pre key={cmdIdx} className="text-xs bg-black/20 border border-border/30 rounded p-2 overflow-x-auto">
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
              <div className="text-center py-8 text-muted-foreground">
                <AlertTriangle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>No resolution steps available</p>
                <p className="text-xs mt-1">Resolution data may be incomplete</p>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Rollback Plan */}
      {hasRollbackPlan && (
        <Card className="p-6 bg-warning/5 border-warning/20">
          <div className="space-y-4">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              <Shield className="w-5 h-5 text-warning" />
              Rollback Plan
            </h3>
            
            {/* If rollback_plan is a string */}
            {rollbackPlanText && (
              <p className="text-sm text-muted-foreground leading-relaxed">{rollbackPlanText}</p>
            )}
            
            {/* If rollback_plan is an object with steps */}
            {rollbackPlanSteps && rollbackPlanSteps.length > 0 && (
              <div className="space-y-3">
                <div className="space-y-2">
                  {rollbackPlanSteps.map((step: string, index: number) => {
                    const stepCommands = rollbackPlanCommands[index] || rollbackPlanCommands[index.toString()] || [];
                    const hasCommands = stepCommands && stepCommands.length > 0;
                    
                    return (
                      <div key={index} className="bg-background/50 border border-warning/30 rounded-lg p-3">
                        <div className="flex items-start gap-3">
                          <span className="flex-shrink-0 w-5 h-5 rounded-full bg-warning/20 text-warning flex items-center justify-center text-xs font-bold">
                            {index + 1}
                          </span>
                          <div className="flex-1">
                            <p className="text-sm text-foreground leading-relaxed">{step}</p>
                            
                            {hasCommands && (
                              <div className="mt-2 space-y-1">
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <Terminal className="w-3 h-3" />
                                  <span>Rollback Commands:</span>
                                </div>
                                {stepCommands.map((cmd: string, cmdIdx: number) => (
                                  <pre key={cmdIdx} className="text-xs bg-black/20 border border-border/30 rounded p-2 overflow-x-auto">
                                    <code className="text-warning">{cmd}</code>
                                  </pre>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                
                {/* Show additional rollback plan metadata if available */}
                {typeof rollbackPlan === 'object' && rollbackPlan !== null && (
                  <div className="space-y-2 pt-3 border-t border-warning/20">
                    {rollbackPlan.estimated_time_minutes && (
                      <div className="text-xs text-muted-foreground">
                        <span className="font-semibold">Estimated Rollback Time:</span> {rollbackPlan.estimated_time_minutes} minutes
                      </div>
                    )}
                    {rollbackPlan.preconditions && rollbackPlan.preconditions.length > 0 && (
                      <div className="text-xs text-muted-foreground">
                        <span className="font-semibold">Preconditions:</span>
                        <ul className="list-disc list-inside mt-1">
                          {rollbackPlan.preconditions.map((precondition: string, idx: number) => (
                            <li key={idx}>{precondition}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {rollbackPlan.triggers && rollbackPlan.triggers.length > 0 && (
                      <div className="text-xs text-muted-foreground">
                        <span className="font-semibold">Rollback Triggers:</span>
                        <ul className="list-disc list-inside mt-1">
                          {rollbackPlan.triggers.map((trigger: string, idx: number) => (
                            <li key={idx}>{trigger}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      )}


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
          onClick={handleMarkCompleteClick}
          className="bg-success hover:bg-success/90 text-success-foreground"
        >
          Mark as Complete
          <CheckCircle className="w-4 h-4 ml-2" />
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
                    You have reviewed {steps.length} resolution step{steps.length !== 1 ? 's' : ''}.
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <h4 className="font-semibold text-sm text-foreground">Before marking complete, ensure:</h4>
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

            {riskLevel && riskLevel !== "unknown" && riskLevel.toLowerCase() !== "low" && (
              <div className="p-4 bg-warning/10 border border-warning/30 rounded-lg">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-semibold text-warning mb-1">
                      {riskLevel.toUpperCase()} Risk Resolution
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Monitor the system closely for the next {estimatedTime ? `${estimatedTime * 2} minutes` : '30 minutes'} to ensure stability.
                    </div>
                  </div>
                </div>
              </div>
            )}
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

