const API_BASE = "http://localhost:8001/api/v1";

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

export function putFeedback(incidentId, payload) {
  return request(`${API_BASE}/incidents/${incidentId}/feedback`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function postResolution(incidentId) {
  return request(`${API_BASE}/resolution?incident_id=${incidentId}`, {
    method: "POST",
  });
}
