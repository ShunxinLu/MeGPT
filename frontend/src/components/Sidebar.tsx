"use client";

import { useState, useEffect } from "react";
import { MessageSquare, Plus, ChevronLeft, ChevronRight, Settings, Trash2, Search, X, Database } from "lucide-react";
import Link from "next/link";

interface Chat {
    id: string;
    title: string;
    updated_at?: string;
}

interface SidebarProps {
    chats: Chat[];
    activeChat: string | null;
    onSelectChat: (id: string) => void;
    onNewChat: () => void;
    onDeleteChat: (id: string) => void;
}

export default function Sidebar({
    chats,
    activeChat,
    onSelectChat,
    onNewChat,
    onDeleteChat,
}: SidebarProps) {
    const [collapsed, setCollapsed] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<Chat[] | null>(null);
    const [isSearching, setIsSearching] = useState(false);

    // Debounced search
    useEffect(() => {
        if (!searchQuery.trim()) {
            setSearchResults(null);
            return;
        }

        const timer = setTimeout(async () => {
            setIsSearching(true);
            try {
                const res = await fetch(`/api/chats/search?q=${encodeURIComponent(searchQuery)}`);
                if (res.ok) {
                    const data = await res.json();
                    setSearchResults(data);
                }
            } catch (err) {
                console.error("Search failed:", err);
            } finally {
                setIsSearching(false);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [searchQuery]);

    const displayChats = searchResults ?? chats;

    const handleDelete = async (e: React.MouseEvent, chatId: string) => {
        e.stopPropagation();
        if (confirm("Delete this memory stream?")) {
            try {
                await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
                onDeleteChat(chatId);
            } catch (err) {
                console.error("Failed to delete:", err);
            }
        }
    };

    const clearSearch = () => {
        setSearchQuery("");
        setSearchResults(null);
    };

    return (
        <aside
            className={`
                ${collapsed ? "w-20" : "w-[300px]"}
                h-screen glass flex flex-col transition-all duration-300 ease-[cubic-bezier(0.2,0,0,1)]
                z-50 relative border-r border-white/5
            `}
        >
            {/* Header */}
            <div className="p-6 flex items-center justify-between">
                {!collapsed && (
                    <div className="flex items-center gap-3">
                        <div className="relative">
                            <div className="w-2.5 h-2.5 rounded-full bg-violet-500 animate-pulse"></div>
                            <div className="absolute inset-0 bg-violet-500 rounded-full blur-[8px] opacity-50"></div>
                        </div>
                        <h1 className="text-xl font-bold tracking-tight text-white font-sans">MeGPT</h1>
                    </div>
                )}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className="p-2 rounded-xl hover:bg-white/5 text-zinc-400 hover:text-white transition-all hover:scale-105 active:scale-95"
                >
                    {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
                </button>
            </div>

            {/* New Chat Button */}
            <div className="px-4 mb-6">
                <button
                    onClick={onNewChat}
                    className={`
                        w-full flex items-center gap-3 p-3.5 rounded-xl
                        glass-button group
                        text-zinc-100 font-medium
                        ${collapsed ? "justify-center p-3.5" : ""}
                    `}
                >
                    <Plus size={20} className="text-violet-400 group-hover:rotate-90 transition-transform duration-300" />
                    {!collapsed && <span className="text-sm">New Memory</span>}
                </button>
            </div>

            {/* Search Bar */}
            {!collapsed && (
                <div className="px-4 mb-4">
                    <div className="relative group">
                        <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-violet-400 transition-colors" />
                        <input
                            type="text"
                            placeholder="Recall memories..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-9 py-2.5 text-sm bg-black/20 border border-white/5 rounded-xl focus:outline-none focus:border-violet-500/50 focus:bg-black/40 text-zinc-200 placeholder-zinc-600 transition-all font-sans shadow-inner"
                        />
                        {searchQuery && (
                            <button
                                onClick={clearSearch}
                                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 hover:bg-white/10 rounded-full transition-colors"
                            >
                                <X size={12} className="text-zinc-500 hover:text-zinc-300" />
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* Chat List */}
            <div className="flex-1 overflow-y-auto px-3 space-y-1 scrollbar-thin pb-4">
                {!collapsed && (
                    <div className="px-3 mb-2 mt-2">
                        <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-600">
                            {searchResults ? "Search Results" : "Recent Memories"}
                        </p>
                    </div>
                )}

                {displayChats.map((chat) => (
                    <div
                        key={chat.id}
                        onClick={() => onSelectChat(chat.id)}
                        className={`
                            group relative flex items-center gap-3 p-3 rounded-xl cursor-pointer
                            transition-all duration-200 border border-transparent
                            ${activeChat === chat.id
                                ? "bg-white/5 border-white/5 text-white shadow-[0_0_20px_rgba(0,0,0,0.2)]"
                                : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200 hover:border-white/5"}
                            ${collapsed ? "justify-center" : ""}
                        `}
                        title={collapsed ? chat.title : undefined}
                    >
                        {/* Active Indicator Glow */}
                        {activeChat === chat.id && (
                            <div className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-transparent rounded-xl pointer-events-none" />
                        )}

                        <MessageSquare size={18} className={`flex-shrink-0 z-10 transition-colors ${activeChat === chat.id ? "text-violet-400" : "opacity-50 group-hover:opacity-75"}`} />

                        {!collapsed && (
                            <>
                                <span className="truncate text-sm flex-1 font-medium font-sans z-10">
                                    {chat.title || "Untitled Memory"}
                                </span>
                                <button
                                    onClick={(e) => handleDelete(e, chat.id)}
                                    className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20 hover:text-red-400 rounded-lg transition-all scale-90 hover:scale-100 z-10"
                                >
                                    <Trash2 size={13} />
                                </button>
                            </>
                        )}

                        {/* Active Indicator Bar */}
                        {activeChat === chat.id && !collapsed && (
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-violet-500 rounded-r-full shadow-[0_0_12px_var(--accent-primary)]"></div>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-white/5 bg-black/20 space-y-1 backdrop-blur-md">
                <Link
                    href="/settings/memory"
                    className={`
                        flex items-center gap-3 p-3 rounded-xl
                        text-zinc-500 hover:text-zinc-200 hover:bg-white/5 transition-all
                        hover:shadow-lg hover:shadow-black/20
                        ${collapsed ? "justify-center" : ""}
                    `}
                    title={collapsed ? "Memory Manager" : undefined}
                >
                    <Settings size={18} />
                    {!collapsed && <span className="text-xs font-medium uppercase tracking-wide">Memory Manager</span>}
                </Link>
                <Link
                    href="/settings/admin"
                    className={`
                        flex items-center gap-3 p-3 rounded-xl
                        text-zinc-500 hover:text-zinc-200 hover:bg-white/5 transition-all
                        hover:shadow-lg hover:shadow-black/20
                        ${collapsed ? "justify-center" : ""}
                    `}
                    title={collapsed ? "Backups & Restore" : undefined}
                >
                    <Database size={18} />
                    {!collapsed && <span className="text-xs font-medium uppercase tracking-wide">Backups</span>}
                </Link>
            </div>
        </aside>
    );
}
