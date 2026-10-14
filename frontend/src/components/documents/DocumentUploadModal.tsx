import React, { useState, useRef } from 'react';
import {
  Upload,
  X,
  FileText,
  AlertCircle,
  CheckCircle2,
  Loader2,
  ShieldAlert,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';

export const DocumentUploadModal: React.FC = () => {
  const { isUploadModalOpen, setIsUploadModalOpen, uploadDocument, userRole } =
    useApp();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [stageMessage, setStageMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isUploadModalOpen) return null;

  const isAuthorized = userRole === 'doc_admin' || userRole === 'super_admin';

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setError('Only .pdf files are accepted by the FastEmbed ingestion pipeline.');
        return;
      }
      if (file.size > 25 * 1024 * 1024) {
        setError('Maximum file size is 25 MB.');
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setError(null);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setError('Only .pdf files are accepted by the FastEmbed ingestion pipeline.');
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setError(null);
    setUploadProgress(10);
    setStageMessage('Parsing PDF layout & extracting text blocks...');

    try {
      await new Promise((r) => setTimeout(r, 400));
      setUploadProgress(40);
      setStageMessage('Generating 384d FastEmbed ONNX vectors...');

      await new Promise((r) => setTimeout(r, 500));
      setUploadProgress(75);
      setStageMessage('Writing vector embeddings into PostgreSQL pgvector HNSW table...');

      await uploadDocument(selectedFile);

      setUploadProgress(100);
      setStageMessage('Ingestion complete! Document ready for hybrid search.');
      setSuccess(true);
      setTimeout(() => {
        setIsUploadModalOpen(false);
        setSelectedFile(null);
        setSuccess(false);
        setUploadProgress(0);
      }, 1500);
    } catch (err: any) {
      setError(err.message || 'Ingestion failed.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
              <Upload className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                Ingest PDF into pgvector
              </h3>
              <p className="text-xs text-slate-500">
                POST /v1/documents/upload · FastEmbed bge-small-en-v1.5
              </p>
            </div>
          </div>
          <button
            onClick={() => !isUploading && setIsUploadModalOpen(false)}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {!isAuthorized ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200 flex items-start gap-3">
              <ShieldAlert className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-semibold">
                  Authorization Error (HTTP 403 Forbidden)
                </strong>
                <span>
                  Your current role is set to <strong>{userRole}</strong>. PDF ingestion
                  and vector index writes require <code>doc_admin</code> or{' '}
                  <code>super_admin</code> privileges. Switch role in the header to proceed.
                </span>
              </div>
            </div>
          ) : (
            <>
              {/* Drag and Drop Zone */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => !isUploading && fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  selectedFile
                    ? 'border-blue-500 bg-blue-50/30 dark:border-blue-500 dark:bg-blue-950/20'
                    : 'border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-950/50'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <FileText className="mx-auto h-10 w-10 text-slate-400 mb-3" />
                {selectedFile ? (
                  <div>
                    <p className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-slate-500 mt-1 font-mono">
                      {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                    <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
                      Click to choose a different PDF
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="font-semibold text-slate-700 dark:text-slate-300 text-sm">
                      Drag and drop PDF here, or click to browse
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      Max file size: 25 MB · Text PDF or searchable scan
                    </p>
                  </div>
                )}
              </div>

              {/* Progress Bar & Stage Messages */}
              {isUploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs font-medium text-slate-700 dark:text-slate-300">
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                      {stageMessage}
                    </span>
                    <span className="font-mono">{uploadProgress}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-blue-600 transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Error Alert */}
              {error && (
                <div className="rounded-lg bg-rose-50 p-3 text-xs text-rose-800 dark:bg-rose-950/50 dark:text-rose-200 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Success */}
              {success && (
                <div className="rounded-lg bg-emerald-50 p-3 text-xs text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  <span>Document indexed successfully! Vector store updated.</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <button
            type="button"
            disabled={isUploading}
            onClick={() => setIsUploadModalOpen(false)}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!selectedFile || isUploading || !isAuthorized}
            onClick={handleUpload}
            className="px-4 py-2 rounded-lg text-xs font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer flex items-center gap-1.5"
          >
            {isUploading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>Start FastEmbed Ingestion</span>
          </button>
        </div>
      </div>
    </div>
  );
};
