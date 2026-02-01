"use client";

import { useState, useEffect } from "react";
import {
  ArrowLeft,
  Server,
  Check,
  X,
  Plus,
  Settings2,
  Zap,
  Star,
  Database,
  Mail,
} from "lucide-react";
import Link from "next/link";

interface ProviderInfo {
  id: string;
  name: string;
  description: string;
  config_schema: {
    required?: string[];
    properties?: Record<string, { type: string; description: string; default?: any }>;
  };
  supports_streaming: boolean;
  supports_tools: boolean;
  max_context: number;
  default_model: string;
  available_models: string[];
  enabled: boolean;
  has_config: boolean;
  is_default: boolean;
}

interface ProvidersResponse {
  available: ProviderInfo[];
  active: string | null;
}

interface EmbeddingProviderInfo {
  id: string;
  name: string;
  description: string;
  default_model: string;
  available_models: string[];
  enabled: boolean;
  has_config: boolean;
  is_default: boolean;
  current_model?: string;
}

interface EmbeddingProvidersResponse {
  available: EmbeddingProviderInfo[];
  active: string | null;
}

interface EmailClassificationConfig {
  provider_id: string;
  model: string;
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Embedding providers state
  const [embeddingProviders, setEmbeddingProviders] = useState<EmbeddingProviderInfo[]>([]);
  const [activeEmbeddingProvider, setActiveEmbeddingProvider] = useState<string | null>(null);
  const [activeEmbeddingModel, setActiveEmbeddingModel] = useState<string>("");
  const [showEmbeddingModal, setShowEmbeddingModal] = useState<string | null>(null);
  const [embedApiKeyInput, setEmbedApiKeyInput] = useState("");
  const [embedBaseUrlInput, setEmbedBaseUrlInput] = useState("");

  // Email classification state
  const [emailClassificationConfig, setEmailClassificationConfig] = useState<EmailClassificationConfig | null>(null);
  const [emailClassificationModel, setEmailClassificationModel] = useState<string>("");
  const [loadingEmailConfig, setLoadingEmailConfig] = useState(false);

  // Modal state
  const [showConnectModal, setShowConnectModal] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [baseUrlInput, setBaseUrlInput] = useState("");

  useEffect(() => {
    loadProviders();
    loadEmbeddingProviders();
    loadEmailClassificationConfig();
  }, []);

  const loadProviders = async () => {
    try {
      const res = await fetch("/api/providers/list");
      if (res.ok) {
        const data: ProvidersResponse = await res.json();
        console.log("Loaded providers:", data.available);
        console.log("Provider count:", data.available?.length);
        setProviders(data.available);
        setActiveProvider(data.active);

        // Set active model from active provider
        const active = data.available.find(p => p.id === data.active);
        if (active && active.available_models.length > 0) {
          setActiveModel(active.available_models[0]);
        }
      } else {
        console.error("API response not OK:", res.status);
      }
    } catch (error) {
      console.error("Failed to load providers:", error);
      setMessage({ type: "error", text: "Failed to load providers" });
    } finally {
      setLoading(false);
    }
  };

  // Load email classification configuration
  const loadEmailClassificationConfig = async () => {
    setLoadingEmailConfig(true);
    try {
      const res = await fetch("/api/email/config/classification");
      if (res.ok) {
        const data: EmailClassificationConfig = await res.json();
        setEmailClassificationConfig(data);
        setEmailClassificationModel(data.model || "");
      }
    } catch (error) {
      console.error("Failed to load email classification config:", error);
    } finally {
      setLoadingEmailConfig(false);
    }
  };

  // Get all available models from CONNECTED providers only
  const getAllModels = () => {
    const models: { provider: string; model: string; providerName: string }[] = [];
    for (const provider of providers) {
      // Only show models from connected providers
      const connected = isProviderConnected(provider);
      if (connected && provider.available_models && provider.available_models.length > 0) {
        for (const model of provider.available_models) {
          models.push({
            provider: provider.id,
            model,
            providerName: provider.name,
          });
        }
      }
    }
    return models;
  };

