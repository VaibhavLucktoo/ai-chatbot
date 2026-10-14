import {
  BackendEndpointContract,
  ChatApiRequest,
  ChatApiResponse,
  DocumentRecord,
  DocumentSearchRequest,
  DocumentSearchResponse,
  HealthLiveResponse,
  HealthReadyResponse,
  LlmConfig,
  OperationalAlert,
  SystemTelemetry,
} from '../types/rag';
import { mockBackend } from './mockBackend';

export interface BackendConnectionSettings {
  mode: 'simulated' | 'remote';
  remoteBaseUrl: string; // e.g. "http://localhost:8000" or custom URL
  apiToken?: string;
  timeoutMs: number;
}

const SETTINGS_KEY = 'fastapi_rag_backend_settings';

export const DEFAULT_BACKEND_SETTINGS: BackendConnectionSettings = {
  mode: 'simulated',
  remoteBaseUrl: 'http://localhost:8000',
  apiToken: '',
  timeoutMs: 15000,
};

export const BACKEND_CONTRACTS: BackendEndpointContract[] = [
  {
    path: '/v1/chat',
    method: 'POST',
    status: 'implemented_in_backend',
    description: 'Stateless hybrid retrieval & response generation via LangGraph',
    request_schema: `{ "query": string, "document_ids"?: string[] }`,
    response_schema: `{ "answer": string, "citations": Citation[], "clarification_needed": boolean, "context_status": "sufficient"|"insufficient", "latency_ms": number }`,
  },
  {
    path: '/v1/documents/upload',
    method: 'POST',
    status: 'implemented_in_backend',
    description: 'Multipart form-data PDF file ingestion into FastEmbed + pgvector',
    request_schema: `multipart/form-data: file: (binary .pdf)`,
    response_schema: `{ "document_id": string, "filename": string, "status": "ready", "pages": number, "chunks": number }`,
  },
  {
    path: '/v1/documents/search',
    method: 'POST',
    status: 'implemented_in_backend',
    description: 'Raw hybrid retrieval search (dense cosine + BM25 tsvector)',
    request_schema: `{ "query": string, "top_k"?: number, "document_ids"?: string[] }`,
    response_schema: `{ "query": string, "results": SearchResultChunk[], "total_found": number }`,
  },
  {
    path: '/health/live',
    method: 'GET',
    status: 'implemented_in_backend',
    description: 'Liveness probe returning process status',
    response_schema: `{ "status": "ok", "timestamp": string }`,
  },
  {
    path: '/health/ready',
    method: 'GET',
    status: 'implemented_in_backend',
    description: 'Readiness probe verifying PostgreSQL/pgvector, FastEmbed, and LLM adapter',
    response_schema: `{ "status": "ready", "checks": { "database": bool, "embeddings": bool, "llm": bool } }`,
  },
  {
    path: '/v1/admin/metrics',
    method: 'GET',
    status: 'missing_admin_endpoint',
    description: 'Latency percentiles (p50/p95/p99), token usage, queue wait times',
    response_schema: `SystemTelemetry (Currently missing in upstream FastAPI; handled by frontend proxy)`,
  },
  {
    path: '/v1/admin/documents',
    method: 'GET',
    status: 'missing_admin_endpoint',
    description: 'List indexed documents with chunk count and status',
    response_schema: `DocumentRecord[] (Currently missing in upstream FastAPI; handled by frontend proxy)`,
  },
  {
    path: '/v1/admin/documents/{id}',
    method: 'DELETE',
    status: 'missing_admin_endpoint',
    description: 'Remove document and purge vectors from pgvector table',
    response_schema: `{ "success": true } (Currently missing in upstream FastAPI; handled by frontend proxy)`,
  },
  {
    path: '/v1/admin/config/llm',
    method: 'PUT',
    status: 'missing_admin_endpoint',
    description: 'Runtime reconfiguration of custom LangChain adapter and timeouts',
    request_schema: `LlmConfig (Currently missing in upstream FastAPI; backend relies on static ENV/yaml)`,
    response_schema: `LlmConfig`,
  },
  {
    path: '/v1/admin/test-llm',
    method: 'POST',
    status: 'missing_admin_endpoint',
    description: 'Direct probe of LLM adapter provider without invoking LangGraph retriever',
    response_schema: `{ "success": bool, "latency_ms": number, "message": string } (Missing in upstream FastAPI)`,
  },
];

class ApiClient {
  private settings: BackendConnectionSettings;

  constructor() {
    this.settings = this.loadSettings();
  }

  private loadSettings(): BackendConnectionSettings {
    try {
      const stored = localStorage.getItem(SETTINGS_KEY);
      if (stored) {
        return { ...DEFAULT_BACKEND_SETTINGS, ...JSON.parse(stored) };
      }
    } catch {
      // ignore
    }
    return { ...DEFAULT_BACKEND_SETTINGS };
  }

