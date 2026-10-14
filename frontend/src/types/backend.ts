export type DocumentStatus = 'pending' | 'ready' | 'failed';
export interface DocumentInfo {
  id: string; filename: string; page_count: number; status: DocumentStatus;
  created_at: string; active: boolean; chunk_count: number; source_available: boolean;
}
export interface DocumentPage {items: DocumentInfo[]; total: number; limit: number; offset: number}
export interface DocumentJob {document_id: string; filename: string; status: DocumentStatus}
export interface ChatRequest {question: string; top_k: number; document_ids?: string[]; conversation_id?: string; assistant_id?: string}
export interface Source {document_id: string; chunk_id: string; filename: string; page_number: number}
export interface Answer {answer: string; sources: Source[]}
export interface Clarification {
  status: 'clarification_required'; question: string; original_question: string; top_k: number;
  documents: {document_id: string; filename: string}[];
}
export type ChatResult = Answer | Clarification;
export const isClarification = (result: ChatResult): result is Clarification =>
  'status' in result && result.status === 'clarification_required';
export interface Passage {
  id: string; document_id: string; filename: string; page_number: number; chunk_index: number; content: string;
}
export interface ConversationMessage {
  id: string; request: ChatRequest; result?: ChatResult; error?: string; pending: boolean;
}
export interface BackendHealth {
  api: 'checking' | 'online' | 'offline';
  readiness: 'checking' | 'ready' | 'not_ready' | 'unknown';
  error?: string; checkedAt?: string;
}
