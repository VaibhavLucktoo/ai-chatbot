/**
 * @license SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Cpu,
  FileText,
  MessageSquare,
  Moon,
  Sun,
  ArrowUpRight,
  Sparkles,
  ShieldCheck,
  ChevronRight,
} from 'lucide-react';
import type {LucideIcon} from 'lucide-react';
import {ChatbotProvider, useChatbot} from './context/ChatbotContext';
import type {Tab} from './context/ChatbotContext';
import {ConnectedChat} from './components/chat/ConnectedChat';
import {ConnectedDocuments} from './components/documents/ConnectedDocuments';
import {BackendStatus} from './components/admin/BackendStatus';
import {ModelAnalyticsPanel} from './components/admin/ModelAnalytics';
import {AssistantSettingsPanel} from './components/admin/AssistantSettings';
import {WebsiteWidgetPanel} from './components/embed/WebsiteWidgetPanel';

type NavItem = {id: Tab; label: string; icon: LucideIcon};

const navGroups: {title: string; items: NavItem[]}[] = [
  {
    title: 'Workspace',
    items: [
      {id: 'chat', label: 'Chat', icon: MessageSquare},
      {id: 'documents', label: 'Documents', icon: FileText},
    ],
  },
  {
    title: 'Intelligence',
    items: [
      {id: 'assistants', label: 'Assistants', icon: Bot},
      {id: 'models', label: 'Models', icon: Cpu},
    ],
  },
  {
    title: 'Operations',
    items: [
      {id: 'analytics', label: 'Analytics', icon: BarChart3},
      {id: 'status', label: 'Status', icon: Activity},
      {id: 'widget', label: 'Website widget', icon: MessageSquare},
    ],
  },
] as const;

const allNavItems = navGroups.flatMap(group => group.items);

function Workspace() {
  const {tab, setTab, theme, toggleTheme, health, readyDocuments, assistantId, assistants} = useChatbot();
  const ready = health.api === 'online' && health.readiness === 'ready';
  const activeAssistantName = assistantId ? assistants.find(a => a.id === assistantId)?.name : 'Workspace Default';

  return (
    <div className="relative flex h-dvh min-h-0 flex-col bg-slate-50 dark:bg-[#090D16] text-slate-900 dark:text-slate-100 font-sans antialiased overflow-hidden selection:bg-blue-500/20 selection:text-blue-700 dark:selection:text-blue-300">
      {/* Ambient Canvas Elements (Zero performance penalty, purely visual) */}
      <div className="bg-dot-pattern fixed inset-0 pointer-events-none opacity-40 dark:opacity-30 z-0" />
      <div className="fixed -top-40 -right-40 w-[450px] h-[450px] bg-gradient-to-br from-blue-500/10 via-indigo-500/10 to-violet-500/5 dark:from-blue-600/15 dark:via-indigo-600/10 dark:to-transparent rounded-full blur-[100px] pointer-events-none animate-ambient-pulse z-0" />
      <div className="fixed -bottom-40 -left-40 w-[400px] h-[400px] bg-gradient-to-tr from-emerald-500/5 via-blue-500/10 to-transparent dark:from-emerald-500/10 dark:via-blue-600/10 dark:to-transparent rounded-full blur-[100px] pointer-events-none z-0" />

      {/* Glassmorphic Header */}
      <header className="relative h-16 shrink-0 backdrop-blur-xl bg-white/75 dark:bg-[#0F172A]/70 border-b border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between px-5 md:px-7 gap-3 z-20 shadow-2xs">
        <div className="flex gap-3.5 items-center">
          <div className="relative group cursor-pointer">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl blur-xs opacity-50 group-hover:opacity-80 transition duration-300" />
            <div className="relative h-10 w-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-violet-500 text-white flex items-center justify-center shadow-md shadow-blue-500/20 ring-1 ring-white/20">
              <BookOpen className="h-5 w-5"/>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm tracking-tight text-slate-900 dark:text-slate-100">
                Document Assistant
              </span>
              <span className="hidden lg:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gradient-to-r from-blue-500/10 to-indigo-500/10 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/60">
                <Sparkles className="w-2.5 h-2.5 text-blue-500"/> Enterprise RAG
              </span>
            </div>
            <p className="text-[10px] tracking-wider uppercase font-medium text-slate-400 dark:text-slate-500">
              Your Local Knowledge Workspace
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Active Assistant Tag */}
          {activeAssistantName && (
            <div className="hidden xl:flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] bg-slate-100/80 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 border border-slate-200/60 dark:border-slate-700/60 backdrop-blur-xs">
              <Bot className="w-3.5 h-3.5 text-blue-500"/>
              <span className="font-medium text-slate-700 dark:text-slate-300 truncate max-w-[140px]">
                {activeAssistantName}
              </span>
            </div>
          )}

          {/* Backend Status Live Badge */}
          <span
            className={`hidden sm:flex items-center gap-2 text-[11px] font-medium rounded-full px-3 py-1 shadow-2xs border backdrop-blur-xs transition-all ${
              ready
                ? 'bg-emerald-50/90 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-800/60'
                : health.api === 'offline'
                ? 'bg-rose-50/90 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border-rose-200/60 dark:border-rose-800/60'
                : 'bg-amber-50/90 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200/60 dark:border-amber-800/60'
            }`}
          >
            <span className="relative flex h-2 w-2">
              {ready && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              )}
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  ready ? 'bg-emerald-500' : health.api === 'offline' ? 'bg-rose-500' : 'bg-amber-500'
                }`}
              />
            </span>
            {ready ? 'Backend ready' : health.api === 'checking' ? 'Connecting' : health.api === 'offline' ? 'Backend offline' : 'Check readiness'}
          </span>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
            className="p-2 rounded-xl text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100/80 dark:hover:bg-slate-800/80 border border-transparent hover:border-slate-200 dark:hover:border-slate-700 transition-all cursor-pointer"
          >
            {theme === 'light' ? <Moon className="h-4 w-4"/> : <Sun className="h-4 w-4"/>}
          </button>
        </div>
      </header>

      {/* Mobile Navigation Bar */}
      <nav aria-label="Workspace navigation" className="relative md:hidden flex overflow-x-auto backdrop-blur-md bg-white/80 dark:bg-slate-900/80 border-b border-slate-200 dark:border-slate-800 px-3 py-2 gap-1.5 shrink-0 z-10 scrollbar-none">
        {allNavItems.map(item => (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            aria-current={tab === item.id ? 'page' : undefined}
            className={`flex-1 shrink-0 rounded-xl flex items-center justify-center gap-2 px-3 py-2 text-xs font-medium transition-all ${
              tab === item.id
                ? 'bg-blue-600 text-white shadow-xs'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <item.icon className="h-3.5 w-3.5"/>
            {item.label}
          </button>
        ))}
      </nav>

      {/* Workspace Body */}
      <div className="relative flex flex-1 min-h-0 z-10">
        {/* Desktop Sidebar */}
        <aside className="hidden md:flex w-64 shrink-0 flex-col border-r border-slate-200/80 dark:border-slate-800/80 backdrop-blur-xl bg-white/60 dark:bg-[#0F172A]/50 p-4">
          <nav aria-label="Main navigation" className="space-y-5 flex-1 overflow-y-auto pr-1">
            {navGroups.map(group => (
              <div key={group.title} className="space-y-1">
                <p className="text-[10px] font-bold tracking-wider uppercase text-slate-400 dark:text-slate-500 px-3 mb-2 flex items-center gap-1">
                  {group.title}
                </p>
                {group.items.map(item => {
                  const active = tab === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setTab(item.id)}
                      aria-current={active ? 'page' : undefined}
                      className={`w-full flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-xs font-medium transition-all group ${
                        active
                          ? 'bg-gradient-to-r from-blue-50 to-indigo-50/60 dark:from-blue-950/60 dark:to-indigo-950/40 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-800/60 shadow-2xs font-semibold'
                          : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100/60 dark:hover:bg-slate-800/40 border border-transparent'
                      }`}
                    >
                      <item.icon className={`h-4 w-4 transition-transform group-hover:scale-110 ${active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500'}`}/>
                      <span className="flex-1 text-left">{item.label}</span>
                      {item.id === 'documents' && (
                        <span className="text-[10px] font-mono font-medium rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-slate-600 dark:text-slate-400 border border-slate-200/60 dark:border-slate-700/60">
                          {readyDocuments.length}
                        </span>
                      )}
                      {active && <ChevronRight className="w-3 h-3 text-blue-500 shrink-0 opacity-75" />}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>

          {/* Sidebar Footer Card */}
          <div className="mt-auto pt-3">
            <div className="relative rounded-2xl bg-gradient-to-br from-white/80 via-slate-50/80 to-blue-50/30 dark:from-slate-900/80 dark:via-slate-900/60 dark:to-blue-950/20 p-4 border border-slate-200/80 dark:border-slate-800/80 shadow-2xs backdrop-blur-xs">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0"/>
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">Grounded in your PDFs</p>
              </div>
              <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400 mt-1.5">
                Every response cites verified document passages with page numbers.
              </p>
              <button
                onClick={() => setTab('documents')}
                className="flex items-center gap-1.5 text-[11px] font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 mt-2.5 transition-colors cursor-pointer group"
              >
                <span>Manage documents</span>
                <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"/>
              </button>
            </div>
            <p className="mt-3 px-1 text-[10px] text-slate-400 dark:text-slate-500">
              Local operator &middot; conversational RAG
            </p>
          </div>
        </aside>

        {/* Workspace Main Pane */}
        <main className="flex-1 min-w-0 min-h-0 overflow-y-auto">
          {health.api === 'offline' && (
            <div role="alert" className="bg-amber-50/90 dark:bg-amber-950/80 text-amber-800 dark:text-amber-200 px-5 py-3 text-xs border-b border-amber-200 dark:border-amber-900 flex items-center justify-between backdrop-blur-xs">
              <span>Backend connection unavailable. Existing conversation and selections are retained.</span>
              <button onClick={() => setTab('status')} className="underline font-semibold ml-2 hover:text-amber-950 dark:hover:text-amber-100">
                Check status
              </button>
            </div>
          )}
          <div key={tab} className="animate-view-enter h-full">
            {tab === 'chat' && <ConnectedChat/>}
            {tab === 'documents' && <ConnectedDocuments/>}
            {tab === 'status' && <BackendStatus/>}
            {tab === 'analytics' && <ModelAnalyticsPanel/>}
            {tab === 'assistants' && <AssistantSettingsPanel/>}
            {tab === 'models' && <AssistantSettingsPanel view="models"/>}
            {tab === 'widget' && <WebsiteWidgetPanel/>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ChatbotProvider>
      <Workspace/>
    </ChatbotProvider>
  );
}
