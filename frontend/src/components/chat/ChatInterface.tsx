import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  Sparkles,
  Trash2,
  Filter,
  Info,
  Loader2,
  FileText,
  AlertCircle,
  HelpCircle,
  RotateCcw,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { ChatMessageItem } from './ChatMessageItem';
import { apiClient } from '../../services/apiClient';

const SAMPLE_PROMPTS = [
  'What are the recommended HNSW parameters for pgvector?',
  'How does the stateless LangGraph traversal work?',
  'What user roles are authorized to ingest PDF documents?',
  'Tell me about security', // Triggers clarification flow!
  'What is the recipe for chocolate cake?', // Triggers insufficient context flow!
];

export const ChatInterface: React.FC = () => {
  const {
    messages,
    addMessage,
    updateMessage,
    clearChatHistory,
    isGenerating,
    setIsGenerating,
    documents,
    selectedDocIds,
    setSelectedDocIds,
    userRole,
    setIsUploadModalOpen,
  } = useApp();

  const [inputQuery, setInputQuery] = useState('');
  const [lastQuery, setLastQuery] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isGenerating]);

  const handleSendMessage = async (queryText?: string) => {
    const textToSend = (queryText || inputQuery).trim();
    if (!textToSend || isGenerating) return;

    setLastQuery(textToSend);
    setInputQuery('');

    // Append user message to visual conversation
    const userMsgId = `msg-user-${Date.now()}`;
    addMessage({
      id: userMsgId,
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });

    setIsGenerating(true);

    const assistantMsgId = `msg-asst-${Date.now()}`;

    try {
      // POST /v1/chat request contract
      const response = await apiClient.sendChat({
        query: textToSend,
        document_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
      });

      addMessage({
        id: assistantMsgId,
        role: 'assistant',
        content: response.answer,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        citations: response.citations,
        clarification_needed: response.clarification_needed,
        clarification_options: response.clarification_options,
        context_status: response.context_status,
        latency_ms: response.latency_ms,
        tokens_used: response.tokens_used,
      });
    } catch (err: any) {
      addMessage({
        id: assistantMsgId,
        role: 'assistant',
        content: 'An error occurred while contacting the FastAPI LangGraph pipeline.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        error: err.message || 'Network timeout or connection refused.',
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleRetry = (query: string) => {
    handleSendMessage(lastQuery || query);
  };

  const handleClarificationSelect = (chosenText: string) => {
    handleSendMessage(chosenText);
  };

  const handleFeedback = (
    messageId: string,
    rating: 'positive' | 'negative',
    notes?: string
  ) => {
    updateMessage(messageId, {
      feedback: rating,
      feedback_notes: notes,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const isRoleAuthorizedForUpload = userRole === 'doc_admin' || userRole === 'super_admin';

  return (
    <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-950 transition-colors">
      {/* Top Controls & Stateless Architecture Callout */}
      <div className="border-b border-slate-200/90 bg-white px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Stateless architecture banner */}
        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
          <Info className="h-4 w-4 text-blue-500 shrink-0" />
          <span>
            <strong className="font-semibold text-slate-700 dark:text-slate-300">
              Stateless Mode:
            </strong>{' '}
            Each prompt is dispatched independently to LangGraph without model memory buffer.
          </span>
        </div>

        {/* Document Selection Scope */}
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-slate-400" />
          <span className="text-slate-500 dark:text-slate-400">Scope:</span>
          <select
            value={selectedDocIds.length === 1 ? selectedDocIds[0] : 'all'}
            onChange={(e) => {
              const val = e.target.value;
              if (val === 'all') {
                setSelectedDocIds([]);
              } else {
                setSelectedDocIds([val]);
              }
            }}
            className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 focus:outline-none"
            aria-label="Filter by document"
          >
            <option value="all">All Documents ({documents.filter((d) => d.status === 'ready').length} Ready)</option>
            {documents
              .filter((d) => d.status === 'ready')
              .map((doc) => (
                <option key={doc.document_id} value={doc.document_id}>
                  {doc.filename}
                </option>
              ))}
          </select>

          <button
            onClick={clearChatHistory}
            className="flex items-center gap-1 px-2 py-1 rounded text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            title="Clear conversation history view"
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-2">
        <div className="max-w-4xl mx-auto">
          {messages.map((msg) => (
            <ChatMessageItem
              key={msg.id}
              message={msg}
              onRetry={handleRetry}
              onClarificationSelect={handleClarificationSelect}
              onFeedback={handleFeedback}
            />
          ))}

          {isGenerating && (
            <div className="flex gap-3 mb-6 max-w-3xl animate-pulse">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 font-semibold text-xs border border-blue-200 dark:border-blue-900">
                <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mb-2">
                  <span className="h-2 w-2 rounded-full bg-blue-500 animate-ping" />
                  <span>Traversing LangGraph: pgvector hybrid retrieval & adapter synthesis...</span>
                </div>
                <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-3/4 mb-2" />
                <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-1/2" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Query Suggestions & Input Container */}
      <div className="border-t border-slate-200/90 bg-white p-3 md:p-4 dark:border-slate-800 dark:bg-slate-900 transition-colors">
        <div className="max-w-4xl mx-auto space-y-2.5">
          {/* Sample Prompts Carousel / Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            <span className="text-slate-400 font-medium shrink-0 flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-amber-500" />
              Try:
            </span>
            {SAMPLE_PROMPTS.map((prompt, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(prompt)}
                disabled={isGenerating}
                className="whitespace-nowrap px-2.5 py-1 rounded-md border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors cursor-pointer text-xs"
              >
                {prompt}
              </button>
            ))}
          </div>

          {/* Input Box */}
          <div className="relative rounded-xl border border-slate-200 bg-slate-50/50 shadow-xs focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 dark:border-slate-800 dark:bg-slate-950 dark:focus-within:border-blue-400 transition-all">
            <textarea
              ref={inputRef}
              rows={2}
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedDocIds.length > 0
                  ? `Ask a question about selected document... (Press Enter to send, Shift+Enter for newline)`
                  : `Ask a question across all indexed PDF documents... (Press Enter to send)`
              }
              disabled={isGenerating}
              className="w-full resize-none bg-transparent px-3.5 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none dark:text-slate-100 dark:placeholder-slate-500"
            />

            <div className="flex items-center justify-between px-3 pb-2 text-xs text-slate-400">
              <div className="flex items-center gap-2">
                {selectedDocIds.length > 0 ? (
                  <span className="flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium">
                    <FileText className="h-3 w-3" />
                    Targeting 1 Document
                  </span>
                ) : (
                  <span>Searching all vector-indexed PDFs</span>
                )}
              </div>

              <button
                onClick={() => handleSendMessage()}
                disabled={!inputQuery.trim() || isGenerating}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white font-medium text-xs hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer shadow-xs"
              >
                <span>Send</span>
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
