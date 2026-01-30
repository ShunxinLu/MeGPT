"use client";

import { useState } from "react";
import UnifiedNavigation from "@/components/UnifiedNavigation";

/**
 * Unified Dashboard Page
 * Main entry point for the integrated assistant
 * Provides quick access to Chat, Email, and Calendar domains
 */
type QuickStat = {
  label: string;
  value: number;
  trend: "up" | "down" | "neutral";
  icon: React.ReactNode;
};

const QUICK_STATS: QuickStat[] = [
  {
    label: "Active Chats",
    value: 12,
    trend: "neutral",
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    label: "Unread Emails",
    value: 3,
    trend: "down",
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M22 6l-10 7L2 6" />
      </svg>
    ),
  },
  {
    label: "Upcoming Events",
    value: 2,
    trend: "neutral",
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
  },
];

const getTrendIcon = (trend: QuickStat["trend"]) => {
  switch (trend) {
    case "up":
      return <span className="text-success">↑</span>;
    case "down":
      return <span className="text-error">↓</span>;
    default:
      return <span className="text-tertiary">→</span>;
  }
};

export default function DashboardPage() {
  const [stats] = useState(QUICK_STATS);

  return (
    <>
      <UnifiedNavigation />
      <main className="min-h-screen bg-gradient-to-br from-background to-background/95 pt-24 px-6 pb-12">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-accent-primary">
              Dashboard
            </h1>
            <p className="text-tertiary mt-2">Overview of your AI assistant activity</p>
          </div>

          {/* Quick Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {stats.map((stat) => (
              <div
                key={stat.label}
                className="glass-card p-6 rounded-2xl border border-glass shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="p-3 rounded-xl bg-primary/10">{stat.icon}</div>
                  <span className="text-sm font-medium text-tertiary">{getTrendIcon(stat.trend)}</span>
                </div>
                <h3 className="text-3xl font-bold text-primary">{stat.value}</h3>
                <p className="text-sm text-tertiary mt-1">{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="glass-card p-6 rounded-2xl border border-glass">
              <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
              <div className="space-y-3">
                <a
                  href="/"
                  className="flex items-center p-3 rounded-lg bg-primary/5 hover:bg-primary/10 transition-colors"
                >
                  <span className="mr-3">💬</span>
                  <span className="font-medium">Start New Chat</span>
                </a>
                <a
                  href="/emails"
                  className="flex items-center p-3 rounded-lg bg-accent-primary/5 hover:bg-accent-primary/10 transition-colors"
                >
                  <span className="mr-3">📧</span>
                  <span className="font-medium">Check Emails</span>
                </a>
                <a
                  href="/calendar"
                  className="flex items-center p-3 rounded-lg bg-accent-tertiary/5 hover:bg-accent-tertiary/10 transition-colors"
                >
                  <span className="mr-3">📅</span>
                  <span className="font-medium">View Calendar</span>
                </a>
              </div>
            </div>

            {/* System Status */}
            <div className="glass-card p-6 rounded-2xl border border-glass">
              <h2 className="text-xl font-semibold mb-4">System Status</h2>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-background/50">
                  <span className="text-tertiary">AI Model</span>
                  <span className="text-success flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                    Online
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-background/50">
                  <span className="text-tertiary">Memory System</span>
                  <span className="text-success flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                    Active
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-background/50">
                  <span className="text-tertiary">Vector Database</span>
                  <span className="text-success flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                    Connected
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      <footer className="glass border-t border-glass bg-white/95 backdrop-blur-md px-6 py-4 mt-auto">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="text-sm text-tertiary">
              <span>© 2025-2026 Unified AI Assistant</span>
              <span className="ml-4">Privacy-first • Local LLM</span>
            </div>
            <div className="text-sm text-tertiary">
              <span>System Status:</span>
              <span className="ml-2 text-success">● All Systems Operational</span>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
