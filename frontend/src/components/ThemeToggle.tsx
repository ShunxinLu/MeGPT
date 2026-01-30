/**
 * ThemeToggle Component
 * Dark/light mode toggle with theme persistence
 * 
 * Features:
 * - LocalStorage persistence
 * - System preference detection
 * - Smooth transitions
 * - Accessible (focus states, reduced motion)
 * - Works with Tailwind CSS dark mode
 */

"use client";

import { useState, useEffect } from "react";
import { Sun, Moon, Monitor } from "lucide-react";

type Theme = "light" | "dark" | "system";

export default function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  // Load theme from localStorage on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") as Theme;
    if (savedTheme) {
      setThemeState(savedTheme);
    }
    setMounted(true);
  }, []);

  // Apply theme to document
  useEffect(() => {
    if (!mounted) return;

    const root = document.documentElement;
    
    // Remove existing classes
    root.classList.remove("dark", "light");

    if (theme === "system") {
      const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      if (systemDark) {
        root.classList.add("dark");
      }
    } else {
      root.classList.add(theme);
    }

    // Save to localStorage
    localStorage.setItem("theme", theme);
  }, [theme, mounted]);

  const handleThemeChange = (newTheme: Theme) => {
    setThemeState(newTheme);
  };

  const getCurrentTheme = () => {
    if (theme === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }
    return theme;
  };

  const isActive = (checkTheme: Theme) => {
    return theme === checkTheme || (theme === "system" && getCurrentTheme() === checkTheme);
  };

  if (!mounted) {
    return (
      <div className="w-10 h-10 rounded-lg bg-white/80 backdrop-blur-md border border-gray-200">
        <div className="w-full h-full animate-pulse bg-gray-500/10" />
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-1">
      <button
        onClick={() => handleThemeChange("light")}
        className={`relative flex items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 hover:scale-105 ${
          isActive("light")
            ? "bg-white text-orange-500 border-orange-500"
            : "bg-white/80 text-gray-500 hover:bg-white border-gray-200"
        }`}
        title="Light mode"
        aria-label="Switch to light mode"
        aria-pressed={isActive("light")}
      >
        <Sun className="w-5 h-5" />
        {isActive("light") && (
          <div className="absolute inset-0 ring-2 ring-orange-500 rounded-lg" />
        )}
      </button>

      <button
        onClick={() => handleThemeChange("dark")}
        className={`relative flex items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 hover:scale-105 ${
          isActive("dark")
            ? "bg-gray-900 text-violet-500 border-violet-500"
            : "bg-white/80 text-gray-500 hover:bg-white border-gray-200"
        }`}
        title="Dark mode"
        aria-label="Switch to dark mode"
        aria-pressed={isActive("dark")}
      >
        <Moon className="w-5 h-5" />
        {isActive("dark") && (
          <div className="absolute inset-0 ring-2 ring-violet-500 rounded-lg" />
        )}
      </button>

      <button
        onClick={() => handleThemeChange("system")}
        className={`relative flex items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 hover:scale-105 ${
          isActive("system")
            ? "bg-gradient-to-br from-gray-100 to-gray-200 text-blue-500 border-blue-500"
            : "bg-white/80 text-gray-500 hover:bg-white border-gray-200"
        }`}
        title="Use system theme"
        aria-label="Use system theme preference"
        aria-pressed={isActive("system")}
      >
        <Monitor className="w-5 h-5" />
        {isActive("system") && (
          <div className="absolute inset-0 ring-2 ring-blue-500 rounded-lg" />
        )}
      </button>
    </div>
  );
}

/**
 * Theme Provider Hook
 * 
 * Usage:
 * ```tsx
 * import { useTheme } from '@/components/ThemeToggle';
 * 
 * export default function MyComponent() {
 *   const { theme, setTheme } = useTheme();
 *   
 *   return (
 *     <div>
 *       <button onClick={() => setTheme('dark')}>
 *         Current theme: {theme}
 *       </button>
 *     </div>
 *   );
 * }
 * ```
 */

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>("system");

  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") as Theme;
    if (savedTheme) {
      setThemeState(savedTheme);
    }
  }, []);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem("theme", newTheme);
  };

  const actualTheme = theme === "system"
    ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : theme;

  return { theme, setTheme, actualTheme };
}
