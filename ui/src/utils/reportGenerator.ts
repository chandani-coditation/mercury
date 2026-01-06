// Report Generator - Creates beautiful HTML reports instead of plain JSON

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
    affected_services: string[];
    confidence: number;
    summary: string;
    likely_cause: string;
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }
        
        .report-container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
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
            padding: 40px;
        }
        
        .section {
            margin-bottom: 40px;
        }
        
        .section-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 3px solid #667eea;
        }
        
        .section-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 18px;
        }
        
        .section-title {
            font-size: 24px;
            font-weight: 700;
            color: #1a1a1a;
        }
        
        .card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
            border-left: 4px solid #667eea;
        }
        
        .card-title {
            font-size: 14px;
            text-transform: uppercase;
            color: #6c757d;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .card-content {
            font-size: 16px;
            color: #1a1a1a;
            line-height: 1.6;
        }
        
        .badge {
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .badge-critical { background: #dc3545; color: white; }
        .badge-high { background: #fd7e14; color: white; }
        .badge-medium { background: #ffc107; color: #1a1a1a; }
        .badge-low { background: #28a745; color: white; }
        
        .badge-auto { background: #28a745; color: white; }
        .badge-propose { background: #ffc107; color: #1a1a1a; }
        .badge-block { background: #dc3545; color: white; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #667eea;
            margin-bottom: 8px;
        }
        
        .stat-label {
            font-size: 14px;
            color: #6c757d;
            font-weight: 500;
        }
        
        .resolution-steps {
            list-style: none;
            counter-reset: step-counter;
        }
        
        .resolution-step {
            counter-increment: step-counter;
            margin-bottom: 16px;
            padding: 16px;
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            position: relative;
            padding-left: 60px;
        }
        
        .resolution-step::before {
            content: counter(step-counter);
            position: absolute;
            left: 16px;
            top: 16px;
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
        }
        
        .tag {
            display: inline-block;
            padding: 4px 12px;
            background: #e9ecef;
            border-radius: 12px;
            font-size: 12px;
            color: #495057;
            margin-right: 8px;
            margin-bottom: 8px;
        }
        
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #0066cc;
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .warning-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .success-box {
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 16px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .report-footer {
            background: #f8f9fa;
            padding: 30px 40px;
            text-align: center;
            border-top: 2px solid #e9ecef;
            color: #6c757d;
            font-size: 14px;
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
        
        @media (max-width: 768px) {
            .report-meta {
                flex-direction: column;
                gap: 16px;
            }
            
            .stats-grid {
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
        
        <!-- Main Content -->
        <div class="report-content">
            <!-- Original Alert -->
            <div class="section">
                <div class="section-header">
                    <div class="section-icon">📋</div>
                    <h2 class="section-title">Original Alert</h2>
                </div>
                
                <div class="card">
                    <div class="card-title">Alert Title</div>
                    <div class="card-content">${data.incident_summary.title}</div>
                </div>
                
                <div class="card">
                    <div class="card-title">Description</div>
                    <div class="card-content">${data.incident_summary.description}</div>
                </div>
                
                <div class="card">
                    <div class="card-title">Timestamp</div>
                    <div class="card-content">${new Date(data.incident_summary.timestamp).toLocaleString()}</div>
                </div>
            </div>
            
            <!-- Triage Analysis -->
            <div class="section">
                <div class="section-header">
                    <div class="section-icon">🔍</div>
                    <h2 class="section-title">Triage Analysis</h2>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${getSeverityBadge(data.triage_analysis.severity)}</div>
                        <div class="stat-label">Severity</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${Math.round(data.triage_analysis.confidence * 100)}%</div>
                        <div class="stat-label">AI Confidence</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${data.triage_analysis.category}</div>
                        <div class="stat-label">Category</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${data.triage_analysis.routing}</div>
                        <div class="stat-label">Routed To</div>
                    </div>
                </div>
                
                <div class="info-box">
                    <strong>Summary:</strong><br>
                    ${data.triage_analysis.summary}
                </div>
                
                <div class="warning-box">
                    <strong>Likely Cause:</strong><br>
                    ${data.triage_analysis.likely_cause}
                </div>
                
                <div class="card">
                    <div class="card-title">Affected Services</div>
                    <div class="card-content">
                        ${data.triage_analysis.affected_services.map((s) => `<span class="tag">${s}</span>`).join("")}
                    </div>
                </div>
            </div>
            
            <!-- Policy Decision -->
            <div class="section">
                <div class="section-header">
                    <div class="section-icon">🛡️</div>
                    <h2 class="section-title">Policy Decision</h2>
                </div>
                
                <div class="card">
                    <div class="card-title">Policy Band</div>
                    <div class="card-content">
                        ${getPolicyBadge(data.policy_decision.policy_band)}
                    </div>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${data.policy_decision.requires_approval ? "✓" : "✗"}</div>
                        <div class="stat-label">Requires Approval</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${data.policy_decision.can_auto_apply ? "✓" : "✗"}</div>
                        <div class="stat-label">Can Auto-Apply</div>
                    </div>
                </div>
                
                <div class="info-box">
                    <strong>Reason:</strong><br>
                    ${data.policy_decision.policy_reason}
                </div>
            </div>
            
            <!-- Knowledge Base Evidence -->
            <div class="section">
                <div class="section-header">
                    <div class="section-icon">📚</div>
                    <h2 class="section-title">Knowledge Base Evidence</h2>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${data.evidence.chunks_used}</div>
                        <div class="stat-label">Evidence Chunks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${data.evidence.sources.length}</div>
                        <div class="stat-label">Unique Sources</div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-title">Sources</div>
                    <div class="card-content">
                        ${data.evidence.sources.map((s) => `<span class="tag">${s}</span>`).join("")}
                    </div>
                </div>
            </div>
            
            <!-- Resolution Steps -->
            <div class="section">
                <div class="section-header">
                    <div class="section-icon">✅</div>
                    <h2 class="section-title">Resolution Steps</h2>
                </div>
                
                ${
                  data.resolution.reasoning
                    ? `
                <div class="info-box">
                    <strong>AI Reasoning:</strong><br>
                    ${data.resolution.reasoning}
                </div>
                `
                    : ""
                }
                
                {/* Removed: Risk level and estimated time stats (deprecated fields) */}
                
                <ol class="resolution-steps">
                    ${data.resolution.steps
                      .map(
                        (step) => `
                        <li class="resolution-step">${step}</li>
                    `,
                      )
                      .join("")}
                </ol>
                
                <div class="success-box">
                    <strong>✅ Resolution Completed</strong><br>
                    All steps have been executed successfully. The incident has been marked as ${data.resolution.status}.
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="report-footer">
            <div>Generated by NOC Agent UI - AI-Powered Incident Resolution</div>
            <div style="margin-top: 8px; font-size: 12px;">
                © ${new Date().getFullYear()} | Report generated on ${timestamp}
            </div>
        </div>
    </div>
</body>
</html>`;
};

function getSeverityBadge(severity: string): string {
  const severityLower = severity.toLowerCase();
  const badgeClass = `badge badge-${severityLower}`;
  return `<span class="${badgeClass}">${severity.toUpperCase()}</span>`;
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
