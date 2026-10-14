import React, { useState } from 'react';
import { Citation } from '../../types/rag';
import { FileText, Copy, Check, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';

interface CitationViewerProps {
  citations: Citation[];
}

export const CitationViewer: React.FC<CitationViewerProps> = ({ citations }) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);

  if (!citations || citations.length === 0) return null;

  const handleCopy = (snippet: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(snippet);
    setCopiedSnippet(snippet);
    setTimeout(() => setCopiedSnippet(null), 2000);
  };

  return (
    <div className="mt-3.5 border-t border-slate-100 dark:border-slate-800/80 pt-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
        <FileText className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
        <span>Sources & Citations ({citations.length})</span>
      </div>

      <div className="space-y-2">
        {citations.map((citation, idx) => {
          const isExpanded = expandedId === `${citation.document_id}-${idx}`;
          const isCopied = copiedSnippet === citation.snippet;
          const scorePercent = Math.round(citation.score * 100);

          return (
            <div
              key={`${citation.document_id}-${idx}`}
              className="rounded-lg border border-slate-200/80 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-900/60 overflow-hidden text-xs transition-all"
            >
              <div
                onClick={() =>
                  setExpandedId(isExpanded ? null : `${citation.document_id}-${idx}`)
                }
                className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-slate-100/60 dark:hover:bg-slate-800/50"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-[11px] text-blue-600 dark:text-blue-400 shrink-0 font-medium">
                    [{idx + 1}]
                  </span>
                  <span className="font-medium text-slate-800 dark:text-slate-200 truncate">
                    {citation.document_name}
                  </span>
                  <span className="text-slate-400 dark:text-slate-500 shrink-0">
                    · Page {citation.page_number}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium ${
                      scorePercent >= 90
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400'
                        : 'bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-400'
                    }`}
                    title="Hybrid retrieval relevance score (RRF pgvector + BM25)"
                  >
                    {scorePercent}% match
                  </span>
                  {isExpanded ? (
                    <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                  )}
                </div>
              </div>

              {isExpanded && (
                <div className="px-3 pb-3 pt-1 border-t border-slate-200/60 dark:border-slate-800/80 text-slate-600 dark:text-slate-300">
                  <div className="bg-white dark:bg-slate-950 p-2.5 rounded border border-slate-100 dark:border-slate-800 font-mono text-[11px] leading-relaxed relative group">
                    <p className="whitespace-pre-wrap">{citation.snippet}</p>
                    <button
                      onClick={(e) => handleCopy(citation.snippet, e)}
                      className="mt-2 flex items-center gap-1 text-[11px] text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 cursor-pointer font-sans"
                    >
                      {isCopied ? (
                        <>
                          <Check className="h-3 w-3 text-emerald-600" />
                          <span>Copied snippet</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3" />
                          <span>Copy snippet</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
