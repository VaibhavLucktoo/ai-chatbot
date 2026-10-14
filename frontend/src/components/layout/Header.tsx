import React from 'react';
import {
  Moon,
  Sun,
  Server,
  Code2,
  Upload,
  Shield,
  Layers,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { UserRole } from '../../types/rag';

export const Header: React.FC = () => {
  const {
    theme,
    toggleTheme,
    userRole,
    setUserRole,
    backendSettings,
    healthStatus,
    setIsSettingsModalOpen,
    setIsUploadModalOpen,
    setIsEmbedModalOpen,
  } = useApp();

  const isRoleAuthorizedForUpload = userRole === 'doc_admin' || userRole === 'super_admin';

  return (
    <header className="h-16 border-b border-slate-200 bg-white px-4 md:px-6 flex items-center justify-between dark:border-slate-800 dark:bg-slate-900 transition-colors">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-sm shadow-sm">
          RAG
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-900 dark:text-slate-100 text-sm md:text-base tracking-tight">
              FastAPI PDF RAG
            </span>
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">
              v2.4
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>PostgreSQL · pgvector</span>
            <span aria-hidden="true">·</span>
            <span>FastEmbed</span>
            <span aria-hidden="true">·</span>
            <span>LangGraph</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 md:gap-3">
        {/* Role Selector */}
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 py-1 text-xs dark:border-slate-800 dark:bg-slate-950">
          <Shield className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
          <span className="text-slate-500 dark:text-slate-400 hidden lg:inline">Role:</span>
          <select
            value={userRole}
            onChange={(e) => setUserRole(e.target.value as UserRole)}
            className="bg-transparent font-medium text-slate-700 dark:text-slate-200 focus:outline-none cursor-pointer text-xs"
            aria-label="Current User Role"
          >
            <option value="super_admin" className="dark:bg-slate-900">
              Super Admin (Full Access)
            </option>
            <option value="doc_admin" className="dark:bg-slate-900">
              Document Admin (Uploads)
            </option>
            <option value="user" className="dark:bg-slate-900">
              End User (Query Only)
            </option>
          </select>
        </div>

        {/* Upload Button (Role-Aware) */}
        <button
          onClick={() => {
            if (isRoleAuthorizedForUpload) {
              setIsUploadModalOpen(true);
            }
          }}
          disabled={!isRoleAuthorizedForUpload}
          title={
            isRoleAuthorizedForUpload
              ? 'Upload PDF document to FastEmbed & pgvector'
              : 'Upload restricted to Document Admin or Super Admin roles'
          }
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            isRoleAuthorizedForUpload
              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm cursor-pointer'
              : 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-600 cursor-not-allowed opacity-75'
          }`}
        >
          <Upload className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Upload PDF</span>
        </button>

        {/* Backend Connectivity Status Button */}
        <button
          onClick={() => setIsSettingsModalOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800/80 transition-colors cursor-pointer"
          title="Configure backend endpoint"
        >
          <Server className="h-3.5 w-3.5 text-slate-500" />
          <span className="hidden md:inline">
            {backendSettings.mode === 'simulated' ? 'Mock Gateway' : 'Remote API'}
          </span>
          {healthStatus.liveness ? (
            <span className="flex h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-emerald-500/20" />
          ) : (
            <span className="flex h-2 w-2 rounded-full bg-amber-500 ring-2 ring-amber-500/20" />
          )}
        </button>

        {/* Embed Widget Modal Launcher */}
        <button
          onClick={() => setIsEmbedModalOpen(true)}
          className="p-2 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          title="Get Reusable Chat Widget Code"
          aria-label="Embed chat widget"
        >
          <Code2 className="h-4 w-4" />
        </button>

        {/* Dark/Light Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4 text-amber-400" />
          ) : (
            <Moon className="h-4 w-4 text-slate-600" />
          )}
        </button>
      </div>
    </header>
  );
};
