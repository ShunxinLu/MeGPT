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
        <div className="min-h-screen bg-[#1e1e1e] text-white">
            {/* Header */}
            <div className="border-b border-[#3c4043] p-4">
                <div className="max-w-4xl mx-auto flex items-center gap-4">
                    <Link
                        href="/"
                        className="p-2 hover:bg-[#2f2f2f] rounded-lg transition-colors"
                    >
                        <ArrowLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-2">
                        <Brain className="text-purple-400" size={24} />
                        <h1 className="text-xl font-semibold">Memory Manager</h1>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-4xl mx-auto p-6">
                {/* Description */}
                <p className="text-[#9aa0a6] mb-6">
                    Manage what MeGPT remembers about you. Delete specific memories without removing entire conversations.
                </p>

                {/* Search */}
                <div className="relative mb-6">
                    <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa0a6]" />
                    <input
                        type="text"
                        placeholder="Filter memories..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-[#0f0f0f] border border-[#3c4043] rounded-xl focus:outline-none focus:border-[#8ab4f8] text-white placeholder-[#9aa0a6]"
                    />
                </div>

                {/* Error */}
                {error && (
                    <div className="flex items-center gap-2 text-red-400 bg-red-400/10 p-4 rounded-xl mb-6">
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {/* Loading */}
                {isLoading ? (
                    <div className="text-center py-12 text-[#9aa0a6]">
                        Loading memories...
                    </div>
                ) : filteredMemories.length === 0 ? (
                    <div className="text-center py-12 text-[#9aa0a6]">
                        {searchQuery ? "No memories match your search" : "No memories stored yet"}
                    </div>
                ) : (
                    <div className="space-y-3">
                        <p className="text-sm text-[#9aa0a6] mb-4">
                            {filteredMemories.length} memorie{filteredMemories.length !== 1 ? "s" : ""} stored
                        </p>
                        {filteredMemories.map((memory) => (
                            <div
                                key={memory.id}
                                className="group flex items-start gap-4 p-4 bg-[#0f0f0f] border border-[#3c4043] rounded-xl hover:border-[#8ab4f8]/50 transition-colors"
                            >
                                <div className="flex-1">
                                    <p className="text-white">{memory.memory}</p>
                                    {memory.created_at && (
                                        <p className="text-xs text-[#9aa0a6] mt-2">
                                            {new Date(memory.created_at).toLocaleDateString()}
                                        </p>
                                    )}
                                </div>
                                <button
                                    onClick={() => deleteMemory(memory.id)}
                                    disabled={deletingId === memory.id}
                                    className="opacity-0 group-hover:opacity-100 p-2 hover:bg-red-500/20 rounded-lg transition-all text-red-400"
                                    title="Delete this memory"
                                >
                                    {deletingId === memory.id ? (
                                        <div className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                                    ) : (
                                        <Trash2 size={16} />
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
