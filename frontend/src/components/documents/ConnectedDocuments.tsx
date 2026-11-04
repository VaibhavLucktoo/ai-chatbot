import React, {useRef, useState} from 'react';
import {
  Archive,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Download,
  FileText,
  FileUp,
  Layers,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';
import {ApiError, backend, describeError, MAX_PDF_BYTES} from '../../services/backend';
import type {DocumentInfo, DocumentStatus} from '../../types/backend';

function StatusBadge({status, active}: {status: DocumentStatus; active?: boolean}) {
  const isRetired = status === 'ready' && active === false;
  const isProcessing = status === 'pending';
  const isFailed = status === 'failed';
  const isReady = status === 'ready' && active !== false;

  const text = isRetired ? 'Retired' : isProcessing ? 'Processing' : isFailed ? 'Failed' : 'Ready';

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
        isReady
          ? 'bg-emerald-50/90 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800/60'
          : isFailed
          ? 'bg-rose-50/90 text-rose-700 border-rose-200/80 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800/60'
          : isProcessing
          ? 'bg-amber-50/90 text-amber-700 border-amber-200/80 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800/60'
          : 'bg-slate-100/90 text-slate-600 border-slate-200/80 dark:bg-slate-800/60 dark:text-slate-400 dark:border-slate-700/60'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isReady
            ? 'bg-emerald-500 shadow-xs shadow-emerald-400'
            : isFailed
            ? 'bg-rose-500'
            : isProcessing
            ? 'bg-amber-500 animate-pulse'
            : 'bg-slate-400'
        }`}
      />
      {text}
    </span>
  );
}

export function ConnectedDocuments() {
  const {
    page,
    offset,
    setOffset,
    documentsLoading,
    documentError,
    refreshDocuments,
    setSelectedIds,
    setTab,
    upload,
    jobs,
    pollError,
    health,
    discardDocument,
  } = useChatbot();

  const [filter, setFilter] = useState('');
  const [file, setFile] = useState<File>();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string>();
  const [uploadMessage, setUploadMessage] = useState<string>();
  const [actionError, setActionError] = useState<string>();
  const [busyId, setBusyId] = useState<string>();
  const [confirmDelete, setConfirmDelete] = useState<DocumentInfo>();
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const choose = (candidate?: File) => {
    if (uploading) return;
    setFile(undefined);
    setUploadError(undefined);
    setUploadMessage(undefined);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Choose a PDF file.');
      return;
    }
    if (!candidate.size) {
      setUploadError('This file is empty. Choose a searchable PDF.');
      return;
    }
    if (candidate.size > MAX_PDF_BYTES) {
      setUploadError('Maximum PDF size is 10 MiB.');
      return;
    }
    setFile(candidate);
  };

  const submitUpload = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError(undefined);
    setUploadMessage(undefined);
    try {
      const job = await upload(file);
      setUploadMessage(
        job.status === 'ready'
          ? 'This PDF is already indexed and ready.'
          : 'PDF received. Processing continues in the backend; its status updates below.'
      );
      setFile(undefined);
      if (input.current) input.current.value = '';
    } catch (error) {
      setUploadError(describeError(error));
    } finally {
      setUploading(false);
    }
  };

  const action = async (doc: DocumentInfo, work: () => Promise<void>, remove = false) => {
    if (busyId) return;
    setBusyId(doc.id);
    setActionError(undefined);
    try {
      try {
        await work();
      } catch (error) {
        // A previous delete can have committed before its response was lost.
        if (!(remove && error instanceof ApiError && error.status === 404)) throw error;
      }
      if (remove) {
        setConfirmDelete(undefined);
        discardDocument(doc.id);
      }
      await refreshDocuments();
    } catch (error) {
      setActionError(describeError(error));
    } finally {
      setBusyId(undefined);
    }
  };

  const docs = page.items.filter(doc => doc.filename.toLowerCase().includes(filter.toLowerCase()));
  const recentJobs = Object.values(jobs);
  const readyCount = page.items.filter(d => d.status === 'ready' && d.active !== false).length;

  return (
    <section className="max-w-6xl mx-auto px-5 md:px-8 py-6 md:py-8 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">Your documents</h1>
            <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/70 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60">
              {page.total} registered
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Upload, inspect, and choose what your assistant can search.
          </p>
        </div>

        <button
          onClick={() => void refreshDocuments()}
          disabled={documentsLoading}
          className="self-start sm:self-auto flex items-center gap-2 text-xs font-medium rounded-xl border border-slate-200/90 dark:border-slate-800/90 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md px-3.5 py-2 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/60 shadow-2xs transition-all disabled:opacity-40 cursor-pointer"
        >
          <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${documentsLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Top Bento Row: Ingestion Dropzone & Corpus Overview */}
      <div className="grid md:grid-cols-[1.6fr_1fr] gap-5">
        {/* Modern Interactive Dropzone */}
        <div
          onDragOver={event => {
            event.preventDefault();
            if (!uploading) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={event => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files[0]);
          }}
          className={`relative overflow-hidden rounded-3xl border-2 border-dashed p-6 md:p-7 transition-all duration-300 ${
            dragging
              ? 'border-blue-500 dark:border-blue-400 bg-blue-50/70 dark:bg-blue-950/50 shadow-lg shadow-blue-500/10 scale-[1.005]'
              : 'border-slate-200/90 dark:border-slate-800/90 glass-panel hover:border-slate-300 dark:hover:border-slate-700'
          }`}
        >
          <div className="flex items-start gap-4">
            <div className="p-3.5 rounded-2xl bg-gradient-to-br from-blue-500/10 to-indigo-500/10 dark:from-blue-500/20 dark:to-indigo-500/20 border border-blue-500/20 text-blue-600 dark:text-blue-400 shrink-0 shadow-2xs">
              <FileUp className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h2 className="font-semibold text-sm text-slate-800 dark:text-slate-100">Add a PDF</h2>
                <span className="text-[10px] uppercase font-mono font-medium px-2 py-0.5 rounded-full bg-blue-100/70 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200/40 dark:border-blue-800/40">
                  hybrid indexed
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                Drop a searchable PDF here or choose one from your device.
                <br />
                Up to 10 MiB and 100 pages. Scanned image-only PDFs require OCR first.
              </p>
            </div>
          </div>

          <input
            ref={input}
            type="file"
            accept=".pdf,application/pdf"
            aria-label="Choose PDF"
            className="sr-only"
            disabled={uploading}
            onChange={event => choose(event.target.files?.[0])}
          />

          <div className="flex flex-wrap items-center gap-3 mt-5 pt-3 border-t border-slate-100 dark:border-slate-800/60">
            <button
              onClick={() => {
                if (input.current) input.current.value = '';
                input.current?.click();
              }}
              disabled={uploading}
              className="text-xs font-medium px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-700/60 text-slate-700 dark:text-slate-200 shadow-2xs transition-all disabled:opacity-40 cursor-pointer"
            >
              Choose PDF
            </button>

            {file && (
              <div className="flex flex-wrap items-center gap-2.5">
                <span
                  className="text-xs font-mono text-slate-600 dark:text-slate-300 bg-slate-100/80 dark:bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-200/60 dark:border-slate-700/60 truncate max-w-64"
                  title={file.name}
                >
                  {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MiB
                </span>
                <button
                  onClick={() => void submitUpload()}
                  disabled={uploading || health.api !== 'online'}
                  className="inline-flex gap-2 items-center px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-xs shadow-xs hover:shadow-blue-500/20 active:scale-95 transition-all disabled:opacity-40 cursor-pointer"
                >
                  {uploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {uploading ? 'Submitting…' : 'Upload PDF'}
                </button>
              </div>
            )}
          </div>

          {uploadError && (
            <p role="alert" className="mt-3.5 text-xs text-rose-600 dark:text-rose-400 bg-rose-50/80 dark:bg-rose-950/40 border border-rose-200/70 dark:border-rose-900/70 px-3.5 py-2.5 rounded-xl">
              {uploadError}
            </p>
          )}

          {uploadMessage && (
            <p role="status" className="mt-3.5 text-xs text-emerald-700 dark:text-emerald-300 bg-emerald-50/80 dark:bg-emerald-950/40 border border-emerald-200/70 dark:border-emerald-900/70 px-3.5 py-2.5 rounded-xl">
              {uploadMessage}
            </p>
          )}
        </div>

        {/* Corpus Overview Bento Card */}
        <div className="relative overflow-hidden rounded-3xl p-6 md:p-7 glass-panel border border-slate-200/90 dark:border-slate-800/90 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500">
                Corpus overview
              </p>
              <Layers className="h-4 w-4 text-slate-400/80" />
            </div>

            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                {page.total}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-normal">
                documents
              </span>
            </div>

            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-50/80 dark:bg-emerald-950/40 px-2 py-0.5 rounded-md border border-emerald-200/60 dark:border-emerald-800/60">
                <CheckCircle2 className="h-3 w-3" />
                {readyCount} ready in search
              </span>
            </div>
          </div>

          <p className="text-xs text-slate-500 dark:text-slate-400 mt-4 leading-relaxed pt-3 border-t border-slate-100 dark:border-slate-800/60">
            Only active, ready documents are searched. Retire an outdated PDF to exclude it while keeping its source and citations.
          </p>
        </div>
      </div>

      {/* Real-Time Upload Activity Tracker */}
      {!!recentJobs.length && (
        <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800/90 glass-panel p-4 md:p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            <h2 className="text-xs font-semibold text-slate-800 dark:text-slate-200">Upload activity</h2>
          </div>
          <div className="space-y-2">
            {recentJobs.map(job => (
              <div
                key={job.document_id}
                className="flex justify-between gap-3 text-xs items-center p-2 rounded-xl bg-slate-50/80 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/60"
              >
                <span className="truncate font-mono text-slate-700 dark:text-slate-300">{job.filename}</span>
                <StatusBadge status={job.status} />
              </div>
            ))}
          </div>
          {recentJobs.some(job => job.status === 'failed') && (
            <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">
              An upload failed. The PDF may be unsupported, or processing was interrupted. Retry the original file when the backend is ready.
            </p>
          )}
        </div>
      )}

      {/* Connection & General Errors */}
      {pollError && (
        <p role="alert" className="text-sm text-amber-700 dark:text-amber-300 bg-amber-50/80 dark:bg-amber-950/40 border border-amber-200/70 dark:border-amber-900/70 p-4 rounded-2xl">
          Status polling paused by a connection error: {pollError} It will retry automatically.
        </p>
      )}

      {documentError && (
        <div role="alert" className="rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50/90 dark:bg-rose-950/60 p-4 text-sm text-rose-700 dark:text-rose-300">
          {documentError} Existing rows may be stale.{' '}
          <button onClick={() => void refreshDocuments()} className="underline font-semibold hover:text-rose-900 dark:hover:text-rose-100 cursor-pointer">
            Try again
          </button>
        </div>
      )}

      {actionError && (
        <p role="alert" className="text-sm text-rose-600 dark:text-rose-400 bg-rose-50/80 dark:bg-rose-950/40 border border-rose-200/70 dark:border-rose-900/70 p-3.5 rounded-2xl">
          {actionError}
        </p>
      )}

      {/* Document Library Bento Container */}
      <div className="rounded-3xl border border-slate-200/90 dark:border-slate-800/90 glass-panel overflow-hidden shadow-xs">
        {/* Table Filter / Search Header */}
        <div className="flex flex-wrap gap-3 items-center justify-between border-b border-slate-200/80 dark:border-slate-800/80 p-4 md:p-5">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-blue-500" />
            <h2 className="font-semibold text-sm text-slate-800 dark:text-slate-100">Document library</h2>
          </div>

          <div className="relative">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              aria-label="Filter documents on this page"
              value={filter}
              onChange={event => setFilter(event.target.value)}
              placeholder="Filter this page…"
              className="rounded-xl bg-slate-50/90 dark:bg-slate-950/80 border border-slate-200/80 dark:border-slate-700/80 pl-8 pr-3 py-2 text-xs text-slate-800 dark:text-slate-200 outline-none focus:border-blue-500 transition-colors w-48 sm:w-60"
            />
          </div>
        </div>

        {/* Document List / Empty States */}
        {documentsLoading && !page.items.length ? (
          <p role="status" className="p-12 flex items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
            Loading documents…
          </p>
        ) : !docs.length ? (
          <div className="p-14 text-center text-sm text-slate-500 dark:text-slate-400">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 flex items-center justify-center mx-auto mb-3 text-slate-400">
              <FileText className="h-6 w-6" />
            </div>
            {filter ? 'No matches on this page.' : documentError ? 'Document library is unavailable.' : 'Your library is empty. Upload a PDF to get started.'}
          </div>
        ) : (
          <div className="divide-y divide-slate-100/90 dark:divide-slate-800/80">
            {docs.map(doc => (
              <div
                key={doc.id}
                className="p-4 md:p-5 flex flex-col md:flex-row md:items-center gap-4 hover:bg-slate-50/70 dark:hover:bg-slate-800/30 transition-colors group"
              >
                <div className="flex items-start gap-3.5 flex-1 min-w-0">
                  <div className="rounded-2xl bg-gradient-to-br from-rose-50 to-orange-50 dark:from-rose-950/40 dark:to-orange-950/20 border border-rose-200/50 dark:border-rose-900/50 p-2.5 text-rose-500 dark:text-rose-400 shrink-0">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-sm text-slate-800 dark:text-slate-100 break-all">
                        {doc.filename}
                      </h3>
                      <StatusBadge status={doc.status} active={doc.active} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {doc.status === 'ready'
                        ? `${doc.page_count} pages · ${doc.chunk_count} passages`
                        : doc.status === 'pending'
                        ? 'Processing and indexing…'
                        : 'Processing failed; re-upload the original PDF to retry.'}{' '}
                      · {new Date(doc.created_at).toLocaleDateString()}
                    </p>
                    {!doc.source_available && (
                      <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                        Original PDF unavailable. Citations remain accessible.
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs shrink-0">
                  {/* Chat with Document */}
                  <button
                    disabled={doc.status !== 'ready' || !doc.active || !!busyId}
                    onClick={() => {
                      setSelectedIds([doc.id]);
                      setTab('chat');
                    }}
                    className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/80 dark:to-indigo-950/60 text-blue-600 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60 font-medium hover:brightness-105 active:scale-95 transition-all disabled:opacity-30 cursor-pointer"
                  >
                    <MessageSquare className="h-3.5 w-3.5" />
                    Chat
                  </button>

                  {/* Download Original PDF */}
                  <button
                    aria-label={`Download ${doc.filename}`}
                    title={doc.source_available ? 'Download original PDF' : 'Re-upload the original file to enable download'}
                    disabled={!doc.source_available || !!busyId}
                    onClick={() => void action(doc, () => backend.download(doc))}
                    className="p-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 rounded-xl transition-all disabled:opacity-25 cursor-pointer"
                  >
                    <Download className="h-4 w-4" />
                  </button>

                  {/* Retire / Reactivate */}
                  <button
                    disabled={doc.status !== 'ready' || !!busyId}
                    onClick={() => void action(doc, () => backend.activation(doc.id, !doc.active))}
                    className="inline-flex items-center gap-1.5 px-3 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 rounded-xl transition-all disabled:opacity-25 cursor-pointer"
                  >
                    {doc.active ? <Archive className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5 text-emerald-500" />}
                    {doc.active ? 'Retire' : 'Reactivate'}
                  </button>

                  {/* Delete Document */}
                  <button
                    aria-label={`Delete ${doc.filename}`}
                    disabled={!!busyId}
                    onClick={() => {
                      setActionError(undefined);
                      setConfirmDelete(doc);
                    }}
                    className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50/80 dark:hover:bg-rose-950/50 rounded-xl transition-all disabled:opacity-25 cursor-pointer"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>

                  {busyId === doc.id && <Loader2 className="h-4 w-4 animate-spin text-blue-500" />}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination Bar */}
        <div className="p-4 md:p-5 border-t border-slate-200/80 dark:border-slate-800/80 flex justify-between items-center text-xs text-slate-500 dark:text-slate-400 bg-slate-50/40 dark:bg-slate-900/40">
          <span>
            {page.total ? `${offset + 1}–${Math.min(offset + page.limit, page.total)} of ${page.total}` : '0 documents'}
          </span>
          <div className="flex gap-2">
            <button
              aria-label="Previous document page"
              disabled={!offset || documentsLoading}
              onClick={() => setOffset(Math.max(0, offset - page.limit))}
              className="p-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/60 rounded-xl disabled:opacity-25 transition-all cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <button
              aria-label="Next document page"
              disabled={offset + page.limit >= page.total || documentsLoading}
              onClick={() => setOffset(offset + page.limit)}
              className="p-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/60 rounded-xl disabled:opacity-25 transition-all cursor-pointer"
            >
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Acrylic Modal */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
          onKeyDown={event => {
            if (event.key === 'Escape' && !busyId) setConfirmDelete(undefined);
            if (event.key === 'Tab') {
              const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not([disabled])');
              const first = buttons[0];
              const last = buttons[buttons.length - 1];
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
              }
            }
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            className="rounded-3xl p-6 md:p-7 w-full max-w-md bg-white/95 dark:bg-slate-900/95 border border-slate-200 dark:border-slate-800 shadow-2xl backdrop-blur-xl"
          >
            <div className="flex justify-between gap-3 items-center">
              <h2 id="delete-title" className="font-semibold text-base text-slate-900 dark:text-white">
                Delete this document?
              </h2>
              <button
                disabled={!!busyId}
                aria-label="Close delete confirmation"
                onClick={() => setConfirmDelete(undefined)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs font-mono text-slate-600 dark:text-slate-300 bg-slate-100/80 dark:bg-slate-800/80 p-2.5 rounded-xl border border-slate-200/60 dark:border-slate-700/60 mt-3.5 break-all">
              {confirmDelete.filename}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
              This permanently removes the PDF and its indexed passages. Existing citations to it will no longer open.
            </p>

            {actionError && (
              <p role="alert" className="text-xs text-rose-600 dark:text-rose-400 mt-3">
                {actionError}
              </p>
            )}

            <div className="flex justify-end gap-2.5 mt-6 pt-3 border-t border-slate-100 dark:border-slate-800">
              <button
                autoFocus
                disabled={!!busyId}
                onClick={() => setConfirmDelete(undefined)}
                className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 px-4 py-2 text-xs font-medium transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                disabled={!!busyId}
                onClick={() => void action(confirmDelete, () => backend.delete(confirmDelete.id), true)}
                className="rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-medium px-4 py-2 text-xs shadow-xs hover:shadow-rose-600/20 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
              >
                {busyId ? 'Deleting…' : 'Delete permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
