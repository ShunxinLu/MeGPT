"use client";

import { useState } from "react";
import {
  MessageSquare,
  Mail,
  Calendar,
  FileText,
  Settings,
  Bell
} from "lucide-react";
import { usePathname } from "next/navigation";

/**
 * Unified Navigation Component
 * Switches between Chat, Email, and Calendar domains
 * Uses modern bento grid layout for quick stats
 */
type NavItem = {
  id: string;
  label: string;
  icon: React.ReactNode;
  href: string;
  badge?: number;
  count?: number;
  domain: "chat" | "email" | "calendar" | "documents" | "settings";
};

const NAV_ITEMS: NavItem[] = [
  {
    id: "chat",
    label: "Chat",
    icon: <MessageSquare className="w-5 h-5" />,
    href: "/",
    domain: "chat",
  },
  {
    id: "emails",
    label: "Emails",
    icon: <Mail className="w-5 h-5" />,
    href: "/emails",
    badge: 3, // TODO: Fetch from API
    domain: "email",
  },
  {
    id: "calendar",
    label: "Calendar",
    icon: <Calendar className="w-5 h-5" />,
    href: "/calendar",
    count: 2, // TODO: Fetch from API
    domain: "calendar",
  },
  {
    id: "documents",
    label: "Knowledge",
    icon: <FileText className="w-5 h-5" />,
    href: "/documents",
    domain: "documents",
  },
  {
    id: "settings",
    label: "Settings",
    icon: <Settings className="w-5 h-5" />,
    href: "/settings",
    domain: "settings",
  },
];

