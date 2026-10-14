import type {ChatRequest, ChatResult, DocumentInfo, DocumentJob, DocumentPage, Passage, Source} from '../types/backend';
import type {ModelAnalytics} from '../types/analytics';
import type {Assistant, AssistantWrite, GenerationSettings, ProviderConnection, ProviderName, ProviderPreset} from '../types/assistants';

export const MAX_PDF_BYTES = 10 * 1024 * 1024;
export const INSUFFICIENT_CONTEXT = "I don't have enough information in the provided documents to answer this question.";

export class ApiError extends Error {
  constructor(message: string, public status?: number, public retryAfter?: number, public requestId?: string) {
    super(message); this.name = 'ApiError';
  }
}
function errorText(detail: unknown): string | undefined {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => `${(item.loc ?? []).slice(1).join('.')}: ${item.msg ?? 'Invalid value'}`).join('; ');
}
export async function request(path: string, options: RequestInit = {}, timeout = 20000): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, {...options, signal: options.signal ?? AbortSignal.timeout(timeout)});
  } catch (error) {
    const name = error instanceof Error ? error.name : '';
    if (name === 'AbortError' || name === 'TimeoutError') throw new ApiError('This request timed out. Your question and document selection are retained; try again shortly.');
    throw new ApiError('Cannot connect to the backend. Check that the API is running on port 8000.');
  }
  if (!response.ok) {
    const payload = await response.clone().json().catch(() => null);
    const raw = response.headers.get('Retry-After');
    const retry = raw ? (/^\d+$/.test(raw) ? Number(raw) : Math.max(0, Math.ceil((Date.parse(raw) - Date.now()) / 1000))) : undefined;
    const fallback: Record<number, string> = {
      403: 'The backend rejected this request. Use the local UI on port 3000.',
      404: 'This document or passage no longer exists.',
      413: 'The upload exceeds the 10 MiB PDF limit.',
      429: 'The backend or model provider is busy. Try again shortly.',
      502: 'The model could not produce a valid answer. Try again or refine the question.',
      503: 'A backend dependency is unavailable. Check status and try again.',
      504: 'Answer generation timed out. Your original request is available to retry.',
    };
    throw new ApiError(errorText(payload?.detail) ?? fallback[response.status] ?? `Request failed (HTTP ${response.status}).`,
      response.status, Number.isFinite(retry) ? retry : undefined, response.headers.get('X-Request-ID') ?? undefined);
  }
  return response;
}
export function describeError(error: unknown): string {
  const message = error instanceof Error ? error.message : 'An unexpected error occurred.';
  return error instanceof ApiError && error.retryAfter ? `${message} Retry after ${error.retryAfter} seconds.` : message;
}
async function json<T>(path: string, options?: RequestInit, timeout?: number): Promise<T> {
  const response = await request(path, options, timeout);
  return response.status === 204 ? undefined as T : response.json();
}
function post(payload: unknown): RequestInit {
  return {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)};
}
let adminToken: string | undefined;
async function adminRequest<T>(path: string, options: RequestInit = {}, timeout = 20000): Promise<T> {
  if (!adminToken) adminToken = (await json<{token: string}>('/v1/admin/session')).token;
  try {
    return await json<T>(path, {...options, headers: {...options.headers, 'X-Admin-Token': adminToken}}, timeout);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 403) throw error;
    // The token rotates on API restart; retain it only in process memory.
    adminToken = (await json<{token: string}>('/v1/admin/session')).token;
    return json<T>(path, {...options, headers: {...options.headers, 'X-Admin-Token': adminToken}}, timeout);
  }
}
export const backend = {
  deleteConnection: (id: string) => adminRequest<void>(`/v1/admin/connections/${encodeURIComponent(id)}`, {method: 'DELETE'}),
  deleteAssistant: (id: string) => adminRequest<void>(`/v1/admin/assistants/${encodeURIComponent(id)}`, {method: 'DELETE'}),
  assistants: () => json<Assistant[]>('/v1/assistants'),
  adminAssistants: () => adminRequest<Assistant[]>('/v1/admin/assistants'),
  providers: () => adminRequest<{items: ProviderPreset[]}>('/v1/admin/providers'),
  connections: () => adminRequest<ProviderConnection[]>('/v1/admin/connections'),
  saveConnection: (payload: {name: string; provider: ProviderName; api_key: string}) =>
    adminRequest<ProviderConnection>('/v1/admin/connections', post(payload)),
  updateConnection: (id: string, payload: {name: string; active: boolean; api_key?: string}) =>
    adminRequest<ProviderConnection>(`/v1/admin/connections/${encodeURIComponent(id)}`, {...post(payload), method: 'PUT'}),
  connectionModels: (id: string) => adminRequest<{items: string[]}>(`/v1/admin/connections/${encodeURIComponent(id)}/models`),
  testConnection: (connection_id: string, settings: GenerationSettings) =>
    adminRequest<{status: 'ok'; provider: ProviderName; model: string}>('/v1/admin/connections/test', post({connection_id, ...settings}), 195000),
  saveAssistant: (payload: AssistantWrite, id?: string) => adminRequest<Assistant>(
    id ? `/v1/admin/assistants/${encodeURIComponent(id)}` : '/v1/admin/assistants', {...post(payload), method: id ? 'PUT' : 'POST'}),
  async allDocuments(): Promise<DocumentInfo[]> {
    const items: DocumentInfo[] = []; let offset = 0;
    while (true) {
      const page = await this.documents(offset); items.push(...page.items); offset += page.items.length;
      if (!page.items.length || offset >= page.total) return items;
    }
  },
  analytics: (hours = 24, model?: string, offset = 0, filters: {assistant?: string; provider?: string} = {}) => {
    const query = new URLSearchParams({hours: String(hours), offset: String(offset), limit: '25'});
    if (model) query.set('model', model);
    if (filters.assistant === 'workspace') query.set('workspace_only', 'true');
    else if (filters.assistant) query.set('assistant_id', filters.assistant);
    if (filters.provider) query.set('provider', filters.provider);
    return adminRequest<ModelAnalytics>(`/v1/admin/metrics?${query}`);
  },
  health: () => json<{status: string; message: string}>('/v1/health', undefined, 10000),
  readiness: () => json<{status: 'ready' | 'not_ready'}>('/v1/ready', undefined, 10000),
  documents: (offset = 0, filters: {status?: string; active?: boolean} = {}) => {
    const query = new URLSearchParams({limit: '25', offset: String(offset)});
    if (filters.status) query.set('status', filters.status);
    if (filters.active !== undefined) query.set('active', String(filters.active));
    return json<DocumentPage>(`/v1/documents?${query}`);
  },
  async readyDocuments(): Promise<DocumentInfo[]> {
    const items: DocumentInfo[] = []; let offset = 0;
    while (true) {
      const page = await this.documents(offset, {status: 'ready', active: true});
      items.push(...page.items); offset += page.items.length;
      if (!page.items.length || offset >= page.total) return items;
    }
  },
  document: (id: string) => json<DocumentInfo>(`/v1/documents/${encodeURIComponent(id)}`),
  async submit(file: File): Promise<DocumentJob> {
    if (!file.name.toLowerCase().endsWith('.pdf')) throw new ApiError('Choose a PDF file.');
    if (!file.size) throw new ApiError('This file is empty. Choose a searchable PDF.');
    if (file.size > MAX_PDF_BYTES) throw new ApiError('Maximum PDF size is 10 MiB.');
    const data = new FormData();
    data.append('file', new File([file], file.name, {type: 'application/pdf'}));
    return json<DocumentJob>('/v1/documents/jobs', {method: 'POST', body: data}, 30000);
  },
  job: (id: string) => json<DocumentJob>(`/v1/documents/jobs/${encodeURIComponent(id)}`, undefined, 10000),
  chat: (payload: ChatRequest, conversationKey?: string) => {
    const options = post(payload);
    if (conversationKey) options.headers = {...options.headers, 'X-Conversation-Key': conversationKey};
    return json<ChatResult>('/v1/chat', options, 195000);
  },
  passage: (source: Source) => json<Passage>(`/v1/documents/${encodeURIComponent(source.document_id)}/chunks/${encodeURIComponent(source.chunk_id)}`),
  async activation(id: string, active: boolean): Promise<void> {
    await request(`/v1/documents/${encodeURIComponent(id)}/activation`, {...post({active}), method: 'PATCH'});
  },
  async delete(id: string): Promise<void> {
    await request(`/v1/documents/${encodeURIComponent(id)}`, {method: 'DELETE'});
  },
  async download(doc: DocumentInfo): Promise<void> {
    const response = await request(`/v1/documents/${encodeURIComponent(doc.id)}/source`);
    const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement('a');
    anchor.href = url; anchor.download = doc.filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
};
