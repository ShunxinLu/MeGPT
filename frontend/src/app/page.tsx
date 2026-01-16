"use client";

import { useState, useEffect, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatInterface from "@/components/ChatInterface";

interface Chat {
  id: string;
  title: string;
  updated_at?: string;
}

export default function Home() {
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
    <main className="flex h-screen overflow-hidden">
      <Sidebar
        chats={chats}
        activeChat={activeChat}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />
      <ChatInterface
        chatId={activeChat}
        onChatCreated={handleChatCreated}
      />
    </main>
  );
}
