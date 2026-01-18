"use client";

import { useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2, Sparkles, Command } from "lucide-react";

interface InputAreaProps {
    value: string;
    onChange: (value: string) => void;
    onSubmit: () => void;
    isLoading: boolean;
    placeholder?: string;
}

export default function InputArea({
    value,
    onChange,
    onSubmit,
    isLoading,
    placeholder = "Ask anything...",
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

    // Focus on mount
    useEffect(() => {
        textareaRef.current?.focus();
    }, []);

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!isLoading && (value || "").trim()) {
                onSubmit();
            }
        }
    };

    return (
        <div className="absolute bottom-0 left-0 right-0 p-8 pt-24 bg-gradient-to-t from-[var(--bg-void)] via-[var(--bg-void)] to-transparent pointer-events-none">
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
                        <Command size={20} className="group-focus-within:drop-shadow-[0_0_8px_rgba(139,92,246,0.6)]" />
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
                        `}
                    />

                    {/* Send Button */}
                    <div className="p-1.5 self-end">
                        <button
                            onClick={onSubmit}
                            disabled={isLoading || !(value || "").trim()}
                            className={`
                                p-3 rounded-[20px] transition-all duration-300
                                flex items-center justify-center aspect-square
                                ${isLoading
                                    ? "bg-zinc-800 text-zinc-400 cursor-not-allowed"
                                    : (value || "").trim()
                                        ? "bg-violet-600 hover:bg-violet-500 text-white shadow-[0_0_20px_rgba(139,92,246,0.4)] hover:shadow-[0_0_25px_rgba(139,92,246,0.6)] transform hover:scale-110 active:scale-95"
                                        : "bg-white/5 text-zinc-500 hover:bg-white/10"
                                }
                            `}
                            aria-label="Send message"
                        >
                            {isLoading ? (
                                <Loader2 size={20} className="animate-spin" />
                            ) : (
                                <Send size={20} className={`${(value || "").trim() ? "translate-x-0.5" : ""} transition-transform`} />
                            )}
                        </button>
                    </div>
                </div>

                {/* Disclaimer */}
                <div className="absolute -bottom-6 left-0 right-0 text-center transition-opacity duration-300 opacity-60 group-hover:opacity-100">
                    <p className="text-[10px] text-zinc-500 font-medium tracking-widest uppercase">
                        MeGPT v1.0 • Private & Local • Long-term Memory
                    </p>
                </div>
            </div>
        </div>
    );
}
