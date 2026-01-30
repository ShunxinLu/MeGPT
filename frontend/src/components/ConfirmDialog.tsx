"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import { AlertTriangle, Info, CheckCircle, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ConfirmDialogType = "danger" | "warning" | "info" | "success";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  type?: ConfirmDialogType;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}

const icons = {
  danger: <AlertTriangle size={24} className="text-red-400" />,
  warning: <AlertTriangle size={24} className="text-amber-400" />,
  info: <Info size={24} className="text-cyan-400" />,
  success: <CheckCircle size={24} className="text-emerald-400" />,
};

const bgColors = {
  danger: "from-red-500/10 to-red-500/5 border-red-500/20",
  warning: "from-amber-500/10 to-amber-500/5 border-amber-500/20",
  info: "from-cyan-500/10 to-cyan-500/5 border-cyan-500/20",
  success: "from-emerald-500/10 to-emerald-500/5 border-emerald-500/20",
};

const buttonColors = {
  danger: "bg-red-500/20 hover:bg-red-500/30 text-red-300 border-red-500/30",
  warning: "bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border-amber-500/30",
  info: "bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border-cyan-500/30",
  success: "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border-emerald-500/30",
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  type = "danger",
  onConfirm,
  onCancel,
  children,
}: ConfirmDialogProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  // Focus confirm button when dialog opens
  useEffect(() => {
    if (open && confirmButtonRef.current) {
      confirmButtonRef.current.focus();
    }
  }, [open]);

  // Handle escape key
  useEffect(() => {
    if (!open) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby="dialog-description"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-in fade-in-50"
        onClick={onCancel}
      />

      {/* Dialog */}
      <div className="relative w-full max-w-md animate-in zoom-in-95 fade-in-50 slide-in-from-bottom-2">
        <div
          className={cn(
            "p-6 rounded-2xl backdrop-blur-xl border shadow-2xl bg-gradient-to-br",
            bgColors[type]
          )}
        >
          {/* Header */}
          <div className="flex items-start gap-4 mb-4">
            <div className="p-3 rounded-xl bg-black/30">{icons[type]}</div>
            <div className="flex-1">
              <h2
                id="dialog-title"
                className="text-lg font-semibold text-white mb-1"
              >
                {title}
              </h2>
              <p
                id="dialog-description"
                className="text-sm text-zinc-400 leading-relaxed"
              >
                {message}
              </p>
            </div>
            <button
              onClick={onCancel}
              className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
              aria-label="Close dialog"
            >
              <X size={18} className="text-zinc-400 hover:text-zinc-200" />
            </button>
          </div>

          {/* Optional children */}
          {children && (
            <div className="mb-6 p-4 rounded-xl bg-black/20 border border-white/5">
              {children}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={onCancel}
              className="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white border border-white/5 transition-all"
            >
              {cancelLabel}
            </button>
            <button
              ref={confirmButtonRef}
              onClick={onConfirm}
              className={cn(
                "px-4 py-2.5 rounded-xl border transition-all hover:scale-105",
                buttonColors[type]
              )}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Confirm hook for easy usage
interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  type?: ConfirmDialogType;
}

let confirmResolve: ((value: boolean) => void) | null = null;
let confirmOptions: ConfirmOptions | null = null;
let confirmListeners: Set<(options: ConfirmOptions | null) => void> = new Set();

export const confirm = {
  show: (options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      confirmOptions = options;
      confirmResolve = resolve;
      confirmListeners.forEach((listener) => listener(options));
    });
  },
  confirm: () => {
    if (confirmResolve) {
      confirmResolve(true);
      confirmResolve = null;
      confirmOptions = null;
      confirmListeners.forEach((listener) => listener(null));
    }
  },
  cancel: () => {
    if (confirmResolve) {
      confirmResolve(false);
      confirmResolve = null;
      confirmOptions = null;
      confirmListeners.forEach((listener) => listener(null));
    }
  },
  subscribe: (listener: (options: ConfirmOptions | null) => void) => {
    confirmListeners.add(listener);
    return () => confirmListeners.delete(listener);
  },
  getOptions: () => confirmOptions,
};

// Confirm Dialog Provider component
export function ConfirmDialogProvider() {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);

  useEffect(() => {
    const unsubscribe = confirm.subscribe((opts) => setOptions(opts));
    return () => {
      unsubscribe();
    };
  }, []);

  return (
    <ConfirmDialog
      open={options !== null}
      title={options?.title || ""}
      message={options?.message || ""}
      confirmLabel={options?.confirmLabel}
      cancelLabel={options?.cancelLabel}
      type={options?.type}
      onConfirm={() => confirm.confirm()}
      onCancel={() => confirm.cancel()}
    />
  );
}
