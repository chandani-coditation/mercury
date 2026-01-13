// Report Generator - Creates beautiful HTML reports matching the summary page design

export interface ReportData {
  incident_summary: {
    alert_id: string;
    source: string;
    timestamp: string;
    title: string;
    description: string;
  };
  triage_analysis: {
    severity: string;
    category: string;
    routing: string;
    affected_services?: string[];
    confidence: number;
    summary: string;
    likely_cause: string;
    impact?: string;
    urgency?: string;
    incident_signature?: Record<string, string>;
  };
  policy_decision: {
    policy_band: string;
    requires_approval: boolean;
    can_auto_apply: boolean;
    policy_reason: string;
  };
  evidence: {
    chunks_used: number;
    sources: string[];
  };
  resolution: {
    steps: string[];
    status: string;
    reasoning?: string;
  };
}

export const generateHTMLReport = (data: ReportData): string => {
  const timestamp = new Date().toLocaleString();
  const incidentDate = new Date(data.incident_summary.timestamp).toLocaleString();
  const affectedServices = data.triage_analysis.affected_services || [];
  const incidentSignature = data.triage_analysis.incident_signature || {};
  const impact = data.triage_analysis.impact || "N/A";
  const urgency = data.triage_analysis.urgency || "N/A";
  const service = (data.incident_summary as any).service || "Database";

  return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Incident Report - ${data.incident_summary.alert_id}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            background: #f5f5f5;
            padding: 20px;
        }
        
        .report-container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .report-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .report-header h1 {
            font-size: 32px;
            margin-bottom: 10px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
        }
        
        .report-header .subtitle {
            font-size: 16px;
            opacity: 0.9;
        }
        
        .report-meta {
            display: flex;
            justify-content: space-between;
            padding: 20px 40px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }
        
        .meta-item {
            display: flex;
            flex-direction: column;
        }
        
        .meta-label {
            font-size: 12px;
            text-transform: uppercase;
            color: #6c757d;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        
        .meta-value {
            font-size: 14px;
            color: #1a1a1a;
            font-weight: 500;
            margin-top: 4px;
        }
        
        .report-content {
            padding: 20px;
        }
        
        .success-title {
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .success-check {
            width: 16px;
            height: 16px;
            color: #28a745;
        }
        
        .success-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #28a745;
        }
        
        .content-layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .left-column, .right-column {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        
        .resolution-card {
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }
        
        .section {
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 10px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }
        
        .glass-card {
            background: rgba(255, 255, 255, 0.6);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 0, 0, 0.1);
        }
        
        .section-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 16px;
        }
        
        .section-icon {
            width: 14px;
            height: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #0066cc;
        }
        
        .section-title {
            font-size: 12px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .subsection {
            margin-bottom: 12px;
        }
        
        .subsection-header {
            display: flex;
            align-items: center;
            gap: 4px;
            margin-bottom: 8px;
            font-size: 12px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .info-icon, .policy-icon {
            width: 14px;
            height: 14px;
            color: #0066cc;
        }
        
        .policy-icon {
            color: #6c757d;
        }
        
        .field-row {
            margin-bottom: 6px;
            font-size: 12px;
            display: flex;
            flex-wrap: wrap;
        }
        
        .field-label {
            color: #6c757d;
            margin-right: 8px;
            font-size: 12px;
        }
        
        .field-value {
            color: #1a1a1a;
            font-weight: 500;
            font-size: 12px;
        }
        
        .success-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 20px;
        }
        
        .success-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #28a745;
        }
        
        .success-check {
            width: 16px;
            height: 16px;
            color: #28a745;
        }
        
        .success-title {
            font-size: 18px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .subsection {
            margin-bottom: 20px;
        }
        
        .subsection-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            font-size: 14px;
            font-weight: 600;
            color: #1a1a1a;
        }
        
        .info-icon {
            width: 16px;
            height: 16px;
            color: #0066cc;
        }
        
        .policy-icon {
            width: 16px;
            height: 16px;
            color: #6c757d;
        }
        
        .field-row {
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        .field-label {
            color: #6c757d;
            margin-right: 8px;
        }
        
        .field-value {
            color: #1a1a1a;
            font-weight: 500;
        }
        
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 12px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .badge-high {
            background: #dc3545;
            color: white;
        }
        
        .badge-medium {
            background: #ff9800;
            color: white;
        }
        
        .badge-low {
            background: #28a745;
            color: white;
        }
        
        .badge-auto {
            background: rgba(40, 167, 69, 0.2);
            color: #28a745;
            border: 1px solid rgba(40, 167, 69, 0.3);
            font-family: monospace;
            font-weight: 700;
        }
        
        .badge-propose {
            background: rgba(255, 193, 7, 0.2);
            color: #ff9800;
            border: 1px solid rgba(255, 193, 7, 0.3);
            font-family: monospace;
            font-weight: 700;
        }
        
        .badge-block {
            background: rgba(220, 53, 69, 0.2);
            color: #dc3545;
            border: 1px solid rgba(220, 53, 69, 0.3);
            font-family: monospace;
            font-weight: 700;
        }
        
        .resolution-steps {
            list-style: none;
            counter-reset: step-counter;
            padding: 0;
        }
        
        .resolution-steps-container {
            background: rgba(0, 0, 0, 0.02);
            border: 1px solid rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            padding: 16px;
        }
        
        .resolution-step {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 8px;
            font-size: 12px;
            color: #1a1a1a;
            line-height: 1.5;
        }
        
        .resolution-step-number {
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            background: rgba(40, 167, 69, 0.2);
            color: #28a745;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 11px;
        }
        
        .resolution-step-text {
            flex: 1;
            padding-top: 2px;
        }
        
        .triage-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
            margin-bottom: 12px;
        }
        
        .triage-field {
            margin-bottom: 6px;
            font-size: 12px;
        }
        
        .triage-label {
            color: #6c757d;
            margin-bottom: 2px;
            font-size: 12px;
            display: block;
        }
        
        .triage-value {
            color: #1a1a1a;
            font-weight: 500;
            font-size: 12px;
        }
        
        .triage-value.blue {
            color: #0066cc;
        }
        
        .triage-value.green {
            color: #28a745;
        }
        
        .triage-value.orange {
            color: #ff9800;
        }
        
        .triage-value.red {
            color: #dc3545;
        }
        
        .evidence-stats {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        
        .evidence-stat {
            flex: 1;
            padding: 8px;
            background: rgba(0, 102, 204, 0.1);
            border: 1px solid rgba(0, 102, 204, 0.2);
            border-radius: 8px;
            text-align: center;
        }
        
        .evidence-stat-number {
            font-size: 18px;
            font-weight: 700;
            color: #0066cc;
            margin-bottom: 2px;
        }
        
        .evidence-stat-label {
            font-size: 12px;
            color: #6c757d;
        }
        
        .source-tag {
            display: inline-block;
            padding: 4px 12px;
            background: #0066cc;
            color: white;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 500;
            margin-right: 8px;
            margin-bottom: 8px;
        }
        
        .signature-item {
            font-size: 13px;
            margin-bottom: 4px;
        }
        
        .signature-key {
            color: #6c757d;
        }
        
        .signature-value {
            color: #0066cc;
            font-weight: 500;
        }
        
        .feedback-history {
            font-size: 14px;
        }
        
        .feedback-item {
            margin-bottom: 8px;
            color: #1a1a1a;
        }
        
        .feedback-date {
            color: #6c757d;
            font-size: 12px;
            margin-top: 4px;
        }
        
        .success-banner {
            background: rgba(40, 167, 69, 0.1);
            border: 1px solid rgba(40, 167, 69, 0.3);
            color: #1a1a1a;
            padding: 16px;
            border-radius: 8px;
            margin-top: 10px;
        }
        
        .success-banner-title {
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
            color: #1a1a1a;
        }
        
        .success-banner-message {
            font-size: 12px;
            color: #6c757d;
            line-height: 1.5;
        }
        
        @media print {
            body {
                background: white;
                padding: 0;
            }
            
            .report-container {
                box-shadow: none;
            }
        }
        
        @media (max-width: 1024px) {
            .content-layout {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="report-container">
        <!-- Header -->
        <div class="report-header">
            <h1>🚨 Incident Resolution Report</h1>
            <div class="subtitle">AI-Powered Incident Analysis & Resolution</div>
        </div>
        
        <!-- Meta Information -->
        <div class="report-meta">
            <div class="meta-item">
                <span class="meta-label">Incident ID</span>
                <span class="meta-value">${data.incident_summary.alert_id}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Source</span>
                <span class="meta-value">${data.incident_summary.source}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Generated</span>
                <span class="meta-value">${timestamp}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Status</span>
                <span class="meta-value">${data.resolution.status}</span>
            </div>
        </div>
        
        <div class="report-content">
            <div class="content-layout">
                <!-- Left Column -->
                <div class="left-column">
                    <!-- Original Alert -->
                    <div class="section">
                        <div class="subsection">
                            <div class="subsection-header">
                                <svg class="info-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                </svg>
                                Original Alert
                            </div>
                            <div class="field-row">
                                <span class="field-label">Alert ID:</span>
                                <span class="field-value">${data.incident_summary.alert_id}</span>
                            </div>
                            <div class="field-row">
                                <span class="field-label">Source:</span>
                                <span class="field-value">${data.incident_summary.source}</span>
                            </div>
                            <div class="field-row">
                                <span class="field-label">Service:</span>
                                <span class="field-value">${service}</span>
                            </div>
                            <div class="field-row">
                                <span class="field-label">Title:</span>
                                <span class="field-value">${data.incident_summary.title}</span>
                            </div>
                            <div class="field-row">
                                <span class="field-label">Description:</span>
                                <span class="field-value">${data.incident_summary.description}</span>
                            </div>
                        </div>
                        
                        <!-- Policy Decision -->
                        <div class="subsection">
                            <div class="subsection-header">
                                <svg class="policy-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
                                </svg>
                                Policy Decision
                            </div>
                            <div class="field-row">
                                <span class="field-label">Policy Band:</span>
                                <span class="field-value">${getPolicyBadge(data.policy_decision.policy_band)}</span>
                            </div>
                            <div class="field-row" style="background: rgba(0,0,0,0.02); border-radius: 4px; padding: 6px; display: flex; justify-content: space-between; align-items: center;">
                                <span class="field-label" style="margin: 0;">Requires Approval</span>
                                <span class="field-value" style="color: ${data.policy_decision.requires_approval ? "#ff9800" : "#28a745"}; font-weight: 600; margin: 0;">${data.policy_decision.requires_approval ? "Yes" : "No"}</span>
                            </div>
                            <div class="field-row" style="background: rgba(0,0,0,0.02); border-radius: 4px; padding: 6px; display: flex; justify-content: space-between; align-items: center;">
                                <span class="field-label" style="margin: 0;">Can Auto-Apply</span>
                                <span class="field-value" style="color: ${data.policy_decision.can_auto_apply ? "#28a745" : "#6c757d"}; font-weight: 600; margin: 0;">${data.policy_decision.can_auto_apply ? "Yes" : "No"}</span>
                            </div>
                            <div class="field-row">
                                <span class="field-label">Reason:</span>
                                <span class="field-value">${data.policy_decision.policy_reason}</span>
                            </div>
                        </div>
                        
                        
                        <!-- Feedback History -->
                        <div class="subsection">
                            <div class="subsection-header">
                                <svg class="success-check" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                                </svg>
                                Feedback History
                            </div>
                            <div class="feedback-history">
                                <div class="feedback-item">Triage</div>
                                <div class="feedback-item">Approved via UI</div>
                                <div class="feedback-date">${incidentDate}</div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Right Column -->
                <div class="right-column">
                    <!-- Triage Analysis -->
                    <div class="section">
                        <div class="section-header">
                            <svg class="section-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                            </svg>
                            <h3 class="section-title">Triage Analysis</h3>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Severity</div>
                            <div class="triage-value">${getSeverityBadgeWithIcon(data.triage_analysis.severity)}</div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Routing</div>
                            <div class="triage-value blue">${data.triage_analysis.routing}</div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Affected Services</div>
                            <div class="triage-value">${affectedServices.length > 0 ? affectedServices.join(", ") : "N/A"}</div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Impact</div>
                            <div class="triage-value orange">${impact}</div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Urgency</div>
                            <div class="triage-value orange">${urgency}</div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">AI Confidence</div>
                            <div class="triage-value green">${Math.round(data.triage_analysis.confidence * 100)}%</div>
                        </div>
                        
                        ${Object.keys(incidentSignature).length > 0 ? `
                        <div class="triage-field" style="background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.1); border-radius: 4px; padding: 6px; margin-top: 6px;">
                            <div class="triage-label" style="font-weight: 600; margin-bottom: 4px;">Incident Signature</div>
                            ${incidentSignature.failure_type ? `
                            <div class="signature-item" style="font-size: 12px;">
                                <span class="signature-key">Failure: </span>
                                <span class="signature-value" style="font-weight: 600; font-family: monospace;">${incidentSignature.failure_type}</span>
                            </div>
                            ` : ""}
                            ${incidentSignature.error_class ? `
                            <div class="signature-item" style="font-size: 12px;">
                                <span class="signature-key">Error: </span>
                                <span class="signature-value" style="font-weight: 600; font-family: monospace;">${incidentSignature.error_class}</span>
                            </div>
                            ` : ""}
                        </div>
                        ` : ""}
                    </div>
                    
                    <!-- Knowledge Base Evidence -->
                    <div class="section">
                        <div class="section-header">
                            <svg class="section-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                            </svg>
                            <h3 class="section-title">Knowledge Base Evidence</h3>
                        </div>
                        
                        <div class="evidence-stats">
                            <div class="evidence-stat">
                                <div class="evidence-stat-number">${data.evidence.chunks_used}</div>
                                <div class="evidence-stat-label">Chunks Used</div>
                            </div>
                            <div class="evidence-stat">
                                <div class="evidence-stat-number">${data.evidence.sources.length}</div>
                                <div class="evidence-stat-label">Unique Sources</div>
                            </div>
                        </div>
                        
                        <div class="triage-field">
                            <div class="triage-label">Sources</div>
                            <div>
                                ${data.evidence.sources.map((s) => `<span class="source-tag">${s}</span>`).join("")}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Resolution Steps - Full Width -->
            ${data.resolution.steps && data.resolution.steps.length > 0 ? `
            <div class="resolution-card">
                <div class="section-header">
                    <svg class="success-check" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                    <h3 class="section-title">Resolution Steps Executed</h3>
                </div>
                <div class="resolution-steps-container">
                    ${data.resolution.steps
                      .map(
                        (step, index) => `
                        <div class="resolution-step">
                            <div class="resolution-step-number">${index + 1}</div>
                            <div class="resolution-step-text">${step}</div>
                        </div>
                    `,
                      )
                      .join("")}
                </div>
            </div>
            ` : ""}
        </div>
        
        <!-- Success Banner -->
        <div class="success-banner">
            <div class="success-banner-title">Incident Resolved Successfully</div>
            <div class="success-banner-message">All resolution steps have been executed. The incident has been marked as complete.</div>
        </div>
    </div>
</body>
</html>`;
};

function getSeverityBadge(severity: string): string {
  const severityLower = severity.toLowerCase();
  const badgeClass = `badge badge-${severityLower}`;
  const severityText = severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase();
  return `<span class="${badgeClass}">${severityText} Severity</span>`;
}

function getSeverityBadgeWithIcon(severity: string): string {
  const severityLower = severity.toLowerCase();
  const badgeClass = `badge badge-${severityLower}`;
  const severityText = severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase();
  return `<span class="${badgeClass}">
    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display: inline-block; vertical-align: middle;">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
    </svg>
    ${severityText} Severity
  </span>`;
}

function getPolicyBadge(policy: string): string {
  const policyLower = policy.toLowerCase();
  const badgeClass = `badge badge-${policyLower}`;
  return `<span class="${badgeClass}">${policy.toUpperCase()}</span>`;
}

export const downloadHTMLReport = (data: ReportData) => {
  const html = generateHTMLReport(data);
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `incident-report-${data.incident_summary.alert_id}-${new Date().getTime()}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const downloadJSONReport = (data: ReportData) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `incident-report-${data.incident_summary.alert_id}-${new Date().getTime()}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
