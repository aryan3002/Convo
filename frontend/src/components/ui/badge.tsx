"use client";

import React from "react";

type BadgeVariant = "neon" | "success" | "warning" | "destructive" | "secondary" | "outline";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  neon: "badge-neon",
  success: "badge-success",
  warning: "badge-warning",
  destructive: "badge-destructive",
  secondary: "bg-secondary/50 text-muted-foreground border border-border",
  outline: "bg-transparent border border-border text-muted-foreground",
};

export function Badge({ variant = "secondary", children, className = "" }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center gap-1
        px-2.5 py-1 text-xs font-medium
        rounded-full
        ${variantClasses[variant]}
        ${className}
      `}
    >
      {children}
    </span>
  );
}

export default Badge;
