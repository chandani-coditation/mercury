import React from "react";
import "./Sidebar.css";
import Button from "../common/Button";

const navItems = [
  { label: "Dashboard", icon: "📊", active: true },
  { label: "Incidents", icon: "🧭" },
  { label: "Playbooks", icon: "📘" },
  { label: "Analytics", icon: "📈" },
];

const policyPills = [
  { label: "AUTO", color: "pill-auto" },
  { label: "PROPOSE", color: "pill-propose" },
  { label: "REVIEW", color: "pill-review" },
];

function Sidebar({ onNewIncident, onRefresh, incidentStats = {} }) {
  const {
    total = 0,
    awaitingApproval = 0,
    pendingActions = 0,
  } = incidentStats;

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-pill">N</div>
        <div>
          <strong>NOC Agent</strong>
          <p>AI Control Center</p>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          let badge = null;
          if (item.label === "Incidents" && total > 0) {
            badge = <span className="nav-badge">{total}</span>;
          } else if (item.label === "Dashboard" && pendingActions > 0) {
            badge = <span className="nav-badge nav-badge-warning">{pendingActions}</span>;
          } else if (item.label === "Dashboard" && awaitingApproval > 0) {
            badge = <span className="nav-badge nav-badge-alert">{awaitingApproval}</span>;
          }
          return (
            <button
              key={item.label}
              className={`nav-item ${item.active ? "active" : ""}`}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              {item.label}
              {badge}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-section">
        <p className="section-label">Policy Bands</p>
        <div className="pill-row">
          {policyPills.map((pill) => (
            <span key={pill.label} className={`policy-pill ${pill.color}`}>
              {pill.label}
            </span>
          ))}
        </div>
      </div>

      <div className="sidebar-actions">
        <Button variant="primary" size="md" onClick={onNewIncident}>
          + New Triage
        </Button>
        <Button variant="ghost" size="sm" onClick={onRefresh}>
          Refresh
        </Button>
      </div>
    </aside>
  );
}

export default Sidebar;

