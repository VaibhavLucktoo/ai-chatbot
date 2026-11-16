import React, {useEffect, useRef} from 'react';

export function ConfirmConfigurationDelete({name, kind, busy, error, onCancel, onConfirm}: {
  name: string; kind: 'assistant' | 'connection'; busy: boolean; error?: string;
  onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    return () => {if (previous?.isConnected) previous.focus();};
  }, []);
  useEffect(() => {
    if (busy) dialog.current?.focus(); else cancel.current?.focus();
  }, [busy]);
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="configuration-delete-title" tabIndex={-1}
      className="w-full max-w-md rounded-3xl bg-white/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-800 p-6 md:p-7 shadow-2xl backdrop-blur-xl"
      onKeyDown={event => {
        if (event.key === 'Escape' && !busy) {event.preventDefault(); onCancel();}
        if (event.key === 'Tab') {
          const buttons = [...(dialog.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
          if (!buttons.length) {event.preventDefault(); return;}
          const target = event.shiftKey ? buttons[buttons.length - 1] : buttons[0];
          if (event.shiftKey && document.activeElement === buttons[0] || !event.shiftKey && document.activeElement === buttons[buttons.length - 1]) {
            event.preventDefault(); target.focus();
          }
        }
      }}>
      <h2 id="configuration-delete-title" className="text-base font-semibold text-slate-900 dark:text-white">Delete {kind}?</h2>
      <p className="mt-3 text-xs font-mono text-slate-700 dark:text-slate-300 bg-slate-100/80 dark:bg-slate-800/80 p-2.5 rounded-xl border border-slate-200/60 dark:border-slate-700/60 break-words">Permanently delete <strong>{name}</strong>?</p>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{kind === 'assistant'
        ? 'Its settings, document assignments and stored conversation history will be removed. Your PDFs and model analytics will remain.'
        : 'Its saved encrypted API key will be removed. The key remains valid at the provider until you revoke it there.'}</p>
      {error && <p role="alert" className="mt-3 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      <div className="mt-6 pt-3 border-t border-slate-100 dark:border-slate-800 flex justify-end gap-2.5">
        <button ref={cancel} type="button" disabled={busy} onClick={onCancel} className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 px-4 py-2 text-xs font-medium transition-all cursor-pointer disabled:opacity-40">Cancel</button>
        <button type="button" disabled={busy} onClick={onConfirm} className="rounded-xl bg-rose-600 hover:bg-rose-500 px-4 py-2 text-xs font-medium text-white shadow-xs hover:shadow-rose-600/20 active:scale-95 transition-all disabled:opacity-40 cursor-pointer">{busy ? 'Deleting…' : 'Delete permanently'}</button>
      </div>
    </div>
  </div>;
}
