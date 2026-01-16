"use client";

import { useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";

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
    placeholder = "Message MeGPT...",
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
        <div className="fixed bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#0f0f0f] via-[#0f0f0f] to-transparent pointer-events-none">
            <div className="max-w-3xl mx-auto pointer-events-auto">
                <div
                    className={`
            flex items-end gap-3 p-3 rounded-3xl
            bg-[#1e1e1e] border border-[#3c4043]
            shadow-xl shadow-black/20
            transition-all duration-200
            focus-within:border-[#8ab4f8]
          `}
                >
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
              text-[#e8eaed] placeholder-[#9aa0a6]
              outline-none text-base leading-6
              max-h-[200px] px-2 py-1
            `}
                    />

                    {/* Send Button */}
                    <button
                        onClick={onSubmit}
                        disabled={isLoading || !(value || "").trim()}
                        className={`
              p-3 rounded-full transition-all duration-200
              ${(value || "").trim() && !isLoading
                                ? "bg-[#8ab4f8] hover:bg-[#aecbfa] text-[#0f0f0f]"
                                : "bg-[#3c4043] text-[#9aa0a6] cursor-not-allowed"
                            }
            `}
                        aria-label="Send message"
                    >
                        {isLoading ? (
                            <Loader2 size={20} className="animate-spin" />
                        ) : (
                            <Send size={20} />
                        )}
                    </button>
                </div>

                {/* Disclaimer */}
                <p className="text-center text-xs text-[#9aa0a6] mt-3">
                    MeGPT runs locally on your machine. Your data stays private.
                </p>
            </div>
        </div>
    );
}
