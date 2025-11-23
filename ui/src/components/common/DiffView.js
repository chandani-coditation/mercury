import React from "react";
import "./DiffView.css";

const DiffView = ({ original, modified, fieldName }) => {
  if (!original && !modified) return null;
  
  const originalText = original || "";
  const modifiedText = modified || "";
  
  // Simple diff: show original and modified side by side
  const hasChanges = originalText !== modifiedText;

  if (!hasChanges) {
    return (
      <div className="diff-view diff-view-unchanged">
        <span className="diff-value">{modifiedText || originalText || "—"}</span>
      </div>
    );
  }

  return (
    <div className="diff-view diff-view-changed">
      <div className="diff-side diff-side-original">
        <div className="diff-label">Original</div>
        <div className="diff-content diff-removed">
          {originalText || "—"}
        </div>
      </div>
      <div className="diff-arrow">→</div>
      <div className="diff-side diff-side-modified">
        <div className="diff-label">Modified</div>
        <div className="diff-content diff-added">
          {modifiedText || "—"}
        </div>
      </div>
    </div>
  );
};

export const DiffViewArray = ({ original = [], modified = [] }) => {
  const originalSet = new Set(original);
  const modifiedSet = new Set(modified);
  
  const added = modified.filter((item) => !originalSet.has(item));
  const removed = original.filter((item) => !modifiedSet.has(item));
  const unchanged = original.filter((item) => modifiedSet.has(item));

  if (added.length === 0 && removed.length === 0) {
    return (
      <div className="diff-view-array">
        {unchanged.map((item, idx) => (
          <span key={idx} className="diff-item diff-item-unchanged">
            {item}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="diff-view-array">
      {removed.map((item, idx) => (
        <span key={`removed-${idx}`} className="diff-item diff-item-removed">
          - {item}
        </span>
      ))}
      {unchanged.map((item, idx) => (
        <span key={`unchanged-${idx}`} className="diff-item diff-item-unchanged">
          {item}
        </span>
      ))}
      {added.map((item, idx) => (
        <span key={`added-${idx}`} className="diff-item diff-item-added">
          + {item}
        </span>
      ))}
    </div>
  );
};

export default DiffView;

