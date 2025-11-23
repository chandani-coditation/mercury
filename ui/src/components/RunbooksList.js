import React, { useState, useEffect } from "react";
import { useToast } from "../context/ToastContext";
import Button from "./common/Button";
import LoadingSkeleton, { ListSkeleton } from "./common/LoadingSkeleton";
import InlineEditableField from "./common/InlineEditableField";
import "./RunbooksList.css";

const RunbooksList = () => {
  const [runbooks, setRunbooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newRunbook, setNewRunbook] = useState({
    title: "",
    service: "",
    component: "",
    content: "",
  });
  const toast = useToast();

  const loadRunbooks = async () => {
    setLoading(true);
    try {
      const ingestionBase = process.env.REACT_APP_INGESTION_URL || "http://localhost:8002";
      const response = await fetch(`${ingestionBase}/documents?doc_type=runbook`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setRunbooks(data.documents || []);
    } catch (err) {
      toast.error(`Failed to load runbooks: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRunbooks();
  }, []);

  const handleDelete = async (runbookId, title) => {
    if (!window.confirm(`Are you sure you want to delete "${title}"? This will also remove all associated embeddings and chunks.`)) {
      return;
    }

    try {
      const ingestionBase = process.env.REACT_APP_INGESTION_URL || "http://localhost:8002";
      const response = await fetch(`${ingestionBase}/documents/${runbookId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      toast.success("Runbook deleted successfully");
      loadRunbooks();
    } catch (err) {
      toast.error(`Failed to delete runbook: ${err.message}`);
    }
  };

  const handleAdd = async () => {
    try {
      const ingestionBase = process.env.REACT_APP_INGESTION_URL || "http://localhost:8002";
      const response = await fetch(`${ingestionBase}/ingest/runbook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newRunbook.title,
          service: newRunbook.service || null,
          component: newRunbook.component || null,
          content: newRunbook.content,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      toast.success("Runbook created successfully");
      setShowAddForm(false);
      setNewRunbook({ title: "", service: "", component: "", content: "" });
      loadRunbooks();
    } catch (err) {
      toast.error(`Failed to create runbook: ${err.message}`);
    }
  };

  if (loading) {
    return <ListSkeleton count={5} />;
  }

  return (
    <div className="runbooks-list">
      <div className="runbooks-header">
        <h2>Runbooks Library</h2>
        <Button
          variant="primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          {showAddForm ? "Cancel" : "+ New Runbook"}
        </Button>
      </div>

      {showAddForm && (
        <div className="runbook-form-card">
          <h3>Create New Runbook</h3>
          <div className="runbook-form">
            <div className="form-row">
              <label>Title</label>
              <input
                type="text"
                value={newRunbook.title}
                onChange={(e) =>
                  setNewRunbook({ ...newRunbook, title: e.target.value })
                }
                placeholder="Runbook title"
              />
            </div>
            <div className="form-row">
              <label>Service (optional)</label>
              <input
                type="text"
                value={newRunbook.service}
                onChange={(e) =>
                  setNewRunbook({ ...newRunbook, service: e.target.value })
                }
                placeholder="e.g., api-gateway"
              />
            </div>
            <div className="form-row">
              <label>Component (optional)</label>
              <input
                type="text"
                value={newRunbook.component}
                onChange={(e) =>
                  setNewRunbook({ ...newRunbook, component: e.target.value })
                }
                placeholder="e.g., gateway"
              />
            </div>
            <div className="form-row">
              <label>Content</label>
              <textarea
                value={newRunbook.content}
                onChange={(e) =>
                  setNewRunbook({ ...newRunbook, content: e.target.value })
                }
                placeholder="Runbook content (markdown or plain text)"
                rows={10}
              />
            </div>
            <div className="form-actions">
              <Button variant="primary" onClick={handleAdd}>
                Create Runbook
              </Button>
              <Button variant="ghost" onClick={() => setShowAddForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {runbooks.length === 0 ? (
        <div className="empty-state">
          <p>No runbooks found. Create your first runbook to get started.</p>
        </div>
      ) : (
        <div className="runbooks-grid">
          {runbooks.map((runbook) => (
            <div key={runbook.id} className="runbook-card">
              <div className="runbook-card-header">
                <h3>{runbook.title}</h3>
                <div className="runbook-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(runbook.id, runbook.title)}
                    title="Delete runbook (will remove embeddings)"
                  >
                    Delete
                  </Button>
                </div>
              </div>
              <div className="runbook-meta">
                {runbook.service && (
                  <span className="meta-tag">Service: {runbook.service}</span>
                )}
                {runbook.component && (
                  <span className="meta-tag">Component: {runbook.component}</span>
                )}
                <span className="meta-date">
                  Created: {new Date(runbook.created_at).toLocaleDateString()}
                </span>
                {runbook.last_reviewed_at && (
                  <span className="meta-date">
                    Last reviewed: {new Date(runbook.last_reviewed_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="runbook-readonly-notice">
                <span className="readonly-badge">Read-only</span>
                <span className="readonly-text">
                  Runbooks are read-only after creation to preserve embeddings. Delete and re-upload to make changes.
                </span>
              </div>
              <div className="runbook-content">
                <pre>{runbook.content}</pre>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RunbooksList;

