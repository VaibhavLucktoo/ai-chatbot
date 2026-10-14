import {
  ChatApiRequest,
  ChatApiResponse,
  Citation,
  DocumentRecord,
  DocumentSearchRequest,
  DocumentSearchResponse,
  HealthLiveResponse,
  HealthReadyResponse,
  LlmConfig,
  SearchResultChunk,
  SystemTelemetry,
  OperationalAlert,
} from '../types/rag';

export const INITIAL_DOCUMENTS: DocumentRecord[] = [
  {
    document_id: 'doc-rag-01',
    filename: 'Enterprise_Security_Architecture_v4.pdf',
    status: 'ready',
    file_size_bytes: 4194304, // 4.0 MB
    page_count: 68,
    chunk_count: 312,
    uploaded_at: '2026-10-06T14:22:00Z',
    uploaded_by: 'sec-admin@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
  },
  {
    document_id: 'doc-rag-02',
    filename: 'PostgreSQL_pgvector_Optimization_Guide.pdf',
    status: 'ready',
    file_size_bytes: 2831155, // 2.7 MB
    page_count: 42,
    chunk_count: 198,
    uploaded_at: '2026-10-07T09:15:30Z',
    uploaded_by: 'dba-team@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
  },
  {
    document_id: 'doc-rag-03',
    filename: 'LangGraph_Workflow_Design_SOP.pdf',
    status: 'ready',
    file_size_bytes: 1945600, // 1.85 MB
    page_count: 34,
    chunk_count: 145,
    uploaded_at: '2026-10-08T11:40:00Z',
    uploaded_by: 'ai-platform@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
  },
  {
    document_id: 'doc-rag-04',
    filename: 'Q3_2026_Enterprise_Compliance_Report.pdf',
    status: 'ready',
    file_size_bytes: 5242880, // 5.0 MB
    page_count: 85,
    chunk_count: 420,
    uploaded_at: '2026-10-08T16:05:12Z',
    uploaded_by: 'audit-sec@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
  },
  {
    document_id: 'doc-rag-05',
    filename: 'FastEmbed_ONNX_Runtime_Benchmarks.pdf',
    status: 'processing',
    file_size_bytes: 3145728, // 3.0 MB
    page_count: 24,
    chunk_count: 88,
    uploaded_at: '2026-10-08T23:45:00Z',
    uploaded_by: 'mlops@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
  },
  {
    document_id: 'doc-rag-06',
    filename: 'Legacy_API_Deprecation_Notice_2025.pdf',
    status: 'failed',
    file_size_bytes: 943718, // 0.9 MB
    page_count: 6,
    chunk_count: 0,
    uploaded_at: '2026-10-05T18:20:00Z',
    uploaded_by: 'legacy-admin@enterprise.internal',
    embedding_model: 'BAAI/bge-small-en-v1.5',
    vector_dimension: 384,
    error_message: 'Corrupted font encoding on page 3: PDFSyntaxError during PyPDF table extraction.',
  },
];

export const DEFAULT_LLM_CONFIG: LlmConfig = {
  provider_type: 'hosted',
  provider_name: 'openai',
  model_id: 'gpt-4o-mini',
  approved_endpoint_url: 'https://api.openai.com/v1/chat/completions',
  credential_reference: 'ENV:OPENAI_API_KEY_SECRET',
  context_window_tokens: 128000,
  tokenizer_id: 'tiktoken:o200k_base',
  max_output_tokens: 2048,
  temperature: 0.2,
  top_p: 0.95,
  seed: 42,
  stop_sequences: ['<|im_end|>', '### Citation End'],
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  reasoning_effort: 'none',
  structured_output_mode: 'none',
  timeouts: {
    connection_timeout_ms: 3000,
    read_timeout_ms: 15000,
    write_timeout_ms: 5000,
    pool_timeout_ms: 4000,
    total_deadline_ms: 25000,
  },
  concurrency: {
    max_concurrency: 16,
    queue_limit: 64,
    connection_pool_limit: 32,
  },
  resiliency: {
    max_retries: 3,
    backoff_multiplier: 1.5,
    circuit_breaker_threshold: 5,
    circuit_breaker_reset_ms: 30000,
  },
};

