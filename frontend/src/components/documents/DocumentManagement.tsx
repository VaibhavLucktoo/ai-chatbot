import React, { useState } from 'react';
import {
  FileText,
  Upload,
  Trash2,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Layers,
  Database,
  ExternalLink,
  MessageSquare,
  Filter,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { VectorSearchSandbox } from './VectorSearchSandbox';
import { DocumentRecord } from '../../types/rag';

export const DocumentManagement: React.FC = () => {
  const {
    documents,
    deleteDocument,
    userRole,
    setIsUploadModalOpen,
    setSelectedDocIds,
    setActiveTab,
  } = useApp();

  const [searchFilter, setSearchFilter] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const isAuthorized = userRole === 'doc_admin' || userRole === 'super_admin';

  const filteredDocs = documents.filter((d) =>
    d.filename.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const handleDelete = async (id: string) => {
    await deleteDocument(id);
    setDeleteConfirmId(null);
  };

  const handleQueryDocument = (docId: string) => {
    setSelectedDocIds([docId]);
    setActiveTab('chat');
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
            Document Corpus & Vector Index
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            PostgreSQL pgvector storage indexed with FastEmbed BAAI/bge-small-en-v1.5 (384 dimensions)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsUploadModalOpen(true)}
            disabled={!isAuthorized}
            className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium transition-colors shadow-xs ${
              isAuthorized
                ? 'bg-blue-600 text-white hover:bg-blue-700 cursor-pointer'
                : 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-600 cursor-not-allowed'
            }`}
            title={
              isAuthorized
                ? 'Ingest new PDF'
                : 'Upload restricted to doc_admin or super_admin'
            }
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Upload New PDF</span>
          </button>
        </div>
      </div>

      {/* Missing Endpoint Architecture Callout */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 text-xs text-slate-600 dark:text-slate-400 flex items-start justify-between gap-4 shadow-2xs">
        <div className="flex items-start gap-3">
          <Database className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-slate-900 dark:text-slate-200 block mb-0.5">
              Vector Ingestion Endpoint Alignment
            </span>
            <span>
              Ingestion uses <code>POST /v1/documents/upload</code> and search uses{' '}
              <code>POST /v1/documents/search</code>. Upstream FastAPI backend currently lacks{' '}
              <code>GET /v1/admin/documents</code> and <code>DELETE /v1/admin/documents/{'{id}'}</code>, which are mediated by this proxy dashboard.
            </span>
          </div>
        </div>
      </div>

      {/* Documents Table */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden shadow-2xs">
        {/* Table Filter Toolbar */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="relative min-w-[260px]">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter by filename..."
              className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="text-xs text-slate-400 font-mono">
            Total Indexed: {documents.length} PDF files
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 dark:bg-slate-950/60 text-slate-500 font-medium border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="py-3 px-4">Filename</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Size</th>
                <th className="py-3 px-4">Pages</th>
                <th className="py-3 px-4">Chunks</th>
                <th className="py-3 px-4">Embedding Config</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-normal">
              {filteredDocs.map((doc) => (
                <tr
                  key={doc.document_id}
                  className="hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors"
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-blue-600 shrink-0" />
                      <div>
                        <span className="font-semibold text-slate-900 dark:text-slate-100 block">
                          {doc.filename}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          ID: {doc.document_id} · By: {doc.uploaded_by}
                        </span>
                      </div>
                    </div>
                  </td>

                  <td className="py-3 px-4">
                    {doc.status === 'ready' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 font-medium text-[11px]">
                        <CheckCircle2 className="h-3 w-3" />
                        Ready
                      </span>
                    )}
                    {doc.status === 'processing' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400 font-medium text-[11px]">
                        <Clock className="h-3 w-3 animate-spin" />
                        Embedding...
                      </span>
                    )}
                    {doc.status === 'failed' && (
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-400 font-medium text-[11px]"
                        title={doc.error_message}
                      >
                        <AlertTriangle className="h-3 w-3" />
                        Failed
                      </span>
                    )}
                  </td>

                  <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                    {(doc.file_size_bytes / (1024 * 1024)).toFixed(1)} MB
                  </td>

                  <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                    {doc.page_count}
                  </td>

                  <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-400">
                    {doc.chunk_count}
                  </td>

                  <td className="py-3 px-4 font-mono text-[11px] text-slate-500">
                    bge-small-en ({doc.vector_dimension}d)
                  </td>

                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {/* Query this document directly in chat */}
                      <button
                        onClick={() => handleQueryDocument(doc.document_id)}
                        disabled={doc.status !== 'ready'}
                        className="p-1.5 rounded hover:bg-blue-50 text-blue-600 dark:hover:bg-blue-950/50 dark:text-blue-400 transition-colors cursor-pointer disabled:opacity-30"
                        title="Focus Chat on this document"
                      >
                        <MessageSquare className="h-4 w-4" />
                      </button>

                      {/* Delete (Role gated) */}
                      {deleteConfirmId === doc.document_id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDelete(doc.document_id)}
                            className="px-2 py-0.5 rounded bg-rose-600 text-white font-medium text-[11px] hover:bg-rose-700 transition-colors cursor-pointer"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="px-2 py-0.5 rounded bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300 text-[11px] cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => {
                            if (isAuthorized) {
                              setDeleteConfirmId(doc.document_id);
                            }
                          }}
                          disabled={!isAuthorized}
                          className={`p-1.5 rounded transition-colors ${
                            isAuthorized
                              ? 'text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 cursor-pointer'
                              : 'text-slate-300 dark:text-slate-700 cursor-not-allowed'
                          }`}
                          title={
                            isAuthorized
                              ? 'Purge vectors from database'
                              : 'Delete restricted to doc_admin or super_admin'
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Vector Search Probe Sandbox */}
      <VectorSearchSandbox />
    </div>
  );
};
