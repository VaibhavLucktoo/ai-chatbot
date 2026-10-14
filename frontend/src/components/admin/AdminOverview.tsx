import React, { useState } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Database,
  Cpu,
  Layers,
  Zap,
  TrendingUp,
  FileText,
  DollarSign,
  RefreshCw,
  Server,
  AlertOctagon,
  ExternalLink,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';

export const AdminOverview: React.FC = () => {
  const {
    telemetry,
    alerts,
    documents,
    healthStatus,
    refreshTelemetry,
    refreshHealth,
    setActiveTab,
  } = useApp();

  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    await Promise.all([refreshTelemetry(), refreshHealth()]);
    setIsRefreshing(false);
  };

  const readyDocs = documents.filter((d) => d.status === 'ready').length;
  const processingDocs = documents.filter((d) => d.status === 'processing').length;
  const failedDocs = documents.filter((d) => d.status === 'failed').length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
            System Telemetry & Administration
          </h2>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
            <span>FastAPI LangGraph Pipeline</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">Config: {telemetry.config_version}</span>
            <span aria-hidden="true">·</span>
            <span>Active Model: {telemetry.active_model}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer shadow-2xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>Refresh Probes</span>
          </button>
        </div>
      </div>

      {/* Connectivity & Health Status Grid (Distinguishing Liveness, Readiness, Provider & Chat throughput) */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center justify-between">
          <span>Component Health Matrix</span>
          <span className="text-[11px] font-normal text-slate-400">
            Automated polling interval: 20s
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {/* Liveness */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-2xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-500">API Liveness</span>
              <span className="text-[10px] font-mono text-slate-400">/health/live</span>
            </div>
            <div className="flex items-center gap-2">
              {healthStatus.liveness ? (
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Healthy (200 OK)</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-rose-500 font-semibold text-sm">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Degraded</span>
                </div>
              )}
            </div>
            <div className="mt-2 text-[11px] text-slate-400">FastAPI HTTP worker runtime</div>
          </div>

          {/* Database / pgvector */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-2xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-500">PostgreSQL (pgvector)</span>
              <span className="text-[10px] font-mono text-slate-400">HNSW m=16</span>
            </div>
            <div className="flex items-center gap-2">
              {healthStatus.database ? (
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                  <Database className="h-4 w-4" />
                  <span>Connected (12ms)</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-rose-500 font-semibold text-sm">
                  <AlertOctagon className="h-4 w-4" />
                  <span>Connection Error</span>
                </div>
              )}
            </div>
            <div className="mt-2 text-[11px] text-slate-400">Dense vector similarity store</div>
          </div>

          {/* Embedding ONNX */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-2xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-500">FastEmbed ONNX</span>
              <span className="text-[10px] font-mono text-slate-400">bge-small-en-v1.5</span>
            </div>
            <div className="flex items-center gap-2">
              {healthStatus.embeddings ? (
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                  <Cpu className="h-4 w-4" />
                  <span>Active (384 dim)</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-amber-500 font-semibold text-sm">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Worker Busy</span>
                </div>
              )}
            </div>
            <div className="mt-2 text-[11px] text-slate-400">Local embedding generator</div>
          </div>

          {/* Custom LLM Adapter */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-2xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-500">LangChain LLM Adapter</span>
              <span className="text-[10px] font-mono text-slate-400">
                {telemetry.active_model}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {healthStatus.llm ? (
                <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-semibold text-sm">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Authenticated</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-rose-500 font-semibold text-sm">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Key Expired</span>
                </div>
              )}
            </div>
            <div className="mt-2 text-[11px] text-slate-400">
              Ref: ENV:OPENAI_API_KEY_SECRET
            </div>
          </div>
        </div>
      </div>

      {/* Latency & Ingestion Queues Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* End to End Latency Percentiles */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              End-to-End Latency
            </span>
            <Clock className="h-4 w-4 text-blue-500" />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">p50 Latency:</span>
              <span className="font-mono text-base font-bold text-slate-900 dark:text-slate-100">
                {telemetry.latency_p50_ms}ms
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">p95 Latency:</span>
              <span className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
                {telemetry.latency_p95_ms}ms
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">p99 Latency:</span>
              <span className="font-mono text-sm font-semibold text-amber-600 dark:text-amber-400">
                {telemetry.latency_p99_ms}ms
              </span>
            </div>
          </div>
        </div>

        {/* Queues & Concurrency */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              Queue Wait Times
            </span>
            <Activity className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">FastEmbed Queue:</span>
              <span className="font-mono text-base font-bold text-slate-900 dark:text-slate-100">
                {telemetry.queue_wait_embedding_ms}ms
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Generation Queue:</span>
              <span className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-300">
                {telemetry.queue_wait_generation_ms}ms
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Active Concurrency:</span>
              <span className="font-mono text-xs text-slate-600 dark:text-slate-400">
                {telemetry.active_concurrency} / {telemetry.max_concurrency} workers
              </span>
            </div>
          </div>
        </div>

        {/* Throughput & Reliability */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              24h Request Volume
            </span>
            <TrendingUp className="h-4 w-4 text-purple-500" />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Total Requests:</span>
              <span className="font-mono text-base font-bold text-slate-900 dark:text-slate-100">
                {telemetry.requests_24h.toLocaleString()}
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Success Rate:</span>
              <span className="font-mono text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                {telemetry.success_rate}%
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Error Rate:</span>
              <span className="font-mono text-xs text-rose-500 font-medium">
                {telemetry.error_rate}%
              </span>
            </div>
          </div>
        </div>

        {/* Tokens & Cost */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
            <span className="font-semibold text-slate-700 dark:text-slate-300">
              Token & Cost Tracking
            </span>
            <DollarSign className="h-4 w-4 text-amber-500" />
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">24h Tokens:</span>
              <span className="font-mono text-base font-bold text-slate-900 dark:text-slate-100">
                {(telemetry.total_tokens_24h / 1000).toFixed(1)}k
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Est. 24h Spend:</span>
              <span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">
                ${telemetry.estimated_cost_usd_24h.toFixed(2)} USD
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-xs text-slate-500">Pricing Tier:</span>
              <span className="font-mono text-xs text-slate-600 dark:text-slate-400">
                Standard (Tier 2)
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Document Ingestion Status Breakdown */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Document Ingestion & Index Pipeline
            </h3>
            <p className="text-xs text-slate-500">
              Corpus indexed with FastEmbed BAAI/bge-small-en-v1.5 into pgvector tables
            </p>
          </div>
          <button
            onClick={() => setActiveTab('documents')}
            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 font-medium cursor-pointer"
          >
            <span>View All Documents</span>
            <ExternalLink className="h-3 w-3" />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3.5 dark:border-emerald-950 dark:bg-emerald-950/20">
            <div className="flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300 mb-1">
              <span className="font-medium">Ready & Queryable</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            </div>
            <div className="text-2xl font-bold font-mono text-emerald-900 dark:text-emerald-100">
              {readyDocs}
            </div>
            <div className="text-[11px] text-emerald-700/80 dark:text-emerald-400/80 mt-1">
              Available for hybrid vector search
            </div>
          </div>

          <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3.5 dark:border-amber-950 dark:bg-amber-950/20">
            <div className="flex items-center justify-between text-xs text-amber-800 dark:text-amber-300 mb-1">
              <span className="font-medium">Processing / Ingesting</span>
              <Clock className="h-4 w-4 text-amber-600" />
            </div>
            <div className="text-2xl font-bold font-mono text-amber-900 dark:text-amber-100">
              {processingDocs}
            </div>
            <div className="text-[11px] text-amber-700/80 dark:text-amber-400/80 mt-1">
              Currently generating ONNX embeddings
            </div>
          </div>

          <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-3.5 dark:border-rose-950 dark:bg-rose-950/20">
            <div className="flex items-center justify-between text-xs text-rose-800 dark:text-rose-300 mb-1">
              <span className="font-medium">Failed Ingestion</span>
              <AlertTriangle className="h-4 w-4 text-rose-600" />
            </div>
            <div className="text-2xl font-bold font-mono text-rose-900 dark:text-rose-100">
              {failedDocs}
            </div>
            <div className="text-[11px] text-rose-700/80 dark:text-rose-400/80 mt-1">
              Requires OCR inspection or re-upload
            </div>
          </div>
        </div>
      </div>

      {/* Operational Alerts & Incident Log */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <span>Recent Operational Alerts & Audit Log</span>
          </h3>
          <span className="text-xs text-slate-400 font-mono">
            {alerts.length} events logged
          </span>
        </div>

        <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
          {alerts.map((alert) => (
            <div key={alert.id} className="py-3 flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 px-2 py-0.5 rounded font-mono text-[10px] uppercase font-semibold shrink-0 ${
                    alert.severity === 'critical'
                      ? 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400'
                      : alert.severity === 'warning'
                      ? 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400'
                      : 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400'
                  }`}
                >
                  {alert.component}
                </span>
                <div>
                  <h4 className="font-semibold text-slate-800 dark:text-slate-200">
                    {alert.title}
                  </h4>
                  <p className="text-slate-600 dark:text-slate-400 mt-0.5">
                    {alert.description}
                  </p>
                </div>
              </div>
              <span className="text-slate-400 text-[11px] shrink-0 font-mono">
                {alert.timestamp}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
