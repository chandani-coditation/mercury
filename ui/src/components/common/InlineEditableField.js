import React, { useCallback, useEffect, useState } from "react";
import Button from "./Button";
import "./InlineEditableField.css";

const InlineEditableField = ({
  label,
  value,
  onChange = () => {},
  placeholder = "Click edit to update",
  multiline = false,
  rows = 3,
  maxLength,
  disabled = false,
  error,
  className = "",
}) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => {
    if (!editing) {
      setDraft(value || "");
    }
  }, [value, editing]);

  const handleSave = useCallback((e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    onChange(draft);
    setEditing(false);
  }, [draft, onChange]);

  const handleCancel = useCallback(() => {
    setDraft(value || "");
    setEditing(false);
  }, [value]);

  return (
    <div
      className={[
        "inline-edit-field",
        editing && "inline-edit-field--editing",
        error && "inline-edit-field--error",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="inline-edit-field__header">
        <label>{label}</label>
        <div className="inline-edit-field__actions">
          {editing ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="primary"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleSave(e);
                }}
                disabled={disabled}
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={handleCancel}
                disabled={disabled}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setEditing(true)}
              disabled={disabled}
            >
              Edit
            </Button>
          )}
        </div>
      </div>

      <div className="inline-edit-field__body">
        {editing ? (
          multiline ? (
            <textarea
              rows={rows}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={maxLength}
            />
          ) : (
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={maxLength}
            />
          )
        ) : (
          <p className={value ? "field-value" : "field-value placeholder"}>
            {value || placeholder}
          </p>
        )}
      </div>
      {error && <span className="inline-edit-field__error">{error}</span>}
    </div>
  );
};

export default InlineEditableField;

