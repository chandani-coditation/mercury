import React from "react";
import "./ProgressStepper.css";

const DEFAULT_STEPS = [
  "initialized",
  "retrieving_context",
  "context_retrieved",
  "calling_llm",
  "llm_completed",
  "validating",
  "validation_complete",
  "policy_evaluating",
  "policy_evaluated",
  "paused_for_review",
  "resumed_from_review",
  "storing",
  "completed",
];

const labelMap = {
  initialized: "Initialized",
  retrieving_context: "Retrieving Context",
  context_retrieved: "Context Ready",
  calling_llm: "Calling LLM",
  llm_completed: "LLM Complete",
  validating: "Validating",
  validation_complete: "Validated",
  policy_evaluating: "Policy Evaluating",
  policy_evaluated: "Policy Evaluated",
  paused_for_review: "Waiting for Review",
  resumed_from_review: "Resumed",
  storing: "Storing",
  completed: "Completed",
  error: "Error",
};

const ProgressStepper = ({
  currentStep,
  steps = DEFAULT_STEPS,
  connectionStatus,
}) => {
  if (!currentStep) return null;
  const stepIndex = steps.indexOf(currentStep);

  return (
    <div className="progress-stepper">
      <div className="progress-status">
        <span className={`connection-dot status-${connectionStatus || "idle"}`} />
        <span className="status-label">
          {connectionStatus === "open"
            ? "Live"
            : connectionStatus === "connecting"
            ? "Connecting..."
            : connectionStatus === "error"
            ? "Connection Error"
            : "Offline"}
        </span>
        <span className="current-step-label">
          {labelMap[currentStep] || currentStep}
        </span>
      </div>
      <div className="progress-track">
        {steps.map((step, index) => {
          const isCompleted = stepIndex > index;
          const isActive = stepIndex === index;
          return (
            <div
              key={step}
              className={`progress-step ${
                isCompleted ? "completed" : isActive ? "active" : ""
              }`}
            >
              <div className="step-dot" />
              <span className="step-label">{labelMap[step] || step}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ProgressStepper;

