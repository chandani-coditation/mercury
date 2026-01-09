import { useState } from "react";
import { ChevronDown, FileText, Hash, TrendingUp, Info } from "lucide-react";
import { ExpandableText } from "@/components/ui/ExpandableText";
import { cn } from "@/lib/utils";
import retrievalConfig from "@/config/retrieval.json";

interface EvidenceChunkProps {
  chunk: {
    chunk_id: string;
    document_id: string;
    doc_title: string;
    content: string;
    provenance?: {
      source_type?: string;
    };
    scores?: {
      vector_score?: number;
      fulltext_score?: number;
      rrf_score?: number;
    };
    metadata?: {
      title?: string;
      service?: string;
      doc_type?: string;
      component?: string;
      incident_signature_id?: string;
      source_incident_ids?: string[];
      match_count?: number;
      failure_type?: string;
      error_class?: string;
      symptoms?: string[];
    };
  };
  index: number;
}

export const EvidenceChunk = ({ chunk, index }: EvidenceChunkProps) => {
  const [expanded, setExpanded] = useState(false);
  const scores = chunk.scores || {};
  // Has scores if at least one score is not null/undefined
  const hasScores =
    (scores.vector_score !== undefined && scores.vector_score !== null) ||
    (scores.fulltext_score !== undefined && scores.fulltext_score !== null) ||
    (scores.rrf_score !== undefined && scores.rrf_score !== null);
  const metadata = chunk.metadata || {};

  // Determine if this is a runbook (threshold applies) or prior incident (always show score)
  const isRunbook =
    chunk.provenance?.source_type === "runbook" ||
    chunk.provenance?.source_type === "runbook_step" ||
    chunk.metadata?.doc_type === "runbook";

  // Calculate overall relevance percentage (using RRF score as primary, or vector as fallback, or fulltext as tertiary)
  // RRF score is typically 0.0x (e.g., 0.0118), so we multiply by 1000 to get percentage-like value
  // Vector score is 0-1 range, so multiply by 100 to get percentage
  // Fulltext score is 0-1 range (ts_rank), so multiply by 100 to get percentage
  // Note: fulltext_score can be very small (1e-20) when there's no keyword match - treat as 0
  const relevanceScore =
    scores.rrf_score !== undefined && scores.rrf_score !== null
      ? Math.round(scores.rrf_score * 1000) // RRF is typically 0.0x (e.g., 0.0118 -> 11.8)
      : scores.vector_score !== undefined && scores.vector_score !== null
        ? Math.round(scores.vector_score * 100) // Vector is 0-1 (e.g., 0.489 -> 48.9)
        : scores.fulltext_score !== undefined && scores.fulltext_score !== null && scores.fulltext_score > 1e-10
          ? Math.round(scores.fulltext_score * 100) // Fulltext is 0-1 (e.g., 0.076 -> 7.6), ignore tiny values like 1e-20
          : null;

  const getRelevanceColor = (score: number) => {
    if (score >= 80) return "text-success";
    if (score >= 60) return "text-primary";
    if (score >= 40) return "text-warning";
    return "text-muted-foreground";
  };

  return (
    <div
      className="glass-card overflow-hidden animate-slide-up hover:border-primary/40 transition-colors"
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-secondary/30 transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className="p-1.5 rounded-lg bg-primary/10 flex-shrink-0">
            <FileText className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-left flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="font-medium text-foreground text-sm">
                <ExpandableText text={chunk.doc_title} charLimit={40} />
              </h4>
              {metadata.doc_type && (
                <span className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary font-medium flex-shrink-0">
                  {metadata.doc_type}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 flex-wrap">
              {/* Show incident IDs instead of signature ID for incident signatures */}
              {metadata.source_incident_ids &&
              metadata.source_incident_ids.length > 0 ? (
                <div className="flex items-center gap-1 flex-wrap">
                  <Hash className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                  <div className="flex items-center gap-1 flex-wrap">
                    {metadata.source_incident_ids
                      .slice(0, 3)
                      .map((incidentId: string, idx: number) => (
                        <span
                          key={idx}
                          className="text-xs font-mono text-primary font-semibold"
                        >
                          {incidentId}
                          {idx <
                            Math.min(metadata.source_incident_ids!.length, 3) -
                              1 && ","}
                        </span>
                      ))}
                    {metadata.source_incident_ids.length > 3 && (
                      <span className="text-xs text-muted-foreground">
                        +{metadata.source_incident_ids.length - 3} more
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <Hash className="w-3 h-3 text-muted-foreground" />
                  <span className="text-xs font-mono text-muted-foreground">
                    <ExpandableText text={chunk.chunk_id} charLimit={8} />
                  </span>
                </div>
              )}
              {/* Show match count for incident signatures */}
              {metadata.match_count !== undefined &&
                metadata.match_count > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({metadata.match_count}{" "}
                    {metadata.match_count === 1 ? "incident" : "incidents"})
                  </span>
                )}
              {metadata.service && (
                <span className="text-xs text-muted-foreground">
                  {metadata.service}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          {relevanceScore !== null &&
            // For runbooks, only show if above threshold; for prior incidents, always show
            (!isRunbook || relevanceScore >= (retrievalConfig.ui_relevance_threshold || 0)) && (
              <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-background/50 border border-border/30">
                <TrendingUp className="w-3 h-3 text-muted-foreground" />
                <span
                  className={cn(
                    "text-sm font-semibold font-mono",
                    getRelevanceColor(relevanceScore),
                  )}
                >
                  {relevanceScore}%
                </span>
              </div>
            )}
          <ChevronDown
            className={cn(
              "w-5 h-5 text-muted-foreground transition-transform duration-200",
              expanded && "rotate-180",
            )}
          />
        </div>
      </button>

      <div
        className={cn(
          "overflow-hidden transition-all duration-300",
          expanded ? "max-h-[600px]" : "max-h-0",
        )}
      >
        <div className="p-3 pt-0 space-y-2">
          {/* Relevance Scores Breakdown */}
          {hasScores && (
            <div className="space-y-1.5">
              <div className="grid grid-cols-3 gap-2 p-2 rounded-lg bg-background/50 border border-border/30">
                <div className="text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <span className="text-xs text-muted-foreground">Vector</span>
                    <div className="group relative inline-block align-middle">
                      <Info className="w-3.5 h-3.5 text-muted-foreground hover:text-primary cursor-help transition-colors" />
                      <div className="hidden group-hover:block absolute z-20 w-56 p-2 text-[10px] text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                        Semantic similarity between this chunk and the alert based on vector embeddings.
                        Higher means a closer semantic match.
                      </div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold font-mono text-foreground">
                    {scores.vector_score
                      ? (scores.vector_score * 100).toFixed(1)
                      : "0.0"}
                    %
                  </div>
                </div>
                <div className="text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <span className="text-xs text-muted-foreground">Fulltext</span>
                    <div className="group relative inline-block align-middle">
                      <Info className="w-3.5 h-3.5 text-muted-foreground hover:text-primary cursor-help transition-colors" />
                      <div className="hidden group-hover:block absolute z-20 w-56 p-2 text-[10px] text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                        Keyword-based match score from full-text search. Higher means more overlapping
                        words and phrases with the alert.
                      </div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold font-mono text-foreground">
                    {scores.fulltext_score
                      ? (scores.fulltext_score * 100).toFixed(1)
                      : "0.0"}
                    %
                  </div>
                </div>
                <div className="text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <span className="text-xs text-muted-foreground">RRF</span>
                    <div className="group relative inline-block align-middle">
                      <Info className="w-3.5 h-3.5 text-muted-foreground hover:text-primary cursor-help transition-colors" />
                      <div className="hidden group-hover:block absolute z-20 w-64 p-2 text-[10px] text-foreground bg-background border border-border rounded-lg shadow-lg left-1/2 -translate-x-1/2 top-4">
                        Reciprocal Rank Fusion (RRF) combines the vector and full-text rankings into a
                        single relevance score so the best matches from both methods are surfaced.
                      </div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold font-mono text-foreground">
                    {scores.rrf_score
                      ? (scores.rrf_score * 1000).toFixed(1)
                      : "0.0"}
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground leading-snug">
                <span className="font-semibold">Vector</span> = semantic similarity,{" "}
                <span className="font-semibold">Fulltext</span> = keyword match,{" "}
                <span className="font-semibold">RRF</span> = combined relevance from both.
              </p>
            </div>
          )}

          {/* Content */}
          <div className="p-3 rounded-lg bg-background/50 border border-border/30">
            <pre className="text-sm text-foreground whitespace-pre-wrap leading-relaxed overflow-auto max-h-64">
              {chunk.content}
            </pre>
          </div>

          {/* Additional metadata for incident signatures */}
          {metadata.failure_type && metadata.error_class && (
            <div className="p-3 rounded-lg bg-background/50 border border-border/30">
              <div className="text-xs text-muted-foreground mb-2">
                Incident Classification:
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Failure Type:
                  </span>
                  <span className="text-xs text-foreground">
                    {metadata.failure_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Error Class:
                  </span>
                  <span className="text-xs text-foreground">
                    {metadata.error_class}
                  </span>
                </div>
                {metadata.symptoms && metadata.symptoms.length > 0 && (
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-semibold text-muted-foreground">
                      Symptoms:
                    </span>
                    <span className="text-xs text-foreground">
                      {metadata.symptoms.join(", ")}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {chunk.provenance?.source_type && (
              <div className="flex items-center gap-1">
                <span className="text-muted-foreground">Source:</span>
                <span className="px-2 py-1 rounded bg-primary/10 text-primary font-medium">
                  {chunk.provenance.source_type}
                </span>
              </div>
            )}
            {metadata.component && (
              <div className="flex items-center gap-1">
                <span className="text-muted-foreground">Component:</span>
                <span className="text-foreground font-medium">
                  {metadata.component}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
