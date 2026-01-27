-- Historical Logs Schema
-- This extends the main schema to support storing and retrieving historical error logs

-- historical_logs: Store error logs from InfluxDB for similarity matching
CREATE TABLE IF NOT EXISTS historical_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id TEXT NOT NULL,  -- Original ticket/incident ID (e.g., INC6052852)
    log_timestamp TIMESTAMPTZ NOT NULL,  -- When the log was generated
    hostname TEXT,
    severity TEXT NOT NULL,  -- error, critical, alert, etc.
    appname TEXT,
    facility TEXT,
    log_message TEXT NOT NULL,  -- The actual log message
    embedding vector(1536),  -- OpenAI text-embedding-3-small
    tsv tsvector,  -- Full-text search vector
    metadata JSONB,  -- Additional metadata (matched_pattern, level, etc.)
    created_at TIMESTAMPTZ DEFAULT now(),  -- When ingested into database
    
    -- For tracking which ticket this log came from
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    
    -- Composite key to prevent duplicates (same log message at same time)
    CONSTRAINT unique_log UNIQUE (ticket_id, log_timestamp, log_message)
);

-- Indexes for efficient retrieval
CREATE INDEX IF NOT EXISTS historical_logs_ticket_id_idx ON historical_logs(ticket_id);
CREATE INDEX IF NOT EXISTS historical_logs_timestamp_idx ON historical_logs(log_timestamp);
CREATE INDEX IF NOT EXISTS historical_logs_hostname_idx ON historical_logs(hostname);
CREATE INDEX IF NOT EXISTS historical_logs_severity_idx ON historical_logs(severity);
CREATE INDEX IF NOT EXISTS historical_logs_embedding_idx ON historical_logs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS historical_logs_tsv_idx ON historical_logs USING GIN (tsv);
CREATE INDEX IF NOT EXISTS historical_logs_metadata_idx ON historical_logs USING GIN (metadata);
CREATE INDEX IF NOT EXISTS historical_logs_incident_id_idx ON historical_logs(incident_id);

-- Index for filtering by severity and searching
CREATE INDEX IF NOT EXISTS historical_logs_severity_embedding_idx ON historical_logs(severity, embedding);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS historical_logs_hostname_severity_idx ON historical_logs(hostname, severity);
