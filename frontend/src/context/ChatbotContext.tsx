import React, {createContext, useCallback, useContext, useEffect, useRef, useState} from 'react';
import {ApiError, backend, describeError} from '../services/backend';
import {forgetChatSession, loadChatSession, newChatSession, saveChatSession} from '../services/chatSession';
import type {BackendHealth, ChatRequest, ConversationMessage, DocumentInfo, DocumentJob, DocumentPage} from '../types/backend';
import type {Assistant} from '../types/assistants';

type Tab = 'chat' | 'documents' | 'status' | 'analytics' | 'assistants' | 'models' | 'widget';
interface ChatbotState {
  tab: Tab; setTab: (tab: Tab) => void;
  theme: 'light' | 'dark'; toggleTheme: () => void;
  health: BackendHealth; refreshHealth: () => Promise<void>;
  page: DocumentPage; offset: number; setOffset: (offset: number) => void;
  readyDocuments: DocumentInfo[]; documentsLoading: boolean; documentError?: string;
  refreshDocuments: () => Promise<void>;
  selectedIds: string[]; setSelectedIds: React.Dispatch<React.SetStateAction<string[]>>;
  jobs: Record<string, DocumentJob>; pollError?: string;
  upload: (file: File) => Promise<DocumentJob>;
  messages: ConversationMessage[]; generating: boolean;
  send: (request: ChatRequest, retryId?: string) => Promise<void>; clearChat: () => void;
  assistants: Assistant[]; assistantId?: string; setAssistant: (id?: string) => void;
  assistantError?: string; assistantsLoading: boolean; refreshAssistants: () => Promise<void>;
  chatDocuments: DocumentInfo[];
  discardAssistant: (id: string) => void;
}
const Context = createContext<ChatbotState | undefined>(undefined);

