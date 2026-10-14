export interface CallTotals {
  attempts: number; provider_requests: number; succeeded: number; failed: number; cancelled: number; rate_limited: number;
  usage_available_calls: number; total_reported_calls: number; priced_calls: number;
  input_tokens: number | null; output_tokens: number | null; total_tokens: number | null;
  estimated_cost_usd: number | null; usage_complete: boolean; cost_complete: boolean;
  average_ms: number | null; p95_ms: number | null; average_queue_ms: number | null; average_provider_ms: number | null;
}
export interface ModelCall {
  id: string; stage: string; model: string | null; provider: string | null; status: string;
  error_type: string | null; provider_requested: boolean; http_status: number | null;
  duration_ms: number; queue_ms: number | null; provider_ms: number | null;
  input_tokens: number | null; output_tokens: number | null; total_tokens: number | null; estimated_cost_usd: number | null;
}
export interface MetricRun {
  assistant_id?: string | null; assistant_name?: string | null; assistant_revision?: number | null;
  connection_id?: string | null; connection_revision?: number | null;
  configured_provider?: string | null; configured_model?: string | null;
  id: string; instance_id: string; started_at: string; endpoint: string;
  workflow_version: string; prompt_version: string | null; http_status: number | null;
  outcome: string; intent: string | null; error_type: string | null; duration_ms: number;
  graph_ms: number | null; retrieval_performed: boolean; result_count: number; source_count: number;
  stage_timings_ms: Record<string, number>; calls: ModelCall[];
}
export interface ModelAnalytics {
  available_assistants?: {id: string; name: string}[];
  available_providers?: string[];
  configuration_cache?: {scope: 'this_process'; ttl_seconds: number; max_entries: number; entries: number;
    hits: number; misses: number; invalidations: number} | null;
  assistants?: {assistant_id: string | null; assistant_name: string | null; assistant_revision: number | null;
    connection_id: string | null; connection_revision: number | null; configured_provider: string | null;
    configured_model: string | null; requests: number; successful: number; success_rate: number;
    average_ms: number | null; median_ms: number | null; p95_ms: number | null; provider_requests: number;
    failed_calls: number; input_tokens: number | null; output_tokens: number | null;
    estimated_cost_usd: number | null; cost_complete: boolean; usage_complete: boolean}[];
  window: {since: string; until: string; hours: number; model: string | null};
  requests: {total: number; successful: number; unsuccessful: number; cancelled: number; retrieval_requests: number;
    average_results: number | null; average_sources: number | null; success_rate: number | null;
    average_ms: number | null; median_ms: number | null; p95_ms: number | null; average_graph_ms: number | null};
  outcomes: Record<string, number>; intents: Record<string, number>; calls: CallTotals;
  models: (CallTotals & {model: string | null; provider: string | null})[];
  call_stages: (CallTotals & {stage: string})[]; workflow_stages_ms: Record<string, number>;
  timeline: {at: string; requests: number; unsuccessful: number; average_ms: number | null}[];
  requests_last_minute: number; available_models: string[];
  recent: {items: MetricRun[]; total: number; offset: number; limit: number};
  runtime: {scope: 'this_process'; instance_id: string; started_at: string; active_chats: number; active_model_calls: number;
    waiting_model_calls: number; pending_metric_writes: number; dropped_events: number; write_failures: number;
    persisted_events: number; last_write_at: string | null; last_error: string | null; writer_running: boolean} | null;
  pricing: {currency: 'USD'; configured_models: string[]; basis: string};
  quality: {status: 'not_evaluated'; accuracy: null; citation_support: null; completeness: null; reason: string};
}
