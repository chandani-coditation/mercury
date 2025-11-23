import React, { useState, useEffect, useMemo, useRef } from "react";
import "./IncidentList.css";
import Button from "./common/Button";
import { FixedSizeList as List } from "react-window";
import { ListSkeleton } from "./common/LoadingSkeleton";

function IncidentList({
  incidents,
  onSelect,
  onNewTriage,
  onResolveIncident,
  onBulkAction,
  loading,
  selectedIncidentId,
  page = 1,
  pageSize = 20,
  totalCount,
  onPageChange,
}) {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkMode, setBulkMode] = useState(false);
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [listHeight, setListHeight] = useState(600);
  const getPolicyBadgeClass = (band) => {
    switch (band) {
      case "AUTO":
        return "badge-auto";
      case "PROPOSE":
        return "badge-propose";
      case "REVIEW":
        return "badge-review";
      case "PENDING":
        return "badge-pending";
      default:
        return "badge-default";
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/A";
    return new Date(dateStr).toLocaleString();
  };

  const toggleSelect = (incidentId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(incidentId)) {
        next.delete(incidentId);
      } else {
        next.add(incidentId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === incidents.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(incidents.map((i) => i.id)));
    }
  };

  const handleBulkAction = async (action) => {
    if (selectedIds.size === 0) return;
    if (onBulkAction) {
      await onBulkAction(Array.from(selectedIds), action);
      setSelectedIds(new Set());
      setBulkMode(false);
    }
  };

  const exitBulkMode = () => {
    setSelectedIds(new Set());
    setBulkMode(false);
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleResize = () => {
      setListHeight(Math.max(window.innerHeight - 320, 360));
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const cardsPerRow = useMemo(() => {
    const width =
      containerWidth ||
      (typeof window !== "undefined" ? window.innerWidth : 1200);
    if (width >= 1500) return 3;
    if (width >= 900) return 2;
    return 1;
  }, [containerWidth]);

  const rowHeight = bulkMode ? 420 : 360;
  const shouldVirtualize = incidents.length > cardsPerRow * 6;
  const rowCount = Math.ceil(incidents.length / cardsPerRow);
  const listWidth = Math.max(containerWidth || 0, 320);

  useEffect(() => {
    if (
      !shouldVirtualize ||
      !containerRef.current ||
      typeof ResizeObserver === "undefined"
    )
      return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry?.contentRect?.width) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [shouldVirtualize]);

  const renderIncidentCard = (incident) => (
    <div
      key={incident.id}
      className={`incident-card ${
        selectedIncidentId === incident.id ? "selected" : ""
      } ${bulkMode && selectedIds.has(incident.id) ? "bulk-selected" : ""}`}
      onClick={() => {
        if (bulkMode) {
          toggleSelect(incident.id);
        } else {
          onSelect(incident);
        }
      }}
    >
      {bulkMode && (
        <div className="bulk-checkbox-overlay" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={selectedIds.has(incident.id)}
            onChange={() => toggleSelect(incident.id)}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
      <div className="card-header">
        <span className={`policy-badge ${getPolicyBadgeClass(incident.policy_band)}`}>
          {incident.policy_band || "PENDING"}
        </span>
        <span className="incident-id">
          #{incident.id?.substring(0, 8) || "00000000"}
        </span>
      </div>

      <div className="card-body">
        <h3 className="card-title">{incident.raw_alert?.title || "Untitled Alert"}</h3>

        <div className="card-meta">
          <span>{incident.raw_alert?.labels?.service || "unknown"}</span>
          <span>•</span>
          <span>{incident.raw_alert?.labels?.component || "n/a"}</span>
        </div>

        {incident.triage_output && (
          <div className="card-info">
            <div className="info-row">
              <span className="label">Severity:</span>
              <span
                className={`severity severity-${incident.triage_output.severity}`}
              >
                {incident.triage_output.severity}
              </span>
            </div>
            <div className="info-row">
              <span className="label">Category:</span>
              <span>{incident.triage_output.category}</span>
            </div>
            <div className="info-row">
              <span className="label">Confidence:</span>
              <span>
                {(incident.triage_output.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        )}

        <div className="status-tags">
          {incident.policy_decision?.requires_approval &&
            !incident.resolution_output && (
              <span className="card-badge pending">Awaiting approval</span>
            )}
          {incident.resolution_output && (
            <span className="card-badge resolved">✓ Resolved</span>
          )}
        </div>
      </div>

      <div className="quick-actions">
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            onSelect(incident);
          }}
        >
          View
        </Button>
        {!incident.resolution_output &&
          incident.policy_decision?.can_auto_apply && (
            <Button
              variant="primary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onResolveIncident?.(incident.id);
              }}
            >
              Auto Resolve
            </Button>
          )}
      </div>

      <div className="card-footer">
        <span className="card-date">{formatDate(incident.alert_received_at)}</span>
      </div>
    </div>
  );

  const VirtualRow = ({ index, style }) => {
    const start = index * cardsPerRow;
    const rowItems = incidents.slice(start, start + cardsPerRow);
    return (
      <div style={{ ...style, width: "100%" }}>
        <div className="incident-row">
          {rowItems.map((incident) => renderIncidentCard(incident))}
        </div>
      </div>
    );
  };

  if (loading && incidents.length === 0) {
    return (
      <div className="incident-list">
        <div className="list-header">
          <div>
            <h2>Incidents</h2>
            <p>Live alerts streamed into the HITL control room</p>
          </div>
        </div>
        <ListSkeleton count={6} />
      </div>
    );
  }

  return (
    <div className="incident-list">
      <div className="list-header">
        <div>
          <h2>Incidents</h2>
          <p>Live alerts streamed into the HITL control room</p>
        </div>
        <div className="list-actions">
          {bulkMode ? (
            <>
              <span className="bulk-count">
                {selectedIds.size} selected
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleBulkAction("approve")}
                disabled={selectedIds.size === 0}
                loading={loading}
              >
                Approve Selected
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleBulkAction("dismiss")}
                disabled={selectedIds.size === 0}
                loading={loading}
              >
                Dismiss Selected
              </Button>
              <Button variant="ghost" size="sm" onClick={exitBulkMode}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setBulkMode(true)}
              >
                Bulk Select
              </Button>
              <Button variant="primary" onClick={onNewTriage}>
                + New Triage
              </Button>
            </>
          )}
        </div>
      </div>

      {incidents.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📋</div>
          <h2>No incidents yet</h2>
          <p>Create a new triage to get started with AI-powered incident management</p>
          <Button variant="primary" onClick={onNewTriage} style={{ marginTop: "var(--spacing-4)" }}>
            + Create First Triage
          </Button>
        </div>
      ) : (
        <>
          {bulkMode && (
            <div className="bulk-select-header">
              <label className="bulk-checkbox">
                <input
                  type="checkbox"
                  checked={
                    selectedIds.size === incidents.length && incidents.length > 0
                  }
                  onChange={toggleSelectAll}
                />
                <span>Select All ({incidents.length})</span>
              </label>
            </div>
          )}
          {shouldVirtualize ? (
            <div className="incident-virtual-container" ref={containerRef}>
              <List
                height={listHeight}
                itemCount={rowCount}
                itemSize={rowHeight}
                width={listWidth}
              >
                {VirtualRow}
              </List>
            </div>
          ) : (
            <div className="incident-grid">
              {incidents.map((incident) => renderIncidentCard(incident))}
            </div>
          )}
          {onPageChange && (
            <div className="pagination">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onPageChange(page - 1)}
                disabled={page <= 1 || loading}
                tooltip={page <= 1 ? "Already on first page" : undefined}
              >
                ← Previous
              </Button>
              <span className="pagination-info">
                Page {page} {totalCount !== undefined && `of ${Math.ceil(totalCount / pageSize)}`}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onPageChange(page + 1)}
                disabled={
                  (totalCount !== undefined && page >= Math.ceil(totalCount / pageSize)) ||
                  incidents.length < pageSize ||
                  loading
                }
                tooltip={
                  (totalCount !== undefined && page >= Math.ceil(totalCount / pageSize)) ||
                  incidents.length < pageSize
                    ? "No more pages"
                    : undefined
                }
              >
                Next →
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default IncidentList;

