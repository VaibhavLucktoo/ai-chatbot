import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import {
  ChatMessage,
  DocumentRecord,
  LlmConfig,
  OperationalAlert,
  SystemTelemetry,
  UserRole,
} from '../types/rag';
import { apiClient, BackendConnectionSettings } from '../services/apiClient';
import { DEFAULT_LLM_CONFIG, INITIAL_TELEMETRY } from '../services/mockBackend';

export type NavigationTab =
  | 'chat'
  | 'documents'
  | 'overview'
  | 'llm_config'
  | 'contracts'
  | 'widget_embed';

interface AppContextType {
  // Theme & Navigation
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  activeTab: NavigationTab;
  setActiveTab: (tab: NavigationTab) => void;

  // Role
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;

  // Backend Connection
  backendSettings: BackendConnectionSettings;
  updateBackendSettings: (settings: Partial<BackendConnectionSettings>) => void;
  isBackendHealthy: boolean;
  healthStatus: {
    liveness: boolean;
    database: boolean;
    embeddings: boolean;
    llm: boolean;
  };
  refreshHealth: () => Promise<void>;

  // Documents
  documents: DocumentRecord[];
  isDocumentsLoading: boolean;
  refreshDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<DocumentRecord>;
  deleteDocument: (id: string) => Promise<void>;
  selectedDocIds: string[];
  setSelectedDocIds: React.Dispatch<React.SetStateAction<string[]>>;

  // Telemetry & Alerts
  telemetry: SystemTelemetry;
  alerts: OperationalAlert[];
  refreshTelemetry: () => Promise<void>;

  // LLM Config
  llmConfig: LlmConfig;
  updateLlmConfig: (config: Partial<LlmConfig>) => Promise<void>;

  // Chat State
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  clearChatHistory: () => void;
  isGenerating: boolean;
  setIsGenerating: (val: boolean) => void;

  // Modals
  isUploadModalOpen: boolean;
  setIsUploadModalOpen: (val: boolean) => void;
  isSettingsModalOpen: boolean;
  setIsSettingsModalOpen: (val: boolean) => void;
  isEmbedModalOpen: boolean;
  setIsEmbedModalOpen: (val: boolean) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'msg-welcome',
    role: 'assistant',
    content:
      'Welcome to the Enterprise PDF RAG Assistant. I am connected to PostgreSQL/pgvector and FastEmbed hybrid retrieval via LangGraph.\n\nYou can ask questions about our indexed technical architecture, pgvector tuning guidelines, LangGraph SOPs, and compliance documentation. Citations with document names and page references are provided with answers.',
    timestamp: 'Just now',
    citations: [
      {
        document_id: 'doc-rag-01',
        document_name: 'Enterprise_Security_Architecture_v4.pdf',
        page_number: 14,
        snippet: 'PDF vector ingestion and index mutation endpoints are strictly restricted to users possessing the doc_admin or super_admin system roles.',
        score: 0.94,
      },
    ],
    context_status: 'sufficient',
  },
];

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Theme
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  // Nav & Role
  const [activeTab, setActiveTab] = useState<NavigationTab>('chat');
  const [userRole, setUserRole] = useState<UserRole>('super_admin');

  // Backend settings
  const [backendSettings, setBackendSettings] = useState<BackendConnectionSettings>(
    apiClient.getSettings()
  );

  const [healthStatus, setHealthStatus] = useState({
    liveness: true,
    database: true,
    embeddings: true,
    llm: true,
  });

  const refreshHealth = useCallback(async () => {
    try {
      const live = await apiClient.checkHealthLive();
      const ready = await apiClient.checkHealthReady();
      setHealthStatus({
        liveness: live.status === 'ok',
        database: ready.checks?.database ?? false,
        embeddings: ready.checks?.embeddings ?? false,
        llm: ready.checks?.llm ?? false,
      });
    } catch {
      setHealthStatus({
        liveness: false,
        database: false,
        embeddings: false,
        llm: false,
      });
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 20000);
    return () => clearInterval(interval);
  }, [refreshHealth]);

  const updateBackendSettings = (newSettings: Partial<BackendConnectionSettings>) => {
    apiClient.saveSettings(newSettings);
    setBackendSettings(apiClient.getSettings());
    refreshHealth();
  };

  // Documents
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isDocumentsLoading, setIsDocumentsLoading] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);

  const refreshDocuments = useCallback(async () => {
    setIsDocumentsLoading(true);
    try {
      const docs = await apiClient.listDocuments();
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to load documents', err);
    } finally {
      setIsDocumentsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshDocuments();
  }, [refreshDocuments]);

  const uploadDocument = async (file: File): Promise<DocumentRecord> => {
    const userEmail =
      userRole === 'super_admin'
        ? 'admin@enterprise.internal'
        : userRole === 'doc_admin'
        ? 'doc-manager@enterprise.internal'
        : 'viewer@enterprise.internal';
    const doc = await apiClient.uploadDocument(file, userEmail);
    await refreshDocuments();
    return doc;
  };

  const deleteDocument = async (id: string) => {
    await apiClient.deleteDocument(id);
    await refreshDocuments();
    setSelectedDocIds((prev) => prev.filter((dId) => dId !== id));
  };

  // Telemetry & Alerts
  const [telemetry, setTelemetry] = useState<SystemTelemetry>(INITIAL_TELEMETRY);
  const [alerts, setAlerts] = useState<OperationalAlert[]>([]);

  const refreshTelemetry = useCallback(async () => {
    try {
      const [t, a] = await Promise.all([apiClient.getTelemetry(), apiClient.getAlerts()]);
      setTelemetry(t);
      setAlerts(a);
    } catch (err) {
      console.error('Failed to refresh telemetry', err);
    }
  }, []);

  useEffect(() => {
    refreshTelemetry();
  }, [refreshTelemetry]);

  // LLM Config
  const [llmConfig, setLlmConfig] = useState<LlmConfig>(DEFAULT_LLM_CONFIG);

  useEffect(() => {
    apiClient.getLlmConfig().then(setLlmConfig);
  }, []);

  const updateLlmConfigState = async (updates: Partial<LlmConfig>) => {
    const updated = await apiClient.updateLlmConfig(updates);
    setLlmConfig(updated);
    refreshTelemetry();
  };

  // Chat
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [isGenerating, setIsGenerating] = useState(false);

  const addMessage = (msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  };

  const updateMessage = (id: string, updates: Partial<ChatMessage>) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m))
    );
  };

  const clearChatHistory = () => {
    setMessages([INITIAL_MESSAGES[0]]);
  };

  // Modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [isEmbedModalOpen, setIsEmbedModalOpen] = useState(false);

  return (
    <AppContext.Provider
      value={{
        theme,
        toggleTheme,
        activeTab,
        setActiveTab,
        userRole,
        setUserRole,
        backendSettings,
        updateBackendSettings,
        isBackendHealthy: healthStatus.liveness,
        healthStatus,
        refreshHealth,
        documents,
        isDocumentsLoading,
        refreshDocuments,
        uploadDocument,
        deleteDocument,
        selectedDocIds,
        setSelectedDocIds,
        telemetry,
        alerts,
        refreshTelemetry,
        llmConfig,
        updateLlmConfig: updateLlmConfigState,
        messages,
        addMessage,
        updateMessage,
        clearChatHistory,
        isGenerating,
        setIsGenerating,
        isUploadModalOpen,
        setIsUploadModalOpen,
        isSettingsModalOpen,
        setIsSettingsModalOpen,
        isEmbedModalOpen,
        setIsEmbedModalOpen,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
