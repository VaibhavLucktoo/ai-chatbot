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
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="configuration-delete-title" tabIndex={-1}
      className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-xl"
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
      <h2 id="configuration-delete-title" className="text-lg font-semibold">Delete {kind}?</h2>
      <p className="mt-3 text-sm break-words">Permanently delete <strong>{name}</strong>?</p>
      <p className="mt-2 text-sm text-slate-500">{kind === 'assistant'
        ? 'Its settings, document assignments and stored conversation history will be removed. Your PDFs and model analytics will remain.'
        : 'Its saved encrypted API key will be removed. The key remains valid at the provider until you revoke it there.'}</p>
      {error && <p role="alert" className="mt-3 text-sm text-rose-600">{error}</p>}
      <div className="mt-5 flex justify-end gap-3">
        <button ref={cancel} type="button" disabled={busy} onClick={onCancel} className="rounded-lg border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm disabled:opacity-40">Cancel</button>
        <button type="button" disabled={busy} onClick={onConfirm} className="rounded-lg bg-rose-600 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? 'Deleting…' : 'Delete permanently'}</button>
      </div>
    </div>
  </div>;
}
