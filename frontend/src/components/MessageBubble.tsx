"use client";

import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, User, Sparkles } from "lucide-react";
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
        <div className={`flex gap-4 message-fade-in ${isUser ? "justify-end" : ""}`}>
            {/* Avatar for AI */}
            {!isUser && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#8ab4f8] to-[#c58af9] flex items-center justify-center flex-shrink-0">
                    <Sparkles size={16} className="text-white" />
                </div>
            )}

            {/* Message Content */}
            <div
                className={`
          max-w-[80%] rounded-2xl px-4 py-3
          ${isUser
                        ? "bg-[#2f2f2f] text-[#e8eaed]"
                        : "bg-transparent"
                    }
        `}
            >
                {isUser ? (
                    <p className="whitespace-pre-wrap">{content}</p>
                ) : (
                    <div className="prose prose-invert max-w-none">
                        <ReactMarkdown
                            components={{
                                // Syntax-highlighted code blocks
                                code({ node, className, children, ...props }) {
                                    const match = /language-(\w+)/.exec(className || "");
                                    const codeString = String(children).replace(/\n$/, "");

                                    // Check if it's an inline code or block
                                    const isInline = !match && !className;

                                    if (isInline) {
                                        return (
                                            <code
                                                className="bg-[#2f2f2f] px-1.5 py-0.5 rounded text-[#e8eaed] text-sm"
                                                {...props}
                                            >
                                                {children}
                                            </code>
                                        );
                                    }

                                    return (
                                        <div className="relative group my-4">
                                            {/* Language badge & Copy button */}
                                            <div className="absolute top-2 right-2 flex items-center gap-2">
                                                {match && (
                                                    <span className="text-xs text-[#9aa0a6] uppercase">
                                                        {match[1]}
                                                    </span>
                                                )}
                                                <button
                                                    onClick={() => copyToClipboard(codeString)}
                                                    className="p-1.5 rounded-lg bg-[#3c4043] hover:bg-[#4a4a4a] transition-colors opacity-0 group-hover:opacity-100"
                                                    aria-label="Copy code"
                                                >
                                                    {copiedCode === codeString ? (
                                                        <Check size={14} className="text-green-400" />
                                                    ) : (
                                                        <Copy size={14} />
                                                    )}
                                                </button>
                                            </div>
                                            <SyntaxHighlighter
                                                style={atomDark}
                                                language={match?.[1] || "text"}
                                                PreTag="div"
                                                customStyle={{
                                                    margin: 0,
                                                    borderRadius: "12px",
                                                    padding: "1rem",
                                                    paddingTop: "2.5rem",
                                                    background: "#1e1e1e",
                                                }}
                                                {...props}
                                            >
                                                {codeString}
                                            </SyntaxHighlighter>
                                        </div>
                                    );
                                },
                                // Style paragraphs
                                p({ children }) {
                                    return <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>;
                                },
                                // Style lists
                                ul({ children }) {
                                    return <ul className="list-disc list-inside mb-4 space-y-1">{children}</ul>;
                                },
                                ol({ children }) {
                                    return <ol className="list-decimal list-inside mb-4 space-y-1">{children}</ol>;
                                },
                                // Style headings
                                h1({ children }) {
                                    return <h1 className="text-xl font-bold mb-3">{children}</h1>;
                                },
                                h2({ children }) {
                                    return <h2 className="text-lg font-bold mb-2">{children}</h2>;
                                },
                                h3({ children }) {
                                    return <h3 className="text-base font-bold mb-2">{children}</h3>;
                                },
                                // Style links
                                a({ href, children }) {
                                    return (
                                        <a
                                            href={href}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-[#8ab4f8] hover:underline"
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
                            <span className="typing-cursor inline-block w-2 h-5 bg-[#8ab4f8] ml-1" />
                        )}
                    </div>
                )}
            </div>

            {/* Avatar for User */}
            {isUser && (
                <div className="w-8 h-8 rounded-full bg-[#3c4043] flex items-center justify-center flex-shrink-0">
                    <User size={16} className="text-[#9aa0a6]" />
                </div>
            )}
        </div>
    );
}
