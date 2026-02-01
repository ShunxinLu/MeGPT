"use client";

import { useState, useEffect } from "react";
import { StoreProvider } from "@/lib/store";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";

interface Chat {
  id: string;
  title: string;
  updated_at?: string;
}

function HomeContent() {
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChat, setActiveChat] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load chats on mount
  useEffect(() => {
    loadChats();
  }, []);

  const loadChats = async () => {
    try {
      const res = await fetch("/api/chats");
      if (res.ok) {
        const data = await res.json();
        setChats(data);
      }
    } catch (err) {
      console.error("Failed to load chats:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    // Clear active chat to start fresh
    setActiveChat(null);
  };

  const handleChatCreated = (chatId: string, title: string) => {
    // Add new chat to list and select it
    const newChat: Chat = {
      id: chatId,
      title: title,
      updated_at: new Date().toISOString(),
    };
    setChats(prev => [newChat, ...prev]);
    setActiveChat(chatId);
  };

  const handleDeleteChat = (id: string) => {
    setChats(chats.filter((chat) => chat.id !== id));
    if (activeChat === id) {
      const remaining = chats.filter((chat) => chat.id !== id);
      setActiveChat(remaining[0]?.id || null);
    }
  };

  const handleSelectChat = (id: string) => {
    setActiveChat(id);
  };

  return (
    <main id="main-content" className="flex h-screen overflow-hidden pt-20">
      <Sidebar
        chats={chats}
        activeChat={activeChat}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />
      {isLoading ? <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-flex items-center gap-3 px-4 py-2 bg-violet-500/10 border border-violet-500/20 rounded-full">
            <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse"></div>
            <span className="text-sm text-violet-300">Loading memories...</span>
          </div>
        </div>
      </div> : <ChatInterface
        chatId={activeChat}
        onChatCreated={handleChatCreated}
      />}
    </main>
  );
}

export default function Home() {
  return (
    <StoreProvider>
      <HomeContent />
    </StoreProvider>
  );
}
