import axios from "axios";

const resolveApiBase = () => {
  const configured = process.env.REACT_APP_API_URL;
  if (configured) {
    return configured.replace(/\/$/, "");
  }
  if (typeof window !== "undefined" && window.location.hostname === "localhost") {
    return "http://localhost:8001/api/v1";
  }
  return "/api/v1";
};

export const API_BASE = resolveApiBase();

export const apiClient = axios.create({
  baseURL: API_BASE,
});

export const get = (path, config) => apiClient.get(path, config);
export const post = (path, data, config) => apiClient.post(path, data, config);
export const put = (path, data, config) => apiClient.put(path, data, config);

const normalizeBaseForWs = (base) => {
  if (base.startsWith("http://") || base.startsWith("https://")) {
    const url = new URL(base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return {
      origin: `${url.protocol}//${url.host}`,
      path: url.pathname.replace(/\/$/, ""),
    };
  }
  const protocol =
    typeof window !== "undefined" && window.location.protocol === "https:"
      ? "wss:"
      : "ws:";
  const host =
    typeof window !== "undefined" ? window.location.host : "localhost:3000";
  return {
    origin: `${protocol}//${host}`,
    path: base.replace(/\/$/, ""),
  };
};

export const buildAgentStateWsUrl = (incidentId) => {
  if (!incidentId) return null;
  const { origin, path } = normalizeBaseForWs(API_BASE);
  const suffix = `/agents/${incidentId}/state`;
  return `${origin}${path}${suffix}`;
};

export default apiClient;


