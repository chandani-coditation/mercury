import React, { useState } from "react";
import TriageReviewForm from "./TriageReviewForm";
import ResolutionReviewForm from "./ResolutionReviewForm";
import "./PendingActionCard.css";

const PendingActionCard = ({ action, onRespond, loading }) => {
  const [showForm, setShowForm] = useState(true);

  if (!action) return null;

  const handleSubmit = async (payload) => {
    await onRespond(payload);
    setShowForm(false);
  };

  const renderForm = () => {
    if (!showForm) {
      return (
        <div className="action-complete">
          <p>Thanks! Response submitted. Awaiting agent update...</p>
        </div>
      );
    }
    if (action.action_type === "review_triage") {
      return (
        <TriageReviewForm
          triage={action.payload?.triage_output || {}}
          onSubmit={handleSubmit}
          loading={loading}
          actionName={action.action_name}
        />
      );
    }
    if (action.action_type === "review_resolution") {
      return (
        <ResolutionReviewForm
          resolution={action.payload?.resolution || {}}
          onSubmit={handleSubmit}
          loading={loading}
          actionName={action.action_name}
        />
      );
    }
    return (
      <div className="unsupported-action">
        <p>
          Action <strong>{action.action_type}</strong> is not yet supported in
          the UI.
        </p>
        <button
          type="button"
          className="btn-secondary"
          onClick={() =>
            handleSubmit({
              approved: true,
              notes: "Approved (default handler)",
            })
          }
        >
          Approve Anyway
        </button>
      </div>
    );
  };

  return (
    <section className="detail-section hitl-action-card">
      <div className="hitl-action-header">
        <div>
          <h2>Pending Action</h2>
          <p>{action.description}</p>
        </div>
        <div className="action-meta">
          <span className="action-name">{action.action_name}</span>
          <span className="action-type">{action.action_type}</span>
        </div>
      </div>
      {renderForm()}
    </section>
  );
};

export default PendingActionCard;

