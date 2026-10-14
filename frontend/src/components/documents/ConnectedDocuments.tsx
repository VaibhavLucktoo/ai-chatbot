import React, {useRef, useState} from 'react';
import {Archive, ArrowLeft, ArrowRight, Check, Download, FileText, Loader2, MessageSquare, RefreshCw, Trash2, Upload, X} from 'lucide-react';
import {useChatbot} from '../../context/ChatbotContext';
import {backend, describeError, MAX_PDF_BYTES} from '../../services/backend';
import type {DocumentInfo, DocumentStatus} from '../../types/backend';

function StatusBadge({status, active}: {status: DocumentStatus; active?: boolean}) {
  const text = status === 'ready' && active === false ? 'Retired' : status === 'pending' ? 'Processing' : status === 'failed' ? 'Failed' : 'Ready';
  const style = text === 'Ready' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
    : text === 'Failed' ? 'bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300'
    : text === 'Processing' ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
    : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';
  return <span className={`inline-flex px-2 py-1 rounded-md text-[11px] font-medium ${style}`}>{text}</span>;
}

export function ConnectedDocuments() {
  const {page, offset, setOffset, documentsLoading, documentError, refreshDocuments, setSelectedIds, setTab,
    upload, jobs, pollError, health} = useChatbot();
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
    setFile(undefined); setUploadError(undefined); setUploadMessage(undefined);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith('.pdf')) {setUploadError('Choose a PDF file.'); return;}
    if (!candidate.size) {setUploadError('This file is empty. Choose a searchable PDF.'); return;}
    if (candidate.size > MAX_PDF_BYTES) {setUploadError('Maximum PDF size is 10 MiB.'); return;}
    setFile(candidate);
  };
  const submitUpload = async () => {
    if (!file || uploading) return;
    setUploading(true); setUploadError(undefined); setUploadMessage(undefined);
    try {
      const job = await upload(file);
      setUploadMessage(job.status === 'ready' ? 'This PDF is already indexed and ready.' : 'PDF received. Processing continues in the backend; its status updates below.');
      setFile(undefined); if (input.current) input.current.value = '';
    } catch (error) {setUploadError(describeError(error));}
    finally {setUploading(false);}
  };
  const action = async (doc: DocumentInfo, work: () => Promise<void>, remove = false) => {
    if (busyId) return;
    setBusyId(doc.id); setActionError(undefined);
    try {
      await work();
      if (remove) {setConfirmDelete(undefined); setSelectedIds(previous => previous.filter(id => id !== doc.id));}
      await refreshDocuments();
    } catch (error) {setActionError(describeError(error));}
    finally {setBusyId(undefined);}
  };
  const docs = page.items.filter(doc => doc.filename.toLowerCase().includes(filter.toLowerCase()));
  const recentJobs = Object.values(jobs);
  return <section className="max-w-6xl mx-auto px-5 md:px-8 py-6 md:py-8 space-y-6">
    <div className="flex items-center justify-between gap-3"><div><h1 className="text-xl font-semibold tracking-tight">Your documents</h1>
      <p className="text-sm text-slate-500 mt-1">Upload, inspect, and choose what your assistant can search.</p></div>
      <button onClick={() => void refreshDocuments()} disabled={documentsLoading} className="flex gap-2 items-center text-xs rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 disabled:opacity-40"><RefreshCw className={`h-3.5 w-3.5 ${documentsLoading ? 'animate-spin' : ''}`}/>Refresh</button>
    </div>
    <div className="grid md:grid-cols-[1.5fr_1fr] gap-4">
      <div onDragOver={event => {event.preventDefault(); if (!uploading) setDragging(true);}} onDragLeave={() => setDragging(false)}
        onDrop={event => {event.preventDefault(); setDragging(false); choose(event.dataTransfer.files[0]);}}
        className={`rounded-2xl border border-dashed p-6 bg-white dark:bg-slate-900 ${dragging ? 'border-blue-500 bg-blue-50 dark:bg-blue-950' : 'border-slate-300 dark:border-slate-700'}`}>
        <div className="flex items-start gap-4"><div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"><Upload className="h-5 w-5"/></div>
          <div className="min-w-0"><h2 className="font-medium text-sm">Add a PDF</h2><p className="text-xs text-slate-500 mt-1 leading-relaxed">Drop a searchable PDF here or choose one from your device.<br/>Up to 10 MiB and 100 pages. Scanned image-only PDFs require OCR first.</p></div></div>
        <input ref={input} type="file" accept=".pdf,application/pdf" aria-label="Choose PDF" className="sr-only" disabled={uploading}
          onChange={event => choose(event.target.files?.[0])}/>
        <div className="flex flex-wrap items-center gap-3 mt-5">
          <button onClick={() => {if (input.current) input.current.value = ''; input.current?.click();}} disabled={uploading} className="text-xs font-medium px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-40">Choose PDF</button>
          {file && <><p className="text-xs text-slate-500 truncate max-w-60" title={file.name}>{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MiB</p>
            <button onClick={() => void submitUpload()} disabled={uploading || health.api !== 'online'} className="inline-flex gap-2 items-center px-3 py-2 rounded-lg bg-blue-600 text-white text-xs disabled:opacity-40">{uploading && <Loader2 className="h-3.5 w-3.5 animate-spin"/>}{uploading ? 'Submitting…' : 'Upload PDF'}</button></>}
        </div>
        {uploadError && <p role="alert" className="mt-3 text-xs text-rose-600 dark:text-rose-400">{uploadError}</p>}
        {uploadMessage && <p role="status" className="mt-3 text-xs text-emerald-700 dark:text-emerald-300">{uploadMessage}</p>}
      </div>
      <div className="rounded-2xl p-6 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Corpus overview</p><p className="text-3xl font-semibold mt-3">{page.total}<span className="text-sm text-slate-500 font-normal ml-2">documents</span></p>
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">Only active, ready documents are searched. Retire an outdated PDF to exclude it while keeping its source and citations.</p>
      </div>
    </div>
    {!!recentJobs.length && <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <h2 className="text-xs font-semibold mb-3">Upload activity</h2><div className="space-y-2">{recentJobs.map(job => <div key={job.document_id} className="flex justify-between gap-3 text-xs items-center"><span className="truncate">{job.filename}</span><StatusBadge status={job.status}/></div>)}</div>
      {recentJobs.some(job => job.status === 'failed') && <p className="mt-3 text-xs text-rose-600 dark:text-rose-400">An upload failed. Check that the PDF has searchable text and meets the limits, then re-upload its original file to retry.</p>}
    </div>}
    {pollError && <p role="alert" className="text-sm text-amber-700 dark:text-amber-300">Status polling paused by a connection error: {pollError} It will retry automatically.</p>}
    {documentError && <div role="alert" className="rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 p-4 text-sm text-rose-700 dark:text-rose-300">{documentError} Existing rows may be stale. <button onClick={() => void refreshDocuments()} className="underline">Try again</button></div>}
    {actionError && <p role="alert" className="text-sm text-rose-600 dark:text-rose-400">{actionError}</p>}
    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
      <div className="flex flex-wrap gap-3 items-center justify-between border-b border-slate-200 dark:border-slate-800 p-4"><h2 className="font-medium text-sm">Document library</h2>
        <input aria-label="Filter documents on this page" value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter this page…" className="rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs outline-none focus:border-blue-500"/></div>
      {documentsLoading && !page.items.length ? <p role="status" className="p-8 flex items-center justify-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin"/>Loading documents…</p>
        : !docs.length ? <div className="p-12 text-center text-sm text-slate-500"><FileText className="h-8 w-8 mx-auto text-slate-300 mb-3"/>{filter ? 'No matches on this page.' : documentError ? 'Document library is unavailable.' : 'Your library is empty. Upload a PDF to get started.'}</div>
        : <div className="divide-y divide-slate-100 dark:divide-slate-800">{docs.map(doc => <div key={doc.id} className="p-4 md:p-5 flex flex-col md:flex-row md:items-center gap-4">
          <div className="flex items-start gap-3 flex-1 min-w-0"><div className="rounded-lg bg-slate-50 dark:bg-slate-800 p-2.5 text-slate-400"><FileText className="h-5 w-5"/></div>
            <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium text-sm break-all">{doc.filename}</h3><StatusBadge status={doc.status} active={doc.active}/></div>
              <p className="mt-1 text-xs text-slate-500">{doc.status === 'ready' ? `${doc.page_count} pages · ${doc.chunk_count} passages` : doc.status === 'pending' ? 'Processing and indexing…' : 'Processing failed; re-upload the original PDF to retry.'} · {new Date(doc.created_at).toLocaleDateString()}</p>
              {!doc.source_available && <p className="text-[11px] text-slate-400 mt-1">Original PDF unavailable. Citations remain accessible.</p>}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs shrink-0">
            <button disabled={doc.status !== 'ready' || !doc.active || !!busyId} onClick={() => {setSelectedIds([doc.id]); setTab('chat');}} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 disabled:opacity-30"><MessageSquare className="h-3.5 w-3.5"/>Chat</button>
            <button aria-label={`Download ${doc.filename}`} title={doc.source_available ? 'Download original PDF' : 'Re-upload the original file to enable download'} disabled={!doc.source_available || !!busyId} onClick={() => void action(doc, () => backend.download(doc))} className="p-2 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg disabled:opacity-25"><Download className="h-4 w-4"/></button>
            <button disabled={doc.status !== 'ready' || !!busyId} onClick={() => void action(doc, () => backend.activation(doc.id, !doc.active))} className="inline-flex items-center gap-1 p-2 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg disabled:opacity-25">{doc.active ? <Archive className="h-4 w-4"/> : <Check className="h-4 w-4"/>}{doc.active ? 'Retire' : 'Reactivate'}</button>
            <button aria-label={`Delete ${doc.filename}`} disabled={!!busyId} onClick={() => {setActionError(undefined); setConfirmDelete(doc);}} className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950 rounded-lg disabled:opacity-25"><Trash2 className="h-4 w-4"/></button>
            {busyId === doc.id && <Loader2 className="h-4 w-4 animate-spin text-slate-400"/>}
          </div>
        </div>)}</div>}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs text-slate-500">
        <span>{page.total ? `${offset + 1}–${Math.min(offset + page.limit, page.total)} of ${page.total}` : '0 documents'}</span>
        <div className="flex gap-2"><button aria-label="Previous document page" disabled={!offset || documentsLoading} onClick={() => setOffset(Math.max(0, offset - page.limit))} className="p-2 border border-slate-200 dark:border-slate-700 rounded-lg disabled:opacity-25"><ArrowLeft className="h-4 w-4"/></button>
          <button aria-label="Next document page" disabled={offset + page.limit >= page.total || documentsLoading} onClick={() => setOffset(offset + page.limit)} className="p-2 border border-slate-200 dark:border-slate-700 rounded-lg disabled:opacity-25"><ArrowRight className="h-4 w-4"/></button></div>
      </div>
    </div>
    {confirmDelete && <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4" onKeyDown={event => {
      if (event.key === 'Escape' && !busyId) setConfirmDelete(undefined);
      if (event.key === 'Tab') {
        const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not([disabled])');
        const first = buttons[0]; const last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus();}
        else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus();}
      }
    }}>
      <div role="dialog" aria-modal="true" aria-labelledby="delete-title" className="rounded-2xl p-6 w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-xl">
        <div className="flex justify-between gap-3 items-center"><h2 id="delete-title" className="font-semibold">Delete this document?</h2><button disabled={!!busyId} aria-label="Close delete confirmation" onClick={() => setConfirmDelete(undefined)}><X className="h-4 w-4"/></button></div>
        <p className="text-sm text-slate-500 mt-3 break-all">{confirmDelete.filename}</p><p className="text-sm text-slate-500 mt-2">This permanently removes the PDF and its indexed passages. Existing citations to it will no longer open.</p>
        {actionError && <p role="alert" className="text-xs text-rose-600 mt-3">{actionError}</p>}
        <div className="flex justify-end gap-2 mt-6"><button autoFocus disabled={!!busyId} onClick={() => setConfirmDelete(undefined)} className="rounded-lg border border-slate-200 dark:border-slate-700 px-4 py-2 text-sm">Cancel</button>
          <button disabled={!!busyId} onClick={() => void action(confirmDelete, () => backend.delete(confirmDelete.id), true)} className="rounded-lg bg-rose-600 text-white px-4 py-2 text-sm disabled:opacity-50">{busyId ? 'Deleting…' : 'Delete permanently'}</button></div>
      </div>
    </div>}
  </section>;
}
