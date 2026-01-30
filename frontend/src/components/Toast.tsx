"use client";

import { useEffect, useState } from "react";
import { CheckCircle, AlertCircle, XCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

const ToastItem = ({ toast, onRemove }: ToastItemProps) => {
  const [isLeaving, setIsLeaving] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLeaving(true);
      setTimeout(() => onRemove(toast.id), 300);
    }, toast.duration || 3000);

    return () => clearTimeout(timer);
  }, [toast, onRemove]);

  const icons = {
    success: <CheckCircle size={18} className="text-emerald-400" />,
    error: <XCircle size={18} className="text-red-400" />,
    warning: <AlertCircle size={18} className="text-amber-400" />,
    info: <Info size={18} className="text-cyan-400" />,
  };

  const bgColors = {
    success: "from-emerald-500/10 to-emerald-500/5 border-emerald-500/20",
    error: "from-red-500/10 to-red-500/5 border-red-500/20",
    warning: "from-amber-500/10 to-amber-500/5 border-amber-500/20",
    info: "from-cyan-500/10 to-cyan-500/5 border-cyan-500/20",
  };

  return (
    <div
      className={`
        flex items-center gap-3 px-4 py-3 rounded-xl backdrop-blur-md
        bg-gradient-to-r ${bgColors[toast.type]} border shadow-lg
        transition-all duration-300 min-w-[300px] max-w-md
        ${isLeaving ? "opacity-0 translate-x-full" : "opacity-100 translate-x-0"}
      `}
      role="alert"
      aria-live={toast.type === "error" ? "assertive" : "polite"}
    >
      {icons[toast.type]}
      <span className="flex-1 text-sm text-zinc-200 font-medium">{toast.message}</span>
      <button
        onClick={() => {
          setIsLeaving(true);
          setTimeout(() => onRemove(toast.id), 300);
        }}
        className="p-1 hover:bg-white/10 rounded-lg transition-colors"
        aria-label="Close notification"
      >
        <X size={14} className="text-zinc-400 hover:text-zinc-200" />
      </button>
    </div>
  );
};

interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: string) => void;
}

export default function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div
      className="fixed bottom-24 right-4 z-[100] flex flex-col gap-2 pointer-events-none"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastItem toast={toast} onRemove={onRemove} />
        </div>
      ))}
    </div>
  );
}

// Toast hook for easy usage
let toastListeners: Set<(toasts: Toast[]) => void> = new Set();
let toastList: Toast[] = [];

export const toast = {
  show: (message: string, type: ToastType = "info", duration?: number) => {
    const id = Math.random().toString(36).substring(7);
    const newToast: Toast = { id, type, message, duration };
    toastList = [...toastList, newToast];
    toastListeners.forEach((listener) => listener(toastList));
    return id;
  },
  success: (message: string, duration?: number) => toast.show(message, "success", duration),
  error: (message: string, duration?: number) => toast.show(message, "error", duration),
  warning: (message: string, duration?: number) => toast.show(message, "warning", duration),
  info: (message: string, duration?: number) => toast.show(message, "info", duration),
  remove: (id: string) => {
    toastList = toastList.filter((t) => t.id !== id);
    toastListeners.forEach((listener) => listener(toastList));
  },
  subscribe: (listener: (toasts: Toast[]) => void) => {
    toastListeners.add(listener);
    listener(toastList);
    return () => toastListeners.delete(listener);
  },
};
