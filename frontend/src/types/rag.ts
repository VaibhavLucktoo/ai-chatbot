/**
 * Type definitions matching FastAPI PDF RAG Backend Contracts
 * and frontend administrative extensions.
 */

export type UserRole = 'user' | 'doc_admin' | 'super_admin';

export interface Citation {
  document_id: string;
  document_name: string;
  page_number: number;
  snippet: string;
  score: number; // 0.0 - 1.0 (hybrid dense+sparse relevance)
  chunk_id?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  citations?: Citation[];
  clarification_needed?: boolean;
  clarification_options?: string[];
  context_status?: 'sufficient' | 'insufficient';
  latency_ms?: number;
  tokens_used?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  error?: string;
  feedback?: 'positive' | 'negative' | null;
  feedback_notes?: string;
}

// Actual backend request schema for POST /v1/chat
export interface ChatApiRequest {
  query: string;
  document_ids?: string[];
  temperature_override?: number;
}

// Actual backend response schema for POST /v1/chat
export interface ChatApiResponse {
  answer: string;
  citations: Citation[];
  clarification_needed: boolean;
  clarification_prompt?: string;
  clarification_options?: string[];
  context_status: 'sufficient' | 'insufficient';
  latency_ms: number;
  tokens_used?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

// Actual backend schema for POST /v1/documents/search
export interface DocumentSearchRequest {
  query: string;
  top_k?: number;
  document_ids?: string[];
}

export interface SearchResultChunk {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number;
  text: string;
  dense_score: number; // pgvector cosine
  sparse_score: number; // BM25
  hybrid_score: number;
}

export interface DocumentSearchResponse {
  query: string;
  results: SearchResultChunk[];
  total_found: number;
  retrieval_latency_ms: number;
}

// Document status in vector database
export type DocumentStatus = 'ready' | 'processing' | 'pending' | 'failed';

export interface DocumentRecord {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  file_size_bytes: number;
  page_count: number;
  chunk_count: number;
  uploaded_at: string;
  uploaded_by: string;
  embedding_model: string;
  vector_dimension: number;
  error_message?: string;
}

// Backend Health schemas
export interface HealthLiveResponse {
  status: 'ok' | 'degraded';
  timestamp: string;
  uptime_seconds?: number;
}

export interface HealthReadyResponse {
  status: 'ready' | 'not_ready';
  checks: {
    database: boolean; // PostgreSQL pgvector
    embeddings: boolean; // FastEmbed ONNX
    llm: boolean; // Custom LangChain Adapter
  };
  version?: string;
}

// Missing Admin Endpoints & Telemetry
export interface SystemTelemetry {
  api_connected: boolean;
  database_connected: boolean;
  embeddings_connected: boolean;
  llm_connected: boolean;
  config_version: string;
  active_model: string;
  provider_name: string;
  requests_24h: number;
  success_rate: number; // percentage
  error_rate: number; // percentage
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  queue_wait_embedding_ms: number;
  queue_wait_generation_ms: number;
  total_tokens_24h: number;
  estimated_cost_usd_24h: number;
  active_concurrency: number;
  max_concurrency: number;
}

export interface OperationalAlert {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  timestamp: string;
  component: 'pgvector' | 'FastEmbed' | 'LangGraph' | 'LLM Adapter' | 'Ingestion';
}

export interface LlmConfig {
  provider_type: 'local' | 'hosted';
  provider_name: string; // 'ollama' | 'vllm' | 'openai' | 'anthropic' | 'groq' | 'vertex'
  model_id: string;
  approved_endpoint_url: string;
  credential_reference: string; // server-side env var name, e.g. "ENV:LLM_API_KEY"
  context_window_tokens: number;
  tokenizer_id: string;
  max_output_tokens: number;
  temperature: number;
  top_p: number;
  seed?: number;
  stop_sequences: string[];
  frequency_penalty: number;
  presence_penalty: number;
  reasoning_effort: 'none' | 'low' | 'medium' | 'high';
  structured_output_mode: 'none' | 'json_object' | 'json_schema';
  timeouts: {
    connection_timeout_ms: number;
    read_timeout_ms: number;
    write_timeout_ms: number;
    pool_timeout_ms: number;
    total_deadline_ms: number;
  };
  concurrency: {
    max_concurrency: number;
    queue_limit: number;
    connection_pool_limit: number;
  };
  resiliency: {
    max_retries: number;
    backoff_multiplier: number;
    circuit_breaker_threshold: number;
    circuit_breaker_reset_ms: number;
  };
}

export interface BackendEndpointContract {
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  status: 'implemented_in_backend' | 'missing_admin_endpoint';
  description: string;
  request_schema?: string;
  response_schema?: string;
}
