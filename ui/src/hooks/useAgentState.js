import { useEffect, useRef, useState } from "react";
import { apiClient, buildAgentStateWsUrl } from "../services/api";

const fetchInitialState = async (incidentId) => {
  try {
    const response = await apiClient.get(`/agents/${incidentId}/state`);
    return response.data;
  } catch (error) {
    console.warn("[useAgentState] Failed to fetch initial state", error);
    return null;
  }
};

const connectionStatuses = {
  IDLE: "idle",
  CONNECTING: "connecting",
  OPEN: "open",
  CLOSED: "closed",
  ERROR: "error",
};

export const useAgentState = (incidentId) => {
  const [state, setState] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState(
    connectionStatuses.IDLE
  );
  const [error, setError] = useState(null);
  const [lastMessageAt, setLastMessageAt] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeout = useRef(null);
  const reconnectAttempts = useRef(0);
  const activeIncidentRef = useRef(incidentId);

  useEffect(() => {
    activeIncidentRef.current = incidentId;
  }, [incidentId]);

  useEffect(() => {
    if (!incidentId) {
      setState(null);
      setConnectionStatus(connectionStatuses.IDLE);
      setError(null);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return undefined;
    }

    let cancelled = false;

    const cleanupWebSocket = () => {
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onerror = null;
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      const attempt = reconnectAttempts.current + 1;
      reconnectAttempts.current = attempt;
      const delay = Math.min(1000 * 2 ** attempt, 10000);
      reconnectTimeout.current = setTimeout(() => {
        if (!cancelled && activeIncidentRef.current === incidentId) {
          connectWebSocket();
        }
      }, delay);
    };

    const connectWebSocket = () => {
      cleanupWebSocket();
      const wsUrl = buildAgentStateWsUrl(incidentId);
      if (!wsUrl) {
        setConnectionStatus(connectionStatuses.ERROR);
        setError("Unable to build WebSocket URL");
        return;
      }

      try {
        const socket = new WebSocket(wsUrl);
        wsRef.current = socket;
        setConnectionStatus(connectionStatuses.CONNECTING);
        setError(null);

        socket.onopen = () => {
          reconnectAttempts.current = 0;
          setConnectionStatus(connectionStatuses.OPEN);
        };

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            setState(payload);
            setLastMessageAt(Date.now());
          } catch (err) {
            console.error("[useAgentState] Failed to parse message", err);
          }
        };

        socket.onerror = (event) => {
          console.error("[useAgentState] WebSocket error", event);
          setError("WebSocket connection error");
          setConnectionStatus(connectionStatuses.ERROR);
        };

        socket.onclose = () => {
          setConnectionStatus(connectionStatuses.CLOSED);
          if (!cancelled) {
            scheduleReconnect();
          }
        };
      } catch (err) {
        console.error("[useAgentState] Failed to open WebSocket", err);
        setError("Failed to open WebSocket");
        setConnectionStatus(connectionStatuses.ERROR);
        scheduleReconnect();
      }
    };

    setConnectionStatus(connectionStatuses.CONNECTING);
    fetchInitialState(incidentId).then((initialState) => {
      if (!cancelled && initialState) {
        setState(initialState);
      }
    });
    connectWebSocket();

    return () => {
      cancelled = true;
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
        reconnectTimeout.current = null;
      }
      cleanupWebSocket();
    };
  }, [incidentId]);

  return {
    state,
    connectionStatus,
    connected: connectionStatus === connectionStatuses.OPEN,
    error,
    lastMessageAt,
  };
};

export default useAgentState;