export default function UnifiedNavigation() {
  const pathname = usePathname();
  const [unreadEmails, setUnreadEmails] = useState(0);
  const [upcomingEvents, setUpcomingEvents] = useState(0);

  const getActiveClass = (item: NavItem) => {
    const isActive = pathname === item.href;
    return isActive
      ? "bg-primary text-white border-primary"
      : "text-primary hover:bg-primary/10 border-transparent";
  };

  const getDomainColor = (domain: string) => {
    switch (domain) {
      case "chat":
        return "border-primary";
      case "email":
        return "border-accent-primary";
      case "calendar":
        return "border-accent-tertiary";
      case "documents":
        return "border-violet-500";
      case "settings":
        return "border-border";
      default:
        return "border-transparent";
    }
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-md border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between py-4">
          {/* Logo/Brand */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-violet-500/30 to-fuchsia-500/30 flex items-center justify-center">
              <span className="text-xl font-bold text-white">M</span>
              <span className="text-lg font-medium text-white/90">eGPT</span>
            </div>
            <div className="text-sm font-medium text-tertiary">Pro Unified Assistant</div>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center space-x-1">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.id}
                href={item.href}
                className={`group flex items-center space-x-2 px-4 py-2 rounded-lg transition-all duration-200 ease-out hover:scale-105 ${getActiveClass(item)}`}
              >
                <span className={`relative transition-colors duration-200 ${getDomainColor(item.domain)}`}>
                  {item.icon}
                </span>
                <span className="font-medium">{item.label}</span>
                
                {/* Badge or Count */}
                {(item.badge !== undefined || item.count !== undefined) && (
                  <span className="ml-2 flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-xs font-medium">
                    {item.badge !== undefined && item.badge}
                    {item.count !== undefined && item.count}
                  </span>
                )}
              </a>
            ))}
          </div>

          {/* Quick Stats Bento Grid */}
          <div className="hidden lg:grid grid-cols-3 gap-3 ml-4">
            {/* Chat Activity */}
            <div className="bg-gradient-to-br from-violet-500/10 to-violet-500/5 p-4 rounded-2xl border border-glass shadow-sm">
              <div className="flex items-center space-x-2 mb-2">
                <MessageSquare className="w-5 h-5 text-primary" />
                <div>
                  <div className="text-sm font-medium text-tertiary">Active Chats</div>
                  <div className="text-2xl font-bold text-primary">12</div>
                </div>
              </div>
              <div className="h-32 bg-gradient-to-br from-primary/5 to-transparent rounded-lg flex items-center justify-center relative overflow-hidden">
                {/* Sparkline graph visualization */}
                <svg className="absolute bottom-0 left-0 w-full h-16" viewBox="0 0 100 32" fill="none">
                  <path
                    d="M0,32 C10,32 L10,32 C20,32 L30,32 C40,32 L50,32 L60,32 L70,32 L80,32 L90,32"
                    stroke="url(#gradient)"
                    strokeWidth="2"
                    fill="none"
                  />
                  <defs>
                    <linearGradient id="gradient" x1="0" y1="0" x2="100" y2="0">
                      <stop offset="0%" stopColor="rgba(139, 92, 246, 0.3)" />
                      <stop offset="100%" stopColor="rgba(139, 92, 246, 0.1)" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>

            {/* Email Activity */}
            <div className="bg-gradient-to-br from-accent-primary/10 to-accent-tertiary/5 p-4 rounded-2xl border border-glass shadow-sm">
              <div className="flex items-center space-x-2 mb-2">
                <Mail className="w-5 h-5 text-accent-primary" />
                <div>
                  <div className="text-sm font-medium text-tertiary">Unread</div>
                  <div className="text-2xl font-bold text-accent-primary">{unreadEmails}</div>
                </div>
              </div>
              <div className="h-32 bg-gradient-to-br from-accent-primary/5 to-transparent rounded-lg flex items-center justify-center relative overflow-hidden">
                <svg className="absolute bottom-0 left-0 w-full h-16" viewBox="0 0 100 32" fill="none">
                  <path
                    d="M0,32 Q10,32 L30,32 Q40,32 Q50,32 Q60,32 Q70,32 Q80,32 Q90,32"
                    stroke="url(#emailGradient)"
                    strokeWidth="2"
                    fill="none"
                  />
                  <defs>
                    <linearGradient id="emailGradient" x1="0" y1="0" x2="100" y2="0">
                      <stop offset="0%" stopColor="rgba(139, 92, 246, 0.3)" />
                      <stop offset="100%" stopColor="rgba(139, 92, 246, 0.1)" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>

            {/* Calendar Activity */}
            <div className="bg-gradient-to-br from-accent-tertiary/10 to-accent-tertiary/5 p-4 rounded-2xl border border-glass shadow-sm">
              <div className="flex items-center space-x-2 mb-2">
                <Calendar className="w-5 h-5 text-accent-tertiary" />
                <div>
                  <div className="text-sm font-medium text-tertiary">Upcoming</div>
                  <div className="text-2xl font-bold text-accent-tertiary">{upcomingEvents}</div>
                </div>
              </div>
              <div className="h-32 bg-gradient-to-br from-accent-tertiary/5 to-transparent rounded-lg flex items-center justify-center relative overflow-hidden">
                <svg className="absolute bottom-0 left-0 w-full h-16" viewBox="0 0 100 32" fill="none">
                  <circle cx="50" cy="16" r="12" fill="none" stroke="url(#calendarGradient)" strokeWidth="2" />
                  <defs>
                    <linearGradient id="calendarGradient" x1="0" y1="0" x2="100" y2="0">
                      <stop offset="0%" stopColor="rgba(236, 72, 153, 0.3)" />
                      <stop offset="100%" stopColor="rgba(236, 72, 153, 0.1)" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>
          </div>

          {/* Theme Toggle */}
          <button
            aria-label="Toggle theme"
            className="p-2 rounded-lg bg-transparent hover:bg-primary/10 border border-glass transition-all duration-200 ease-out"
            >
            <span className="text-sm font-medium text-tertiary">Theme</span>
          </button>
        </div>
      </div>
    </nav>
  );
}
