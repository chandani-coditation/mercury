import React, { useMemo, useState, useEffect } from "react";
import "./HITLForms.css";
import DiffView, { DiffViewArray } from "../common/DiffView";
import Button from "../common/Button";
import InlineEditableField from "../common/InlineEditableField";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";

const defaultArray = (value) =>
  Array.isArray(value) && value.length > 0 ? value : [""];

const TriageReviewForm = ({
  triage = {},
  onSubmit,
  loading,
  actionName,
  onCancel,
}) => {
  const initialState = useMemo(
    () => ({
      severity: triage.severity || "medium",
      category: triage.category || "other",
      confidence:
        triage.confidence !== undefined ? triage.confidence : 0.7,
      summary: triage.summary || "",
      likely_cause: triage.likely_cause || "",
      affected_services: defaultArray(triage.affected_services),
      recommended_actions: defaultArray(triage.recommended_actions),
      notes: "",
      policy_band: "AUTO",
    }),
    [triage]
  );

  const {
    value: formState,
    setValue: setFormState,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useUndoRedo(initialState, 50);
  const [errors, setErrors] = useState({});
  const [showDiff, setShowDiff] = useState(false);

  // Keyboard shortcuts for undo/redo
  useKeyboardShortcuts(
    {
      "ctrl+z": (e) => {
        e.preventDefault();
        if (canUndo) undo();
      },
      "ctrl+shift+z": (e) => {
        e.preventDefault();
        if (canRedo) redo();
      },
      "ctrl+y": (e) => {
        e.preventDefault();
        if (canRedo) redo();
      },
    },
    true
  );

  // Update undo/redo history when form state changes
  useEffect(() => {
    // This will be handled by setFormState from useUndoRedo
  }, [formState]);

  const validateField = (field, value) => {
    const fieldErrors = {};
    if (field === "confidence" && (value < 0 || value > 1)) {
      fieldErrors.confidence = "Confidence must be between 0 and 1";
    }
    if (field === "summary" && !value.trim()) {
      fieldErrors.summary = "Summary is required";
    }
    setErrors((prev) => ({ ...prev, ...fieldErrors }));
    return Object.keys(fieldErrors).length === 0;
  };

  const handleFieldChange = (field, value) => {
    validateField(field, value);
    setFormState((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleArrayChange = (field, index, value) => {
    setFormState((prev) => {
      const copy = [...prev[field]];
      copy[index] = value;
      return { ...prev, [field]: copy };
    });
  };

  const handleAddArrayItem = (field) => {
    setFormState((prev) => ({
      ...prev,
      [field]: [...prev[field], ""],
    }));
  };

  const handleRemoveArrayItem = (field, index) => {
    setFormState((prev) => {
      const copy = [...prev[field]];
      if (copy.length > 1) {
        copy.splice(index, 1);
      } else {
        copy[index] = "";
      }
      return { ...prev, [field]: copy };
    });
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    
    // Validate all fields
    const allErrors = {};
    if (!formState.summary.trim()) {
      allErrors.summary = "Summary is required";
    }
    const confidence = Number(formState.confidence);
    if (isNaN(confidence) || confidence < 0 || confidence > 1) {
      allErrors.confidence = "Confidence must be between 0 and 1";
    }
    
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      return;
    }
    
    const payload = {
      severity: formState.severity,
      category: formState.category,
      confidence: confidence,
      summary: formState.summary,
      likely_cause: formState.likely_cause,
      affected_services: formState.affected_services.filter(Boolean),
      recommended_actions: formState.recommended_actions.filter(Boolean),
    };
    onSubmit({
      approved: true,
      user_edited: {
        ...triage,
        ...payload,
      },
      notes:
        formState.notes ||
        `Approved via HITL action ${actionName || ""}`.trim(),
      policy_band: formState.policy_band,
    });
  };

  const hasChanges = useMemo(() => {
    return (
      formState.severity !== (triage.severity || "medium") ||
      formState.category !== (triage.category || "other") ||
      formState.confidence !== (triage.confidence !== undefined ? triage.confidence : 0.7) ||
      formState.summary !== (triage.summary || "") ||
      formState.likely_cause !== (triage.likely_cause || "") ||
      JSON.stringify(formState.affected_services.filter(Boolean)) !== JSON.stringify(defaultArray(triage.affected_services).filter(Boolean)) ||
      JSON.stringify(formState.recommended_actions.filter(Boolean)) !== JSON.stringify(defaultArray(triage.recommended_actions).filter(Boolean))
    );
  }, [formState, triage]);

  return (
    <form className="hitl-form" onSubmit={handleSubmit}>
      {hasChanges && (
        <div className="hitl-form-diff-toggle">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowDiff(!showDiff)}
          >
            {showDiff ? "Hide" : "Show"} Changes
          </Button>
        </div>
      )}

      {showDiff && hasChanges && (
        <div className="hitl-form-diff-section">
          <h4 className="diff-section-title">Changes Preview</h4>
          <div className="diff-fields">
            {formState.summary !== (triage.summary || "") && (
              <div className="diff-field">
                <label>Summary</label>
                <DiffView
                  original={triage.summary || ""}
                  modified={formState.summary}
                />
              </div>
            )}
            {formState.likely_cause !== (triage.likely_cause || "") && (
              <div className="diff-field">
                <label>Likely Cause</label>
                <DiffView
                  original={triage.likely_cause || ""}
                  modified={formState.likely_cause}
                />
              </div>
            )}
            {JSON.stringify(formState.affected_services.filter(Boolean)) !== JSON.stringify(defaultArray(triage.affected_services).filter(Boolean)) && (
              <div className="diff-field">
                <label>Affected Services</label>
                <DiffViewArray
                  original={defaultArray(triage.affected_services).filter(Boolean)}
                  modified={formState.affected_services.filter(Boolean)}
                />
              </div>
            )}
            {JSON.stringify(formState.recommended_actions.filter(Boolean)) !== JSON.stringify(defaultArray(triage.recommended_actions).filter(Boolean)) && (
              <div className="diff-field">
                <label>Recommended Actions</label>
                <DiffViewArray
                  original={defaultArray(triage.recommended_actions).filter(Boolean)}
                  modified={formState.recommended_actions.filter(Boolean)}
                />
              </div>
            )}
            {formState.severity !== (triage.severity || "medium") && (
              <div className="diff-field">
                <label>Severity</label>
                <DiffView
                  original={triage.severity || "medium"}
                  modified={formState.severity}
                />
              </div>
            )}
            {formState.confidence !== (triage.confidence !== undefined ? triage.confidence : 0.7) && (
              <div className="diff-field">
                <label>Confidence</label>
                <DiffView
                  original={String(triage.confidence !== undefined ? triage.confidence : 0.7)}
                  modified={String(formState.confidence)}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="hitl-form-section">
        <h3 className="form-section-title">Basic Information</h3>
        <div className="hitl-form-grid">
        <div className="form-group">
          <label>Severity</label>
          <select
            value={formState.severity}
            onChange={(e) => handleFieldChange("severity", e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        <div className="form-group">
          <label>Category</label>
          <select
            value={formState.category}
            onChange={(e) => handleFieldChange("category", e.target.value)}
          >
            <option value="database">Database</option>
            <option value="network">Network</option>
            <option value="application">Application</option>
            <option value="infrastructure">Infrastructure</option>
            <option value="security">Security</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div className="form-group">
          <label>Confidence</label>
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={formState.confidence}
            onChange={(e) => handleFieldChange("confidence", e.target.value)}
            className={errors.confidence ? "error" : ""}
          />
          {errors.confidence && <span className="error-message">{errors.confidence}</span>}
        </div>
        <div className="form-group">
          <label>Policy Band</label>
          <select
            value={formState.policy_band}
            onChange={(e) => handleFieldChange("policy_band", e.target.value)}
          >
            <option value="AUTO">AUTO</option>
            <option value="PROPOSE">PROPOSE</option>
            <option value="REVIEW">REVIEW</option>
          </select>
        </div>
      </div>
      </div>

      <div className="hitl-form-section">
        <h3 className="form-section-title">Analysis Details</h3>
        <InlineEditableField
          label="Summary"
          value={formState.summary}
          onChange={(val) => handleFieldChange("summary", val)}
          multiline
          rows={4}
          placeholder="Summarize the triage findings..."
          error={errors.summary}
        />

        <InlineEditableField
          label="Likely Cause"
          value={formState.likely_cause}
          onChange={(val) => handleFieldChange("likely_cause", val)}
          multiline
          rows={3}
          placeholder="Describe the probable root cause..."
        />
      </div>

      <div className="hitl-form-section">
        <h3 className="form-section-title">Impact & Actions</h3>
        <div className="form-group">
          <label>Affected Services</label>
        {formState.affected_services.map((svc, index) => (
          <div className="array-input-row" key={`svc-${index}`}>
            <input
              type="text"
              value={svc}
              onChange={(e) =>
                handleArrayChange("affected_services", index, e.target.value)
              }
              placeholder="service-name"
            />
            <button
              type="button"
              className="btn-small"
              onClick={() => handleRemoveArrayItem("affected_services", index)}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleAddArrayItem("affected_services")}
        >
          + Add service
        </button>
        </div>

        <div className="form-group">
          <label>Recommended Actions</label>
        {formState.recommended_actions.map((action, index) => (
          <div className="array-input-row" key={`action-${index}`}>
            <input
              type="text"
              value={action}
              onChange={(e) =>
                handleArrayChange("recommended_actions", index, e.target.value)
              }
              placeholder="Action description"
            />
            <button
              type="button"
              className="btn-small"
              onClick={() => handleRemoveArrayItem("recommended_actions", index)}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleAddArrayItem("recommended_actions")}
        >
          + Add action
        </button>
        </div>
      </div>

      <div className="hitl-form-section">
        <h3 className="form-section-title">Review Notes</h3>
        <InlineEditableField
          label="Reviewer Notes"
          value={formState.notes}
          onChange={(val) => handleFieldChange("notes", val)}
          multiline
          rows={3}
          placeholder="Add context about your review..."
        />
      </div>

      <div className="hitl-form-actions">
        <div className="hitl-form-undo-redo">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={undo}
            disabled={!canUndo || loading}
            tooltip={!canUndo ? "Nothing to undo" : "Undo (Ctrl+Z)"}
          >
            ↶ Undo
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={redo}
            disabled={!canRedo || loading}
            tooltip={!canRedo ? "Nothing to redo" : "Redo (Ctrl+Shift+Z)"}
          >
            ↷ Redo
          </Button>
        </div>
        <div className="hitl-form-submit-actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
          >
            {loading ? "Submitting..." : "Approve & Continue"}
          </button>
          {onCancel && (
            <button
              type="button"
              className="btn-secondary"
              onClick={onCancel}
              disabled={loading}
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </form>
  );
};

export default TriageReviewForm;