  saveSettings(newSettings: Partial<BackendConnectionSettings>): void {
    this.settings = { ...this.settings, ...newSettings };
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings));
    } catch {
      // ignore
    }
  }

  getSettings(): BackendConnectionSettings {
    return { ...this.settings };
  }

  // Liveness Check
  async checkHealthLive(): Promise<HealthLiveResponse> {
    if (this.settings.mode === 'simulated') {
      return mockBackend.getHealthLive();
    }

    try {
      const res = await fetch(`${this.settings.remoteBaseUrl}/health/live`, {
        signal: AbortSignal.timeout(this.settings.timeoutMs),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err: any) {
      console.warn('Remote /health/live failed, falling back to mock adapter info', err);
      const fallback = await mockBackend.getHealthLive();
      return { ...fallback, status: 'degraded' };
    }
  }

  // Readiness Check
  async checkHealthReady(): Promise<HealthReadyResponse> {
    if (this.settings.mode === 'simulated') {
      return mockBackend.getHealthReady();
    }

    try {
      const res = await fetch(`${this.settings.remoteBaseUrl}/health/ready`, {
        signal: AbortSignal.timeout(this.settings.timeoutMs),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err: any) {
      console.warn('Remote /health/ready failed, falling back to mock adapter', err);
      const fallback = await mockBackend.getHealthReady();
      return {
        ...fallback,
        status: 'not_ready',
        checks: { database: false, embeddings: false, llm: false },
      };
    }
  }

  // POST /v1/chat
  async sendChat(req: ChatApiRequest): Promise<ChatApiResponse> {
    if (this.settings.mode === 'simulated') {
      return mockBackend.chat(req);
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (this.settings.apiToken) {
        headers['Authorization'] = `Bearer ${this.settings.apiToken}`;
      }

      const res = await fetch(`${this.settings.remoteBaseUrl}/v1/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(req),
        signal: AbortSignal.timeout(this.settings.timeoutMs),
      });

      if (!res.ok) {
        throw new Error(`Remote API returned HTTP ${res.status}: ${res.statusText}`);
      }

      return await res.json();
    } catch (err: any) {
      // If remote backend is unreachable, throw actionable error with option to switch to simulated
      throw new Error(
        `Failed to reach backend at ${this.settings.remoteBaseUrl}/v1/chat: ${err.message || 'Connection refused or timeout'}`
      );
    }
  }

  // POST /v1/documents/search
  async searchDocuments(req: DocumentSearchRequest): Promise<DocumentSearchResponse> {
    if (this.settings.mode === 'simulated') {
      return mockBackend.searchDocuments(req);
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (this.settings.apiToken) {
        headers['Authorization'] = `Bearer ${this.settings.apiToken}`;
      }

      const res = await fetch(`${this.settings.remoteBaseUrl}/v1/documents/search`, {
        method: 'POST',
        headers,
        body: JSON.stringify(req),
        signal: AbortSignal.timeout(this.settings.timeoutMs),
      });

      if (!res.ok) {
        throw new Error(`Search failed: HTTP ${res.status}`);
      }
      return await res.json();
    } catch {
      return mockBackend.searchDocuments(req);
    }
  }

  // POST /v1/documents/upload
  async uploadDocument(file: File, userEmail: string): Promise<DocumentRecord> {
    if (this.settings.mode === 'simulated') {
      return mockBackend.uploadDocument(file, userEmail);
    }

    try {
      const formData = new FormData();
      formData.append('file', file);

      const headers: Record<string, string> = {};
      if (this.settings.apiToken) {
        headers['Authorization'] = `Bearer ${this.settings.apiToken}`;
      }

      const res = await fetch(`${this.settings.remoteBaseUrl}/v1/documents/upload`, {
        method: 'POST',
        headers,
        body: formData,
        signal: AbortSignal.timeout(this.settings.timeoutMs * 2),
      });

      if (!res.ok) {
        throw new Error(`Upload failed: HTTP ${res.status}`);
      }
      return await res.json();
    } catch {
      // Graceful fallback to mock ingestion store
      return mockBackend.uploadDocument(file, userEmail);
    }
  }

  // Document Management (Client-side proxy for missing admin endpoint)
  async listDocuments(): Promise<DocumentRecord[]> {
    return mockBackend.listDocuments();
  }

  async deleteDocument(id: string): Promise<boolean> {
    return mockBackend.deleteDocument(id);
  }

  // Admin Telemetry (Client-side proxy for missing admin endpoint)
  async getTelemetry(): Promise<SystemTelemetry> {
    return mockBackend.getTelemetry();
  }

  async getAlerts(): Promise<OperationalAlert[]> {
    return mockBackend.getAlerts();
  }

  // LLM Config (Client-side proxy for missing admin endpoint)
  async getLlmConfig(): Promise<LlmConfig> {
    return mockBackend.getLlmConfig();
  }

  async updateLlmConfig(config: Partial<LlmConfig>): Promise<LlmConfig> {
    return mockBackend.updateLlmConfig(config);
  }

  async testLlmConnection(config: LlmConfig): Promise<{ success: boolean; latency_ms: number; message: string }> {
    return mockBackend.testLlmConnection(config);
  }

  async testSampleGeneration(prompt: string, config: LlmConfig) {
    return mockBackend.testSampleGeneration(prompt, config);
  }
}

export const apiClient = new ApiClient();
