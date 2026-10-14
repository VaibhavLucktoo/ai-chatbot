import React, { useState } from 'react';
import {
  Globe,
  Code,
  Copy,
  Check,
  ExternalLink,
  Sliders,
  Sparkles,
  MessageSquare,
  Shield,
  Layers,
  CheckCircle2,
  Send,
  X,
  FileText,
  Loader2,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../services/apiClient';
import { ChatMessage } from '../../types/rag';
import { CitationViewer } from '../chat/CitationViewer';

export const WebsiteEmbedDemo: React.FC = () => {
  const { backendSettings } = useApp();

  // Widget Customization Settings
  const [widgetTitle, setWidgetTitle] = useState('Enterprise PDF Assistant');
  const [primaryColor, setPrimaryColor] = useState('#2563eb');
  const [position, setPosition] = useState<'right' | 'left'>('right');
  const [greeting, setGreeting] = useState('Hello! Ask me anything about our technical documentation.');
  const [copiedCodeKey, setCopiedCodeKey] = useState<string | null>(null);

  // Active Embed Format Tab
  const [activeTab, setActiveTab] = useState<'script' | 'react' | 'iframe' | 'direct'>('script');

  // Interactive Live Preview State inside Mock External Website
  const [isSimWidgetOpen, setIsSimWidgetOpen] = useState(false);
  const [simQuery, setSimQuery] = useState('');
  const [simMessages, setSimMessages] = useState<ChatMessage[]>([
    {
      id: 'sim-welcome',
      role: 'assistant',
      content: greeting,
      timestamp: 'Now',
    },
  ]);
  const [isSimLoading, setIsSimLoading] = useState(false);

  const currentOrigin = window.location.origin;
  const targetEndpoint =
    backendSettings.mode === 'remote'
      ? `${backendSettings.remoteBaseUrl}/v1/chat`
      : `${currentOrigin}/v1/chat`;

  const scriptTagCode = `<!-- 1. Paste this single script tag right before </body> on ANY website -->
<script
  src="${currentOrigin}/rag-widget.js"
  data-endpoint="${targetEndpoint}"
  data-title="${widgetTitle}"
  data-color="${primaryColor}"
  data-position="${position}"
  async>
</script>`;

  const reactComponentCode = `// 2. React / Next.js Integration (Any React project)
import { useEffect } from 'react';

export function RagChatWidget() {
  useEffect(() => {
    const script = document.createElement('script');
    script.src = '${currentOrigin}/rag-widget.js';
    script.setAttribute('data-endpoint', '${targetEndpoint}');
    script.setAttribute('data-title', '${widgetTitle}');
    script.setAttribute('data-color', '${primaryColor}');
    script.setAttribute('data-position', '${position}');
    script.async = true;
    document.body.appendChild(script);

    return () => {
      document.body.removeChild(script);
    };
  }, []);

  return null; // Widget mounts floating button to document.body
}`;

  const iframeEmbedCode = `<!-- 3. Responsive iframe for embedding in portals, sidebars or modals -->
<iframe
  src="${currentOrigin}/?mode=widget"
  width="400"
  height="600"
  style="border: none; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.15);"
  allow="clipboard-write"
  title="${widgetTitle}"
></iframe>`;

  const standaloneUrl = `${currentOrigin}/?mode=widget`;

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCodeKey(key);
    setTimeout(() => setCopiedCodeKey(null), 2000);
  };

  const handleSimSend = async () => {
    const q = simQuery.trim();
    if (!q || isSimLoading) return;
    setSimQuery('');

    const userMsg: ChatMessage = {
      id: `sim-user-${Date.now()}`,
      role: 'user',
      content: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setSimMessages((prev) => [...prev, userMsg]);
    setIsSimLoading(true);

    try {
      const res = await apiClient.sendChat({ query: q });
      setSimMessages((prev) => [
        ...prev,
        {
          id: `sim-resp-${Date.now()}`,
          role: 'assistant',
          content: res.answer,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          citations: res.citations,
          context_status: res.context_status,
          latency_ms: res.latency_ms,
        },
      ]);
    } catch (err: any) {
      setSimMessages((prev) => [
        ...prev,
        {
          id: `sim-err-${Date.now()}`,
          role: 'assistant',
          content: 'Unable to connect to RAG backend.',
          error: err.message || 'Connection failed',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsSimLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Banner: Direct Answer to User's Question */}
      <div className="rounded-2xl border border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50/50 p-6 dark:border-blue-900/60 dark:from-blue-950/40 dark:to-indigo-950/20 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-300 text-xs font-semibold">
              <Globe className="h-3.5 w-3.5" />
              <span>Cross-Site Embedding Enabled</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              Yes! This Chatbot Can Be Shown on Any Other Website
            </h2>
            <p className="text-xs text-slate-600 dark:text-slate-300 max-w-3xl leading-relaxed">
              You can embed this PDF RAG chatbot onto any website (HTML, WordPress, Webflow, Shopify, React, Next.js, or internal portals) using a simple <strong>1-line JavaScript snippet</strong>, a <strong>React Component</strong>, or an <strong>iframe</strong>.
            </p>
          </div>

          <a
            href={standaloneUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs shadow-xs transition-colors shrink-0 cursor-pointer"
          >
            <span>Open Standalone Widget URL</span>
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Embed Configurator & Code Snippets */}
        <div className="lg:col-span-6 space-y-6">
          {/* Customizer */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 shadow-2xs space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Sliders className="h-4 w-4 text-blue-600" />
              <span>Customize Widget for Your Website</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
              <div>
                <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Widget Title
                </label>
                <input
                  type="text"
                  value={widgetTitle}
                  onChange={(e) => setWidgetTitle(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Brand Color
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={primaryColor}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                    className="h-8 w-10 cursor-pointer rounded border border-slate-200 dark:border-slate-800 bg-transparent p-0"
                  />
                  <input
                    type="text"
                    value={primaryColor}
                    onChange={(e) => setPrimaryColor(e.target.value)}
                    className="flex-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Screen Position
                </label>
                <select
                  value={position}
                  onChange={(e) => setPosition(e.target.value as any)}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
                >
                  <option value="right">Bottom Right (Standard)</option>
                  <option value="left">Bottom Left</option>
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Target Endpoint
                </label>
                <input
                  type="text"
                  readOnly
                  value={targetEndpoint}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-950 px-3 py-1.5 font-mono text-[11px] text-slate-500 truncate"
                />
              </div>
            </div>
          </div>

          {/* Embed Code Tabs */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 shadow-2xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <Code className="h-4 w-4 text-purple-600" />
                <span>Ready-To-Copy Embed Code</span>
              </h3>

              <div className="flex gap-1">
                {(['script', 'react', 'iframe', 'direct'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-2.5 py-1 rounded text-xs font-medium cursor-pointer transition-colors ${
                      activeTab === tab
                        ? 'bg-blue-600 text-white'
                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                    }`}
                  >
                    {tab === 'script' && 'HTML Script'}
                    {tab === 'react' && 'React / Next.js'}
                    {tab === 'iframe' && 'iframe'}
                    {tab === 'direct' && 'Direct Link'}
                  </button>
                ))}
              </div>
            </div>

            {/* Code Display */}
            <div className="relative rounded-xl border border-slate-200 bg-slate-950 p-4 text-xs font-mono text-slate-100 dark:border-slate-800">
              <div className="absolute top-3 right-3">
                <button
                  onClick={() => {
                    let codeToCopy = scriptTagCode;
                    if (activeTab === 'react') codeToCopy = reactComponentCode;
                    if (activeTab === 'iframe') codeToCopy = iframeEmbedCode;
                    if (activeTab === 'direct') codeToCopy = standaloneUrl;
                    handleCopy(codeToCopy, activeTab);
                  }}
                  className="flex items-center gap-1.5 rounded-md bg-slate-800 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-700 hover:text-white transition-colors cursor-pointer"
                >
                  {copiedCodeKey === activeTab ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" />
                      <span>Copy Code</span>
                    </>
                  )}
                </button>
              </div>

              <pre className="overflow-x-auto pr-24 py-1 leading-relaxed text-[11px]">
                {activeTab === 'script' && scriptTagCode}
                {activeTab === 'react' && reactComponentCode}
                {activeTab === 'iframe' && iframeEmbedCode}
                {activeTab === 'direct' && standaloneUrl}
              </pre>
            </div>

            {/* Implementation Guide */}
            <div className="rounded-lg bg-slate-50 dark:bg-slate-950/60 p-3 text-xs text-slate-600 dark:text-slate-400 space-y-1.5">
              <strong className="text-slate-800 dark:text-slate-200 block">
                How it functions on other websites:
              </strong>
              <ul className="list-disc pl-4 space-y-1 text-[11px]">
                <li>
                  <strong>Zero Dependencies:</strong> <code>rag-widget.js</code> has no external package requirements (no React, no jQuery, no Tailwind required on the destination site).
                </li>
                <li>
                  <strong>CORS Compatible:</strong> When calling your FastAPI backend from another domain, ensure FastAPI allows the origin via <code>CORSMiddleware</code> in Python.
                </li>
                <li>
                  <strong>Safe & Sandboxed:</strong> Floating style does not conflict with host website CSS classes.
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Right Column: Interactive External Website Mockup */}
        <div className="lg:col-span-6 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-amber-500" />
              Live Interactive Simulation: Inside Another Website
            </span>
            <span>Click floating bubble to test!</span>
          </div>

          {/* Browser Mockup Window */}
          <div className="rounded-2xl border border-slate-300 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden flex flex-col h-[640px] relative">
            {/* Browser Top Bar */}
            <div className="bg-slate-100 dark:bg-slate-950 px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-full bg-rose-400" />
                <span className="h-3 w-3 rounded-full bg-amber-400" />
                <span className="h-3 w-3 rounded-full bg-emerald-400" />
              </div>
              <div className="flex-1 rounded-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-3 py-1 text-[11px] font-mono text-slate-500 flex items-center gap-2">
                <Globe className="h-3 w-3 text-slate-400" />
                <span>https://external-company-portal.com/documentation</span>
              </div>
            </div>

            {/* Mock Website Content Area */}
            <div className="flex-1 overflow-y-auto p-6 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 relative">
              {/* Fake Host Website Header */}
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4 mb-6">
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 font-bold text-xs flex items-center justify-center">
                    AC
                  </div>
                  <span className="font-bold text-sm tracking-tight">ACME Developer Hub</span>
                </div>
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>Guides</span>
                  <span>API Docs</span>
                  <span>Changelog</span>
                </div>
              </div>

              {/* Fake Host Website Article */}
              <div className="space-y-4 max-w-md">
                <span className="text-[10px] font-mono uppercase text-slate-400">
                  Enterprise Documentation
                </span>
                <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100 leading-tight">
                  Integrating RAG Search Into Enterprise Workflows
                </h1>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Welcome to our corporate knowledge base. You can browse articles manually, or use the floating AI assistant in the corner to ask questions against all indexed company PDFs in real time.
                </p>

                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2">
                  <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Quick Links:
                  </h4>
                  <ul className="text-xs text-blue-600 dark:text-blue-400 space-y-1">
                    <li>• PostgreSQL pgvector index configuration</li>
                    <li>• LangGraph state machine traversal guidelines</li>
                    <li>• FastEmbed ONNX local deployment SOP</li>
                  </ul>
                </div>
              </div>

              {/* SIMULATED EMBEDDED CHAT WIDGET */}
              <div
                className={`absolute bottom-6 ${
                  position === 'left' ? 'left-6' : 'right-6'
                } z-20`}
              >
                {/* Floating button */}
                {!isSimWidgetOpen && (
                  <button
                    onClick={() => setIsSimWidgetOpen(true)}
                    style={{ backgroundColor: primaryColor }}
                    className="flex h-12 w-12 items-center justify-center rounded-full text-white shadow-xl hover:scale-105 transition-all cursor-pointer ring-4 ring-black/5"
                    title="Open RAG Chatbot"
                  >
                    <MessageSquare className="h-5 w-5" />
                  </button>
                )}

                {/* Popover Chat window */}
                {isSimWidgetOpen && (
                  <div className="w-[330px] sm:w-[360px] h-[480px] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                    {/* Header */}
                    <div
                      style={{ backgroundColor: primaryColor }}
                      className="p-3 text-white flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <div className="h-6 w-6 rounded bg-white/20 flex items-center justify-center font-bold text-xs">
                          AI
                        </div>
                        <div>
                          <h4 className="text-xs font-semibold leading-tight">{widgetTitle}</h4>
                          <p className="text-[10px] text-white/80">FastEmbed · pgvector</p>
                        </div>
                      </div>
                      <button
                        onClick={() => setIsSimWidgetOpen(false)}
                        className="p-1 rounded hover:bg-white/10 text-white/90 hover:text-white cursor-pointer"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>

                    {/* Messages Body */}
                    <div className="flex-1 overflow-y-auto p-3 space-y-2.5 bg-slate-50 dark:bg-slate-950 text-xs">
                      {simMessages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`flex ${
                            msg.role === 'user' ? 'justify-end' : 'justify-start'
                          }`}
                        >
                          <div
                            style={
                              msg.role === 'user'
                                ? { backgroundColor: primaryColor, color: '#fff' }
                                : undefined
                            }
                            className={`max-w-[85%] rounded-xl p-2.5 ${
                              msg.role === 'user'
                                ? 'rounded-tr-none'
                                : 'bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-800 rounded-tl-none shadow-2xs'
                            }`}
                          >
                            <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            {msg.citations && msg.citations.length > 0 && (
                              <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                                <CitationViewer citations={msg.citations} />
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                      {isSimLoading && (
                        <div className="flex justify-start">
                          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-2.5 flex items-center gap-2 text-slate-500 text-xs">
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                            <span>Retrieving vector citations...</span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Footer Input */}
                    <div className="p-2 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center gap-2">
                      <input
                        type="text"
                        value={simQuery}
                        onChange={(e) => setSimQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSimSend()}
                        placeholder="Ask documentation..."
                        disabled={isSimLoading}
                        className="flex-1 rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2.5 py-1.5 text-xs text-slate-900 dark:text-slate-100 focus:outline-none"
                      />
                      <button
                        onClick={handleSimSend}
                        disabled={!simQuery.trim() || isSimLoading}
                        style={{ backgroundColor: primaryColor }}
                        className="p-1.5 rounded-md text-white hover:opacity-90 disabled:opacity-40 cursor-pointer"
                      >
                        <Send className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
