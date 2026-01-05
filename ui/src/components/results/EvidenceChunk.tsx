import { useState } from "react";
import { ChevronDown, FileText, Hash, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

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
  const hasScores = (scores.vector_score !== undefined && scores.vector_score !== null) ||
                    (scores.fulltext_score !== undefined && scores.fulltext_score !== null) ||
                    (scores.rrf_score !== undefined && scores.rrf_score !== null);
  const metadata = chunk.metadata || {};

  // Calculate overall relevance percentage (using RRF score as primary, or vector as fallback)
  // RRF score is typically 0.0x (e.g., 0.0118), so we multiply by 1000 to get percentage-like value
  // Vector score is 0-1 range, so multiply by 100 to get percentage
  const relevanceScore = scores.rrf_score !== undefined && scores.rrf_score !== null
    ? Math.round(scores.rrf_score * 1000) // RRF is typically 0.0x (e.g., 0.0118 -> 11.8)
    : scores.vector_score !== undefined && scores.vector_score !== null
    ? Math.round(scores.vector_score * 100) // Vector is 0-1 (e.g., 0.489 -> 48.9)
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
        className="w-full flex items-center justify-between p-4 hover:bg-secondary/30 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="p-2 rounded-lg bg-primary/10 flex-shrink-0">
            <FileText className="w-4 h-4 text-primary" />
          </div>
          <div className="text-left flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="font-medium text-foreground text-sm truncate">{chunk.doc_title}</h4>
              {metadata.doc_type && (
                <span className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary font-medium flex-shrink-0">
                  {metadata.doc_type}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 flex-wrap">
              {/* Show incident IDs instead of signature ID for incident signatures */}
              {metadata.source_incident_ids && metadata.source_incident_ids.length > 0 ? (
                <div className="flex items-center gap-1 flex-wrap">
                  <Hash className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                  <div className="flex items-center gap-1 flex-wrap">
                    {metadata.source_incident_ids.slice(0, 3).map((incidentId: string, idx: number) => (
                      <span key={idx} className="text-xs font-mono text-primary font-semibold">
                        {incidentId}
                        {idx < Math.min(metadata.source_incident_ids!.length, 3) - 1 && ","}
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
                  <span className="text-xs font-mono text-muted-foreground truncate max-w-[150px]">
                    {chunk.chunk_id.slice(0, 8)}...
                  </span>
                </div>
              )}
              {/* Show match count for incident signatures */}
              {metadata.match_count !== undefined && metadata.match_count > 0 && (
                <span className="text-xs text-muted-foreground">
                  ({metadata.match_count} {metadata.match_count === 1 ? 'incident' : 'incidents'})
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
          {relevanceScore !== null && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-background/50 border border-border/30">
              <TrendingUp className="w-3 h-3 text-muted-foreground" />
              <span className={cn("text-sm font-semibold font-mono", getRelevanceColor(relevanceScore))}>
                {relevanceScore}%
              </span>
            </div>
          )}
          <ChevronDown
            className={cn(
              "w-5 h-5 text-muted-foreground transition-transform duration-200",
              expanded && "rotate-180"
            )}
          />
        </div>
      </button>
      
      <div
        className={cn(
          "overflow-hidden transition-all duration-300",
          expanded ? "max-h-[600px]" : "max-h-0"
        )}
      >
        <div className="p-4 pt-0 space-y-3">
          {/* Relevance Scores Breakdown */}
          {hasScores && (
            <div className="grid grid-cols-3 gap-3 p-3 rounded-lg bg-background/50 border border-border/30">
              <div className="text-center">
                <div className="text-xs text-muted-foreground mb-1">Vector</div>
                <div className="text-sm font-semibold font-mono text-foreground">
                  {scores.vector_score ? (scores.vector_score * 100).toFixed(1) : "0.0"}%
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-muted-foreground mb-1">Fulltext</div>
                <div className="text-sm font-semibold font-mono text-foreground">
                  {scores.fulltext_score ? (scores.fulltext_score * 100).toFixed(1) : "0.0"}%
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-muted-foreground mb-1">RRF</div>
                <div className="text-sm font-semibold font-mono text-foreground">
                  {scores.rrf_score ? (scores.rrf_score * 1000).toFixed(1) : "0.0"}
                </div>
              </div>
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
              <div className="text-xs text-muted-foreground mb-2">Incident Classification:</div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">Failure Type:</span>
                  <span className="text-xs text-foreground">{metadata.failure_type}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">Error Class:</span>
                  <span className="text-xs text-foreground">{metadata.error_class}</span>
                </div>
                {metadata.symptoms && metadata.symptoms.length > 0 && (
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-semibold text-muted-foreground">Symptoms:</span>
                    <span className="text-xs text-foreground">{metadata.symptoms.join(", ")}</span>
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
                <span className="text-foreground font-medium">{metadata.component}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
