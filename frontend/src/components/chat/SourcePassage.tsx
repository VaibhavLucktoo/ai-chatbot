import React, {useState} from 'react';
import {ChevronDown, ChevronUp, Copy, FileText, Loader2} from 'lucide-react';
import {backend, describeError} from '../../services/backend';
import type {Passage, Source} from '../../types/backend';

export function SourcePassage({source, number}: {source: Source; number: number}) {
  const [open, setOpen] = useState(false);
  const [passage, setPassage] = useState<Passage>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [copied, setCopied] = useState(false);
  const load = async () => {
    setLoading(true); setError(undefined);
    try {setPassage(await backend.passage(source));} catch (problem) {setError(describeError(problem));}
    finally {setLoading(false);}
  };
  const toggle = () => {
    const next = !open; setOpen(next);
    if (next && !passage && !loading) void load();
  };
  return <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
    <button type="button" onClick={toggle} aria-expanded={open} aria-label={`Inspect source ${number}: ${source.filename}, page ${source.page_number}`} className="w-full flex items-center gap-2 p-3 text-left text-xs hover:bg-slate-50 dark:hover:bg-slate-800">
      <span className="font-mono text-blue-600 dark:text-blue-400">[{number}]</span><FileText className="h-4 w-4 shrink-0 text-slate-400"/>
      <span className="truncate flex-1 font-medium">{source.filename}</span><span className="shrink-0 text-slate-500">Page {source.page_number}</span>
      {open ? <ChevronUp className="w-4 h-4"/> : <ChevronDown className="w-4 h-4"/>}
    </button>
    {open && <div className="border-t border-slate-200 dark:border-slate-700 p-4 bg-slate-50 dark:bg-slate-950">
      {loading && <p role="status" className="text-xs flex gap-2 items-center"><Loader2 className="h-4 w-4 animate-spin"/>Loading original passage…</p>}
      {error && <div role="alert" className="text-xs text-rose-600 dark:text-rose-400">{error} <button onClick={() => void load()} className="underline">Retry passage</button></div>}
      {passage && <><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{passage.content}</p>
        <button className="mt-3 flex items-center gap-1 text-xs text-slate-500" onClick={async () => {
          try {await navigator.clipboard.writeText(passage.content); setCopied(true);} catch {setError('Clipboard unavailable. Select the passage text to copy it.');}
        }}><Copy className="h-3 w-3"/>{copied ? 'Copied' : 'Copy passage'}</button></>}
    </div>}
  </div>;
}
