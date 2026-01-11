import { useState } from "react";
import { Database, FileSearch, Info, ChevronDown, ChevronRight } from "lucide-react";
import { EvidenceChunk } from "./EvidenceChunk";
import retrievalConfig from "@/config/retrieval.json";

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
  // State for collapsible sections - collapsed by default
  const [isPriorIncidentsExpanded, setIsPriorIncidentsExpanded] = useState(false);
  const [isRunbooksExpanded, setIsRunbooksExpanded] = useState(false);

  // Handle cases where data might be undefined or have different structure
  const chunksUsed = data?.chunks_used || 0;
  const chunks = data?.chunks || [];

  // Helper function to calculate relevance score (same logic as EvidenceChunk)
  const calculateRelevanceScore = (chunk: any): number | null => {
    const scores = chunk.scores || {};
    if (scores.rrf_score !== undefined && scores.rrf_score !== null) {
      return Math.round(scores.rrf_score * 1000);
    }
    if (scores.vector_score !== undefined && scores.vector_score !== null) {
      return Math.round(scores.vector_score * 100);
    }
    if (scores.fulltext_score !== undefined && scores.fulltext_score !== null && scores.fulltext_score > 1e-10) {
      return Math.round(scores.fulltext_score * 100);
    }
    return null;
  };

  // Get threshold from config
  const relevanceThreshold = retrievalConfig.ui_relevance_threshold || 0;

  // Calculate filtered chunks (apply threshold filtering to runbooks)
  const filteredChunks = (() => {
    // Prior incidents - no threshold filtering
    const priorIncidents = chunks.filter(
      (c: any) =>
        c.provenance?.source_type === "incident_signature" ||
        c.metadata?.doc_type === "incident_signature",
    );

    // Runbooks (both metadata and steps) - apply threshold filtering
    const allRunbooks = chunks.filter(
      (c: any) =>
        c.provenance?.source_type === "runbook" ||
        c.provenance?.source_type === "runbook_step" ||
        c.metadata?.doc_type === "runbook",
    );

    const filteredRunbooks = allRunbooks.filter((chunk: any) => {
      const relevanceScore = calculateRelevanceScore(chunk);
      return relevanceScore === null || relevanceScore >= relevanceThreshold;
    });

    return [...priorIncidents, ...filteredRunbooks];
  })();

  // Calculate breakdown of DISPLAYED chunks by source type (after threshold filtering)
  const chunkBreakdown = (() => {
    const priorIncidents = filteredChunks.filter(
      (c: any) =>
        c.provenance?.source_type === "incident_signature" ||
        c.metadata?.doc_type === "incident_signature",
    ).length;
    const runbookMetadata = filteredChunks.filter(
      (c: any) =>
        c.provenance?.source_type === "runbook" ||
        c.metadata?.doc_type === "runbook",
    ).length;
    const runbookSteps = filteredChunks.filter(
      (c: any) => c.provenance?.source_type === "runbook_step",
    ).length;
    return { priorIncidents, runbookMetadata, runbookSteps };
  })();

  // Calculate actually displayed chunks count (top 5 from each category after filtering)
  const displayedChunksCount = (() => {
    const priorIncidentsCount = filteredChunks
      .filter(
        (chunk: any) =>
          chunk.provenance?.source_type === "incident_signature" ||
          chunk.metadata?.doc_type === "incident_signature",
      )
      .slice(0, 5).length;

    const runbooksCount = filteredChunks
      .filter(
        (chunk: any) =>
          chunk.provenance?.source_type === "runbook" ||
          chunk.provenance?.source_type === "runbook_step" ||
          chunk.metadata?.doc_type === "runbook",
      )
      .slice(0, 5).length;

    return priorIncidentsCount + runbooksCount;
  })();

  // Filter knowledge sources to only include sources from displayed chunks
  const displayedKnowledgeSources = (() => {
    // Get doc_title from filtered chunks (top 5 from each category)
    const priorIncidentsChunks = filteredChunks
      .filter(
        (chunk: any) =>
          chunk.provenance?.source_type === "incident_signature" ||
          chunk.metadata?.doc_type === "incident_signature",
      )
      .slice(0, 5);

    const runbooksChunks = filteredChunks
      .filter(
        (chunk: any) =>
          chunk.provenance?.source_type === "runbook" ||
          chunk.provenance?.source_type === "runbook_step" ||
          chunk.metadata?.doc_type === "runbook",
      )
      .slice(0, 5);

    const displayedChunksArray = [...priorIncidentsChunks, ...runbooksChunks];

    // Extract unique doc_title values from displayed chunks
    const sourceTitles = displayedChunksArray
      .map((chunk: any) => chunk.doc_title)
      .filter((title): title is string => Boolean(title));

    return [...new Set(sourceTitles)];
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

  // Calculate number of non-zero source types for display
  const nonZeroSourceTypesCount = sourceTypes.filter((sourceType) => {
    const count =
      sourceType === "incident_signature"
        ? chunkBreakdown.priorIncidents
        : sourceType === "runbook"
          ? chunkBreakdown.runbookSteps
          : sourceType === "runbook_step"
            ? chunkBreakdown.runbookMetadata
            : 0;
    return count > 0;
  }).length;

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
              {displayedChunksCount}
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
              {nonZeroSourceTypesCount}
            </p>
          </div>
        </div>
      </div>

      {/* Consolidated Source Breakdown - Shows the unique source types with counts */}
      {displayedChunksCount > 0 && nonZeroSourceTypesCount > 0 && (
        <div className="glass-card p-2.5 space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold text-foreground">
              {nonZeroSourceTypesCount === 1
                ? "The Unique Source Type"
                : `The ${nonZeroSourceTypesCount} Unique Source Types`}
            </h4>
            <div className="group relative inline-block align-middle">
              <Info className="w-3 h-3 text-muted-foreground hover:text-primary cursor-help transition-colors" />
              <div className="hidden group-hover:block absolute z-20 w-80 p-2 text-xs text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                <p className="font-semibold mb-1">Displaying: {displayedChunksCount} chunks</p>
                <p className="mb-1">
                  Breakdown: {chunkBreakdown.priorIncidents} Prior Incidents,{" "}
                  {chunkBreakdown.runbookMetadata} Runbook Metadata,{" "}
                  {chunkBreakdown.runbookSteps} Runbook Steps
                </p>
                <p className="text-muted-foreground mt-2">
                  Runbooks below {relevanceThreshold}% relevance are filtered out. Only the top 5 from each category are displayed.
                </p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {sourceTypes
              .map((sourceType) => {
                const count =
                  sourceType === "incident_signature"
                    ? chunkBreakdown.priorIncidents
                    : sourceType === "runbook"
                      ? chunkBreakdown.runbookSteps
                      : sourceType === "runbook_step"
                        ? chunkBreakdown.runbookMetadata
                        : 0;
                return { sourceType, count };
              })
              .filter(({ count }) => count > 0)
              .map(({ sourceType, count }, index) => (
                <div
                  key={index}
                  className="px-2 py-1 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs font-medium flex items-center gap-1.5"
                >
                  <span>{sourceTypeNames[sourceType] || sourceType}</span>
                  <span className="text-xs font-bold text-primary/70">
                    ({count})
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Knowledge Sources (Document Titles) - Different from Source Types */}
      {displayedKnowledgeSources.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Knowledge Sources ({displayedKnowledgeSources.length})
            </h4>
            <div className="group relative inline-block align-middle">
              <Info className="w-3 h-3 text-muted-foreground hover:text-primary cursor-help transition-colors" />
              <div className="hidden group-hover:block absolute z-20 w-64 p-2 text-xs text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                Specific documents and runbooks displayed in the evidence sections below (after threshold filtering)
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {displayedKnowledgeSources.map((source, index) => (
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
      {filteredChunks.length > 0 ? (
        <div className="space-y-3">
          {/* Separate chunks into Prior Incidents and Runbooks */}
          {(() => {
            // Use filteredChunks which already has threshold filtering applied
            const priorIncidents = filteredChunks
              .filter(
                (chunk: any) =>
                  chunk.provenance?.source_type === "incident_signature" ||
                  chunk.metadata?.doc_type === "incident_signature",
              )
              .slice(0, 5); // Limit to top 5

            const allRunbooks = filteredChunks.filter(
              (chunk: any) =>
                chunk.provenance?.source_type === "runbook" ||
                chunk.provenance?.source_type === "runbook_step" ||
                chunk.metadata?.doc_type === "runbook",
            );

            const runbooks = allRunbooks.slice(0, 5); // Limit to top 5
            const totalFilteredRunbooks = allRunbooks.length;

            return (
              <>
                {/* Prior Incidents Section */}
                {priorIncidents.length > 0 && (
                  <div className="space-y-2">
                    <h4
                      className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2 cursor-pointer hover:text-foreground transition-colors"
                      onClick={() => setIsPriorIncidentsExpanded(!isPriorIncidentsExpanded)}
                    >
                      {isPriorIncidentsExpanded ? (
                        <ChevronDown className="w-4 h-4 text-primary" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-primary" />
                      )}
                      <span className="w-1 h-4 bg-primary rounded-full" />
                      Prior Incidents ({priorIncidents.length}
                      {filteredChunks.filter(
                        (chunk: any) =>
                          chunk.provenance?.source_type === "incident_signature" ||
                          chunk.metadata?.doc_type === "incident_signature",
                      ).length > 5
                        ? ` of ${filteredChunks.filter(
                            (chunk: any) =>
                              chunk.provenance?.source_type ===
                                "incident_signature" ||
                              chunk.metadata?.doc_type === "incident_signature",
                          ).length}`
                        : ""}
                      )
                    </h4>
                    {isPriorIncidentsExpanded && (
                      <div className="space-y-2">
                        {priorIncidents.map((chunk, index) => (
                          <EvidenceChunk
                            key={chunk.chunk_id}
                            chunk={chunk}
                            index={index}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Runbooks Section */}
                {runbooks.length > 0 && (
                  <div className="space-y-2">
                    <h4
                      className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-2 cursor-pointer hover:text-foreground transition-colors"
                      onClick={() => setIsRunbooksExpanded(!isRunbooksExpanded)}
                    >
                      {isRunbooksExpanded ? (
                        <ChevronDown className="w-4 h-4 text-primary" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-primary" />
                      )}
                      <span className="w-1 h-4 bg-primary rounded-full" />
                      Runbooks ({runbooks.length}
                      {totalFilteredRunbooks > runbooks.length
                        ? ` of ${totalFilteredRunbooks}`
                        : ""}
                      )
                    </h4>
                    {isRunbooksExpanded && (
                      <div className="space-y-3">
                        {runbooks.map((chunk, index) => (
                          <EvidenceChunk
                            key={chunk.chunk_id}
                            chunk={chunk}
                            index={priorIncidents.length + index}
                          />
                        ))}
                      </div>
                    )}
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
