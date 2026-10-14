import React, { useState } from 'react';
import {
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  ShieldAlert,
  HelpCircle,
  Copy,
  Check,
  Server,
  Zap,
  Lock,
  Cpu,
  Layers,
  FileCode,
} from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { LlmConfig } from '../../types/rag';
import { apiClient } from '../../services/apiClient';

interface ModelCapabilityPreset {
  provider_name: string;
  provider_type: 'local' | 'hosted';
  model_id: string;
  approved_endpoint: string;
  context_window: number;
  tokenizer_id: string;
  supports_reasoning: boolean;
  supports_penalties: boolean;
  supports_temperature: boolean;
  supports_seed: boolean;
  supports_json_schema: boolean;
  notes?: string;
}

const PRESET_MODELS: Record<string, ModelCapabilityPreset> = {
  'gpt-4o-mini': {
    provider_name: 'openai',
    provider_type: 'hosted',
    model_id: 'gpt-4o-mini',
    approved_endpoint: 'https://api.openai.com/v1/chat/completions',
    context_window: 128000,
    tokenizer_id: 'tiktoken:o200k_base',
    supports_reasoning: false,
    supports_penalties: true,
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: true,
  },
  'gpt-4o': {
    provider_name: 'openai',
    provider_type: 'hosted',
    model_id: 'gpt-4o',
    approved_endpoint: 'https://api.openai.com/v1/chat/completions',
    context_window: 128000,
    tokenizer_id: 'tiktoken:o200k_base',
    supports_reasoning: false,
    supports_penalties: true,
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: true,
  },
  'o1-mini': {
    provider_name: 'openai',
    provider_type: 'hosted',
    model_id: 'o1-mini',
    approved_endpoint: 'https://api.openai.com/v1/chat/completions',
    context_window: 128000,
    tokenizer_id: 'tiktoken:o200k_base',
    supports_reasoning: true,
    supports_penalties: false, // o1 does NOT support frequency/presence penalties
    supports_temperature: false, // o1 only supports fixed temperature=1.0
    supports_seed: false,
    supports_json_schema: true,
    notes: 'Reasoning model: enforces fixed temperature 1.0, penalties are unsupported.',
  },
  'claude-3-5-sonnet': {
    provider_name: 'anthropic',
    provider_type: 'hosted',
    model_id: 'claude-3-5-sonnet-20241022',
    approved_endpoint: 'https://api.anthropic.com/v1/messages',
    context_window: 200000,
    tokenizer_id: 'anthropic:claude-3',
    supports_reasoning: false,
    supports_penalties: false, // Anthropic does not support frequency/presence penalties in messages API
    supports_temperature: true,
    supports_seed: false,
    supports_json_schema: true,
    notes: 'Anthropic Messages API does not recognize frequency or presence penalty.',
  },
  'meta-llama-3.1-70b-instruct': {
    provider_name: 'groq',
    provider_type: 'hosted',
    model_id: 'llama-3.1-70b-versatile',
    approved_endpoint: 'https://api.groq.com/openai/v1/chat/completions',
    context_window: 131072,
    tokenizer_id: 'meta-llama:Llama-3-Tokenizer',
    supports_reasoning: false,
    supports_penalties: true,
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: true,
  },
  'ollama-local-llama3': {
    provider_name: 'ollama',
    provider_type: 'local',
    model_id: 'llama3:8b-instruct-q8_0',
    approved_endpoint: 'http://localhost:11434/v1/chat/completions',
    context_window: 8192,
    tokenizer_id: 'sentencepiece:llama3',
    supports_reasoning: false,
    supports_penalties: true,
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: false,
    notes: 'Local Ollama endpoint: structured outputs require local GBNF grammar parser.',
  },
  'vllm-mistral-nemo': {
    provider_name: 'vllm',
    provider_type: 'local',
    model_id: 'mistralai/Mistral-Nemo-Instruct-2407',
    approved_endpoint: 'http://vllm.internal:8000/v1/chat/completions',
    context_window: 128000,
    tokenizer_id: 'mistral:tekken',
    supports_reasoning: false,
    supports_penalties: true,
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: true,
  },
};

