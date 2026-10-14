import React, { useState, useRef, useEffect } from 'react';
import {
  MessageSquare,
  X,
  Send,
  Loader2,
  FileText,
  Minimize2,
  Maximize2,
  ExternalLink,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../services/apiClient';
import { ChatMessage } from '../../types/rag';
import { CitationViewer } from './CitationViewer';

export const ChatWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [widgetMessages, setWidgetMessages] = useState<ChatMessage[]>([
    {
      id: 'wm-init',
      role: 'assistant',
      content: 'Hi! Ask me anything about our indexed enterprise PDF documentation.',
      timestamp: 'Now',
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [widgetMessages, isOpen]);

  const handleSend = async () => {
    const text = query.trim();
    if (!text || isLoading) return;
    setQuery('');

    const userMsg: ChatMessage = {
      id: `wm-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setWidgetMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await apiClient.sendChat({ query: text });
      setWidgetMessages((prev) => [
        ...prev,
        {
          id: `wm-resp-${Date.now()}`,
          role: 'assistant',
          content: res.answer,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          citations: res.citations,
          context_status: res.context_status,
          latency_ms: res.latency_ms,
        },
      ]);
    } catch (err: any) {
      setWidgetMessages((prev) => [
        ...prev,
        {
          id: `wm-err-${Date.now()}`,
          role: 'assistant',
          content: 'Unable to connect to the PDF RAG backend.',
          error: err.message || 'Connection error',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-40">
      {/* Floating Trigger Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-xl hover:bg-blue-700 transition-all hover:scale-105 cursor-pointer ring-4 ring-blue-500/20"
          title="Open Embedded Chat Widget Preview"
          aria-label="Open chat widget"
        >
          <MessageSquare className="h-6 w-6" />
        </button>
      )}

      {/* Floating Popover Window */}
      {isOpen && (
        <div
          className={`flex flex-col bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden transition-all duration-200 ${
            isExpanded
              ? 'w-[520px] h-[640px]'
              : 'w-[360px] md:w-[400px] h-[520px]'
          }`}
        >
          {/* Header */}
          <div className="bg-blue-600 p-3.5 text-white flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-lg bg-white/20 flex items-center justify-center font-bold text-xs">
                RAG
              </div>
              <div>
                <h4 className="text-sm font-semibold leading-tight">Doc Assistant</h4>
                <p className="text-[10px] text-blue-100">PostgreSQL · FastEmbed</p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-1 rounded hover:bg-white/10 text-blue-100 hover:text-white transition-colors cursor-pointer"
                title={isExpanded ? 'Collapse' : 'Expand'}
              >
                {isExpanded ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded hover:bg-white/10 text-blue-100 hover:text-white transition-colors cursor-pointer"
                title="Close Widget"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Conversation history */}
          <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-50 dark:bg-slate-950 text-xs">
            {widgetMessages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-xl p-3 ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-800 rounded-tl-none shadow-2xs'
                  }`}
                >
                  <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                      <CitationViewer citations={msg.citations} />
                    </div>
                  )}
                  {msg.latency_ms && (
                    <div className="mt-1 text-[10px] text-slate-400 font-mono text-right">
                      {msg.latency_ms}ms
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-2.5 flex items-center gap-2 text-slate-500 text-xs">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                  <span>Retrieving answer...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-2.5 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Ask a question..."
              disabled={isLoading}
              className="flex-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={handleSend}
              disabled={!query.trim() || isLoading}
              className="p-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors cursor-pointer"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
