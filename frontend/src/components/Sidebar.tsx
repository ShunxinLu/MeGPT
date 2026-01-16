"use client";

import { useState, useEffect, useCallback } from "react";
import { MessageSquare, Plus, ChevronLeft, ChevronRight, Settings, Trash2, Search, X } from "lucide-react";
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
    onChatsUpdated?: () => void;
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

        // Call API to delete
        try {
            await fetch(`/api/chats/${chatId}`, { method: "DELETE" });
            onDeleteChat(chatId);
        } catch (err) {
            console.error("Failed to delete:", err);
        }
    };

    const clearSearch = () => {
        setSearchQuery("");
        setSearchResults(null);
    };

    return (
        <aside
            className={`
                ${collapsed ? "w-16" : "w-[260px]"}
                h-screen bg-[#0f0f0f] border-r border-[#3c4043]
                flex flex-col transition-all duration-300 ease-in-out
            `}
        >
            {/* Header */}
            <div className="p-4 flex items-center justify-between">
                {!collapsed && (
                    <h1 className="text-lg font-semibold gradient-text">MeGPT</h1>
                )}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className="p-2 rounded-lg hover:bg-[#2f2f2f] transition-colors"
                    aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                    {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
                </button>
            </div>

            {/* New Chat Button */}
            <div className="px-3 mb-2">
                <button
                    onClick={onNewChat}
                    className={`
                        w-full flex items-center gap-3 p-3 rounded-xl
                        bg-[#1e1e1e] hover:bg-[#2f2f2f] transition-colors
                        border border-[#3c4043]
                        ${collapsed ? "justify-center" : ""}
                    `}
                >
                    <Plus size={18} />
                    {!collapsed && <span>New Chat</span>}
                </button>
            </div>

            {/* Search Bar */}
            {!collapsed && (
                <div className="px-3 mb-3">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa0a6]" />
                        <input
                            type="text"
                            placeholder="Search chats..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-8 py-2 text-sm bg-[#1e1e1e] border border-[#3c4043] rounded-lg focus:outline-none focus:border-[#8ab4f8] text-white placeholder-[#9aa0a6]"
                        />
                        {searchQuery && (
                            <button
                                onClick={clearSearch}
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-[#3c4043] rounded"
                            >
                                <X size={12} className="text-[#9aa0a6]" />
                            </button>
                        )}
                    </div>
                    {isSearching && (
                        <p className="text-xs text-[#9aa0a6] mt-1 px-1">Searching...</p>
                    )}
                </div>
            )}

            {/* Chat List */}
            <div className="flex-1 overflow-y-auto px-2">
                {!collapsed && (
                    <p className="text-xs text-[#9aa0a6] px-2 mb-2">
                        {searchResults ? `Results (${searchResults.length})` : "Recent"}
                    </p>
                )}
                {displayChats.length === 0 && !collapsed && (
                    <p className="text-xs text-[#9aa0a6] px-2 text-center py-4">
                        {searchResults ? "No results found" : "No chats yet"}
                    </p>
                )}
                {displayChats.map((chat) => (
                    <div
                        key={chat.id}
                        onClick={() => onSelectChat(chat.id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && onSelectChat(chat.id)}
                        className={`
                            w-full flex items-center gap-3 p-3 rounded-xl mb-1
                            transition-colors group relative cursor-pointer
                            ${activeChat === chat.id ? "bg-[#2f2f2f]" : "hover:bg-[#1e1e1e]"}
                            ${collapsed ? "justify-center" : ""}
                        `}
                        title={collapsed ? chat.title : undefined}
                    >
                        <MessageSquare size={18} className="text-[#9aa0a6] flex-shrink-0" />
                        {!collapsed && (
                            <>
                                <span className="truncate text-sm text-left flex-1">
                                    {chat.title || "New Chat"}
                                </span>
                                <button
                                    onClick={(e) => handleDelete(e, chat.id)}
                                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-[#3c4043] rounded transition-all"
                                    aria-label="Delete chat"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-[#3c4043]">
                <Link
                    href="/settings/memory"
                    className={`
                        w-full flex items-center gap-3 p-3 rounded-xl
                        hover:bg-[#1e1e1e] transition-colors text-[#9aa0a6]
                        ${collapsed ? "justify-center" : ""}
                    `}
                >
                    <Settings size={18} />
                    {!collapsed && <span className="text-sm">Memory Manager</span>}
                </Link>
            </div>
        </aside>
    );
}
