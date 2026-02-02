"use client";

import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Mail,
  Calendar,
  Activity,
  Heart,
} from "lucide-react";

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
  domain: "chat" | "email" | "calendar" | "health";
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
    domain: "email",
  },
  {
    id: "calendar",
    label: "Calendar",
    icon: <Calendar className="w-5 h-5" />,
    href: "/calendar",
    domain: "calendar",
  },
  {
    id: "health",
    label: "Health",
    icon: <Heart className="w-5 h-5" />,
    href: "/health",
    domain: "health",
  },
];

export default function UnifiedNavigation() {
  const pathname = usePathname();

  const getActiveClass = (item: NavItem) => {
    const isActive = pathname === item.href;
    return isActive
      ? "bg-violet-500/20 text-violet-300 border border-violet-500/30"
      : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200 border border-transparent";
  };

  const getDomainColor = (domain: string) => {
    switch (domain) {
      case "chat":
        return "border-primary";
      case "email":
        return "border-accent-primary";
      case "calendar":
        return "border-accent-tertiary";
      case "health":
        return "border-red-500";
      default:
        return "border-transparent";
    }
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-black/80 backdrop-blur-xl border-b border-white/5">
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
                <span className="font-medium text-sm">{item.label}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}
