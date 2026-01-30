"use client";

import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
  variant?: "text" | "circular" | "rectangular";
  width?: string | number;
  height?: string | number;
  animation?: "pulse" | "wave" | "none";
}

export function Skeleton({
  className,
  variant = "text",
  width,
  height,
  animation = "pulse",
}: SkeletonProps) {
  const variantStyles = {
    text: "rounded-md h-4",
    circular: "rounded-full",
    rectangular: "rounded-lg",
  };

  const animationStyles = {
    pulse: "animate-pulse",
    wave: "animate-shimmer",
    none: "",
  };

  return (
    <div
      className={cn(
        "bg-white/5",
        variantStyles[variant],
        animationStyles[animation],
        className
      )}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

// Pre-built skeleton components

interface ChatListSkeletonProps {
  count?: number;
  collapsed?: boolean;
}

export function ChatListSkeleton({ count = 5, collapsed = false }: ChatListSkeletonProps) {
  return (
    <div className="space-y-2 px-3 animate-in fade-in-50">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-transparent",
            collapsed ? "justify-center" : ""
          )}
        >
          <Skeleton variant="circular" width={18} height={18} />
          {!collapsed && (
            <>
              <Skeleton className="flex-1 h-4" />
              <Skeleton variant="rectangular" width={20} height={20} />
            </>
          )}
        </div>
      ))}
    </div>
  );
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-4 animate-in fade-in-50">
      <Skeleton variant="circular" width={36} height={36} />
      <div className="flex-1 space-y-3">
        <div className="flex items-center gap-2">
          <Skeleton width={100} height={16} />
          <Skeleton width={60} height={12} className="opacity-50" />
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    </div>
  );
}

export function EmailListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-4 animate-in fade-in-50">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 rounded-xl bg-white/5 border border-white/5">
          <div className="flex items-start gap-4">
            <Skeleton variant="circular" width={40} height={40} />
            <div className="flex-1 space-y-3">
              <div className="flex items-center justify-between">
                <Skeleton width={150} height={16} />
                <Skeleton width={100} height={12} className="opacity-50" />
              </div>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CalendarEventSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3 animate-in fade-in-50">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 rounded-xl bg-white/5 border border-white/5">
          <div className="flex items-start gap-4">
            <div className="text-center">
              <Skeleton width={40} height={24} />
              <Skeleton width={40} height={16} className="mt-1" />
            </div>
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <div className="flex items-center gap-2 mt-3">
                <Skeleton variant="circular" width={16} height={16} />
                <Skeleton className="h-3 w-24" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function StatsCardSkeleton() {
  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/5 animate-in fade-in-50">
      <div className="flex items-center justify-between mb-4">
        <Skeleton variant="circular" width={40} height={40} />
        <Skeleton width={80} height={20} />
      </div>
      <Skeleton className="h-10 w-24 mb-2" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}