export const LlmConfiguration: React.FC = () => {
  const { llmConfig, updateLlmConfig } = useApp();
  const [formData, setFormData] = useState<LlmConfig>({ ...llmConfig });
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>('gpt-4o-mini');

  // Capability checks
  const currentCapability = PRESET_MODELS[selectedPresetKey] || {
    supports_reasoning: false,
    supports_penalties: formData.provider_type === 'hosted' && formData.provider_name === 'openai',
    supports_temperature: true,
    supports_seed: true,
    supports_json_schema: true,
  };

  // Test Connection Probe
  const [isTestingConn, setIsTestingConn] = useState(false);
  const [connResult, setConnResult] = useState<{
    success: boolean;
    latency_ms: number;
    message: string;
  } | null>(null);

  // Sample Generation Probe
  const [isTestingGen, setIsTestingGen] = useState(false);
  const [samplePrompt, setSamplePrompt] = useState(
    'Synthesize the key architectural requirements for the PDF vector index.'
  );
  const [genResult, setGenResult] = useState<{
    success: boolean;
    output: string;
    tokens_generated: number;
    latency_ms: number;
    tokens_per_second: number;
  } | null>(null);

  // Save state
  const [isSaved, setIsSaved] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);

  const handlePresetSelect = (key: string) => {
    setSelectedPresetKey(key);
    const preset = PRESET_MODELS[key];
    if (preset) {
      setFormData((prev) => ({
        ...prev,
        provider_name: preset.provider_name,
        provider_type: preset.provider_type,
        model_id: preset.model_id,
        approved_endpoint_url: preset.approved_endpoint,
        context_window_tokens: preset.context_window,
        tokenizer_id: preset.tokenizer_id,
        reasoning_effort: preset.supports_reasoning ? 'medium' : 'none',
        temperature: preset.supports_temperature ? prev.temperature : 1.0,
      }));
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateLlmConfig(formData);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2500);
  };

  const handleTestConnection = async () => {
    setIsTestingConn(true);
    setConnResult(null);
    try {
      const res = await apiClient.testLlmConnection(formData);
      setConnResult(res);
    } catch (err: any) {
      setConnResult({
        success: false,
        latency_ms: 0,
        message: err.message || 'Probe request timed out or was rejected.',
      });
    } finally {
      setIsTestingConn(false);
    }
  };

  const handleRunSampleProbe = async () => {
    setIsTestingGen(true);
    setGenResult(null);
    try {
      const res = await apiClient.testSampleGeneration(samplePrompt, formData);
      setGenResult(res);
    } catch (err: any) {
      setGenResult({
        success: false,
        output: err.message || 'Generation failed.',
        tokens_generated: 0,
        latency_ms: 0,
        tokens_per_second: 0,
      });
    } finally {
      setIsTestingGen(false);
    }
  };

  const yamlExport = `# FastAPI RAG - Custom LangChain Model Adapter Configuration
# Injected via Server-Side Settings / Environment Config
llm:
  provider_type: "${formData.provider_type}"
  provider_name: "${formData.provider_name}"
  model_id: "${formData.model_id}"
  approved_endpoint_url: "${formData.approved_endpoint_url}"
  credential_reference: "${formData.credential_reference}"
  context_window_tokens: ${formData.context_window_tokens}
  tokenizer_id: "${formData.tokenizer_id}"
  max_output_tokens: ${formData.max_output_tokens}
  temperature: ${formData.temperature}
  top_p: ${formData.top_p}
  seed: ${formData.seed ?? 'null'}
  stop_sequences: ${JSON.stringify(formData.stop_sequences)}
  frequency_penalty: ${formData.frequency_penalty}
  presence_penalty: ${formData.presence_penalty}
  reasoning_effort: "${formData.reasoning_effort}"
  structured_output_mode: "${formData.structured_output_mode}"

timeouts:
  connection_timeout_ms: ${formData.timeouts.connection_timeout_ms}
  read_timeout_ms: ${formData.timeouts.read_timeout_ms}
  write_timeout_ms: ${formData.timeouts.write_timeout_ms}
  pool_timeout_ms: ${formData.timeouts.pool_timeout_ms}
  total_deadline_ms: ${formData.timeouts.total_deadline_ms}

concurrency:
  max_concurrency: ${formData.concurrency.max_concurrency}
  queue_limit: ${formData.concurrency.queue_limit}
  connection_pool_limit: ${formData.concurrency.connection_pool_limit}

resiliency:
  max_retries: ${formData.resiliency.max_retries}
  backoff_multiplier: ${formData.resiliency.backoff_multiplier}
  circuit_breaker_threshold: ${formData.resiliency.circuit_breaker_threshold}
  circuit_breaker_reset_ms: ${formData.resiliency.circuit_breaker_reset_ms}
`;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
            LLM Adapter & Generation Configuration
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Capability-aware parameter tuning for LangGraph model adapter with endpoint whitelist verification
          </p>
        </div>

        {/* Missing Endpoint Callout Badge */}
        <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
          <span>
            <strong>Missing Endpoint:</strong> <code>PUT /v1/admin/config/llm</code> is not in upstream FastAPI.
          </span>
        </div>
      </div>

      {/* Preset Model Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 shadow-2xs">
        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
          Model Identity & Capability Presets
        </label>
        <div className="flex flex-wrap gap-2">
          {Object.entries(PRESET_MODELS).map(([key, item]) => {
            const isSelected = selectedPresetKey === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => handlePresetSelect(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center gap-2 ${
                  isSelected
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                <span>{item.model_id}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                    isSelected
                      ? 'bg-blue-700 text-blue-100'
                      : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                  }`}
                >
                  {item.provider_type}
                </span>
              </button>
            );
          })}
        </div>
        {PRESET_MODELS[selectedPresetKey]?.notes && (
          <div className="mt-3 text-xs text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
            <HelpCircle className="h-3.5 w-3.5 shrink-0" />
            <span>{PRESET_MODELS[selectedPresetKey].notes}</span>
          </div>
        )}
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Section 1: Provider & Endpoint Whitelist */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
            <Server className="h-4 w-4 text-blue-600" />
            <span>1. Provider & Approved Endpoint Whitelist</span>
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
            {/* Provider Type */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Provider Type
              </label>
              <select
                value={formData.provider_type}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    provider_type: e.target.value as 'local' | 'hosted',
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-medium text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="hosted">Hosted Provider (OpenAI, Anthropic, Groq)</option>
                <option value="local">Local Worker (Ollama, vLLM, LocalAI)</option>
              </select>
            </div>

            {/* Provider Name */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Provider Identifier
              </label>
              <input
                type="text"
                value={formData.provider_name}
                onChange={(e) =>
                  setFormData({ ...formData, provider_name: e.target.value })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs text-slate-800 dark:text-slate-200 font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Model ID */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Model Identifier
              </label>
              <input
                type="text"
                value={formData.model_id}
                onChange={(e) =>
                  setFormData({ ...formData, model_id: e.target.value })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs text-slate-800 dark:text-slate-200 font-mono focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Approved Endpoint URL */}
            <div className="md:col-span-2">
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Approved Endpoint URL (Network Whitelist)
              </label>
              <input
                type="url"
                value={formData.approved_endpoint_url}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    approved_endpoint_url: e.target.value,
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs text-slate-800 dark:text-slate-200 font-mono focus:outline-none focus:border-blue-500"
                placeholder="https://api.openai.com/v1/chat/completions"
              />
            </div>

            {/* Credential Reference */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Server Credential Reference (Non-Leaking)
              </label>
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950 px-3 py-2">
                <Lock className="h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  value={formData.credential_reference}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      credential_reference: e.target.value,
                    })
                  }
                  className="w-full bg-transparent text-xs text-slate-700 dark:text-slate-300 font-mono focus:outline-none"
                  placeholder="ENV:LLM_API_KEY_SECRET"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Generation Hyperparameters & Capability Gating */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
            <Sliders className="h-4 w-4 text-purple-600" />
            <span>2. Capability-Aware Generation Controls</span>
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            {/* Context Window */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Context Window (Tokens)
              </label>
              <input
                type="number"
                value={formData.context_window_tokens}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    context_window_tokens: Number(e.target.value),
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Tokenizer Identifier */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Tokenizer Identifier
              </label>
              <input
                type="text"
                value={formData.tokenizer_id}
                onChange={(e) =>
                  setFormData({ ...formData, tokenizer_id: e.target.value })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Max Output Tokens */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Max Output Tokens
              </label>
              <input
                type="number"
                value={formData.max_output_tokens}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    max_output_tokens: Number(e.target.value),
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-mono text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            {/* Seed (Reproducibility) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Seed (Deterministic)
                </label>
                {!currentCapability.supports_seed && (
                  <span className="text-[10px] text-amber-600 font-normal">
                    Unsupported
                  </span>
                )}
              </div>
              <input
                type="number"
                value={formData.seed ?? 42}
                disabled={!currentCapability.supports_seed}
                onChange={(e) =>
                  setFormData({ ...formData, seed: Number(e.target.value) })
                }
                className={`w-full rounded-lg border px-3 py-2 text-xs font-mono focus:outline-none ${
                  currentCapability.supports_seed
                    ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 text-slate-800 dark:text-slate-200'
                    : 'border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-900/50 text-slate-400 cursor-not-allowed'
                }`}
              />
            </div>

            {/* Temperature */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Temperature: {formData.temperature}
                </label>
                {!currentCapability.supports_temperature && (
                  <span
                    className="text-[10px] text-amber-600 font-normal"
                    title="Reasoning models enforce fixed temperature=1.0"
                  >
                    Fixed (1.0)
                  </span>
                )}
              </div>
              <input
                type="range"
                min="0"
                max="2"
                step="0.05"
                value={formData.temperature}
                disabled={!currentCapability.supports_temperature}
                onChange={(e) =>
                  setFormData({ ...formData, temperature: parseFloat(e.target.value) })
                }
                className="w-full accent-blue-600 disabled:opacity-40"
              />
            </div>

            {/* Top P */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Top_P: {formData.top_p}
                </label>
              </div>
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={formData.top_p}
                onChange={(e) =>
                  setFormData({ ...formData, top_p: parseFloat(e.target.value) })
                }
                className="w-full accent-blue-600"
              />
            </div>

            {/* Frequency Penalty (Capability Gated) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Frequency Penalty
                </label>
                {!currentCapability.supports_penalties && (
                  <span
                    className="text-[10px] text-amber-600"
                    title="Model or endpoint does not support frequency penalty"
                  >
                    Disabled (N/A)
                  </span>
                )}
              </div>
              <input
                type="number"
                step="0.1"
                min="-2"
                max="2"
                value={formData.frequency_penalty}
                disabled={!currentCapability.supports_penalties}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    frequency_penalty: parseFloat(e.target.value),
                  })
                }
                className={`w-full rounded-lg border px-3 py-2 text-xs font-mono focus:outline-none ${
                  currentCapability.supports_penalties
                    ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 text-slate-800 dark:text-slate-200'
                    : 'border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-900/50 text-slate-400 cursor-not-allowed'
                }`}
              />
            </div>

            {/* Presence Penalty (Capability Gated) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Presence Penalty
                </label>
                {!currentCapability.supports_penalties && (
                  <span
                    className="text-[10px] text-amber-600"
                    title="Model or endpoint does not support presence penalty"
                  >
                    Disabled (N/A)
                  </span>
                )}
              </div>
              <input
                type="number"
                step="0.1"
                min="-2"
                max="2"
                value={formData.presence_penalty}
                disabled={!currentCapability.supports_penalties}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    presence_penalty: parseFloat(e.target.value),
                  })
                }
                className={`w-full rounded-lg border px-3 py-2 text-xs font-mono focus:outline-none ${
                  currentCapability.supports_penalties
                    ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 text-slate-800 dark:text-slate-200'
                    : 'border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-900/50 text-slate-400 cursor-not-allowed'
                }`}
              />
            </div>

            {/* Reasoning Effort (Capability Gated) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="font-medium text-slate-700 dark:text-slate-300">
                  Reasoning Effort
                </label>
                {!currentCapability.supports_reasoning && (
                  <span
                    className="text-[10px] text-slate-400"
                    title="Only available on reasoning models (o1/o3/DeepSeek-R1)"
                  >
                    Non-reasoning
                  </span>
                )}
              </div>
              <select
                value={formData.reasoning_effort}
                disabled={!currentCapability.supports_reasoning}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    reasoning_effort: e.target.value as any,
                  })
                }
                className={`w-full rounded-lg border px-3 py-2 text-xs font-medium focus:outline-none ${
                  currentCapability.supports_reasoning
                    ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 text-slate-800 dark:text-slate-200'
                    : 'border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-900/50 text-slate-400 cursor-not-allowed'
                }`}
              >
                <option value="none">None (Standard)</option>
                <option value="low">Low Effort</option>
                <option value="medium">Medium Effort</option>
                <option value="high">High Effort</option>
              </select>
            </div>

            {/* Structured Output Mode */}
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Structured Output Mode
              </label>
              <select
                value={formData.structured_output_mode}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    structured_output_mode: e.target.value as any,
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 text-xs font-medium text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="none">Disabled (Freeform Markdown)</option>
                <option value="json_object">JSON Object (Generic)</option>
                <option value="json_schema">Strict JSON Schema Validation</option>
              </select>
            </div>
          </div>
        </div>

        {/* Section 3: Timeouts, Concurrency & Circuit Breaker */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
            <Zap className="h-4 w-4 text-emerald-600" />
            <span>3. Network Timeouts, Concurrency & Resiliency</span>
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3.5 text-xs">
            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Conn Timeout (ms)
              </label>
              <input
                type="number"
                value={formData.timeouts.connection_timeout_ms}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    timeouts: {
                      ...formData.timeouts,
                      connection_timeout_ms: Number(e.target.value),
                    },
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 font-mono text-xs focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Read Timeout (ms)
              </label>
              <input
                type="number"
                value={formData.timeouts.read_timeout_ms}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    timeouts: {
                      ...formData.timeouts,
                      read_timeout_ms: Number(e.target.value),
                    },
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 font-mono text-xs focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Total Deadline (ms)
              </label>
              <input
                type="number"
                value={formData.timeouts.total_deadline_ms}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    timeouts: {
                      ...formData.timeouts,
                      total_deadline_ms: Number(e.target.value),
                    },
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 font-mono text-xs focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Max Concurrency
              </label>
              <input
                type="number"
                value={formData.concurrency.max_concurrency}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    concurrency: {
                      ...formData.concurrency,
                      max_concurrency: Number(e.target.value),
                    },
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 font-mono text-xs focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-700 dark:text-slate-300 mb-1">
                Retry Count
              </label>
              <input
                type="number"
                value={formData.resiliency.max_retries}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    resiliency: {
                      ...formData.resiliency,
                      max_retries: Number(e.target.value),
                    },
                  })
                }
                className="w-full rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950 px-3 py-2 font-mono text-xs focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Action Buttons: Save & Export */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="flex items-center gap-3">
            <button
              type="submit"
              className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs shadow-xs transition-colors cursor-pointer"
            >
              Apply In-Memory Adapter Config
            </button>
            {isSaved && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
                <Check className="h-4 w-4" />
                Updated Active Adapter!
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(yamlExport);
              setCopiedConfig(true);
              setTimeout(() => setCopiedConfig(false), 2000);
            }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 transition-colors cursor-pointer"
          >
            {copiedConfig ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-500" />
                <span>Copied YAML!</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>Export config.yaml</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Section 4: Live Verification Probes */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 space-y-4">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <Play className="h-4 w-4 text-emerald-600" />
          <span>4. Adapter Probing & Sample Generation Tests</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Probe 1: Ping Connection */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-3">
            <div>
              <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                A. Provider Connection Handshake Probe
              </h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Verifies network route to approved endpoint and secret credential reference.
              </p>
            </div>

            <button
              type="button"
              onClick={handleTestConnection}
              disabled={isTestingConn}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 text-xs font-medium transition-colors cursor-pointer flex items-center gap-2"
            >
              <RotateCcw className={`h-3.5 w-3.5 ${isTestingConn ? 'animate-spin' : ''}`} />
              <span>{isTestingConn ? 'Probing Endpoint...' : 'Execute Connection Test'}</span>
            </button>

            {connResult && (
              <div
                className={`p-3 rounded-lg text-xs ${
                  connResult.success
                    ? 'bg-emerald-50 text-emerald-900 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-900'
                    : 'bg-rose-50 text-rose-900 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-200 dark:border-rose-900'
                }`}
              >
                <div className="flex items-center justify-between font-semibold mb-1">
                  <span>{connResult.success ? 'Handshake Succeeded' : 'Handshake Failed'}</span>
                  <span className="font-mono">{connResult.latency_ms}ms</span>
                </div>
                <p>{connResult.message}</p>
              </div>
            )}
          </div>

          {/* Probe 2: Sample Generation */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 space-y-3">
            <div>
              <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                B. Sample Generation & Token Throughput Test
              </h4>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Sends sample prompt through custom LangChain adapter and measures generation velocity.
              </p>
            </div>

            <input
              type="text"
              value={samplePrompt}
              onChange={(e) => setSamplePrompt(e.target.value)}
              className="w-full rounded border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 px-2.5 py-1 text-xs text-slate-800 dark:text-slate-200 focus:outline-none"
              placeholder="Test prompt..."
            />

            <button
              type="button"
              onClick={handleRunSampleProbe}
              disabled={isTestingGen || !samplePrompt.trim()}
              className="px-3.5 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 text-xs font-medium transition-colors cursor-pointer flex items-center gap-2"
            >
              <Play className="h-3.5 w-3.5" />
              <span>{isTestingGen ? 'Generating Tokens...' : 'Run Generation Probe'}</span>
            </button>

            {genResult && (
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs space-y-1.5">
                <div className="flex items-center justify-between text-slate-500 font-mono text-[11px]">
                  <span>Latency: {genResult.latency_ms}ms</span>
                  <span>Throughput: {genResult.tokens_per_second} tok/s</span>
                  <span>Total: {genResult.tokens_generated} tokens</span>
                </div>
                <p className="text-slate-700 dark:text-slate-300 font-mono text-[11px] bg-white dark:bg-slate-900 p-2 rounded border border-slate-100 dark:border-slate-800">
                  {genResult.output}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
