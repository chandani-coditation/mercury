import React from "react";
import "./TopBar.css";
import Button from "../common/Button";
import ThemeToggle from "../common/ThemeToggle";

function TopBar({
  selectedIncident,
  searchTerm,
  onSearchChange,
  policyFilter,
  onPolicyFilterChange,
  severityFilter,
  onSeverityFilterChange,
  onNewIncident,
  onRefresh,
  workspaceTab = "incidents",
  onWorkspaceTabChange = () => {},
  searchInputRef,
}) {
  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="workspace-tabs">
          {["incidents", "runbooks", "analytics"].map((tab) => (
            <button
              key={tab}
              className={`workspace-tab ${
                workspaceTab === tab ? "active" : ""
              }`}
              onClick={() => onWorkspaceTabChange(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="breadcrumb">
          <span>{workspaceTab.charAt(0).toUpperCase() + workspaceTab.slice(1)}</span>
          <span>/</span>
          <strong>{selectedIncident?.raw_alert?.title || "Overview"}</strong>
        </div>
      </div>

      <div className="topbar-actions">
        <input
          ref={searchInputRef}
          type="search"
          className="search-input"
          placeholder="Search by title, service, or ID (Ctrl+K)"
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <select
          className="filter-select"
          value={policyFilter}
          onChange={(e) => onPolicyFilterChange(e.target.value)}
        >
          <option value="all">All Policy Bands</option>
          <option value="AUTO">AUTO</option>
          <option value="PROPOSE">PROPOSE</option>
          <option value="REVIEW">REVIEW</option>
          <option value="PENDING">PENDING</option>
        </select>
        <select
          className="filter-select"
          value={severityFilter}
          onChange={(e) => onSeverityFilterChange(e.target.value)}
        >
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <Button variant="secondary" onClick={onRefresh}>
          Refresh
        </Button>
        <Button variant="primary" onClick={onNewIncident}>
          + New Triage
        </Button>
        <ThemeToggle />
      </div>
    </div>
  );
}

export default TopBar;

