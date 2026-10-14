import React, { useState } from 'react';
import {
  ChatMessage,
  Citation,
} from '../../types/rag';
import {
  User,
  Bot,
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  AlertTriangle,
  Clock,
  Sparkles,
  Info,
} from 'lucide-react';
import { CitationViewer } from './CitationViewer';
import { ClarificationPicker } from './ClarificationPicker';

interface ChatMessageItemProps {
  message: ChatMessage;
  onRetry?: (query: string) => void;
  onClarificationSelect?: (option: string) => void;
  onFeedback?: (messageId: string, rating: 'positive' | 'negative', notes?: string) => void;
}

export const ChatMessageItem: React.FC<ChatMessageItemProps> = ({
  message,
  onRetry,
  onClarificationSelect,
  onFeedback,
}) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [feedbackNotes, setFeedbackNotes] = useState('');

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRating = (rating: 'positive' | 'negative') => {
    if (onFeedback) {
      onFeedback(message.id, rating, feedbackNotes);
    }
  };

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-2xl bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-xs">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          <div className="mt-1 text-[11px] text-blue-100/80 text-right font-mono">
            {message.timestamp}
          </div>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex gap-3 mb-6 max-w-3xl">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 font-semibold text-xs border border-blue-200 dark:border-blue-900 shadow-2xs">
        <Bot className="h-4 w-4" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="rounded-xl border border-slate-200/90 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900 transition-colors">
          {/* Insufficient context banner if applicable */}
          {message.context_status === 'insufficient' && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50/80 p-3 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200 flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block mb-0.5">
                  Insufficient Context in Vector Store
                </span>
                <span>
                  The hybrid retrieval engine (pgvector cosine + BM25) found no chunks
                  exceeding the relevance threshold for this query. The model cannot answer
                  without grounded evidence.
                </span>
              </div>
            </div>
          )}

          {/* Error / Timeout Banner */}
          {message.error && (
            <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50/80 p-3 text-xs text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Execution Error</span>
                    <span>{message.error}</span>
                  </div>
                </div>
                {onRetry && (
                  <button
                    onClick={() => onRetry(message.content)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-rose-600 text-white font-medium text-xs hover:bg-rose-700 transition-colors cursor-pointer shrink-0 ml-3"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Retry
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Main Answer text */}
          <div className="text-sm text-slate-800 dark:text-slate-100 leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>

          {/* Citations section */}
          {message.citations && message.citations.length > 0 && (
            <CitationViewer citations={message.citations} />
          )}

          {/* Clarification prompt if required */}
          {message.clarification_needed && message.clarification_options && (
            <ClarificationPicker
              prompt={message.content}
              options={message.clarification_options}
              onSelectOption={(opt) => onClarificationSelect && onClarificationSelect(opt)}
            />
          )}

          {/* Telemetry info & Action bar */}
          <div className="mt-3.5 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
            <div className="flex items-center gap-3 font-mono text-[11px]">
              {message.latency_ms !== undefined && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3 text-slate-400" />
                  {message.latency_ms}ms
                </span>
              )}
              {message.tokens_used && (
                <span className="hidden sm:inline">
                  {message.tokens_used.total_tokens} tokens ({message.tokens_used.prompt_tokens}p + {message.tokens_used.completion_tokens}c)
                </span>
              )}
              <span>{message.timestamp}</span>
            </div>

            <div className="flex items-center gap-1">
              {/* Copy answer */}
              <button
                onClick={handleCopy}
                className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
                title="Copy answer to clipboard"
                aria-label="Copy answer"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>

              {/* Feedback buttons */}
              <button
                onClick={() => handleRating('positive')}
                className={`p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer ${
                  message.feedback === 'positive'
                    ? 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/60'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
                title="Helpful response"
                aria-label="Thumbs up"
              >
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => handleRating('negative')}
                className={`p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer ${
                  message.feedback === 'negative'
                    ? 'text-rose-600 bg-rose-50 dark:bg-rose-950/60'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
                title="Unhelpful response"
                aria-label="Thumbs down"
              >
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
