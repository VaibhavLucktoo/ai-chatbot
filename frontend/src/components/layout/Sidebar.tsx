import React from 'react';
import {
  MessageSquare,
  FileText,
  Activity,
  Sliders,
  FileCode2,
  Database,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Globe,
} from 'lucide-react';
import { NavigationTab, useApp } from '../../context/AppContext';

export const Sidebar: React.FC = () => {
  const { activeTab, setActiveTab, healthStatus, documents, telemetry } = useApp();

  const navItems: { id: NavigationTab; label: string; icon: React.ReactNode; badge?: string }[] = [
    {
      id: 'chat',
      label: 'User Chat',
      icon: <MessageSquare className="h-4 w-4" />,
    },
    {
      id: 'widget_embed',
      label: 'Embed on Other Sites',
      icon: <Globe className="h-4 w-4" />,
      badge: 'Embed',
    },
    {
      id: 'documents',
      label: 'Documents & Hybrid Search',
      icon: <FileText className="h-4 w-4" />,
      badge: `${documents.length}`,
    },
    {
      id: 'overview',
      label: 'Admin Overview',
      icon: <Activity className="h-4 w-4" />,
    },
    {
      id: 'llm_config',
      label: 'LLM Configuration',
      icon: <Sliders className="h-4 w-4" />,
    },
    {
      id: 'contracts',
      label: 'Contracts & Missing Endpoints',
      icon: <FileCode2 className="h-4 w-4" />,
      badge: 'Audit',
    },
  ];

  return (
    <aside className="w-64 border-r border-slate-200 bg-white flex flex-col justify-between shrink-0 dark:border-slate-800 dark:bg-slate-900 transition-colors">
      <div className="p-4 space-y-6">
        <div>
          <div className="px-2 text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-2">
            Navigation
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300'
                      : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500'}>
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-mono ${
                        item.badge === 'Audit'
                          ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400'
                          : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* System Component Status */}
        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 dark:border-slate-800 dark:bg-slate-950/50">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 mb-3 flex items-center justify-between">
            <span>Stack Telemetry</span>
            <span className="font-mono text-[10px] text-slate-400">/health/ready</span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                <Database className="h-3.5 w-3.5 text-slate-400" />
                <span>PostgreSQL (pgvector)</span>
              </div>
              {healthStatus.database ? (
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                  <CheckCircle2 className="h-3 w-3" />
                  Ready
                </span>
              ) : (
                <span className="flex items-center gap-1 text-rose-500 font-medium">
                  <AlertCircle className="h-3 w-3" />
                  Down
                </span>
              )}
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                <Cpu className="h-3.5 w-3.5 text-slate-400" />
                <span>FastEmbed ONNX</span>
              </div>
              {healthStatus.embeddings ? (
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                  <CheckCircle2 className="h-3 w-3" />
                  Ready
                </span>
              ) : (
                <span className="flex items-center gap-1 text-rose-500 font-medium">
                  <AlertCircle className="h-3 w-3" />
                  Down
                </span>
              )}
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                <Cpu className="h-3.5 w-3.5 text-slate-400" />
                <span>LangChain Adapter</span>
              </div>
              {healthStatus.llm ? (
                <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                  <CheckCircle2 className="h-3 w-3" />
                  Ready
                </span>
              ) : (
                <span className="flex items-center gap-1 text-rose-500 font-medium">
                  <AlertCircle className="h-3 w-3" />
                  Down
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Model & Config footer info */}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/30">
        <div className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Active Model:</span>
            <span className="font-mono font-medium text-slate-700 dark:text-slate-300">
              {telemetry.active_model}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Embeddings:</span>
            <span className="font-mono text-slate-600 dark:text-slate-400">
              bge-small-en (384d)
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Config:</span>
            <span className="font-mono text-slate-600 dark:text-slate-400">
              {telemetry.config_version}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
};