  const handleModelChange = async (value: string) => {
    const [providerId, model] = value.split("::");
    const provider = providers.find(p => p.id === providerId);

    if (!provider) return;

    // Check if provider is connected
    const connected = isProviderConnected(provider);

    if (!connected) {
      // Provider not connected - prompt to connect
      setMessage({
        type: "error",
        text: `Please connect ${provider.name} first to use ${model}`
      });
      setShowConnectModal(providerId);
      return;
    }

    // Provider is connected - switch model
    setActiveModel(model);
    setSaving(true);
    setMessage(null);

    try {
      // Set the provider as default and update the model
      await fetch("/api/providers/set-default", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId, model }),
      });
      setActiveProvider(providerId);
      setMessage({ type: "success", text: `Switched to ${model}` });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: "error", text: "Failed to switch model" });
    } finally {
      setSaving(false);
    }
  };

  const connectProvider = async (providerId: string) => {
    setSaving(true);
    setMessage(null);

    try {
      const config: Record<string, string> = {};
      if (apiKeyInput) config.api_key = apiKeyInput;
      if (baseUrlInput) config.base_url = baseUrlInput;

      const res = await fetch("/api/providers/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          config,
          enabled: true,
        }),
      });

      if (res.ok) {
        setMessage({ type: "success", text: `${providerId} connected successfully!` });
        setShowConnectModal(null);
        setApiKeyInput("");
        setBaseUrlInput("");
        await loadProviders();
      } else {
        const error = await res.json();
        setMessage({ type: "error", text: error.detail || "Failed to connect" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Failed to connect provider" });
    } finally {
      setSaving(false);
    }
  };

  const disconnectProvider = async (providerId: string) => {
    setSaving(true);
    try {
      await fetch("/api/providers/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          config: {},
          enabled: false,
        }),
      });
      setMessage({ type: "success", text: `${providerId} disconnected` });
      await loadProviders();
    } catch (error) {
      setMessage({ type: "error", text: "Failed to disconnect" });
    } finally {
      setSaving(false);
    }
  };

  const isProviderConnected = (provider: ProviderInfo) => {
    // Provider is connected if it has configuration saved
    return provider.has_config === true;
  };

  // ========== Embedding Providers ==========
  const loadEmbeddingProviders = async () => {
    try {
      const res = await fetch("/api/providers/embedding");
      if (res.ok) {
        const data: EmbeddingProvidersResponse = await res.json();
        setEmbeddingProviders(data.available);
        setActiveEmbeddingProvider(data.active);
      }
    } catch (error) {
      console.error("Failed to load embedding providers:", error);
    }
  };

  const handleEmbeddingConnect = async (providerId: string) => {
    setSaving(true);
    setMessage(null);
    try {
      const config: Record<string, string> = {};
      if (embedApiKeyInput) config.api_key = embedApiKeyInput;
      if (embedBaseUrlInput) config.base_url = embedBaseUrlInput;

      const res = await fetch("/api/providers/embedding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          config,
          enabled: true,
          is_default: false,
        }),
      });

      if (res.ok) {
        setMessage({ type: "success", text: `Embedding provider connected!` });
        setShowEmbeddingModal(null);
        setEmbedApiKeyInput("");
        setEmbedBaseUrlInput("");
        await loadEmbeddingProviders();
      } else {
        const error = await res.json();
        setMessage({ type: "error", text: error.detail || "Failed to connect" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Failed to connect embedding provider" });
    } finally {
      setSaving(false);
    }
  };

  const handleEmbeddingModelChange = async (providerId: string, model: string) => {
    const provider = embeddingProviders.find(p => p.id === providerId);
    if (!provider || !provider.has_config) {
      setMessage({ type: "error", text: "Please connect the embedding provider first" });
      setShowEmbeddingModal(providerId);
      return;
    }

    setSaving(true);
    try {
      await fetch("/api/providers/embedding/set-default", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId }),
      });
      setActiveEmbeddingProvider(providerId);
      setActiveEmbeddingModel(model);
      setMessage({ type: "success", text: `Switched to ${model}` });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: "error", text: "Failed to switch embedding model" });
    } finally {
      setSaving(false);
    }
  };

  // Email Classification Model Handler
  const handleEmailClassificationModelChange = async (value: string) => {
    const [providerId, model] = value.split("::");
    const provider = providers.find(p => p.id === providerId);

    if (!provider) return;

    const connected = isProviderConnected(provider);
    if (!connected) {
      setMessage({
        type: "error",
        text: `Please connect ${provider.name} first to use ${model} for email classification`
      });
      setShowConnectModal(providerId);
      return;
    }

    setSaving(true);
    setMessage(null);

    try {
      await fetch("/api/email/config/classification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          model,
        }),
      });
      setEmailClassificationConfig({ provider_id: providerId, model });
      setEmailClassificationModel(model);
      setMessage({ type: "success", text: `Email classification: ${model}` });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      setMessage({ type: "error", text: "Failed to set email classification model" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const allModels = getAllModels();

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 p-6 pt-24">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <Link
            href="/settings"
            className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-zinc-400" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white">LLM Providers</h1>
            <p className="text-zinc-400">Connect providers and select your model</p>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-3 ${message.type === "success"
            ? "bg-green-500/10 border border-green-500/20 text-green-400"
            : "bg-red-500/10 border border-red-500/20 text-red-400"
            }`}>
            {message.type === "success" ? <Check className="w-5 h-5" /> : <X className="w-5 h-5" />}
            {message.text}
          </div>
        )}

        {/* Active Model Selector */}
        <div className="mb-8 p-6 rounded-2xl bg-gradient-to-br from-violet-500/10 to-violet-500/5 border border-violet-500/20">
          <div className="flex items-center gap-3 mb-4">
            <Zap className="w-6 h-6 text-violet-400" />
            <h2 className="text-lg font-semibold text-white">Active Model</h2>
          </div>

          {allModels.length > 0 ? (
            <select
              value={`${activeProvider}::${activeModel}`}
              onChange={(e) => handleModelChange(e.target.value)}
              disabled={saving}
              className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white text-lg focus:outline-none focus:border-violet-500/50 disabled:opacity-50"
            >
              {allModels.map(({ provider, model, providerName }) => (
                <option key={`${provider}::${model}`} value={`${provider}::${model}`}>
                  {model} ({providerName})
                </option>
              ))}
            </select>
          ) : (
            <p className="text-zinc-500 italic">No models available. Connect a provider below.</p>
          )}
        </div>

        {/* Provider Cards */}
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <Server className="w-5 h-5 text-zinc-400" />
          Available Providers ({providers.length})
        </h2>

        <div className="grid gap-4">
          {providers.map((provider) => {
            const connected = isProviderConnected(provider);
            const isLocal = provider.id === "lmstudio" || provider.id === "ollama";

            return (
              <div
                key={provider.id}
                className={`p-5 rounded-xl border transition-all ${connected
                  ? "bg-zinc-900/50 border-green-500/30"
                  : "bg-zinc-900/30 border-white/5 hover:border-white/10"
                  }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {/* Status indicator */}
                    <div className={`w-3 h-3 rounded-full ${connected ? "bg-green-500" : "bg-zinc-600"}`} />

                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-white">{provider.name}</h3>
                        {provider.id === activeProvider && (
                          <span className="px-2 py-0.5 text-xs bg-violet-500/20 text-violet-300 rounded-full flex items-center gap-1">
                            <Star className="w-3 h-3" /> Active
                          </span>
                        )}
                        {isLocal && (
                          <span className="px-2 py-0.5 text-xs bg-zinc-700 text-zinc-300 rounded-full">
                            Local
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-zinc-500 mt-0.5">
                        {connected
                          ? `${provider.available_models.length} model${provider.available_models.length !== 1 ? 's' : ''} available`
                          : provider.description
                        }
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {connected ? (
                      <>
                        {!isLocal && (
                          <button
                            onClick={() => setShowConnectModal(provider.id)}
                            className="px-3 py-1.5 text-sm text-zinc-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors flex items-center gap-1.5"
                          >
                            <Settings2 className="w-4 h-4" />
                            Edit
                          </button>
                        )}
                        {!isLocal && (
                          <button
                            onClick={() => disconnectProvider(provider.id)}
                            className="px-3 py-1.5 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"
                          >
                            Disconnect
                          </button>
                        )}
                      </>
                    ) : (
                      <button
                        onClick={() => setShowConnectModal(provider.id)}
                        className="px-4 py-2 bg-violet-500/20 text-violet-300 hover:bg-violet-500/30 rounded-lg transition-colors flex items-center gap-2"
                      >
                        <Plus className="w-4 h-4" />
                        Connect
                      </button>
                    )}
                  </div>
                </div>

                {/* Models preview for connected providers */}
                {connected && provider.available_models.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {provider.available_models.slice(0, 5).map((model) => (
                      <span
                        key={model}
                        className="px-2.5 py-1 text-xs bg-white/5 text-zinc-400 rounded-md"
                      >
                        {model}
                      </span>
                    ))}
                    {provider.available_models.length > 5 && (
                      <span className="px-2.5 py-1 text-xs text-zinc-500">
                        +{provider.available_models.length - 5} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Embedding Providers Section */}
        <h2 className="text-lg font-semibold text-white mb-4 mt-10 flex items-center gap-2">
          <Database className="w-5 h-5 text-cyan-400" />
          Embedding Providers ({embeddingProviders.length})
        </h2>
        <p className="text-zinc-500 text-sm mb-4 -mt-3">For vector search and memory retrieval</p>

        <div className="grid gap-4">
          {embeddingProviders.map((provider) => {
            const connected = provider.has_config === true;
            const isDefault = provider.is_default === true;

            return (
              <div
                key={provider.id}
                className={`p-5 rounded-xl border transition-all ${isDefault
                  ? "bg-cyan-950/30 border-cyan-500/30"
                  : connected
                  ? "bg-zinc-900/50 border-green-500/30"
                  : "bg-zinc-900/30 border-white/5 hover:border-white/10"
                  }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-3 h-3 rounded-full ${connected ? "bg-green-500" : "bg-zinc-600"}`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-white">{provider.name}</h3>
                        {isDefault && (
                          <span className="px-2 py-0.5 text-xs bg-cyan-500/20 text-cyan-300 rounded-full flex items-center gap-1">
                            <Star className="w-3 h-3" /> Active
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-zinc-500 mt-0.5">
                        {connected
                          ? `${provider.available_models.length} model${provider.available_models.length !== 1 ? 's' : ''} available`
                          : provider.description
                        }
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {connected && provider.available_models.length > 0 && (
                      <select
                        value={provider.current_model || provider.available_models[0]}
                        onChange={(e) => handleEmbeddingModelChange(provider.id, e.target.value)}
                        disabled={saving}
                        className="px-3 py-1.5 text-sm bg-black/40 border border-white/10 rounded-lg text-zinc-300 focus:outline-none focus:border-cyan-500/50 disabled:opacity-50"
                      >
                        {provider.available_models.map((model) => (
                          <option key={model} value={model}>{model}</option>
                        ))}
                      </select>
                    )}
                    {connected ? (
                      <button
                        onClick={() => setShowEmbeddingModal(provider.id)}
                        className="px-3 py-1.5 text-sm text-zinc-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
                      >
                        Edit
                      </button>
                    ) : (
                      <button
                        onClick={() => setShowEmbeddingModal(provider.id)}
                        className="px-4 py-2 bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 rounded-lg transition-colors flex items-center gap-2"
                      >
                        <Plus className="w-4 h-4" />
                        Connect
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Email Classification Section */}
        <h2 className="text-lg font-semibold text-white mb-4 mt-10 flex items-center gap-2">
          <Mail className="w-5 h-5 text-amber-400" />
          Email Classification Model
        </h2>
        <p className="text-zinc-500 text-sm mb-4 -mt-3">Separate model for processing emails (priority, summaries, action items)</p>

        <div className="p-6 rounded-2xl bg-gradient-to-br from-amber-500/10 to-amber-500/5 border border-amber-500/20">
          <div className="flex items-center gap-3 mb-4">
            <Mail className="w-6 h-6 text-amber-400" />
            <h3 className="text-lg font-semibold text-white">Email Processing Model</h3>
          </div>

          {allModels.length > 0 ? (
            <div className="space-y-3">
              <select
                value={emailClassificationConfig ? `${emailClassificationConfig.provider_id}::${emailClassificationModel}` : ""}
                onChange={(e) => handleEmailClassificationModelChange(e.target.value)}
                disabled={saving || loadingEmailConfig}
                className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white focus:outline-none focus:border-amber-500/50 disabled:opacity-50"
              >
                <option value="">Select a model for email classification...</option>
                {allModels.map(({ provider, model, providerName }) => (
                  <option key={`email-${provider}::${model}`} value={`${provider}::${model}`}>
                    {model} ({providerName})
                  </option>
                ))}
              </select>
              <p className="text-sm text-zinc-500">
                This model will be used to classify email priority, extract summaries, and identify action items.
                You can use a different model than your chat model - a local model is recommended for privacy.
              </p>
              {emailClassificationConfig && (
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <Check className="w-4 h-4" />
                  Current: {emailClassificationModel} (from {providers.find(p => p.id === emailClassificationConfig.provider_id)?.name || "Unknown"})
                </div>
              )}
            </div>
          ) : (
            <p className="text-zinc-500 italic">No models available. Connect a provider above.</p>
          )}
        </div>

        {/* Embedding Connect Modal */}
        {showEmbeddingModal && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl">
              <h3 className="text-xl font-bold text-white mb-4">
                Connect {embeddingProviders.find(p => p.id === showEmbeddingModal)?.name}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-zinc-400 mb-2">API Key (optional for local)</label>
                  <input
                    type="password"
                    value={embedApiKeyInput}
                    onChange={(e) => setEmbedApiKeyInput(e.target.value)}
                    placeholder="sk-..."
                    className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white placeholder-zinc-600 focus:outline-none focus:border-cyan-500/50"
                  />
                </div>

                {["openai", "ollama", "lmstudio"].includes(showEmbeddingModal || "") && (
                  <div>
                    <label className="block text-sm text-zinc-400 mb-2">
                      Base URL <span className="text-zinc-600">(optional for local)</span>
                    </label>
                    <input
                      type="text"
                      value={embedBaseUrlInput}
                      onChange={(e) => setEmbedBaseUrlInput(e.target.value)}
                      placeholder="http://localhost:1234"
                      className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white placeholder-zinc-600 focus:outline-none focus:border-cyan-500/50"
                    />
                  </div>
                )}
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => {
                    setShowEmbeddingModal(null);
                    setEmbedApiKeyInput("");
                    setEmbedBaseUrlInput("");
                  }}
                  className="flex-1 px-4 py-3 bg-white/5 text-zinc-300 hover:bg-white/10 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => showEmbeddingModal && handleEmbeddingConnect(showEmbeddingModal)}
                  disabled={saving}
                  className="flex-1 px-4 py-3 bg-cyan-500 text-white hover:bg-cyan-600 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {saving ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      <Check className="w-5 h-5" />
                      Connect
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Connect Modal */}
        {showConnectModal && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-md mx-4 shadow-2xl">
              <h3 className="text-xl font-bold text-white mb-4">
                Connect {providers.find(p => p.id === showConnectModal)?.name}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-zinc-400 mb-2">API Key</label>
                  <input
                    type="password"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder="sk-..."
                    className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500/50"
                  />
                </div>

                {/* Base URL for providers that support it */}
                {["openai", "ollama", "lmstudio"].includes(showConnectModal) && (
                  <div>
                    <label className="block text-sm text-zinc-400 mb-2">
                      Base URL <span className="text-zinc-600">(optional)</span>
                    </label>
                    <input
                      type="text"
                      value={baseUrlInput}
                      onChange={(e) => setBaseUrlInput(e.target.value)}
                      placeholder="https://api.openai.com/v1"
                      className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500/50"
                    />
                  </div>
                )}
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => {
                    setShowConnectModal(null);
                    setApiKeyInput("");
                    setBaseUrlInput("");
                  }}
                  className="flex-1 px-4 py-3 bg-white/5 text-zinc-300 hover:bg-white/10 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => connectProvider(showConnectModal)}
                  disabled={saving || !apiKeyInput}
                  className="flex-1 px-4 py-3 bg-violet-500 text-white hover:bg-violet-600 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {saving ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      <Check className="w-5 h-5" />
                      Connect
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
