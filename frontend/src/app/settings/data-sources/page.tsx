"use client";

import { useState, useEffect } from "react";
import {
    ArrowLeft,
    Database,
    Check,
    AlertCircle,
    Plus,
    Trash2,
    RefreshCw,
} from "lucide-react";
import Link from "next/link";

interface DataSourceType {
  id: string;
  name: string;
  description: string;
  config_schema: {
    required?: string[];
    properties?: Record<string, { type: string; description: string; default?: any }>;
  };
}

interface ConfiguredDataSource {
  source_id: string;
  source_type: string;
  config: Record<string, any>;
  enabled: boolean;
  sync_interval_minutes?: number;
  last_sync?: string;
  has_config: boolean;
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

export default function DataSourcesPage() {
  const [availableTypes, setAvailableTypes] = useState<DataSourceType[]>([]);
  const [configuredSources, setConfiguredSources] = useState<ConfiguredDataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [expandedSource, setExpandedSource] = useState<string | null>(null);
  const [sourceConfigs, setSourceConfigs] = useState<Record<string, Record<string, string>>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSourceId, setNewSourceId] = useState("");
  const [selectedSourceType, setSelectedSourceType] = useState<string>("");

  useEffect(() => {
    loadDataSources();
  }, []);

  const loadDataSources = async () => {
    try {
      const res = await fetch("/api/providers/data-sources");
      if (res.ok) {
        const data = await res.json();
        setAvailableTypes(data.available_types || []);
        setConfiguredSources(data.configured || []);

        // Initialize configs from configured sources
        const configs: Record<string, Record<string, string>> = {};
        for (const source of data.configured || []) {
          configs[source.source_id] = source.config as Record<string, string>;
        }
        setSourceConfigs(configs);
      }
    } catch (error) {
      console.error("Failed to load data sources:", error);
      setMessage({ type: "error", text: "Failed to load data sources" });
    } finally {
      setLoading(false);
    }
  };

  const getSourceTypeSchema = (typeId: string): DataSourceType | undefined => {
    return availableTypes.find(t => t.id === typeId);
  };

  const getConfigFields = (source: ConfiguredDataSource | null, sourceType: DataSourceType): ConfigField[] => {
    const fields: ConfigField[] = [];
    const schema = sourceType.config_schema.properties || {};
    const required = sourceType.config_schema.required || [];
    const existingConfig = source?.config || {};

    for (const [key, fieldDef] of Object.entries(schema)) {
      const isSecret = key.toLowerCase().includes("key") ||
                      key.toLowerCase().includes("secret") ||
                      key.toLowerCase().includes("token") ||
                      key.toLowerCase().includes("password");

      fields.push({
        key,
        type: fieldDef.type || "string",
        description: fieldDef.description || key,
        default: fieldDef.default,
        required: required.includes(key),
        value: existingConfig[key] || fieldDef.default || "",
        is_secret: isSecret,
      });
    }

    return fields;
  };

  const handleConfigChange = (sourceId: string, key: string, value: string) => {
    setSourceConfigs(prev => ({
      ...prev,
      [sourceId]: {
        ...prev[sourceId],
        [key]: value,
      },
    }));
  };

