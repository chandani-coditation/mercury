import { Database, FileSearch, Info } from "lucide-react";
import { EvidenceChunk } from "./EvidenceChunk";

interface Chunk {
  chunk_id: string;
  document_id: string;
  doc_title: string;
  content: string;
  provenance?: {
    source_type?: string;
  };
}

interface RetrievalData {
  chunks_used: number;
  chunk_ids: string[];
  chunk_sources: string[];
  chunks: Chunk[];
}

interface RetrievalTabProps {
  data: RetrievalData;
}

export const RetrievalTab = ({ data }: RetrievalTabProps) => {
  // Handle cases where data might be undefined or have different structure
  const chunksUsed = data?.chunks_used || 0;
  const chunkSources = data?.chunk_sources || [];
  const chunks = data?.chunks || [];

  // Calculate breakdown of chunks by source type
  const chunkBreakdown = (() => {
    const priorIncidents = chunks.filter(
      (c: any) =>
        c.provenance?.source_type === "incident_signature" ||
        c.metadata?.doc_type === "incident_signature",
    ).length;
    const runbookMetadata = chunks.filter(
      (c: any) =>
        c.provenance?.source_type === "runbook" ||
        c.metadata?.doc_type === "runbook",
    ).length;
    const runbookSteps = chunks.filter(
      (c: any) => c.provenance?.source_type === "runbook_step",
    ).length;
    return { priorIncidents, runbookMetadata, runbookSteps };
  })();

  // Get unique source types with friendly names
  const sourceTypes = Array.from(
    new Set(
      chunks
        .map((c: any) => c.provenance?.source_type || "unknown")
        .filter(Boolean),
    ),
  );
  const sourceTypeNames: Record<string, string> = {
    incident_signature: "Prior Incidents",
    runbook: "Runbook Metadata",
    runbook_step: "Runbook Steps",
    unknown: "Unknown",
  };

  return (
    <div className="space-y-2.5 animate-fade-in">
      {/* Stats Header - Simplified */}
      <div className="flex flex-wrap gap-2.5">
        <div className="glass-card px-3 py-2.5 flex items-center gap-2 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
          <div className="absolute -inset-0.5 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          <div className="p-1.5 rounded-lg bg-primary/10 relative z-10">
            <Database className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="relative z-10 flex-1">
            <p className="text-xs text-muted-foreground">Chunks Retrieved</p>
            <p className="text-lg font-bold font-mono text-foreground">
              {chunksUsed}
            </p>
          </div>
        </div>

        <div className="glass-card px-3 py-2.5 flex items-center gap-2 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
          <div className="absolute -inset-0.5 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          <div className="p-1.5 rounded-lg bg-primary/10 relative z-10">
            <FileSearch className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="relative z-10 flex-1">
            <p className="text-xs text-muted-foreground">Unique Source Types</p>
            <p className="text-lg font-bold font-mono text-foreground">
              {sourceTypes.length || 0}
            </p>
          </div>
        </div>
      </div>

      {/* Consolidated Source Breakdown - Shows the 3 unique source types with counts */}
      {chunksUsed > 0 && sourceTypes.length > 0 && (
        <div className="glass-card p-2.5 space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold text-foreground">
              The {sourceTypes.length} Unique Source Types
            </h4>
            <div className="group relative inline-block align-middle">
              <Info className="w-3 h-3 text-muted-foreground hover:text-primary cursor-help transition-colors" />
              <div className="hidden group-hover:block absolute z-20 w-80 p-2 text-xs text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                <p className="font-semibold mb-1">Total: {chunksUsed} chunks retrieved</p>
                <p className="mb-1">
                  Breakdown: {chunkBreakdown.priorIncidents} Prior Incidents,{" "}
                  {chunkBreakdown.runbookMetadata} Runbook Metadata,{" "}
                  {chunkBreakdown.runbookSteps} Runbook Steps
                </p>
                <p className="text-muted-foreground mt-2">
                  Only the top 5 from each category are displayed in the evidence details below.
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {sourceTypes.map((sourceType, index) => {
              const count =
                sourceType === "incident_signature"
                  ? chunkBreakdown.priorIncidents
                  : sourceType === "runbook"
                    ? chunkBreakdown.runbookMetadata
                    : sourceType === "runbook_step"
                      ? chunkBreakdown.runbookSteps
                      : 0;
              return (
                <div
                  key={index}
                  className="px-2 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium flex items-center gap-1.5"
                >
                  <span>{sourceTypeNames[sourceType] || sourceType}</span>
                  <span className="text-xs font-bold text-primary/70">
                    ({count})
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Knowledge Sources (Document Titles) - Different from Source Types */}
      {chunkSources.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Knowledge Sources ({[...new Set(chunkSources)].length})
            </h4>
            <div className="group relative inline-block align-middle">
              <Info className="w-3 h-3 text-muted-foreground hover:text-primary cursor-help transition-colors" />
              <div className="hidden group-hover:block absolute z-20 w-64 p-2 text-xs text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                Specific documents and runbooks retrieved from the knowledge base
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[...new Set(chunkSources)].map((source, index) => (
              <div
                key={index}
                className="px-2 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-medium"
              >
                {source}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence Chunks - Separated by Type */}
      {chunks.length > 0 ? (
        <div className="space-y-3">
          {/* Separate chunks into Prior Incidents and Runbooks */}
          {(() => {
            const priorIncidents = chunks
              .filter(
                (chunk: any) =>
                  chunk.provenance?.source_type === "incident_signature" ||
                  chunk.metadata?.doc_type === "incident_signature",
              )
              .slice(0, 5); // Limit to top 5
            const runbooks = chunks
              .filter(
                (chunk: any) =>
                  chunk.provenance?.source_type === "runbook" ||
                  chunk.provenance?.source_type === "runbook_step" ||
                  chunk.metadata?.doc_type === "runbook",
              )
              .slice(0, 5); // Limit to top 5

            return (
              <>
                {/* Prior Incidents Section */}
                {priorIncidents.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2">
                      <span className="w-1 h-4 bg-primary rounded-full" />
                      Prior Incidents ({priorIncidents.length}
                      {chunks.filter(
                        (chunk: any) =>
                          chunk.provenance?.source_type === "incident_signature" ||
                          chunk.metadata?.doc_type === "incident_signature",
                      ).length > 5
                        ? ` of ${chunks.filter(
                            (chunk: any) =>
                              chunk.provenance?.source_type ===
                                "incident_signature" ||
                              chunk.metadata?.doc_type === "incident_signature",
                          ).length}`
                        : ""}
                      )
                    </h4>
                    <div className="space-y-2">
                      {priorIncidents.map((chunk, index) => (
                        <EvidenceChunk
                          key={chunk.chunk_id}
                          chunk={chunk}
                          index={index}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Runbooks Section */}
                {runbooks.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2">
                      <span className="w-1 h-4 bg-primary rounded-full" />
                      Runbooks ({runbooks.length}
                      {chunks.filter(
                        (chunk: any) =>
                          chunk.provenance?.source_type === "runbook" ||
                          chunk.provenance?.source_type === "runbook_step" ||
                          chunk.metadata?.doc_type === "runbook",
                      ).length > 5
                        ? ` of ${chunks.filter(
                            (chunk: any) =>
                              chunk.provenance?.source_type === "runbook" ||
                              chunk.provenance?.source_type === "runbook_step" ||
                              chunk.metadata?.doc_type === "runbook",
                          ).length}`
                        : ""}
                      )
                    </h4>
                    <div className="space-y-3">
                      {runbooks.map((chunk, index) => (
                        <EvidenceChunk
                          key={chunk.chunk_id}
                          chunk={chunk}
                          index={priorIncidents.length + index}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Show message if no chunks match either category */}
                {priorIncidents.length === 0 && runbooks.length === 0 && (
                  <div className="glass-card p-4 text-center">
                    <FileSearch className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-50" />
                    <p className="text-sm text-muted-foreground">
                      No categorized evidence chunks available
                    </p>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      ) : (
        <div className="glass-card p-4 text-center">
          <FileSearch className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-50" />
          <p className="text-sm text-muted-foreground">No evidence chunks available</p>
          <p className="text-xs text-muted-foreground mt-1">
            {chunksUsed > 0
              ? "Chunk details were not returned by the API"
              : "No matching knowledge base entries found"}
          </p>
        </div>
      )}
    </div>
  );
};
