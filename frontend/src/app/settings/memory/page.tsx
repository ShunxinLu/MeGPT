"use client";

import { useState, useEffect } from "react";
import { ArrowLeft, Trash2, Brain, Search, AlertCircle } from "lucide-react";
import Link from "next/link";

interface Memory {
    id: string;
    memory: string;
    created_at?: string;
    metadata?: Record<string, unknown>;
}

export default function MemoryManager() {
    const [memories, setMemories] = useState<Memory[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [deletingId, setDeletingId] = useState<string | null>(null);

    useEffect(() => {
        loadMemories();
    }, []);

    const loadMemories = async () => {
        try {
            const res = await fetch("/api/memories");
            if (res.ok) {
                const data = await res.json();
                setMemories(data);
            } else {
                setError("Failed to load memories");
            }
        } catch (err) {
            setError("Failed to connect to server");
        } finally {
            setIsLoading(false);
        }
    };

    const deleteMemory = async (id: string) => {
        setDeletingId(id);
        try {
            const res = await fetch(`/api/memories/${id}`, { method: "DELETE" });
            if (res.ok) {
                setMemories(memories.filter(m => m.id !== id));
            } else {
                setError("Failed to delete memory");
            }
        } catch (err) {
            setError("Failed to delete memory");
        } finally {
            setDeletingId(null);
        }
    };

    const filteredMemories = memories.filter(m =>
        m.memory.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="h-screen overflow-y-auto bg-void text-white relative">
            {/* Background Texture */}
            <div className="fixed inset-0 bg-noise opacity-[0.03] pointer-events-none"></div>

            {/* Header */}
            <div className="sticky top-0 z-10 border-b border-white/5 bg-black/80 backdrop-blur-xl p-4">
                <div className="max-w-4xl mx-auto flex items-center gap-4">
                    <Link
                        href="/"
                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white"
                    >
                        <ArrowLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-violet-500/10">
                            <Brain className="text-violet-400" size={20} />
                        </div>
                        <h1 className="text-xl font-bold font-sans tracking-tight">Memory Manager</h1>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-4xl mx-auto p-6 pb-20">
                {/* Description */}
                <div className="bg-white/5 border border-white/10 rounded-2xl p-6 mb-8 backdrop-blur-sm">
                    <h2 className="text-lg font-semibold mb-2">Neural Long-term Storage</h2>
                    <p className="text-zinc-400 leading-relaxed">
                        Manage what MeGPT remembers about you. These memories persistent across all conversations.
                        Deleting a memory here removes it permanently from the semantic search index.
                    </p>
                </div>

                {/* Search */}
                <div className="relative mb-8 group">
                    <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-violet-400 transition-colors" />
                    <input
                        type="text"
                        placeholder="Search neural patterns..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-11 pr-4 py-4 bg-black/40 border border-white/10 rounded-xl focus:outline-none focus:border-violet-500/50 focus:bg-black/60 text-white placeholder-zinc-600 transition-all font-sans shadow-lg"
                    />
                </div>

                {/* Error */}
                {error && (
                    <div className="flex items-center gap-2 text-red-300 bg-red-500/10 border border-red-500/20 p-4 rounded-xl mb-6">
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {/* Loading */}
                {isLoading ? (
                    <div className="text-center py-20">
                        <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                        <p className="text-zinc-500 font-mono text-sm animate-pulse">Syncing with vector database...</p>
                    </div>
                ) : filteredMemories.length === 0 ? (
                    <div className="text-center py-20 rounded-3xl border border-dashed border-white/10 bg-white/[0.02]">
                        <Brain size={48} className="mx-auto text-zinc-700 mb-4" />
                        <p className="text-zinc-500">{searchQuery ? "No matching memories found" : "Neural network is empty"}</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between px-2 text-xs font-medium uppercase tracking-wider text-zinc-500 font-mono">
                            <span>Detected Patterns</span>
                            <span>{filteredMemories.length} entries</span>
                        </div>
                        {filteredMemories.map((memory) => (
                            <div
                                key={memory.id}
                                className="group flex items-start gap-4 p-5 bg-white/[0.03] border border-white/5 rounded-2xl hover:border-violet-500/30 hover:bg-white/[0.05] transition-all duration-300 hover:shadow-lg hover:shadow-black/20"
                            >
                                <div className="flex-1">
                                    <p className="text-zinc-200 leading-relaxed font-sans">{memory.memory}</p>
                                    {memory.created_at && (
                                        <p className="text-xs text-zinc-600 mt-2 font-mono">
                                            {new Date(memory.created_at).toLocaleDateString()} • ID: {memory.id.substring(0, 8)}
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={() => deleteMemory(memory.id)}
                                    disabled={deletingId === memory.id}
                                    className="opacity-0 group-hover:opacity-100 p-2.5 rounded-xl hover:bg-red-500/10 text-zinc-500 hover:text-red-400 transition-all scale-95 group-hover:scale-100"
                                    title="Delete from permanent memory"
                                >
                                    {deletingId === memory.id ? (
                                        <div className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                                    ) : (
                                        <Trash2 size={18} />
                                    )}
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
