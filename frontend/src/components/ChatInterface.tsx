"use client";

import { useState, useRef, useEffect } from "react";
import { AlertCircle, StopCircle, RefreshCw, Brain, Search, Sparkles, Terminal, ChevronDown, Plus } from "lucide-react";
import MessageBubble from "./MessageBubble";
import InputArea from "./InputArea";
import ToastContainer from "./Toast";
import type { Toast } from "./Toast";

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
}

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
    const [toasts, setToasts] = useState<Toast[]>([]);

    // Model selector state
    const [providers, setProviders] = useState<ProviderInfo[]>([]);
    const [activeProvider, setActiveProvider] = useState<string | null>(null);
    const [activeModel, setActiveModel] = useState<string>("");

    // Load messages when chat changes
    useEffect(() => {
        setCurrentChatId(chatId);
        if (chatId) {
            loadMessages(chatId);
        } else {
            setMessages([]);
        }
    }, [chatId]);

    // Load providers on mount
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

                // Set active model from active provider
                const active = data.available.find(p => p.id === data.active);
                if (active && active.available_models.length > 0) {
                    setActiveModel(active.available_models[0]);
                }
            }
        } catch (error) {
            console.error("Failed to load providers:", error);
        }
    };

    const getAllModels = () => {
        const models: { provider: string; model: string; providerName: string }[] = [];
        for (const provider of providers) {
            const connected = provider.has_config === true;
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

        const connected = provider.has_config === true;

        if (!connected) {
            // Redirect to settings to connect provider
            window.location.href = "/settings/providers";
            return;
        }

        setActiveModel(model);

        try {
            await fetch("/api/providers/set-default", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider_id: providerId, model }),
            });
            setActiveProvider(providerId);
        } catch (error) {
            console.error("Failed to switch model:", error);
        }
    };

    const allModels = getAllModels();

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
        setStatus("🧠 Accessing neural context...");

        abortControllerRef.current = new AbortController();

        try {
            const messagesToSend = isRegenerate
                ? messages.slice(0, -1)
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

                for (const event of events) {
                    if (event.type === "status") {
                        setStatus(event.content);
                    } else if (event.type === "error") {
                        setError(event.content);
                    }
                }

                fullText += textContent;

                setMessages(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg?.role === "assistant") {
                        // Create new object instead of mutating
                        return [
                            ...prev.slice(0, -1),
                            { ...lastMsg, content: fullText }
                        ];
                    } else {
                        return [
                            ...prev,
                            {
                                id: (Date.now() + 1).toString(),
                                role: "assistant",
                                content: fullText,
                            },
                        ];
                    }
                });
            }

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
        <div className="flex-1 flex flex-col h-screen text-zinc-100 relative overflow-hidden bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-[#131316] via-transparent to-transparent">
            {/* Extended Background Texture */}
            <div className="absolute inset-0 pointer-events-none opacity-[0.02]"
                style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")` }}>
            </div>

            {/* Model Selector - ChatGPT Style */}
            <div className="relative z-20 px-4 md:px-8 pt-3 pb-2">
                <div className="max-w-xs mx-auto">
                    {allModels.length > 0 ? (
                        <div className="relative group">
                            <select
                                value={`${activeProvider}::${activeModel}`}
                                onChange={(e) => handleModelChange(e.target.value)}
                                className="w-full px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-violet-500/30 rounded-xl text-sm text-zinc-300 focus:outline-none focus:border-violet-500/50 transition-all cursor-pointer appearance-none pr-8"
                                style={{
                                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='currentColor'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/svg%3E")`,
                                    backgroundRepeat: 'no-repeat',
                                    backgroundPosition: 'right 0.5rem center',
                                    backgroundSize: '1rem',
                                }}
                            >
                                {allModels.map(({ provider, model, providerName }) => (
                                    <option key={`${provider}::${model}`} value={`${provider}::${model}`}>
                                        {model}
                                    </option>
                                ))}
                            </select>
                        </div>
                    ) : (
                        <button
                            onClick={() => window.location.href = "/settings/providers"}
                            className="w-full px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-violet-500/30 rounded-xl text-sm text-zinc-400 hover:text-zinc-200 transition-all flex items-center justify-center gap-2"
                        >
                            <Plus className="w-4 h-4" />
                            Add Model
                        </button>
                    )}
                </div>
            </div>

            {/* Chat Messages Area */}
            <div className="flex-1 overflow-y-auto px-4 md:px-8 pb-32 pt-2 scrollbar-thin z-10">
                <div className="max-w-3xl mx-auto space-y-8">
                    {/* Welcome Screen */}
                    {messages.length === 0 && (
                        <div className="text-center py-24 animate-in">
                            <div className="inline-flex justify-center items-center p-4 mb-8 bg-black/30 rounded-3xl border border-white/5 shadow-[0_0_50px_rgba(139,92,246,0.1)] relative overflow-hidden group">
                                <div className="absolute inset-0 bg-gradient-to-tr from-violet-500/10 to-cyan-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none"></div>
                                <Sparkles size={40} className="text-violet-400 relative z-10 drop-shadow-[0_0_15px_rgba(139,92,246,0.8)]" />
                            </div>
                            <h2 className="text-6xl font-bold tracking-tight mb-6 font-sans">
                                <span className="gradient-text">MeGPT</span>
                            </h2>
                            <p className="text-zinc-400 text-lg max-w-lg mx-auto leading-relaxed mb-12 font-light">
                                Your persistent neural memory. I recall our past conversations to build deeper context over time, evolving with every interaction.
                            </p>

                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto">
                                {[
                                    { text: "Query my past memories", icon: <Brain size={16} />, delay: "0ms" },
                                    { text: "Analyze this code block", icon: <Terminal size={16} />, delay: "100ms" },
                                    { text: "Search the web for info", icon: <Search size={16} />, delay: "200ms" },
                                ].map((suggestion, i) => (
                                    <button
                                        key={suggestion.text}
                                        type="button"
                                        onClick={() => handleSuggestionClick(suggestion.text)}
                                        style={{ animationDelay: suggestion.delay }}
                                        className="flex items-center justify-center gap-3 px-5 py-4 rounded-2xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-violet-500/30 text-sm text-zinc-300 transition-all hover:-translate-y-1 hover:shadow-lg hover:shadow-violet-500/10 animate-in opacity-0 fill-mode-forwards"
                                    >
                                        <span className="text-violet-400">{suggestion.icon}</span>
                                        <span>{suggestion.text}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Messages */}
                    {messages.map((message) => (
                        <div key={message.id} className="message-enter">
                            <MessageBubble
                                role={message.role}
                                content={message.content}
                                isStreaming={isLoading && message.role === "assistant" && message === messages[messages.length - 1]}
                            />
                        </div>
                    ))}

                    {/* Thinking Indicator */}
                    {isLoading && status && (
                        <div className="flex justify-center my-6 message-enter">
                            <div className="inline-flex items-center gap-4 px-5 py-2.5 bg-black/40 border border-violet-500/20 rounded-full backdrop-blur-md shadow-[0_0_20px_rgba(139,92,246,0.15)] relative overflow-hidden">
                                <div className="absolute inset-0 bg-gradient-to-r from-violet-500/5 via-cyan-500/5 to-violet-500/5 animate-[pulse_3s_infinite]"></div>
                                <div className="flex gap-1.5 relative z-10">
                                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-[bounce_1s_infinite_0ms] shadow-[0_0_8px_rgba(139,92,246,0.8)]"></span>
                                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-[bounce_1s_infinite_150ms] shadow-[0_0_8px_rgba(139,92,246,0.8)]"></span>
                                    <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-[bounce_1s_infinite_300ms] shadow-[0_0_8px_rgba(139,92,246,0.8)]"></span>
                                </div>
                                <span className="text-xs font-mono text-violet-300 tracking-wide uppercase relative z-10 text-glow">{status}</span>
                                <button
                                    onClick={handleStop}
                                    className="ml-2 hover:bg-white/10 rounded-full p-1 transition-colors relative z-10 group"
                                >
                                    <StopCircle size={14} className="text-red-400/80 group-hover:text-red-400 transition-colors" />
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Error message */}
                    {error && (
                        <div className="flex items-center justify-center gap-2 text-red-300 bg-red-950/30 border border-red-500/20 p-4 rounded-xl mx-auto max-w-md backdrop-blur-md shadow-lg shadow-red-900/10 animate-in">
                            <AlertCircle size={18} />
                            <span className="text-sm font-medium">{error}</span>
                        </div>
                    )}

                    {/* Spacer for bottom input */}
                    <div ref={messagesEndRef} className="h-4" />
                </div>
            </div>

            {/* Input Area */}
            <div className="relative z-20">
                <InputArea
                    value={input}
                    onChange={setInput}
                    onSubmit={onSubmit}
                    isLoading={isLoading}
                    onStop={handleStop}
                    chatId={currentChatId ?? undefined}
                    onFileUploaded={(doc) => {
                        // Add system message about uploaded document
                        setMessages(prev => [...prev, {
                            id: Date.now().toString(),
                            role: "assistant",
                            content: `📄 Document "${doc.filename}" uploaded and processed. You can now ask questions about its contents.`
                        }]);
                    }}
                />
            </div>

            {/* Toast Container */}
            <ToastContainer toasts={toasts} onRemove={(id) => setToasts(prev => prev.filter(t => t.id !== id))} />
        </div>
    );
}