export function ChatbotProvider({children}: {children: React.ReactNode}) {
  const [assistantId, setAssistantId] = useState<string | undefined>(() => {
    try {return sessionStorage.getItem('pdf-assistant-selected') || undefined;} catch {return undefined;}
  });
  const [session, setSession] = useState(() => loadChatSession(assistantId));
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [assistantError, setAssistantError] = useState<string>();
  const [assistantsLoading, setAssistantsLoading] = useState(true);
  const assistantGeneration = useRef(0);
  const refreshAssistants = useCallback(async () => {
    const generation = ++assistantGeneration.current; setAssistantsLoading(true);
    try {
      const available = await backend.assistants();
      if (generation === assistantGeneration.current) {setAssistants(available); setAssistantError(undefined);}
    } catch (error) {
      if (generation === assistantGeneration.current) setAssistantError(describeError(error));
    } finally {if (generation === assistantGeneration.current) setAssistantsLoading(false);}
  }, []);
  useEffect(() => {void refreshAssistants();}, [refreshAssistants]);
  const [tab, setTab] = useState<Tab>('chat');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {return localStorage.getItem('theme') === 'dark' ? 'dark' : 'light';} catch {return 'light';}
  });
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try {localStorage.setItem('theme', theme);} catch { /* Storage can be unavailable. */ }
  }, [theme]);
  const [health, setHealth] = useState<BackendHealth>({api: 'checking', readiness: 'checking'});
  const healthBusy = useRef(false);
  const refreshHealth = useCallback(async () => {
    if (healthBusy.current) return;
    healthBusy.current = true;
    const [live, ready] = await Promise.allSettled([backend.health(), backend.readiness()]);
    const api = live.status === 'fulfilled' && live.value.status === 'ok' ? 'online' : 'offline';
    const readiness = ready.status === 'fulfilled' ? ready.value.status
      : ready.reason instanceof ApiError && ready.reason.status === 503 ? 'not_ready' : 'unknown';
    setHealth({api, readiness, checkedAt: new Date().toISOString(),
      error: api === 'offline' ? 'Cannot reach the API on port 8000. Start the backend and check again.'
        : readiness === 'not_ready' ? 'The API is running, but the database/schema or embedding model is not ready.'
        : readiness === 'unknown' ? 'The readiness check failed. Check the backend connection.' : undefined});
    healthBusy.current = false;
  }, []);
  useEffect(() => {
    void refreshHealth(); const timer = window.setInterval(() => void refreshHealth(), 20000);
    return () => clearInterval(timer);
  }, [refreshHealth]);

  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<DocumentPage>({items: [], total: 0, limit: 25, offset: 0});
  const [readyDocuments, setReadyDocuments] = useState<DocumentInfo[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentError, setDocumentError] = useState<string>();
  const [selectedIds, setSelectedIds] = useState<string[]>(session.selectedIds);
  const documentGeneration = useRef(0);
  const refreshDocuments = useCallback(async () => {
    const generation = ++documentGeneration.current;
    setDocumentsLoading(true);
    try {
      const [catalog, ready] = await Promise.all([backend.documents(offset), backend.readyDocuments()]);
      if (generation !== documentGeneration.current) return;
      if (!catalog.items.length && catalog.total && offset >= catalog.total) {
        setOffset(Math.max(0, Math.floor((catalog.total - 1) / catalog.limit) * catalog.limit));
        return;
      }
      setPage(catalog); setReadyDocuments(ready); setDocumentError(undefined);
    } catch (error) {
      if (generation === documentGeneration.current) setDocumentError(describeError(error));
    } finally {
      if (generation === documentGeneration.current) setDocumentsLoading(false);
    }
  }, [offset]);
  useEffect(() => {void refreshDocuments();}, [refreshDocuments]);
  // Reconnect catalog after the API recovers without repeatedly querying an outage.
  const lastApi = useRef(health.api);
  useEffect(() => {
    if (health.api === 'online' && lastApi.current === 'offline') {void refreshDocuments(); void refreshAssistants();}
    lastApi.current = health.api;
  }, [health.api, refreshDocuments, refreshAssistants]);

  const [jobs, setJobs] = useState<Record<string, DocumentJob>>({});
  const [pollError, setPollError] = useState<string>();
  const pendingIds = [...new Set([
    ...Object.values(jobs).filter(job => job.status === 'pending').map(job => job.document_id),
    ...page.items.filter(doc => doc.status === 'pending').map(doc => doc.id),
  ])].sort().join(',');
  useEffect(() => {
    if (!pendingIds) {setPollError(undefined); return;}
    let disposed = false; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const results = await Promise.allSettled(pendingIds.split(',').map(id => backend.job(id)));
      if (disposed) return;
      let finished = false; let problem: string | undefined;
      const updates: Record<string, DocumentJob> = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          updates[result.value.document_id] = result.value;
          if (result.value.status !== 'pending') finished = true;
        } else if (result.reason instanceof ApiError && result.reason.status === 404) {
          const id = pendingIds.split(',')[index];
          setJobs(previous => {const next = {...previous}; delete next[id]; return next;});
          finished = true;
        } else problem = describeError(result.reason);
      });
      if (Object.keys(updates).length) setJobs(previous => ({...previous, ...updates}));
      setPollError(problem);
      if (finished) await refreshDocuments();
      if (!disposed) timer = setTimeout(() => void poll(), problem ? 10000 : 3000);
    };
    timer = setTimeout(() => void poll(), 1500);
    return () => {disposed = true; clearTimeout(timer);};
  }, [pendingIds, refreshDocuments]);
  const upload = async (file: File) => {
    const job = await backend.submit(file);
    setJobs(previous => ({...previous, [job.document_id]: job}));
    await refreshDocuments();
    return job;
  };

  const [messages, setMessages] = useState<ConversationMessage[]>(session.messages);
  useEffect(() => {saveChatSession({...session, messages, selectedIds});}, [session, messages, selectedIds]);
  const [generating, setGenerating] = useState(false);
  const generationBusy = useRef(false);
  const send = async (request: ChatRequest, retryId?: string) => {
    if (generationBusy.current) return;
    if (retryId && request.assistant_id !== assistantId) return;
    if (assistantId && (!assistants.some(assistant => assistant.id === assistantId) || assistantError || assistantsLoading)) return;
    generationBusy.current = true; setGenerating(true);
    const id = retryId ?? crypto.randomUUID();
    const snapshot = {...request, conversation_id: session.id, assistant_id: assistantId,
      document_ids: request.document_ids ? [...request.document_ids] : undefined};
    const entry = {id, request: snapshot, pending: true};
    setMessages(previous => retryId ? previous.map(message => message.id === id ? entry : message) : [...previous, entry]);
    try {
      const result = await backend.chat(snapshot, session.key);
      setMessages(previous => previous.map(message => message.id === id ? {...message, result, pending: false} : message));
    } catch (error) {
      setMessages(previous => previous.map(message => message.id === id ? {...message, error: describeError(error), pending: false} : message));
    } finally {generationBusy.current = false; setGenerating(false);}
  };
  const setAssistant = (id?: string) => {
    if (generationBusy.current || id === assistantId) return;
    saveChatSession({...session, messages, selectedIds});
    const next = loadChatSession(id);
    setAssistantId(id); setSession(next); setMessages(next.messages); setSelectedIds(next.selectedIds);
    try {if (id) sessionStorage.setItem('pdf-assistant-selected', id); else sessionStorage.removeItem('pdf-assistant-selected');} catch { /* Optional persistence. */ }
  };
  const selectedAssistant = assistants.find(assistant => assistant.id === assistantId);
  const discardAssistant = (id: string) => {
    forgetChatSession(id);
    setAssistants(previous => previous.filter(item => item.id !== id));
    if (id === assistantId) {
      const next = loadChatSession();
      setAssistantId(undefined); setSession(next); setMessages(next.messages); setSelectedIds(next.selectedIds);
    }
  };
  const chatDocuments = assistantId ? readyDocuments.filter(doc => selectedAssistant?.document_ids.includes(doc.id)) : readyDocuments;
  return <Context.Provider value={{tab, setTab, theme, toggleTheme: () => setTheme(theme === 'light' ? 'dark' : 'light'),
    health, refreshHealth, page, offset, setOffset, readyDocuments, documentsLoading, documentError, refreshDocuments,
    selectedIds, setSelectedIds, jobs, pollError, upload, messages, generating, send,
    assistants, assistantId, setAssistant, assistantError, assistantsLoading, refreshAssistants, chatDocuments, discardAssistant,
    clearChat: () => {if (!generationBusy.current) {setMessages([]); setSession(newChatSession(assistantId));}}}}>{children}</Context.Provider>;
}
export function useChatbot() {
  const context = useContext(Context);
  if (!context) throw new Error('ChatbotProvider is required.');
  return context;
}