export const INITIAL_TELEMETRY: SystemTelemetry = {
  api_connected: true,
  database_connected: true,
  embeddings_connected: true,
  llm_connected: true,
  config_version: 'v2.4.1-prod',
  active_model: 'gpt-4o-mini',
  provider_name: 'OpenAI (Hosted)',
  requests_24h: 3842,
  success_rate: 99.4,
  error_rate: 0.6,
  latency_p50_ms: 412,
  latency_p95_ms: 1240,
  latency_p99_ms: 2180,
  queue_wait_embedding_ms: 48,
  queue_wait_generation_ms: 135,
  total_tokens_24h: 1845200,
  estimated_cost_usd_24h: 3.42,
  active_concurrency: 3,
  max_concurrency: 16,
};

export const INITIAL_ALERTS: OperationalAlert[] = [
  {
    id: 'alt-01',
    severity: 'warning',
    title: 'FastEmbed Queue Depth Spike',
    description: 'Embedding worker queue temporarily reached 14 jobs during concurrent batch PDF ingestion.',
    timestamp: '18 minutes ago',
    component: 'FastEmbed',
  },
  {
    id: 'alt-02',
    severity: 'info',
    title: 'pgvector HNSW Index Compaction',
    description: 'Routine maintenance vacuum and HNSW index optimization completed successfully in 320ms.',
    timestamp: '2 hours ago',
    component: 'pgvector',
  },
  {
    id: 'alt-03',
    severity: 'info',
    title: 'LangGraph Custom Adapter Handshake',
    description: 'Active model gpt-4o-mini verified via server-side credential reference ENV:OPENAI_API_KEY_SECRET.',
    timestamp: '5 hours ago',
    component: 'LangGraph',
  },
];

// Document vector chunks database for hybrid search simulation
const KNOWLEDGE_BASE_CHUNKS: SearchResultChunk[] = [
  {
    chunk_id: 'chk-0101',
    document_id: 'doc-rag-01',
    document_name: 'Enterprise_Security_Architecture_v4.pdf',
    page_number: 14,
    text: 'Section 4.2 - RBAC and PDF Vector Ingestion Authorization: PDF ingestion and administrative index mutation endpoints must be restricted to users possessing the doc_admin or super_admin system roles. Unauthenticated or standard viewer accounts are restricted strictly to query evaluation via POST /v1/chat.',
    dense_score: 0.94,
    sparse_score: 0.88,
    hybrid_score: 0.92,
  },
  {
    chunk_id: 'chk-0102',
    document_id: 'doc-rag-01',
    document_name: 'Enterprise_Security_Architecture_v4.pdf',
    page_number: 22,
    text: 'Section 6.1 - Zero Trust Network Access & Secrets Management: All LLM provider API credentials must be mounted via server environment references (e.g., ENV:LLM_API_KEY). Client applications and frontends must never handle raw provider credentials.',
    dense_score: 0.91,
    sparse_score: 0.85,
    hybrid_score: 0.89,
  },
  {
    chunk_id: 'chk-0201',
    document_id: 'doc-rag-02',
    document_name: 'PostgreSQL_pgvector_Optimization_Guide.pdf',
    page_number: 8,
    text: 'Chapter 2: HNSW vs IVFFlat Configuration: For production workloads using FastEmbed bge-small-en-v1.5 (384 dimensions), HNSW with m=16 and ef_construction=64 provides 99.2% recall at p95 retrieval latencies under 12ms. Ensure pgvector extension version >= 0.5.1.',
    dense_score: 0.96,
    sparse_score: 0.91,
    hybrid_score: 0.94,
  },
  {
    chunk_id: 'chk-0202',
    document_id: 'doc-rag-02',
    document_name: 'PostgreSQL_pgvector_Optimization_Guide.pdf',
    page_number: 19,
    text: 'Chapter 4: Hybrid Retrieval Weighting: We utilize Reciprocal Rank Fusion (RRF) combining dense cosine similarity (weight 0.7) and PostgreSQL tsvector BM25 keyword matching (weight 0.3) to resolve domain-specific acronyms and entity lookups.',
    dense_score: 0.93,
    sparse_score: 0.89,
    hybrid_score: 0.91,
  },
  {
    chunk_id: 'chk-0301',
    document_id: 'doc-rag-03',
    document_name: 'LangGraph_Workflow_Design_SOP.pdf',
    page_number: 7,
    text: 'Workflow Stage 1 - Query Routing & Intent Analysis: The LangGraph state machine begins with an intent evaluation node. If a user query lacks specific context or can refer to multiple distinct architectural subsystems, the system generates a structured clarification response rather than hallucinating.',
    dense_score: 0.92,
    sparse_score: 0.87,
    hybrid_score: 0.90,
  },
  {
    chunk_id: 'chk-0302',
    document_id: 'doc-rag-03',
    document_name: 'LangGraph_Workflow_Design_SOP.pdf',
    page_number: 15,
    text: 'Workflow Stage 3 - Stateless Architecture: In the current backend implementation, POST /v1/chat is entirely stateless. The LangGraph state exists only for the duration of a single request traversal. Multi-turn conversational memory is deliberately not stored in the backend model memory.',
    dense_score: 0.95,
    sparse_score: 0.93,
    hybrid_score: 0.94,
  },
  {
    chunk_id: 'chk-0401',
    document_id: 'doc-rag-04',
    document_name: 'Q3_2026_Enterprise_Compliance_Report.pdf',
    page_number: 45,
    text: 'Compliance Item 12 - Data Sovereignty and Vector Retention: All PDF embeddings generated via FastEmbed are stored locally in the PostgreSQL pgvector instance without transmitting document chunks to external third-party embedding APIs.',
    dense_score: 0.89,
    sparse_score: 0.82,
    hybrid_score: 0.86,
  },
];

