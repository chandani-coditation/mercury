import React, { useMemo, useState, useEffect } from "react";
import "./HITLForms.css";
import Button from "../common/Button";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";
import InlineEditableField from "../common/InlineEditableField";

const defaultArray = (value) =>
  Array.isArray(value) && value.length > 0 ? value : [""];

const ResolutionReviewForm = ({
  resolution = {},
  onSubmit,
  loading,
  actionName,
  onCancel,
}) => {
  const initialState = useMemo(
    () => ({
      resolution_steps: defaultArray(resolution.resolution_steps),
      commands: defaultArray(resolution.commands),
      rollback_plan: defaultArray(resolution.rollback_plan),
      risk_level: resolution.risk_level || "medium",
      estimated_time_minutes: resolution.estimated_time_minutes || 30,
      notes: "",
      policy_band: resolution.policy_band || "AUTO",
    }),
    [resolution]
  );

  const {
    value: formState,
    setValue: setFormState,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useUndoRedo(initialState, 50);

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

  const handleFieldChange = (field, value) => {
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
    const payload = {
      resolution_steps: formState.resolution_steps.filter(Boolean),
      commands: formState.commands.filter(Boolean),
      rollback_plan: formState.rollback_plan.filter(Boolean),
      risk_level: formState.risk_level,
      estimated_time_minutes: Number(formState.estimated_time_minutes) || 0,
      requires_approval: formState.policy_band !== "AUTO",
    };
    onSubmit({
      approved: true,
      user_edited: {
        ...resolution,
        ...payload,
      },
      notes:
        formState.notes ||
        `Resolution reviewed via HITL action ${actionName || ""}`.trim(),
      policy_band: formState.policy_band,
    });
  };

  return (
    <form className="hitl-form" onSubmit={handleSubmit}>
      <div className="hitl-form-grid">
        <div className="form-group">
          <label>Risk Level</label>
          <select
            value={formState.risk_level}
            onChange={(e) => handleFieldChange("risk_level", e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        <div className="form-group">
          <label>Est. Time (minutes)</label>
          <input
            type="number"
            min="0"
            value={formState.estimated_time_minutes}
            onChange={(e) =>
              handleFieldChange("estimated_time_minutes", e.target.value)
            }
          />
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

      <div className="form-group">
        <label>Resolution Steps</label>
        {formState.resolution_steps.map((step, index) => (
          <div className="array-input-row" key={`step-${index}`}>
            <input
              type="text"
              value={step}
              onChange={(e) =>
                handleArrayChange("resolution_steps", index, e.target.value)
              }
              placeholder="Describe the step"
            />
            <button
              type="button"
              className="btn-small"
              onClick={() => handleRemoveArrayItem("resolution_steps", index)}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleAddArrayItem("resolution_steps")}
        >
          + Add step
        </button>
      </div>

      <div className="form-group">
        <label>Commands</label>
        {formState.commands.map((command, index) => (
          <div className="array-input-row" key={`command-${index}`}>
            <input
              type="text"
              value={command}
              onChange={(e) =>
                handleArrayChange("commands", index, e.target.value)
              }
              placeholder="Command snippet"
            />
            <button
              type="button"
              className="btn-small"
              onClick={() => handleRemoveArrayItem("commands", index)}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleAddArrayItem("commands")}
        >
          + Add command
        </button>
      </div>

      <div className="form-group">
        <label>Rollback Plan</label>
        {formState.rollback_plan.map((step, index) => (
          <div className="array-input-row" key={`rollback-${index}`}>
            <input
              type="text"
              value={step}
              onChange={(e) =>
                handleArrayChange("rollback_plan", index, e.target.value)
              }
              placeholder="Rollback step"
            />
            <button
              type="button"
              className="btn-small"
              onClick={() => handleRemoveArrayItem("rollback_plan", index)}
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => handleAddArrayItem("rollback_plan")}
        >
          + Add rollback step
        </button>
      </div>

      <InlineEditableField
        label="Reviewer Notes"
        value={formState.notes}
        onChange={(val) => handleFieldChange("notes", val)}
        multiline
        rows={3}
        placeholder="Add context about your review..."
      />

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
          <button type="submit" className="btn-primary" disabled={loading}>
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

export default ResolutionReviewForm;

