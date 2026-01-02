import { Database, FileSearch } from "lucide-react";
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
  
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stats Header - Highlighted for Demo */}
      <div className="flex flex-wrap gap-4">
        <div className="glass-card px-5 py-4 flex items-center gap-3 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
          <div className="absolute -inset-0.5 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          <div className="p-2 rounded-lg bg-primary/10 relative z-10">
            <Database className="w-5 h-5 text-primary" />
          </div>
          <div className="relative z-10">
            <p className="text-xs text-muted-foreground">Chunks Retrieved</p>
            <p className="text-2xl font-bold font-mono text-foreground">
              {chunksUsed}
            </p>
          </div>
        </div>
        
        <div className="glass-card px-5 py-4 flex items-center gap-3 relative border-2 border-primary/30 shadow-lg shadow-primary/10">
          <div className="absolute -inset-0.5 bg-primary/20 rounded-lg blur-sm opacity-50 animate-pulse" />
          <div className="p-2 rounded-lg bg-primary/10 relative z-10">
            <FileSearch className="w-5 h-5 text-primary" />
          </div>
          <div className="relative z-10">
            <p className="text-xs text-muted-foreground">Unique Sources</p>
            <p className="text-2xl font-bold font-mono text-foreground">
              {(() => {
                const sourceTypes = new Set(chunks.map((c: any) => c.provenance?.source_type || 'unknown').filter(Boolean));
                return sourceTypes.size || 0;
              })()}
            </p>
          </div>
        </div>
      </div>

      {/* Sources List */}
      {chunkSources.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Knowledge Sources
          </h4>
          <div className="flex flex-wrap gap-2">
            {[...new Set(chunkSources)].map((source, index) => (
              <div
                key={index}
                className="px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium"
              >
                {source}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evidence Chunks */}
      {chunks.length > 0 ? (
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Evidence Details
          </h4>
          <div className="space-y-3">
            {chunks.map((chunk, index) => (
              <EvidenceChunk key={chunk.chunk_id} chunk={chunk} index={index} />
            ))}
          </div>
        </div>
      ) : (
        <div className="glass-card p-8 text-center">
          <FileSearch className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-50" />
          <p className="text-muted-foreground">No evidence chunks available</p>
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