/**
 * High-fidelity Mock Backend Service
 * Faithfully matches FastAPI contracts and exposes inspection metrics.
 */
class MockBackendService {
  private documents: DocumentRecord[] = [...INITIAL_DOCUMENTS];
  private llmConfig: LlmConfig = { ...DEFAULT_LLM_CONFIG };
  private telemetry: SystemTelemetry = { ...INITIAL_TELEMETRY };
  private alerts: OperationalAlert[] = [...INITIAL_ALERTS];

  // Simulated latency
  private async delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // Health: GET /health/live
  async getHealthLive(): Promise<HealthLiveResponse> {
    await this.delay(120);
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime_seconds: 432000,
    };
  }

  // Health: GET /health/ready
  async getHealthReady(): Promise<HealthReadyResponse> {
    await this.delay(180);
    return {
      status: 'ready',
      checks: {
        database: this.telemetry.database_connected,
        embeddings: this.telemetry.embeddings_connected,
        llm: this.telemetry.llm_connected,
      },
      version: this.telemetry.config_version,
    };
  }

  // Contract: POST /v1/chat
  async chat(request: ChatApiRequest): Promise<ChatApiResponse> {
    const startTime = performance.now();
    await this.delay(500 + Math.random() * 400);

    const q = request.query.toLowerCase().trim();

    // Check for ambiguous trigger requiring clarification
    if (q === 'security' || q === 'what are the rules?' || q === 'tell me about architecture' || q === 'how does security work?') {
      const elapsed = Math.round(performance.now() - startTime);
      return {
        answer: 'Your query is broad and matches several distinct architectural components in our indexed documentation. To provide an accurate retrieval from the vector store, please clarify your specific focus:',
        citations: [],
        clarification_needed: true,
        clarification_prompt: 'Please select which aspect of security architecture you would like to explore:',
        clarification_options: [
          'Role-Based Access Control (RBAC) and PDF upload permissions',
          'Zero Trust Secrets Management for LLM provider credentials',
          'Data sovereignty and on-premise vector embeddings compliance',
        ],
        context_status: 'sufficient',
        latency_ms: elapsed,
        tokens_used: {
          prompt_tokens: 142,
          completion_tokens: 65,
          total_tokens: 207,
        },
      };
    }

    // Check for insufficient context
    if (
      q.includes('recipe') ||
      q.includes('chocolate cake') ||
      q.includes('weather') ||
      q.includes('football') ||
      q.includes('world cup') ||
      q.includes('crypto')
    ) {
      const elapsed = Math.round(performance.now() - startTime);
      return {
        answer: "I searched all indexed PDF vector documents using FastEmbed hybrid retrieval, but no relevant content was found matching your query. The indexed corpus covers Enterprise Security Architecture, PostgreSQL/pgvector optimization, LangGraph workflow SOPs, and Q3 Compliance reports.",
        citations: [],
        clarification_needed: false,
        context_status: 'insufficient',
        latency_ms: elapsed,
        tokens_used: {
          prompt_tokens: 88,
          completion_tokens: 44,
          total_tokens: 132,
        },
      };
    }

    // Perform hybrid search against internal chunks
    let matchingChunks = KNOWLEDGE_BASE_CHUNKS;
    if (request.document_ids && request.document_ids.length > 0) {
      matchingChunks = matchingChunks.filter((chk) =>
        request.document_ids!.includes(chk.document_id)
      );
    }

    // Filter relevant chunks based on query terms
    const relevant = matchingChunks.filter((c) => {
      const words = q.split(/\s+/).filter((w) => w.length > 3);
      if (words.length === 0) return true;
      return words.some(
        (w) =>
          c.text.toLowerCase().includes(w) ||
          c.document_name.toLowerCase().includes(w)
      );
    });

    const chosenChunks = relevant.length > 0 ? relevant.slice(0, 3) : matchingChunks.slice(0, 2);

    const citations: Citation[] = chosenChunks.map((c) => ({
      document_id: c.document_id,
      document_name: c.document_name,
      page_number: c.page_number,
      snippet: c.text,
      score: c.hybrid_score,
      chunk_id: c.chunk_id,
    }));

    // Generate response text synthesizing citations
    let answerText = '';
    if (q.includes('pgvector') || q.includes('database') || q.includes('hnsw') || q.includes('index')) {
      answerText = `Based on the indexed PostgreSQL optimization guidelines [Document: PostgreSQL_pgvector_Optimization_Guide.pdf, Page 8], the recommended configuration for FastEmbed 384-dimensional embeddings is an HNSW index with m=16 and ef_construction=64. This configuration delivers 99.2% recall with p95 retrieval latencies under 12ms.\n\nFurthermore, hybrid retrieval leverages Reciprocal Rank Fusion (RRF) with a 0.7 cosine similarity weight and 0.3 BM25 text match weight [Page 19].`;
    } else if (q.includes('stateless') || q.includes('memory') || q.includes('langgraph')) {
      answerText = `According to the LangGraph Workflow Design SOP [Document: LangGraph_Workflow_Design_SOP.pdf, Page 15], the POST /v1/chat endpoint operates entirely in a stateless mode. LangGraph manages request state exclusively within a single execution graph traversal. Prior conversational history is not retained in model memory between HTTP calls unless explicitly re-supplied in the client query payload.`;
    } else if (q.includes('upload') || q.includes('role') || q.includes('permission') || q.includes('rbac')) {
      answerText = `In accordance with Section 4.2 of the Enterprise Security Architecture [Document: Enterprise_Security_Architecture_v4.pdf, Page 14], PDF ingestion and vector index mutation endpoints (POST /v1/documents/upload) are strictly restricted to users with the 'doc_admin' or 'super_admin' roles. Standard viewers are limited exclusively to querying via POST /v1/chat.`;
    } else {
      answerText = `According to our indexed enterprise documents, the system employs FastEmbed (BAAI/bge-small-en-v1.5) with PostgreSQL/pgvector for hybrid retrieval and LangGraph execution [Enterprise_Security_Architecture_v4.pdf, Page 14; LangGraph_Workflow_Design_SOP.pdf, Page 7]. Provider API keys are managed securely server-side through environment references [Enterprise_Security_Architecture_v4.pdf, Page 22].`;
    }

    const elapsed = Math.round(performance.now() - startTime);

    // Update telemetry
    this.telemetry.requests_24h += 1;
    this.telemetry.total_tokens_24h += 385;
    this.telemetry.estimated_cost_usd_24h += 0.0006;

    return {
      answer: answerText,
      citations,
      clarification_needed: false,
      context_status: 'sufficient',
      latency_ms: elapsed,
      tokens_used: {
        prompt_tokens: 280,
        completion_tokens: 105,
        total_tokens: 385,
      },
    };
  }

  // Contract: POST /v1/documents/search
  async searchDocuments(request: DocumentSearchRequest): Promise<DocumentSearchResponse> {
    const startTime = performance.now();
    await this.delay(220);

    let list = [...KNOWLEDGE_BASE_CHUNKS];
    if (request.document_ids && request.document_ids.length > 0) {
      list = list.filter((item) => request.document_ids!.includes(item.document_id));
    }

    const q = request.query.toLowerCase();
    const ranked = list
      .map((item) => {
        let matchCount = 0;
        const terms = q.split(/\s+/).filter((t) => t.length > 2);
        for (const t of terms) {
          if (item.text.toLowerCase().includes(t)) matchCount++;
        }
        const sparseBonus = matchCount * 0.15;
        return {
          ...item,
          sparse_score: Math.min(0.99, Number((item.sparse_score + sparseBonus).toFixed(2))),
          hybrid_score: Math.min(0.99, Number((item.hybrid_score + sparseBonus * 0.5).toFixed(2))),
        };
      })
      .sort((a, b) => b.hybrid_score - a.hybrid_score);

    const topK = request.top_k || 5;
    const results = ranked.slice(0, topK);
    const elapsed = Math.round(performance.now() - startTime);

    return {
      query: request.query,
      results,
      total_found: results.length,
      retrieval_latency_ms: elapsed,
    };
  }

  // Contract: POST /v1/documents/upload
  async uploadDocument(file: File, userEmail: string = 'admin@enterprise.internal'): Promise<DocumentRecord> {
    await this.delay(800 + Math.random() * 500);

    const newDocId = `doc-rag-${Date.now().toString(36)}`;
    const pageCount = Math.max(1, Math.round(file.size / 45000));
    const chunkCount = pageCount * 4;

    const record: DocumentRecord = {
      document_id: newDocId,
      filename: file.name,
      status: 'ready',
      file_size_bytes: file.size,
      page_count: pageCount,
      chunk_count: chunkCount,
      uploaded_at: new Date().toISOString(),
      uploaded_by: userEmail,
      embedding_model: 'BAAI/bge-small-en-v1.5',
      vector_dimension: 384,
    };

    this.documents.unshift(record);

    // Also add a sample chunk into the simulated searchable store
    KNOWLEDGE_BASE_CHUNKS.unshift({
      chunk_id: `chk-${Date.now().toString(36)}`,
      document_id: newDocId,
      document_name: file.name,
      page_number: 1,
      text: `Ingested content from ${file.name}. Parsed with FastEmbed ONNX runtime into 384-dimensional dense vectors with pgvector cosine distance index. Document is indexed and immediately queryable.`,
      dense_score: 0.95,
      sparse_score: 0.9,
      hybrid_score: 0.93,
    });

    return record;
  }

  // Documents Management (Simulated frontend proxy for missing GET /v1/admin/documents)
  async listDocuments(): Promise<DocumentRecord[]> {
    await this.delay(150);
    return [...this.documents];
  }

  async deleteDocument(documentId: string): Promise<boolean> {
    await this.delay(200);
    this.documents = this.documents.filter((d) => d.document_id !== documentId);
    return true;
  }

  // Admin Telemetry (Simulated for missing GET /v1/admin/metrics)
  async getTelemetry(): Promise<SystemTelemetry> {
    await this.delay(100);
    return { ...this.telemetry };
  }

  async getAlerts(): Promise<OperationalAlert[]> {
    await this.delay(100);
    return [...this.alerts];
  }

  // Admin LLM Config (Simulated for missing GET & PUT /v1/admin/config/llm)
  async getLlmConfig(): Promise<LlmConfig> {
    await this.delay(100);
    return { ...this.llmConfig };
  }

  async updateLlmConfig(config: Partial<LlmConfig>): Promise<LlmConfig> {
    await this.delay(250);
    this.llmConfig = {
      ...this.llmConfig,
      ...config,
      timeouts: { ...this.llmConfig.timeouts, ...(config.timeouts || {}) },
      concurrency: { ...this.llmConfig.concurrency, ...(config.concurrency || {}) },
      resiliency: { ...this.llmConfig.resiliency, ...(config.resiliency || {}) },
    };
    this.telemetry.active_model = this.llmConfig.model_id;
    this.telemetry.provider_name = `${this.llmConfig.provider_name} (${this.llmConfig.provider_type})`;
    return { ...this.llmConfig };
  }

  // LLM Test Connection Probe (Simulated for missing POST /v1/admin/test-llm)
  async testLlmConnection(config: LlmConfig): Promise<{ success: boolean; latency_ms: number; message: string }> {
    const start = performance.now();
    await this.delay(450);
    const latency = Math.round(performance.now() - start);

    if (!config.approved_endpoint_url || !config.approved_endpoint_url.startsWith('http')) {
      return {
        success: false,
        latency_ms: latency,
        message: 'Endpoint URL is invalid or malformed.',
      };
    }

    return {
      success: true,
      latency_ms: latency,
      message: `Successfully connected to ${config.model_id} via ${config.approved_endpoint_url}. Credential ref ${config.credential_reference} validated.`,
    };
  }

  // Sample Generation Probe
  async testSampleGeneration(prompt: string, config: LlmConfig): Promise<{
    success: boolean;
    output: string;
    tokens_generated: number;
    latency_ms: number;
    tokens_per_second: number;
  }> {
    const start = performance.now();
    await this.delay(680);
    const latency = Math.round(performance.now() - start);
    const output = `Probe generation completed successfully. Model '${config.model_id}' operating via Custom LangChain Adapter. Temperature: ${config.temperature}, Max Tokens: ${config.max_output_tokens}, Seed: ${config.seed ?? 'unset'}.`;

    return {
      success: true,
      output,
      tokens_generated: 48,
      latency_ms: latency,
      tokens_per_second: Number(((48 / (latency / 1000))).toFixed(1)),
    };
  }
}

export const mockBackend = new MockBackendService();
