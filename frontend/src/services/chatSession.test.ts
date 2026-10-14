import {describe, expect, it} from 'vitest';
import {loadChatSession, newChatSession, saveChatSession} from './chatSession';

describe('Tab conversation storage', () => {
  it('restores credentials, scope and transcript after reload', () => {
    const session = newChatSession();
    session.selectedIds = ['document-id'];
    session.messages = [{id: 'turn', request: {question: 'Hello', top_k: 5, conversation_id: session.id}, pending: false, result: {answer: 'Hi!', sources: []}}];
    saveChatSession(session);
    expect(loadChatSession()).toEqual(session);
  });
  it('marks interrupted requests retryable and keeps a bounded transcript', () => {
    const session = newChatSession();
    session.messages = Array.from({length: 10}, (_, index) => ({id: String(index), request: {question: 'Hello', top_k: 5}, pending: true}));
    saveChatSession(session);
    const restored = loadChatSession();
    expect(restored.messages).toHaveLength(6);
    expect(restored.messages[0].id).toBe('4');
    expect(restored.messages.every(message => !message.pending && message.error?.includes('interrupted'))).toBe(true);
  });
  it('starts fresh when stored JSON is malformed', () => {
    sessionStorage.setItem('pdf-assistant-chat-v1', '{');
    expect(loadChatSession().messages).toEqual([]);
  });
});
