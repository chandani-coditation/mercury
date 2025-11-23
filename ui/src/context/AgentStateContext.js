import React, { createContext, useContext, useMemo } from "react";
import useAgentState from "../hooks/useAgentState";

const AgentStateContext = createContext({
  incidentId: null,
  state: null,
  connectionStatus: "idle",
  connected: false,
  error: null,
  lastMessageAt: null,
});

export const AgentStateProvider = ({ incidentId, children }) => {
  const agentState = useAgentState(incidentId);

  const value = useMemo(
    () => ({
      incidentId,
      ...agentState,
    }),
    [
      incidentId,
      agentState.state,
      agentState.connectionStatus,
      agentState.connected,
      agentState.error,
      agentState.lastMessageAt,
    ]
  );

  return (
    <AgentStateContext.Provider value={value}>
      {children}
    </AgentStateContext.Provider>
  );
};

export const useAgentStateContext = () => useContext(AgentStateContext);

export default AgentStateContext;

