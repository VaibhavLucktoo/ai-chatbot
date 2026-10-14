import type {ConversationMessage} from '../types/backend';

export interface ChatSession {id: string; key: string; messages: ConversationMessage[]; selectedIds: string[]; assistantId?: string}
const STORAGE_KEY = 'pdf-assistant-chat-v1';
const storageKey = (assistantId?: string) => assistantId ? `${STORAGE_KEY}:${assistantId}` : STORAGE_KEY;
export function forgetChatSession(assistantId: string): void {
  try {
    sessionStorage.removeItem(storageKey(assistantId));
    if (sessionStorage.getItem('pdf-assistant-selected') === assistantId) sessionStorage.removeItem('pdf-assistant-selected');
  } catch { /* In-memory state is cleared by the caller. */ }
}
export function newChatSession(assistantId?: string): ChatSession {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return {id: crypto.randomUUID(), key: [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join(''), messages: [], selectedIds: [], assistantId};
}
export function loadChatSession(assistantId?: string): ChatSession {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey(assistantId)) ?? 'null');
    if (saved && /^[0-9a-f-]{36}$/.test(saved.id) && /^[0-9a-f]{64}$/.test(saved.key)
        && Array.isArray(saved.messages) && Array.isArray(saved.selectedIds) && saved.assistantId === assistantId) {
      return {...saved, messages: saved.messages.slice(-6).map((message: ConversationMessage) =>
        message.pending ? {...message, pending: false, error: 'This request was interrupted. Retry the original question.'} : message)};
    }
  } catch { /* Private browsing may disable session storage. */ }
  return newChatSession(assistantId);
}
export function saveChatSession(session: ChatSession): void {
  try {
    const saved = {...session, messages: session.messages.slice(-6)};
    // Retain complete messages; drop oversized transcripts rather than partial claims.
    while (saved.messages.length && new TextEncoder().encode(JSON.stringify(saved)).length > 24000) saved.messages.shift();
    sessionStorage.setItem(storageKey(session.assistantId), JSON.stringify(saved));
  } catch { /* In-memory chat still works without browser storage. */ }
}
