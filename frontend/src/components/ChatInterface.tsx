"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { AlertCircle, StopCircle, RefreshCw, Brain, Search } from "lucide-react";
import MessageBubble from "./MessageBubble";
import InputArea from "./InputArea";

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
}

interface ChatInterfaceProps {
    chatId: string | null;
    onChatCreated?: (chatId: string, title: string) => void;
}

interface StreamEvent {
    type: "status" | "text" | "error";
    content: string;
}

export default function ChatInterface({ chatId, onChatCreated }: ChatInterfaceProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [status, setStatus] = useState<string>("");
    const [currentChatId, setCurrentChatId] = useState<string | null>(chatId);
    const [lastUserMessage, setLastUserMessage] = useState<string>("");

    // Load messages when chat changes
    useEffect(() => {
        setCurrentChatId(chatId);
        if (chatId) {
            loadMessages(chatId);
        } else {
            setMessages([]);
        }
    }, [chatId]);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, isLoading, status]);

    const loadMessages = async (id: string) => {
        try {
            const res = await fetch(`/api/chats/${id}/messages`);
            if (res.ok) {
                const data = await res.json();
                setMessages(data.map((m: { id: string; role: string; content: string }) => ({
                    id: m.id,
                    role: m.role as "user" | "assistant",
                    content: m.content,
                })));
            }
        } catch (err) {
            console.error("Failed to load messages:", err);
        }
    };

    const createChat = async (firstMessage: string): Promise<string> => {
        const title = firstMessage.slice(0, 50) + (firstMessage.length > 50 ? "..." : "");
        const res = await fetch("/api/chats", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title }),
        });
        const data = await res.json();
        setCurrentChatId(data.id);
        onChatCreated?.(data.id, title);
        return data.id;
    };

    const saveMessage = async (chatId: string, role: string, content: string) => {
        await fetch(`/api/chats/${chatId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role, content }),
        });
    };

    const parseStreamEvents = (text: string): { events: StreamEvent[]; textContent: string } => {
        const events: StreamEvent[] = [];
        let textContent = "";

        const lines = text.split("\n");
        for (const line of lines) {
            if (line.startsWith("0:")) {
                try {
                    const event = JSON.parse(line.slice(2)) as StreamEvent;
                    events.push(event);
                    if (event.type === "text") {
                        textContent += event.content;
                    }
                } catch {
                    // Non-JSON line, treat as plain text
                    textContent += line;
                }
            } else if (line.trim()) {
                textContent += line;
            }
        }

        return { events, textContent };
    };

    const sendMessage = async (content: string, isRegenerate = false) => {
        if (!content.trim() || isLoading) return;

        // Create chat if needed
        let activeChatId = currentChatId;
        if (!activeChatId) {
            activeChatId = await createChat(content);
        }

        const userMessage: Message = {
            id: Date.now().toString(),
            role: "user",
            content: content.trim(),
        };

        if (!isRegenerate) {
            setMessages(prev => [...prev, userMessage]);
            setLastUserMessage(content.trim());
            await saveMessage(activeChatId, "user", content.trim());
        }

        setInput("");
        setIsLoading(true);
        setError(null);
        setStatus("🧠 Recalling memories...");

        // Setup abort controller for stop button
        abortControllerRef.current = new AbortController();

        try {
            const messagesToSend = isRegenerate
                ? messages.slice(0, -1) // Remove last assistant message for regenerate
                : [...messages, userMessage];

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: messagesToSend.map(m => ({
                        role: m.role,
                        content: m.content,
                    })),
                    chat_id: activeChatId,
                }),
                signal: abortControllerRef.current.signal,
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const reader = response.body?.getReader();
            if (!reader) throw new Error("No response body");

            const decoder = new TextDecoder();
            let fullText = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const { events, textContent } = parseStreamEvents(chunk);

                // Update status from events
                for (const event of events) {
                    if (event.type === "status") {
                        setStatus(event.content);
                    } else if (event.type === "error") {
                        setError(event.content);
                    }
                }

                fullText += textContent;

                // Update assistant message in real-time
                setMessages(prev => {
                    const newMessages = [...prev];
                    const lastMsg = newMessages[newMessages.length - 1];
                    if (lastMsg?.role === "assistant") {
                        lastMsg.content = fullText;
                    } else {
                        newMessages.push({
                            id: (Date.now() + 1).toString(),
                            role: "assistant",
                            content: fullText,
                        });
                    }
                    return [...newMessages];
                });
            }

            // Save assistant message
            if (fullText) {
                await saveMessage(activeChatId, "assistant", fullText);
            }

            setStatus("");
        } catch (err) {
            if (err instanceof Error && err.name === "AbortError") {
                setStatus("Stopped");
            } else {
                console.error("Chat error:", err);
                setError(err instanceof Error ? err.message : "Failed to get response");
            }
        } finally {
            setIsLoading(false);
            abortControllerRef.current = null;
        }
    };

    const handleStop = () => {
        abortControllerRef.current?.abort();
    };

    const handleRegenerate = () => {
        if (lastUserMessage && !isLoading) {
            // Remove last assistant message
            setMessages(prev => prev.slice(0, -1));
            sendMessage(lastUserMessage, true);
        }
    };

    const onSubmit = () => {
        sendMessage(input);
    };

    const handleSuggestionClick = (suggestion: string) => {
        sendMessage(suggestion);
    };

    return (
        <div className="flex-1 flex flex-col h-screen bg-[#1e1e1e] overflow-hidden">
            {/* Chat Messages Area */}
            <div className="flex-1 overflow-y-auto p-6 pb-32">
                <div className="max-w-3xl mx-auto space-y-6">
                    {/* Welcome message if no messages */}
                    {messages.length === 0 && (
                        <div className="text-center py-20">
                            <h2 className="text-3xl font-semibold gradient-text mb-4">
                                Hello! I&apos;m MeGPT
                            </h2>
                            <p className="text-[#9aa0a6] text-lg max-w-md mx-auto">
                                Your privacy-first AI assistant with persistent memory.
                                I remember our conversations and can search the web when needed.
                            </p>
                            <div className="mt-8 flex flex-wrap justify-center gap-3">
                                {[
                                    "Do you have long-term memory?",
                                    "What's the weather like?",
                                    "Help me with coding",
                                ].map((suggestion) => (
                                    <button
                                        key={suggestion}
                                        type="button"
                                        onClick={() => handleSuggestionClick(suggestion)}
                                        className="px-4 py-2 rounded-full bg-[#2f2f2f] hover:bg-[#3c4043] text-sm transition-colors"
                                    >
                                        {suggestion}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Messages */}
                    {messages.map((message) => (
                        <MessageBubble
                            key={message.id}
                            role={message.role}
                            content={message.content}
                            isStreaming={isLoading && message.role === "assistant" && message === messages[messages.length - 1]}
                        />
                    ))}

                    {/* Thinking Indicator */}
                    {isLoading && status && (
                        <div className="flex items-center gap-3 text-[#9aa0a6] bg-[#2f2f2f] p-3 rounded-xl">
                            <div className="flex items-center gap-2">
                                {status.includes("🧠") && <Brain size={18} className="text-purple-400 animate-pulse" />}
                                {status.includes("🔎") && <Search size={18} className="text-blue-400 animate-pulse" />}
                                {!status.includes("🧠") && !status.includes("🔎") && (
                                    <div className="flex gap-1">
                                        <div className="w-2 h-2 bg-[#8ab4f8] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                                        <div className="w-2 h-2 bg-[#8ab4f8] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                                        <div className="w-2 h-2 bg-[#8ab4f8] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                                    </div>
                                )}
                            </div>
                            <span className="text-sm">{status}</span>
                            <button
                                onClick={handleStop}
                                className="ml-auto p-1 hover:bg-[#3c4043] rounded transition-colors"
                                title="Stop generating"
                            >
                                <StopCircle size={18} className="text-red-400" />
                            </button>
                        </div>
                    )}

                    {/* Regenerate button */}
                    {!isLoading && messages.length > 0 && messages[messages.length - 1]?.role === "assistant" && (
                        <div className="flex justify-center">
                            <button
                                onClick={handleRegenerate}
                                className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#9aa0a6] hover:text-white hover:bg-[#2f2f2f] rounded-lg transition-colors"
                            >
                                <RefreshCw size={14} />
                                Regenerate response
                            </button>
                        </div>
                    )}

                    {/* Error message */}
                    {error && (
                        <div className="flex items-center gap-2 text-red-400 bg-red-400/10 p-4 rounded-xl">
                            <AlertCircle size={18} />
                            <span>{error}</span>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input Area */}
            <InputArea
                value={input}
                onChange={setInput}
                onSubmit={onSubmit}
                isLoading={isLoading}
            />
        </div>
    );
}
