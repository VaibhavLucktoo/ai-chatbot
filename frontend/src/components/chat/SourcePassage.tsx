import React, {useState} from 'react';
import {Check, ChevronDown, ChevronUp, Copy, FileText, Loader2, Quote} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import type {Passage, Source} from '../../types/backend';

export function SourcePassage({source, number}: {source: Source; number: number}) {
  const [open, setOpen] = useState(false);
  const [passage, setPassage] = useState<Passage>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(undefined);
    try {
      setPassage(await backend.passage(source));
    } catch (problem) {
      setError(describeError(problem));
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && !passage && !loading) void load();
  };

  const handleCopy = async () => {
    if (!passage) return;
    try {
      await navigator.clipboard.writeText(passage.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Clipboard unavailable. Select the passage text to copy it.');
    }
  };

  return (
    <div className="rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 overflow-hidden shadow-2xs hover:border-blue-300 dark:hover:border-blue-700/60 transition-all">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={`Inspect source ${number}: ${source.filename}, page ${source.page_number}`}
        className="w-full flex items-center gap-2.5 p-2.5 sm:px-3.5 text-left text-xs hover:bg-slate-100/60 dark:hover:bg-slate-800/60 transition-colors group"
      >
        <span className="font-mono text-[11px] font-bold px-1.5 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/60 shrink-0">
          [{number}]
        </span>
        <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400 group-hover:text-blue-500 transition-colors"/>
        <span className="truncate flex-1 font-medium text-slate-700 dark:text-slate-300">
          {source.filename}
        </span>
        <span className="shrink-0 text-[10px] font-mono font-medium text-slate-500 dark:text-slate-400 px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50">
          Page {source.page_number}
        </span>
        {open ? (
          <ChevronUp className="w-3.5 h-3.5 text-slate-400 shrink-0"/>
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0"/>
        )}
      </button>

      {open && (
        <div className="border-t border-slate-200/80 dark:border-slate-800 p-4 bg-white dark:bg-slate-950/70 animate-in fade-in duration-150">
          {loading && (
            <p role="status" className="text-xs flex gap-2 items-center text-slate-500 dark:text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin text-blue-600"/>
              Loading original passage from page {source.page_number}…
            </p>
          )}

          {error && (
            <div role="alert" className="text-xs text-rose-600 dark:text-rose-400 flex items-center justify-between">
              <span>{error}</span>
              <button onClick={() => void load()} className="underline font-semibold ml-2">
                Retry passage
              </button>
            </div>
          )}

          {passage && (
            <div className="space-y-3">
              <div className="relative pl-3.5 border-l-2 border-blue-500/70">
                <Quote className="w-3 h-3 text-blue-400 mb-1 opacity-70"/>
                <p className="whitespace-pre-wrap break-words text-xs sm:text-sm leading-relaxed text-slate-700 dark:text-slate-300 font-sans">
                  {passage.content}
                </p>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800/80 text-[11px]">
                <span className="text-[10px] font-mono text-slate-400">
                  Chunk #{passage.chunk_index + 1} &middot; Page {passage.page_number}
                </span>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 font-medium transition-colors cursor-pointer"
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-500"/>
                      <span className="text-emerald-600 dark:text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3"/>
                      <span>Copy passage</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
