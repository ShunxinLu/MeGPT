"use client";

import { useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2, Command, CornerDownLeft } from "lucide-react";
import FileUpload from "./FileUpload";

interface InputAreaProps {
    value: string;
    onChange: (value: string) => void;
    onSubmit: () => void;
    isLoading: boolean;
    placeholder?: string;
    onStop?: () => void;
    chatId?: string;
    onFileUploaded?: (document: any) => void;
}

export default function InputArea({
    value,
    onChange,
    onSubmit,
    isLoading,
    placeholder = "Ask anything...",
    onStop,
    chatId,
    onFileUploaded,
}: InputAreaProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize textarea
    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
        }
    }, [value]);

    // Focus on mount (only on desktop)
    useEffect(() => {
        if (window.innerWidth >= 768) {
            textareaRef.current?.focus();
        }
    }, []);

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        // Enter to send, Shift+Enter for new line
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!isLoading && (value || "").trim()) {
                onSubmit();
            }
        }
    };

    const canSend = (value || "").trim() && !isLoading;

    return (
        <div className="absolute bottom-0 left-0 right-0 p-4 md:p-8 pt-12 md:pt-24 bg-gradient-to-t from-[var(--bg-void)] via-[var(--bg-void)] to-transparent pointer-events-none">
            <div className="max-w-3xl mx-auto relative group pointer-events-auto">
                <div
                    className={`
                        relative flex items-end gap-3 p-2.5 rounded-[28px]
                        bg-black/40 backdrop-blur-xl border border-white/10
                        shadow-[0_10px_40px_-10px_rgba(0,0,0,0.5)]
                        transition-all duration-300 ease-out
                        focus-within:border-violet-500/50 focus-within:bg-black/60
                        focus-within:shadow-[0_0_30px_rgba(139,92,246,0.15)]
                        focus-within:translate-y-[-2px]
                    `}
                >
                    {/* Magic Icon */}
                    <div className="pb-3.5 pl-4 text-zinc-500 group-focus-within:text-violet-400 transition-colors duration-300">
                        <Command size={20} className="group-focus-within:drop-shadow-[0_0_8px_rgba(139,92,246,0.6)]" aria-hidden="true" />
                    </div>

                    {/* Textarea */}
                    <textarea
                        ref={textareaRef}
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={placeholder}
                        disabled={isLoading}
                        rows={1}
                        className={`
                            flex-1 resize-none bg-transparent
                            text-zinc-100 placeholder-zinc-500
                            outline-none text-base leading-7
                            max-h-[200px] py-3 font-sans
                            selection:bg-violet-500/30 selection:text-white
                            disabled:opacity-50 disabled:cursor-not-allowed
                            focus-visible:ring-0
                        `}
                        aria-label="Message input"
                        aria-describedby="input-hint"
                    />

                    {/* File Upload Button */}
                    <div className="pb-3.5 pr-2">
                        <FileUpload
                            chatId={chatId}
                            onFileUploaded={onFileUploaded}
                            onError={(error) => console.error("Upload error:", error)}
                        />
                    </div>

                    {/* Send/Stop Button */}
                    <div className="p-1.5 self-end">
                        {isLoading && onStop ? (
                            <button
                                onClick={onStop}
                                className="p-3 rounded-[20px] bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 border border-amber-500/20 transition-all flex items-center justify-center aspect-square focus:outline-none focus:ring-2 focus:ring-amber-500/50"
                                aria-label="Stop generation"
                            >
                                <Loader2 size={20} className="animate-spin" />
                            </button>
                        ) : (
                            <button
                                onClick={onSubmit}
                                disabled={!canSend}
                                className={`
                                    p-3 rounded-[20px] transition-all duration-300
                                    flex items-center justify-center aspect-square
                                    ${!canSend
                                        ? "bg-white/5 text-zinc-600 cursor-not-allowed"
                                        : "bg-violet-600 hover:bg-violet-500 text-white shadow-[0_0_20px_rgba(139,92,246,0.4)] hover:shadow-[0_0_25px_rgba(139,92,246,0.6)] transform hover:scale-110 active:scale-95"
                                    }
                                `}
                                aria-label="Send message"
                                aria-describedby="input-hint"
                            >
                                <Send size={20} className={canSend ? "translate-x-0.5" : ""} transition-transform />
                            </button>
                        )}
                    </div>
                </div>

                {/* Hint Text */}
                <div
                    id="input-hint"
                    className="absolute -bottom-6 left-0 right-0 text-center transition-opacity duration-300 opacity-60 group-hover:opacity-100"
                    aria-live="polite"
                >
                    <p className="text-[10px] text-zinc-500 font-medium tracking-widest uppercase flex items-center justify-center gap-2">
                        <span className="hidden md:inline-flex items-center gap-1">
                            <CornerDownLeft size={12} /> to send
                        </span>
                        <span className="hidden md:inline">•</span>
                        Shift + <CornerDownLeft size={12} className="inline" /> for new line
                        <span className="hidden md:inline">•</span>
                        <span className="hidden md:inline">MeGPT v1.0</span>
                    </p>
                </div>
            </div>
        </div>
    );
}