  const saveDataSource = async (sourceId: string, sourceType: string) => {
    setSaving(true);
    setMessage(null);

    try {
      const res = await fetch("/api/providers/data-sources/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId,
          source_type: sourceType,
          config: sourceConfigs[sourceId] || {},
          enabled: true,
        }),
      });

      if (res.ok) {
        setMessage({ type: "success", text: `Data source "${sourceId}" configured successfully` });
        await loadDataSources();
        setShowAddForm(false);
        setNewSourceId("");
        setSelectedSourceType("");
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

  const syncDataSource = async (sourceId: string) => {
    setSyncing(sourceId);
    setMessage(null);

    try {
      const res = await fetch(`/api/providers/data-sources/${sourceId}/sync`, {
        method: "POST",
      });

      const data = await res.json();
      if (data.success) {
        setMessage({ type: "success", text: data.message || "Sync completed" });
        await loadDataSources();
      } else {
        setMessage({ type: "error", text: data.message || "Sync failed" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Sync failed" });
    } finally {
      setSyncing(null);
    }
  };

  const deleteDataSource = async (sourceId: string) => {
    if (!confirm(`Are you sure you want to delete "${sourceId}"?`)) {
      return;
    }

    setSaving(true);
    setMessage(null);

    try {
      const res = await fetch(`/api/providers/data-sources/${sourceId}`, {
        method: "DELETE",
      });

      if (res.ok) {
        setMessage({ type: "success", text: `Data source "${sourceId}" deleted` });
        await loadDataSources();
      } else {
        setMessage({ type: "error", text: "Failed to delete data source" });
      }
    } catch (error) {
      setMessage({ type: "error", text: "Failed to delete data source" });
    } finally {
      setSaving(false);
    }
  };

  const startAddDataSource = (typeId: string) => {
    setSelectedSourceType(typeId);
    setNewSourceId(`${typeId}_${Date.now()}`);
    setSourceConfigs(prev => ({
      ...prev,
      [`${typeId}_${Date.now()}`]: {},
    }));
    setShowAddForm(true);
  };

  if (loading) {
    return (
      <div className="h-screen bg-void flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-zinc-500 font-mono text-sm animate-pulse">Loading data sources...</p>
        </div>
      </div>
    );
  }

  // Get selected source type schema for add form
  const addFormSchema = selectedSourceType ? getSourceTypeSchema(selectedSourceType) : null;
  const addFormFields = addFormSchema ? getConfigFields(null, addFormSchema) : [];

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
            <div className="p-2 rounded-lg bg-cyan-500/10">
              <Database className="text-cyan-400" size={20} />
            </div>
            <h1 className="text-xl font-bold font-sans tracking-tight">Data Sources</h1>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto p-6 pb-20">

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

        {/* Add New Data Source */}
        <section className="mb-8">
          <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4 font-mono ml-1">
            Add New Data Source
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {availableTypes.map((type) => (
              <button
                key={type.id}
                onClick={() => startAddDataSource(type.id)}
                className="p-4 bg-white/[0.03] border border-white/5 rounded-xl hover:border-cyan-500/30 hover:bg-white/[0.05] transition-all text-left group"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-cyan-500/10 group-hover:bg-cyan-500/20 transition-colors">
                    <Database size={18} className="text-cyan-400" />
                  </div>
                  <div className="flex-1">
                    <div className="font-medium text-zinc-200">{type.name}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">{type.description}</div>
                  </div>
                  <Plus size={16} className="text-zinc-600 group-hover:text-cyan-400 transition-colors" />
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Add Form (shown when adding) */}
        {showAddForm && addFormSchema && (
          <section className="mb-8 p-5 bg-cyan-500/5 border border-cyan-500/20 rounded-2xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-medium text-cyan-300">Configure {addFormSchema.name}</h3>
                <p className="text-xs text-zinc-500 mt-0.5">{addFormSchema.description}</p>
              </div>
              <button
                onClick={() => {
                  setShowAddForm(false);
                  setNewSourceId("");
                  setSelectedSourceType("");
                }}
                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white"
              >
                <Plus size={18} className="rotate-45" />
              </button>
            </div>

            {/* Source ID */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                Source ID
              </label>
              <input
                type="text"
                value={newSourceId}
                onChange={(e) => setNewSourceId(e.target.value)}
                placeholder="my-email-account"
                className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-cyan-500/50 text-zinc-200 placeholder-zinc-600"
              />
            </div>

            {/* Config Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {addFormFields.map((field) => (
                <div key={field.key}>
                  <label className="block text-sm font-medium text-zinc-300 mb-1.5">
                    {field.description}
                    {field.required && <span className="text-red-400 ml-1">*</span>}
                  </label>
                  {field.is_secret ? (
                    <input
                      type="password"
                      value={field.value}
                      onChange={(e) => handleConfigChange(newSourceId, field.key, e.target.value)}
                      placeholder={field.default || ""}
                      className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-cyan-500/50 text-zinc-200 placeholder-zinc-600"
                    />
                  ) : (
                    <input
                      type="text"
                      value={field.value}
                      onChange={(e) => handleConfigChange(newSourceId, field.key, e.target.value)}
                      placeholder={field.default || ""}
                      className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-cyan-500/50 text-zinc-200 placeholder-zinc-600"
                    />
                  )}
                </div>
              ))}
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={() => saveDataSource(newSourceId, selectedSourceType)}
                disabled={saving || !newSourceId.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium transition-all disabled:opacity-50"
              >
                <Check size={16} />
                Save Data Source
              </button>
              <button
                onClick={() => {
                  setShowAddForm(false);
                  setNewSourceId("");
                  setSelectedSourceType("");
                }}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 rounded-lg font-medium transition-all"
              >
                Cancel
              </button>
            </div>
          </section>
        )}

        {/* Configured Data Sources */}
        {configuredSources.length > 0 && (
          <section>
            <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4 font-mono ml-1">
              Configured Data Sources
            </h2>
            <div className="space-y-4">
              {configuredSources.map((source) => {
                const isExpanded = expandedSource === source.source_id;
                const typeSchema = getSourceTypeSchema(source.source_type);
                const fields = typeSchema ? getConfigFields(source, typeSchema) : [];

                return (
                  <div
                    key={source.source_id}
                    className="bg-white/[0.03] border border-white/5 rounded-2xl overflow-hidden hover:border-cyan-500/30 transition-all duration-300"
                  >
                    {/* Source Header */}
                    <button
                      onClick={() => setExpandedSource(isExpanded ? null : source.source_id)}
                      className="w-full p-5 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                          source.enabled ? "bg-cyan-500/20 text-cyan-400" : "bg-white/5 text-zinc-600"
                        }`}>
                          <Database size={20} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-zinc-200">{source.source_id}</h3>
                            <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                              {typeSchema?.name || source.source_type}
                            </span>
                            {source.enabled && (
                              <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                Active
                              </span>
                            )}
                          </div>
                          {source.last_sync && (
                            <p className="text-xs text-zinc-500 mt-0.5">
                              Last sync: {new Date(source.last_sync).toLocaleString()}
                            </p>
                          )}
                        </div>
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
                                  onChange={(e) => handleConfigChange(source.source_id, field.key, e.target.value)}
                                  placeholder={field.default || ""}
                                  className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-cyan-500/50 text-zinc-200 placeholder-zinc-600"
                                />
                              ) : (
                                <input
                                  type="text"
                                  value={field.value}
                                  onChange={(e) => handleConfigChange(source.source_id, field.key, e.target.value)}
                                  placeholder={field.default || ""}
                                  className="w-full px-3 py-2 bg-black/30 border border-white/10 rounded-lg focus:outline-none focus:border-cyan-500/50 text-zinc-200 placeholder-zinc-600"
                                />
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Actions */}
                        <div className="flex flex-wrap gap-3 pt-2 border-t border-white/5">
                          <button
                            onClick={() => saveDataSource(source.source_id, source.source_type)}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                          >
                            <Check size={16} />
                            Save Changes
                          </button>
                          <button
                            onClick={() => syncDataSource(source.source_id)}
                            disabled={syncing === source.source_id || saving}
                            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 rounded-lg font-medium transition-all disabled:opacity-50"
                          >
                            {syncing === source.source_id ? (
                              <>
                                <div className="w-4 h-4 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
                                Syncing...
                              </>
                            ) : (
                              <>
                                <RefreshCw size={16} />
                                Sync Now
                              </>
                            )}
                          </button>
                          <button
                            onClick={() => deleteDataSource(source.source_id)}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg font-medium transition-all disabled:opacity-50 ml-auto"
                          >
                            <Trash2 size={16} />
                            Delete
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Info Section */}
        <section className="mt-10 p-6 bg-white/[0.02] border border-white/5 rounded-xl">
          <h3 className="text-sm font-medium text-zinc-300 mb-3">About Data Sources</h3>
          <div className="text-xs text-zinc-500 space-y-2">
            <p>• Connect external data sources to expand my knowledge and context</p>
            <p>• Data is indexed and made searchable for intelligent retrieval</p>
            <p>• Sync intervals determine how often I check for new data</p>
            <p>• <strong>Privacy:</strong> Your data is processed locally and only used for context - never shared</p>
          </div>
        </section>
      </div>
    </div>
  );
}
