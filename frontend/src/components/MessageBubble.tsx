"use client";

import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, User, Sparkles, Bot, Terminal } from "lucide-react";
import { useState } from "react";

interface MessageBubbleProps {
    role: "user" | "assistant";
    content: string;
    isStreaming?: boolean;
}

export default function MessageBubble({ role, content, isStreaming }: MessageBubbleProps) {
    const [copiedCode, setCopiedCode] = useState<string | null>(null);

    const copyToClipboard = async (code: string) => {
        await navigator.clipboard.writeText(code);
        setCopiedCode(code);
        setTimeout(() => setCopiedCode(null), 2000);
    };

    const isUser = role === "user";

    return (
        <div className={`flex gap-5 group/msg ${isUser ? "justify-end" : "justify-start"}`}>
            {/* Avatar for AI */}
            {!isUser && (
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-[0_4px_20px_-4px_rgba(139,92,246,0.5)] mt-1 border border-white/10 relative overflow-hidden">
                    <div className="absolute inset-0 bg-white/20 opacity-0 group-hover/msg:opacity-100 transition-opacity"></div>
                    <Bot size={20} className="text-white relative z-10" />
                </div>
            )}

            {/* Message Content */}
            <div
                className={`
                    max-w-[85%] lg:max-w-[75%] rounded-3xl px-6 py-5 text-base leading-7
                    transition-all duration-300
                    ${isUser
                        ? "bg-white/5 backdrop-blur-xl border border-white/10 text-zinc-100 rounded-tr-sm shadow-[0_4px_20px_-4px_rgba(0,0,0,0.2)]"
                        : "bg-transparent text-zinc-300 pl-0"
                    }
                `}
            >
                {isUser ? (
                    <p className="whitespace-pre-wrap font-sans tracking-wide">{content}</p>
                ) : (
                    <div className="prose prose-invert prose-violet max-w-none prose-p:leading-7 prose-pre:bg-transparent prose-pre:p-0 prose-pre:border-none prose-pre:shadow-none">
                        <ReactMarkdown
                            components={{
                                code({ node, className, children, ...props }) {
                                    const match = /language-(\w+)/.exec(className || "");
                                    const codeString = String(children).replace(/\n$/, "");
                                    const isInline = !match && !className;

                                    if (isInline) {
                                        return (
                                            <code
                                                className="bg-violet-500/10 px-1.5 py-0.5 rounded text-violet-200 font-mono text-sm border border-violet-500/20"
                                                {...props}
                                            >
                                                {children}
                                            </code>
                                        );
                                    }

                                    return (
                                        <div className="relative group/code my-6 rounded-2xl overflow-hidden border border-white/10 shadow-2xl bg-[#09090b]">
                                            {/* Code Header */}
                                            <div className="flex items-center justify-between px-4 py-3 bg-[#18181b] border-b border-white/5">
                                                <div className="flex items-center gap-2">
                                                    <div className="flex gap-1.5">
                                                        <div className="w-2.5 h-2.5 rounded-full bg-[#ef4444] opacity-80" />
                                                        <div className="w-2.5 h-2.5 rounded-full bg-[#eab308] opacity-80" />
                                                        <div className="w-2.5 h-2.5 rounded-full bg-[#22c55e] opacity-80" />
                                                    </div>
                                                    {match && (
                                                        <span className="ml-3 text-xs text-zinc-500 font-mono font-medium uppercase tracking-wider flex items-center gap-1.5">
                                                            <Terminal size={10} />
                                                            {match[1]}
                                                        </span>
                                                    )}
                                                </div>
                                                <button
                                                    onClick={() => copyToClipboard(codeString)}
                                                    className="p-1.5 rounded-lg hover:bg-white/10 transition-all text-zinc-500 hover:text-zinc-200"
                                                    aria-label="Copy code"
                                                >
                                                    {copiedCode === codeString ? (
                                                        <Check size={14} className="text-emerald-400" />
                                                    ) : (
                                                        <div className="flex items-center gap-1.5 text-xs font-medium">
                                                            <Copy size={14} />
                                                            <span>Copy</span>
                                                        </div>
                                                    )}
                                                </button>
                                            </div>

                                            {/* Code Content */}
                                            <div className="relative">
                                                <SyntaxHighlighter
                                                    style={atomDark}
                                                    language={match?.[1] || "text"}
                                                    PreTag="div"
                                                    customStyle={{
                                                        margin: 0,
                                                        padding: "1.5rem",
                                                        background: "transparent",
                                                        fontSize: "0.9rem",
                                                        lineHeight: "1.6",
                                                    }}
                                                    {...props}
                                                >
                                                    {codeString}
                                                </SyntaxHighlighter>
                                            </div>
                                        </div>
                                    );
                                },
                                p({ children }) {
                                    return <p className="mb-4 last:mb-0 text-zinc-300 font-light leading-relaxed">{children}</p>;
                                },
                                ul({ children }) {
                                    return <ul className="list-disc list-outside ml-4 mb-4 space-y-2 marker:text-violet-500/70 text-zinc-300">{children}</ul>;
                                },
                                ol({ children }) {
                                    return <ol className="list-decimal list-outside ml-4 mb-4 space-y-2 marker:text-violet-500/70 text-zinc-300">{children}</ol>;
                                },
                                strong({ children }) {
                                    return <strong className="font-bold text-zinc-100">{children}</strong>;
                                },
                                h1({ children }) {
                                    return <h1 className="text-3xl font-bold mb-6 text-white mt-8 pb-2 border-b border-white/5 inline-block bg-gradient-to-r from-white to-zinc-500 bg-clip-text text-transparent">{children}</h1>;
                                },
                                h2({ children }) {
                                    return <h2 className="text-xl font-bold mb-4 text-zinc-100 mt-8 flex items-center gap-2">
                                        <span className="w-1 h-5 bg-violet-500 rounded-full"></span>
                                        {children}
                                    </h2>;
                                },
                                h3({ children }) {
                                    return <h3 className="text-lg font-semibold mb-3 text-zinc-100 mt-6">{children}</h3>;
                                },
                                blockquote({ children }) {
                                    return (
                                        <blockquote className="border-l-2 border-violet-500/50 pl-4 py-1 my-4 bg-violet-500/5 rounded-r-lg italic text-zinc-400">
                                            {children}
                                        </blockquote>
                                    );
                                },
                                a({ href, children }) {
                                    return (
                                        <a
                                            href={href}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-violet-400 hover:text-violet-300 decoration-violet-500/30 underline underline-offset-4 transition-colors font-medium"
                                        >
                                            {children}
                                        </a>
                                    );
                                },
                            }}
                        >
                            {content}
                        </ReactMarkdown>
                        {isStreaming && (
                            <span className="inline-block w-2 h-5 bg-violet-400 ml-1 animate-pulse shadow-[0_0_10px_rgba(167,139,250,0.5)] rounded-full" />
                        )}
                    </div>
                )}
            </div>

            {/* Avatar for User */}
            {isUser && (
                <div className="w-10 h-10 rounded-2xl bg-zinc-800/80 border border-white/5 flex items-center justify-center flex-shrink-0 mt-1 shadow-lg">
                    <User size={18} className="text-zinc-400" />
                </div>
            )}
        </div>
    );
}
