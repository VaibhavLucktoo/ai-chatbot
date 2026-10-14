import React, { useState } from 'react';
import {
  Search,
  Sliders,
  Layers,
  Database,
  Loader2,
  FileText,
  Clock,
  Sparkles,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { DocumentSearchResponse, SearchResultChunk } from '../../types/rag';

export const VectorSearchSandbox: React.FC = () => {
  const [query, setQuery] = useState('HNSW pgvector parameters');
  const [topK, setTopK] = useState(4);
  const [isLoading, setIsLoading] = useState(false);
  const [searchResponse, setSearchResponse] = useState<DocumentSearchResponse | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    try {
      const res = await apiClient.searchDocuments({
        query: query.trim(),
        top_k: topK,
      });
      setSearchResponse(res);
    } catch (err) {
      console.error('Search failed', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 shadow-2xs space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Search className="h-4 w-4 text-blue-600" />
            <span>Hybrid Retrieval Sandbox (POST /v1/documents/search)</span>
          </h3>
          <p className="text-xs text-slate-500">
            Probe raw vector chunks combining pgvector dense cosine & PostgreSQL BM25 sparse rankings
          </p>
        </div>
      </div>

      {/* Query Form */}
      <form onSubmit={handleSearch} className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[240px] relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter search terms to probe vector index..."
            className="w-full rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950 px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
          <span>Top K:</span>
          <select
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            className="rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-2 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
          >
            <option value={3}>3</option>
            <option value={5}>5</option>
            <option value={10}>10</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors cursor-pointer flex items-center gap-1.5"
        >
          {isLoading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Search className="h-3.5 w-3.5" />
          )}
          <span>Execute Probe</span>
        </button>
      </form>

      {/* Results */}
      {searchResponse && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>
              Found <strong>{searchResponse.total_found}</strong> vector chunks for{' '}
              <code className="text-slate-700 dark:text-slate-300">"{searchResponse.query}"</code>
            </span>
            <span className="flex items-center gap-1 font-mono text-[11px]">
              <Clock className="h-3 w-3 text-slate-400" />
              Retrieval: {searchResponse.retrieval_latency_ms}ms
            </span>
          </div>

          <div className="space-y-2.5">
            {searchResponse.results.map((chunk, i) => (
              <div
                key={chunk.chunk_id || i}
                className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 p-3 text-xs space-y-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-blue-600 dark:text-blue-400 font-bold">
                      #{i + 1}
                    </span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {chunk.document_name}
                    </span>
                    <span className="text-slate-400">· Page {chunk.page_number}</span>
                  </div>

                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className="text-slate-500">
                      Dense Cosine: <strong>{(chunk.dense_score * 100).toFixed(0)}%</strong>
                    </span>
                    <span className="text-slate-500">
                      BM25 Sparse: <strong>{(chunk.sparse_score * 100).toFixed(0)}%</strong>
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 font-bold">
                      Hybrid RRF: {(chunk.hybrid_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <p className="bg-white dark:bg-slate-900 p-2.5 rounded border border-slate-200/80 dark:border-slate-800 text-slate-700 dark:text-slate-300 font-mono text-[11px] leading-relaxed">
                  {chunk.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
