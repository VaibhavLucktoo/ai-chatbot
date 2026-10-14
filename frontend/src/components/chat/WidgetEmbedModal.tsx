import React, { useState } from 'react';
import { X, Copy, Check, Code, Globe, Layers } from 'lucide-react';
import { useApp } from '../../context/AppContext';

export const WidgetEmbedModal: React.FC = () => {
  const { isEmbedModalOpen, setIsEmbedModalOpen, backendSettings } = useApp();
  const [activeTab, setActiveTab] = useState<'script' | 'react' | 'iframe'>('script');
  const [copied, setCopied] = useState(false);

  if (!isEmbedModalOpen) return null;

  const endpointUrl =
    backendSettings.mode === 'remote'
      ? backendSettings.remoteBaseUrl
      : window.location.origin;

  const scriptCode = `<!-- Embed FastAPI PDF RAG Chatbot Widget -->
<script
  src="${window.location.origin}/rag-widget.js"
  data-endpoint="${endpointUrl}/v1/chat"
  data-title="Enterprise Documentation AI"
  data-primary-color="#2563eb"
  async>
</script>`;

  const reactCode = `import { FastApiRagWidget } from '@enterprise/rag-react-widget';

export function DocumentationLayout() {
  return (
    <div className="layout">
      {/* Your application content */}
      <FastApiRagWidget
        apiEndpoint="${endpointUrl}/v1/chat"
        title="PDF RAG Assistant"
        theme="auto"
        placeholder="Ask about architecture, guidelines, compliance..."
      />
    </div>
  );
}`;

  const iframeCode = `<iframe
  src="${window.location.origin}/?embed=true"
  width="420"
  height="640"
  style="border: none; border-radius: 16px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);"
  title="FastAPI PDF RAG Chat"
></iframe>`;

  const getActiveCode = () => {
    if (activeTab === 'script') return scriptCode;
    if (activeTab === 'react') return reactCode;
    return iframeCode;
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(getActiveCode());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
              <Code className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                Embed Chat Widget in Your Project
              </h3>
              <p className="text-xs text-slate-500">
                Lightweight, responsive chat interface connecting to your FastAPI RAG backend
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsEmbedModalOpen(false)}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Format Tabs */}
          <div className="flex gap-2 border-b border-slate-100 dark:border-slate-800 pb-2">
            <button
              onClick={() => setActiveTab('script')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${
                activeTab === 'script'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
              }`}
            >
              HTML Script Tag
            </button>
            <button
              onClick={() => setActiveTab('react')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${
                activeTab === 'react'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
              }`}
            >
              React Component
            </button>
            <button
              onClick={() => setActiveTab('iframe')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors ${
                activeTab === 'iframe'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
              }`}
            >
              Embedded iframe
            </button>
          </div>

          {/* Code block */}
          <div className="relative rounded-xl border border-slate-200 bg-slate-900 p-4 text-xs font-mono text-slate-100 dark:border-slate-800">
            <div className="absolute top-3 right-3">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 rounded-md bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors cursor-pointer"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    <span>Copy Snippet</span>
                  </>
                )}
              </button>
            </div>
            <pre className="overflow-x-auto pr-24 py-1 leading-relaxed">
              {getActiveCode()}
            </pre>
          </div>

          <div className="rounded-lg bg-blue-50/70 p-3 text-xs text-blue-900 dark:bg-blue-950/40 dark:text-blue-200">
            <span className="font-semibold block mb-1">Architecture Details:</span>
            <span>
              The embedded widget targets the stateless <code>POST /v1/chat</code> endpoint.
              Citations are rendered inline and can be styled to match host application design systems.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-slate-200 px-6 py-3.5 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <button
            onClick={() => setIsEmbedModalOpen(false)}
            className="px-4 py-2 rounded-lg bg-slate-200 text-slate-800 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 text-xs font-medium cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
