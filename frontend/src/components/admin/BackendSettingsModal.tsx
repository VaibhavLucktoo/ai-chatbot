import React, { useState } from 'react';
import {
  Server,
  X,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Shield,
  Layers,
  Globe,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { apiClient } from '../../services/apiClient';

export const BackendSettingsModal: React.FC = () => {
  const {
    backendSettings,
    updateBackendSettings,
    isSettingsModalOpen,
    setIsSettingsModalOpen,
    refreshHealth,
  } = useApp();

  const [mode, setMode] = useState<'simulated' | 'remote'>(backendSettings.mode);
  const [remoteBaseUrl, setRemoteBaseUrl] = useState(backendSettings.remoteBaseUrl);
  const [apiToken, setApiToken] = useState(backendSettings.apiToken || '');
  const [timeoutMs, setTimeoutMs] = useState(backendSettings.timeoutMs);

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    live: boolean;
    ready: boolean;
    message: string;
  } | null>(null);

  if (!isSettingsModalOpen) return null;

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);

    // Save temporarily for probe test
    apiClient.saveSettings({ mode, remoteBaseUrl, apiToken, timeoutMs });

    try {
      const live = await apiClient.checkHealthLive();
      const ready = await apiClient.checkHealthReady();
      setTestResult({
        live: live.status === 'ok',
        ready: ready.status === 'ready',
        message:
          mode === 'simulated'
            ? 'Simulated in-memory FastAPI backend is fully operational with pgvector & FastEmbed emulation.'
            : `Remote endpoint reached at ${remoteBaseUrl}. Liveness: ${live.status}, Readiness: ${ready.status}.`,
      });
    } catch (err: any) {
      setTestResult({
        live: false,
        ready: false,
        message: err.message || 'Failed to connect to specified backend endpoint.',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = () => {
    updateBackendSettings({
      mode,
      remoteBaseUrl,
      apiToken,
      timeoutMs,
    });
    setIsSettingsModalOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
              <Server className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                FastAPI Backend Connectivity Settings
              </h3>
              <p className="text-xs text-slate-500">
                Switch between high-fidelity local simulator and live remote FastAPI server
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsSettingsModalOpen(false)}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form Body */}
        <div className="p-6 space-y-4">
          {/* Mode Selector */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Backend Execution Mode
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setMode('simulated')}
                className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                  mode === 'simulated'
                    ? 'border-blue-600 bg-blue-50/50 dark:border-blue-500 dark:bg-blue-950/30'
                    : 'border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-xs text-slate-900 dark:text-slate-100">
                    Integrated Simulator
                  </span>
                  {mode === 'simulated' && (
                    <CheckCircle2 className="h-4 w-4 text-blue-600" />
                  )}
                </div>
                <p className="text-[11px] text-slate-500 leading-tight">
                  Preloaded with enterprise technical PDFs, pgvector simulation, and FastEmbed ONNX
                </p>
              </button>

              <button
                type="button"
                onClick={() => setMode('remote')}
                className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                  mode === 'remote'
                    ? 'border-blue-600 bg-blue-50/50 dark:border-blue-500 dark:bg-blue-950/30'
                    : 'border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-xs text-slate-900 dark:text-slate-100">
                    Live Remote Endpoint
                  </span>
                  {mode === 'remote' && (
                    <CheckCircle2 className="h-4 w-4 text-blue-600" />
                  )}
                </div>
                <p className="text-[11px] text-slate-500 leading-tight">
                  Connect to your existing FastAPI server running on localhost or cloud host
                </p>
              </button>
            </div>
          </div>

          {/* Remote Settings inputs */}
          {mode === 'remote' && (
            <div className="space-y-3 pt-2">
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Remote Backend Base URL
                </label>
                <input
                  type="url"
                  value={remoteBaseUrl}
                  onChange={(e) => setRemoteBaseUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
                />
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Must expose POST /v1/chat, POST /v1/documents/upload, GET /health/live
                </span>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Authorization Bearer Token (Optional)
                </label>
                <input
                  type="password"
                  value={apiToken}
                  onChange={(e) => setApiToken(e.target.value)}
                  placeholder="Bearer token if endpoint is protected..."
                  className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Request Timeout (ms)
                </label>
                <input
                  type="number"
                  value={timeoutMs}
                  onChange={(e) => setTimeoutMs(Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
          )}

          {/* Test Probe Action */}
          <div className="pt-2">
            <button
              type="button"
              onClick={handleTest}
              disabled={isTesting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 transition-colors cursor-pointer"
            >
              <RotateCcw className={`h-3.5 w-3.5 ${isTesting ? 'animate-spin' : ''}`} />
              <span>{isTesting ? 'Testing Connectivity...' : 'Test Backend Connection'}</span>
            </button>

            {testResult && (
              <div
                className={`mt-2 p-3 rounded-lg text-xs ${
                  testResult.live
                    ? 'bg-emerald-50 text-emerald-900 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900'
                    : 'bg-rose-50 text-rose-900 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-200 dark:border-rose-900'
                }`}
              >
                <div className="flex items-center justify-between font-semibold mb-1">
                  <span>
                    {testResult.live ? 'Connection Succeeded' : 'Connection Failed'}
                  </span>
                  <span className="font-mono">
                    Liveness: {testResult.live ? '200 OK' : 'ERR'} · Readiness:{' '}
                    {testResult.ready ? '200 OK' : 'Degraded'}
                  </span>
                </div>
                <p>{testResult.message}</p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <button
            type="button"
            onClick={() => setIsSettingsModalOpen(false)}
            className="px-4 py-2 rounded-lg text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-4 py-2 rounded-lg text-xs font-medium bg-blue-600 text-white hover:bg-blue-700 transition-colors cursor-pointer"
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};
