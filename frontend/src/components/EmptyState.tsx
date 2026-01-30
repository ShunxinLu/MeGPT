"use client";

import { LucideIcon, Mail, Calendar, MessageSquare, Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
  className?: string;
}

export function EmptyState({
  icon: Icon = MessageSquare,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-16 px-4 text-center animate-in fade-in-50",
        className
      )}
    >
      <div className="relative mb-6">
        <div className="absolute inset-0 bg-violet-500/20 blur-3xl rounded-full" />
        <div className="relative w-20 h-20 rounded-2xl bg-black/40 border border-white/5 flex items-center justify-center">
          <Icon size={32} className="text-violet-400" />
        </div>
      </div>
      <h3 className="text-xl font-semibold text-white mb-2">{title}</h3>
      <p className="text-zinc-400 max-w-sm mb-6">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-violet-500/20 hover:bg-violet-500/30 text-violet-300 hover:text-violet-200 border border-violet-500/20 hover:border-violet-500/30 transition-all hover:scale-105"
        >
          {action.icon && <action.icon size={16} />}
          <span className="font-medium">{action.label}</span>
        </button>
      )}
    </div>
  );
}

// Pre-built empty states for specific domains

interface EmptyChatStateProps {
  onNewChat?: () => void;
}

export function EmptyChatState({ onNewChat }: EmptyChatStateProps) {
  const suggestions = [
    { text: "What do you remember about me?", icon: Search },
    { text: "Help me brainstorm ideas", icon: MessageSquare },
    { text: "Explain a complex topic", icon: MessageSquare },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 animate-in fade-in-50">
      <div className="relative mb-8">
        <div className="absolute inset-0 bg-violet-500/20 blur-3xl rounded-full animate-pulse" />
        <div className="relative w-24 h-24 rounded-3xl bg-black/40 border border-white/5 flex items-center justify-center shadow-[0_0_50px_rgba(139,92,246,0.15)]">
          <MessageSquare size={42} className="text-violet-400 drop-shadow-[0_0_15px_rgba(139,92,246,0.8)]" />
        </div>
      </div>
      <h2 className="text-4xl font-bold mb-3">
        <span className="gradient-text">MeGPT</span>
      </h2>
      <p className="text-zinc-400 max-w-md mb-10 text-center leading-relaxed">
        Your persistent neural memory. I recall our past conversations to build deeper context over time.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl w-full mb-8">
        {suggestions.map((suggestion, i) => (
          <button
            key={suggestion.text}
            onClick={() => onNewChat?.()}
            className="flex items-center justify-center gap-3 px-4 py-3.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-violet-500/30 text-sm text-zinc-300 transition-all hover:-translate-y-1 hover:shadow-lg hover:shadow-violet-500/10"
            style={{ animationDelay: `${i * 100}ms` }}
          >
            <suggestion.icon size={16} className="text-violet-400" />
            <span>{suggestion.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function EmptyEmailState({ onCompose }: { onCompose?: () => void }) {
  return (
    <EmptyState
      icon={Mail}
      title="No emails yet"
      description="Connect your email account to start receiving and organizing messages."
      action={
        onCompose
          ? {
              label: "Connect Email",
              onClick: onCompose,
              icon: Mail,
            }
          : undefined
      }
    />
  );
}

export function EmptyCalendarState({ onNewEvent }: { onNewEvent?: () => void }) {
  return (
    <EmptyState
      icon={Calendar}
      title="No upcoming events"
      description="Your calendar is clear. Create an event to get started."
      action={
        onNewEvent
          ? {
              label: "Create Event",
              onClick: onNewEvent,
              icon: Calendar,
            }
          : undefined
      }
    />
  );
}

export function EmptySearchState({ query }: { query: string }) {
  return (
    <EmptyState
      icon={Search}
      title="No results found"
      description={`We couldn't find anything matching "${query}". Try a different search term.`}
    />
  );
}

export function EmptyMemoryState({ onAddMemory }: { onAddMemory?: () => void }) {
  return (
    <EmptyState
      icon={MessageSquare}
      title="No memories yet"
      description="Start a conversation to build your persistent memory. I'll remember what matters."
      action={
        onAddMemory
          ? {
              label: "Start Chat",
              onClick: onAddMemory,
              icon: MessageSquare,
            }
          : undefined
      }
    />
  );
}
