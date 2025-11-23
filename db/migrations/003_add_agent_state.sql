-- Migration: Add agent_state table for state-based HITL persistence
-- Created: 2025-01-13

-- Table to store agent state snapshots
CREATE TABLE IF NOT EXISTS agent_state (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
  agent_type TEXT NOT NULL, -- 'triage' or 'resolution'
  current_step TEXT NOT NULL,
  state_data JSONB NOT NULL, -- Full AgentState as JSON
  pending_action JSONB, -- PendingAction as JSON if paused
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS agent_state_incident_id_idx ON agent_state(incident_id);
CREATE INDEX IF NOT EXISTS agent_state_agent_type_idx ON agent_state(agent_type);
CREATE INDEX IF NOT EXISTS agent_state_current_step_idx ON agent_state(current_step);
CREATE INDEX IF NOT EXISTS agent_state_updated_at_idx ON agent_state(updated_at);

-- Index for pending actions (for querying pending HITL actions)
CREATE INDEX IF NOT EXISTS agent_state_pending_action_idx ON agent_state USING GIN (pending_action) WHERE pending_action IS NOT NULL;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_agent_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
CREATE TRIGGER agent_state_updated_at_trigger
  BEFORE UPDATE ON agent_state
  FOR EACH ROW
  EXECUTE FUNCTION update_agent_state_updated_at();

