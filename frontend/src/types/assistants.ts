export type ProviderName = 'groq' | 'gemini';
export interface ProviderPreset {id: ProviderName; name: string}
export interface ProviderConnection {
  id: string; name: string; provider: ProviderName; active: boolean; revision: number;
  created_at: string; updated_at: string;
}
export interface GenerationSettings {
  model: string; max_output_tokens: number; context_window_tokens: number;
  temperature: number; timeout_seconds: number;
}
export interface AssistantWrite extends GenerationSettings {
  name: string; description: string; connection_id: string; document_ids: string[]; active: boolean;
}
export interface Assistant extends AssistantWrite {
  id: string; provider: ProviderName; revision: number; created_at: string; updated_at: string;
}
