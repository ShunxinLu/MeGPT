"use client";

import { useState, useEffect } from "react";
import {
    ArrowLeft,
    Server,
    Check,
    AlertCircle,
    Zap,
    Key,
    Star,
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

interface ConfigField {
  key: string;
  type: string;
  description: string;
  default?: any;
  required: boolean;
  value: string;
  is_secret: boolean;
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [providerConfigs, setProviderConfigs] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    try {
      const res = await fetch("/api/providers/list");
      if (res.ok) {
        const data: ProvidersResponse = await res.json();
        setProviders(data.available);
        setActiveProvider(data.active);

        // Initialize provider configs from available
        const configs: Record<string, Record<string, string>> = {};
        for (const provider of data.available) {
          if (provider.has_config) {
            // Load actual config for each provider
            try {
              const configRes = await fetch(`/api/providers/default`);
              if (configRes.ok) {
                const defaultData = await configRes.json();
                if (defaultData.provider_id === provider.id) {
                  configs[provider.id] = defaultData.config as Record<string, string>;
                }
              }
            } catch {
              // Skip if can't load config
            }
          }
        }
        setProviderConfigs(configs);
      }
    } catch (error) {
      console.error("Failed to load providers:", error);
      setMessage({ type: "error", text: "Failed to load providers" });
    } finally {
      setLoading(false);
    }
  };

  const getConfigFields = (provider: ProviderInfo): ConfigField[] => {
    const fields: ConfigField[] = [];
    const schema = provider.config_schema.properties || {};
    const required = provider.config_schema.required || [];

    for (const [key, fieldDef] of Object.entries(schema)) {
      const isSecret = key.toLowerCase().includes("key") ||
                      key.toLowerCase().includes("secret") ||
                      key.toLowerCase().includes("token") ||
                      key.toLowerCase().includes("password") ||
                      key.toLowerCase().includes("api_key");

      fields.push({
        key,
        type: fieldDef.type || "string",
        description: fieldDef.description || key,
        default: fieldDef.default,
        required: required.includes(key),
        value: providerConfigs[provider.id]?.[key] || fieldDef.default || "",
        is_secret: isSecret,
      });
    }

    return fields;
  };

  const handleConfigChange = (providerId: string, key: string, value: string) => {
    setProviderConfigs(prev => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        [key]: value,
      },
    }));
  };

  const saveProvider = async (providerId: string) => {
    setSaving(true);
    setMessage(null);

    try {
      const res = await fetch("/api/providers/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          config: providerConfigs[providerId] || {},
          enabled: true,
        }),
      });

      if (res.ok) {
        setMessage({ type: "success", text: `${providers.find(p => p.id === providerId)?.name || providerId} configured successfully` });
        await loadProviders();
      } else {
        const error = await res.json();
        setMessage({ type: "error", text: error.detail || "Failed to save configuration" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Failed to save configuration" });
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async (providerId: string) => {
    setTesting(providerId);
    setMessage(null);

    try {
      const res = await fetch("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: providerId,
          config: providerConfigs[providerId],
        }),
      });

      const data = await res.json();
      if (data.success) {
        setMessage({ type: "success", text: `Connection to ${providers.find(p => p.id === providerId)?.name} successful!` });
      } else {
        setMessage({ type: "error", text: data.message || "Connection test failed" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Connection test failed" });
    } finally {
      setTesting(null);
    }
  };

  const setAsDefault = async (providerId: string) => {
    setSaving(true);
    setMessage(null);

    try {
      const res = await fetch("/api/providers/set-default", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider_id: providerId }),
      });

      if (res.ok) {
        setMessage({ type: "success", text: `${providers.find(p => p.id === providerId)?.name} set as default` });
        await loadProviders();
      } else {
        setMessage({ type: "error", text: "Failed to set default provider" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Failed to set default provider" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="h-screen bg-void flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-zinc-500 font-mono text-sm animate-pulse">Loading providers...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen overflow-y-auto bg-void text-white relative">
      {/* Background Texture */}
      <div className="fixed inset-0 bg-noise opacity-[0.03] pointer-events-none"></div>

      {/* Header */}
      <div className="sticky top-0 z-10 border-b border-white/5 bg-black/80 backdrop-blur-xl p-4">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <Link
            href="/"
            className="p-2 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white"
          >
            <ArrowLeft size={20} />
          </Link>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-violet-500/10">
              <Zap className="text-violet-400" size={20} />
            </div>
            <h1 className="text-xl font-bold font-sans tracking-tight">LLM Providers</h1>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto p-6 pb-20">

        {/* Active Provider Indicator */}
        <section className="mb-8">
          <div className="flex items-center justify-between mb-4 px-1">
            <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 font-mono">Active Provider</h2>
          </div>
          {activeProvider ? (
            <div className="bg-violet-500/10 border border-violet-500/20 rounded-xl p-4 flex items-center gap-4">
              <Server size={20} className="text-violet-400" />
              <div>
                <div className="font-medium text-violet-300">{providers.find(p => p.id === activeProvider)?.name}</div>
                <div className="text-xs text-zinc-400 font-mono mt-0.5">{activeProvider}</div>
              </div>
            </div>
          ) : (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex items-center gap-4">
              <AlertCircle size={20} className="text-amber-400" />
              <div className="text-amber-300">No provider configured. Add a provider below.</div>
            </div>
          )}
        </section>

        {/* Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-xl flex items-center gap-3 border ${message.type === "success"
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
            : "bg-red-500/10 border-red-500/20 text-red-400"
          }`}>
            {message.type === "success" ? <Check size={18} /> : <AlertCircle size={18} />}
            <span className="font-medium text-sm">{message.text}</span>
          </div>
        )}

        {/* Providers List */}
        <section>
          <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4 font-mono ml-1">
            Available Providers
          </h2>
          <div className="space-y-4">
            {providers.map((provider) => {
              const isExpanded = expandedProvider === provider.id;
              const fields = getConfigFields(provider);
              const hasRequiredConfig = fields.filter(f => f.required && !f.value).length === 0;

              return (
                <div
                  key={provider.id}
                  className="bg-white/[0.03] border border-white/5 rounded-2xl overflow-hidden hover:border-violet-500/30 transition-all duration-300"
                >
                  {/* Provider Header */}
                  <button
                    onClick={() => setExpandedProvider(isExpanded ? null : provider.id)}
                    className="w-full p-5 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                        provider.enabled ? "bg-violet-500/20 text-violet-400" : "bg-white/5 text-zinc-600"
                      }`}>
                        <Server size={20} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-zinc-200">{provider.name}</h3>
                          {provider.is_default && (
                            <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-violet-500/20 text-violet-300 border border-violet-500/30">
                              Default
                            </span>
                          )}
                          {provider.enabled && (
                            <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-zinc-500 mt-0.5">{provider.description}</p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-zinc-600">
                          <span>Context: {provider.max_context.toLocaleString()} tokens</span>
                          <span>•</span>
                          <span>{provider.supports_streaming ? "Streaming" : "No streaming"}</span>
                          <span>•</span>
                          <span>{provider.available_models[0]} model</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {provider.has_config ? (
                        <Key size={14} className="text-emerald-400" />
                      ) : (
                        <AlertCircle size={14} className="text-zinc-600" />
                      )}
                    </div>
                  </button>

                  {/* Expanded Config */}
                  {isExpanded && (
                    <div className="border-t border-white/5 p-5 space-y-4">
                      {/* Config Fields */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {fields.map((field) => (
                          <div key={field.key}>
                            <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                              {field.description}
                              {field.required && <span className="text-red-400 ml-1">*</span>}
                            </label>
                            {field.is_secret ? (
                              <input
                                type="password"
                                value={field.value}
                                onChange={(e) => handleConfigChange(provider.id, field.key, e.target.value)}
                                placeholder={field.default || ""}
                                className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-violet-500/50 text-zinc-200 placeholder-zinc-600"
                              />
                            ) : field.type === "select" ? (
                              <select
                                value={field.value}
                                onChange={(e) => handleConfigChange(provider.id, field.key, e.target.value)}
                                className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-violet-500/50 text-zinc-200"
                              >
                                {provider.available_models.map((model: string) => (
                                  <option key={model} value={model}>{model}</option>
                                ))}
                              </select>
                            ) : (
                              <input
                                type="text"
                                value={field.value}
                                onChange={(e) => handleConfigChange(provider.id, field.key, e.target.value)}
                                placeholder={field.default || ""}
                                className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-violet-500/50 text-zinc-200 placeholder-zinc-600"
                              />
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Actions */}
                      <div className="flex flex-wrap gap-3 pt-2 border-t border-white/5">
                        <button
                          onClick={() => saveProvider(provider.id)}
                          disabled={saving}
                          className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                        >
                          <Check size={16} />
                          Save Configuration
                        </button>
                        <button
                          onClick={() => testConnection(provider.id)}
                          disabled={testing === provider.id || saving}
                          className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 rounded-lg font-medium transition-all disabled:opacity-50"
                        >
                          {testing === provider.id ? (
                            <>
                              <div className="w-4 h-4 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
                              Testing...
                            </>
                          ) : (
                            <>
                              <Server size={16} />
                              Test Connection
                            </>
                          )}
                        </button>
                        {!provider.is_default && (
                          <button
                            onClick={() => setAsDefault(provider.id)}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 rounded-lg font-medium transition-all disabled:opacity-50"
                          >
                            <Star size={16} />
                            Set as Default
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Info Section */}
        <section className="mt-10 p-6 bg-white/[0.02] border border-white/5 rounded-xl">
          <h3 className="text-sm font-medium text-zinc-300 mb-3">About Provider Configuration</h3>
          <div className="text-xs text-zinc-500 space-y-2">
            <p>• Configure API keys and settings for your preferred LLM providers</p>
            <p>• Providers can be configured here or via environment variables (see documentation)</p>
            <p>• Your API keys are stored locally and only sent to the respective provider's API</p>
            <p>• <strong>Privacy:</strong> No data is sent to any third-party services except the configured providers</p>
          </div>
        </section>
      </div>
    </div>
  );
}
