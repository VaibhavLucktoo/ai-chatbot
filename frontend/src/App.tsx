/**
 * @license SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
import {Activity, BarChart3, BookOpen, Bot, Cpu, FileText, MessageSquare, Moon, Sun, ArrowUpRight} from 'lucide-react';
import {ChatbotProvider, useChatbot} from './context/ChatbotContext';
import {ConnectedChat} from './components/chat/ConnectedChat';
import {ConnectedDocuments} from './components/documents/ConnectedDocuments';
import {BackendStatus} from './components/admin/BackendStatus';
import {ModelAnalyticsPanel} from './components/admin/ModelAnalytics';
import {AssistantSettingsPanel} from './components/admin/AssistantSettings';
import {WebsiteWidgetPanel} from './components/embed/WebsiteWidgetPanel';

const navigation = [
  {id: 'chat', label: 'Chat', icon: MessageSquare},
  {id: 'documents', label: 'Documents', icon: FileText},
  {id: 'status', label: 'Status', icon: Activity},
  {id: 'analytics', label: 'Analytics', icon: BarChart3},
  {id: 'assistants', label: 'Assistants', icon: Bot},
  {id: 'models', label: 'Models', icon: Cpu},
  {id: 'widget', label: 'Website widget', icon: MessageSquare},
] as const;

function Workspace() {
  const {tab, setTab, theme, toggleTheme, health, readyDocuments} = useChatbot();
  const ready = health.api === 'online' && health.readiness === 'ready';
  return <div className="flex h-dvh min-h-0 flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans antialiased">
    <header className="h-16 shrink-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-5 md:px-7 gap-3">
      <div className="flex gap-3 items-center"><div className="h-9 w-9 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-sm"><BookOpen className="h-5 w-5"/></div>
        <div><p className="font-semibold text-sm tracking-tight">Document Assistant</p><p className="text-[10px] text-slate-400">YOUR LOCAL KNOWLEDGE WORKSPACE</p></div></div>
      <div className="flex items-center gap-3"><span className={`hidden sm:flex items-center gap-1.5 text-[11px] rounded-full px-2.5 py-1 ${ready ? 'bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300'}`}>
        <span className={`h-1.5 w-1.5 rounded-full ${ready ? 'bg-emerald-500' : 'bg-amber-500'}`}/>{ready ? 'Backend ready' : health.api === 'checking' ? 'Connecting' : health.api === 'offline' ? 'Backend offline' : 'Check readiness'}</span>
        <button onClick={toggleTheme} aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'} className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">{theme === 'light' ? <Moon className="h-4 w-4"/> : <Sun className="h-4 w-4"/>}</button></div>
    </header>
    <nav aria-label="Workspace navigation" className="md:hidden flex overflow-x-auto bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-3 py-2 gap-2">
      {navigation.map(item => <button key={item.id} onClick={() => setTab(item.id)} aria-current={tab === item.id ? 'page' : undefined} className={`flex-1 shrink-0 rounded-lg flex items-center justify-center gap-2 px-3 py-2 text-xs ${tab === item.id ? 'bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300' : 'text-slate-500'}`}><item.icon className="h-4 w-4"/>{item.label}</button>)}
    </nav>
    <div className="flex flex-1 min-h-0">
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
        <p className="text-[10px] tracking-wider uppercase text-slate-400 px-3 mb-3 mt-2">Workspace</p>
        <nav aria-label="Main navigation" className="space-y-1">{navigation.map(item => <button key={item.id} onClick={() => setTab(item.id)} aria-current={tab === item.id ? 'page' : undefined} className={`w-full flex items-center gap-3 rounded-xl px-3 py-3 text-xs font-medium transition-colors ${tab === item.id ? 'bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300' : 'text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
          <item.icon className="h-4 w-4"/><span className="flex-1 text-left">{item.label}</span>{item.id === 'documents' && <span className="text-[10px] rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5">{readyDocuments.length}</span>}</button>)}</nav>
        <div className="mt-auto rounded-xl bg-slate-50 dark:bg-slate-950 p-4 border border-slate-100 dark:border-slate-800">
          <p className="text-xs font-medium">Grounded in your PDFs</p><p className="text-[11px] leading-relaxed text-slate-500 mt-2">Open a source to check the evidence behind an answer.</p>
          <button onClick={() => setTab('documents')} className="flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 mt-3">Manage documents<ArrowUpRight className="h-3 w-3"/></button>
        </div>
        <p className="mt-4 px-2 text-[10px] text-slate-400">Local operator &middot; conversational chat</p>
      </aside>
      <main className="flex-1 min-w-0 min-h-0 overflow-y-auto">
        {health.api === 'offline' && <div role="alert" className="bg-amber-50 dark:bg-amber-950 text-amber-800 dark:text-amber-200 px-5 py-3 text-xs border-b border-amber-200 dark:border-amber-900">Backend connection unavailable. <button onClick={() => setTab('status')} className="underline font-medium">Check status</button>. Existing conversation and selections are retained.</div>}
        {tab === 'chat' && <ConnectedChat/>}
        {tab === 'documents' && <ConnectedDocuments/>}
        {tab === 'status' && <BackendStatus/>}
        {tab === 'analytics' && <ModelAnalyticsPanel/>}
        {tab === 'assistants' && <AssistantSettingsPanel/>}
        {tab === 'models' && <AssistantSettingsPanel view="models"/>}
        {tab === 'widget' && <WebsiteWidgetPanel/>}
      </main>
    </div>
  </div>;
}

export default function App() {
  return <ChatbotProvider><Workspace/></ChatbotProvider>;
}
