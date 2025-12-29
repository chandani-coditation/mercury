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
    };
  };
  index: number;
}

export const EvidenceChunk = ({ chunk, index }: EvidenceChunkProps) => {
  const [expanded, setExpanded] = useState(false);
  const scores = chunk.scores || {};
  const hasScores = scores.vector_score || scores.fulltext_score || scores.rrf_score;
  const metadata = chunk.metadata || {};

  // Calculate overall relevance percentage (using RRF score as primary, or vector as fallback)
  const relevanceScore = scores.rrf_score 
    ? Math.round(scores.rrf_score * 100 * 10) // RRF is typically 0.0x, scale it up
    : scores.vector_score 
    ? Math.round(scores.vector_score * 100) 
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
            <div className="flex items-center gap-3 mt-1">
              <div className="flex items-center gap-1">
                <Hash className="w-3 h-3 text-muted-foreground" />
                <span className="text-xs font-mono text-muted-foreground truncate max-w-[150px]">
                  {chunk.chunk_id.slice(0, 8)}...
                </span>
              </div>
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
            <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap leading-relaxed overflow-auto max-h-64">
              {chunk.content}
            </pre>
          </div>
          
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
