// Use environment variable if available, otherwise default to localhost
// In Docker, this will be set via docker-compose environment
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001/api/v1";

async function request(url, options = {}) {
  const timeoutMs = options.timeoutMs ?? 70000; // allow longer-running triage
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    signal: controller.signal,
    ...options,
  }).finally(() => clearTimeout(timeout));

  if (!resp.ok) {
    const text = await resp.text();
    // Try to parse as JSON, otherwise use text
    let errorData;
    try {
      errorData = text ? JSON.parse(text) : { detail: resp.statusText };
    } catch {
      errorData = { detail: text || resp.statusText };
    }
    const error = new Error(text || resp.statusText);
    error.response = { data: errorData, status: resp.status };
    throw error;
  }
  return resp.json();
}

export function postTriage(payload) {
  return request(`${API_BASE}/triage`, {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 70000,
  });
}

export function getIncident(incidentId) {
  return request(`${API_BASE}/incidents/${incidentId}`);
}

export function listIncidents(limit = 50, offset = 0, search = null) {
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  if (search != null && search.trim() !== "") {
    params.set("search", search.trim());
  }
  return request(`${API_BASE}/incidents?${params.toString()}`);
}

export function putFeedback(incidentId, payload) {
  return request(`${API_BASE}/incidents/${incidentId}/feedback`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getIncidentFeedback(incidentId) {
  return request(`${API_BASE}/incidents/${incidentId}/feedback`);
}

export function postResolution(incidentId, payload = null) {
  const options = {
    method: "POST",
    timeoutMs: 70000,
  };

  // Only add body if payload is provided
  if (payload) {
    options.body = JSON.stringify(payload);
  }

  return request(`${API_BASE}/resolution?incident_id=${incidentId}`, options);
}

export function putResolutionComplete(incidentId, payload = {}) {
  return request(`${API_BASE}/incidents/${incidentId}/resolution`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

