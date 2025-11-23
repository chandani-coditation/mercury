import React, { useState } from 'react';
import './TriageForm.css';

function TriageForm({ onSubmit, onCancel, loading }) {
  const [formData, setFormData] = useState({
    alert_id: `test-alert-${Date.now()}`,
    source: 'test',
    title: '',
    description: '',
    service: 'api-gateway',
    component: 'api',
    severity: 'high'
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const alertData = {
      alert_id: formData.alert_id,
      source: formData.source,
      title: formData.title,
      description: formData.description,
      labels: {
        service: formData.service,
        component: formData.component,
        severity: formData.severity
      },
      ts: new Date().toISOString()
    };
    onSubmit(alertData);
  };

  return (
    <div className="triage-form-container">
      <div className="form-header">
        <h2>Create New Triage</h2>
        <button className="btn-back" onClick={onCancel}>Cancel</button>
      </div>

      <form className="triage-form" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="title">Alert Title *</label>
          <input
            type="text"
            id="title"
            name="title"
            value={formData.title}
            onChange={handleChange}
            required
            placeholder="e.g., High CPU Usage on API Gateway"
          />
        </div>

        <div className="form-group">
          <label htmlFor="description">Description *</label>
          <textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={handleChange}
            required
            rows={4}
            placeholder="Detailed description of the alert..."
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="service">Service</label>
            <input
              type="text"
              id="service"
              name="service"
              value={formData.service}
              onChange={handleChange}
              placeholder="api-gateway"
            />
          </div>

          <div className="form-group">
            <label htmlFor="component">Component</label>
            <input
              type="text"
              id="component"
              name="component"
              value={formData.component}
              onChange={handleChange}
              placeholder="api"
            />
          </div>

          <div className="form-group">
            <label htmlFor="severity">Severity</label>
            <select
              id="severity"
              name="severity"
              value={formData.severity}
              onChange={handleChange}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Processing...' : 'Submit Triage'}
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

export default TriageForm;

