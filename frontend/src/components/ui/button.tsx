"use client";

import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";

type ButtonVariant = "neon" | "glass" | "ghost" | "destructive" | "success";
type ButtonSize = "sm" | "default" | "lg" | "xl" | "icon";

interface ButtonProps extends Omit<HTMLMotionProps<"button">, "ref"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  neon: "btn-neon text-white font-semibold",
  glass: "btn-glass",
  ghost: "btn-ghost",
  destructive: "bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30",
  success: "bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/30",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs rounded-lg",
  default: "h-10 px-4 text-sm rounded-xl",
  lg: "h-12 px-6 text-base rounded-xl",
  xl: "h-14 px-8 text-lg rounded-2xl",
  icon: "h-10 w-10 rounded-xl",
};

export function Button({
  variant = "glass",
  size = "default",
  loading = false,
  children,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  return (
    <motion.button
      whileHover={{ scale: disabled || loading ? 1 : 1.02 }}
      whileTap={{ scale: disabled || loading ? 1 : 0.98 }}
      className={`
        inline-flex items-center justify-center gap-2
        font-medium cursor-pointer
        disabled:opacity-50 disabled:cursor-not-allowed
        ${variantClasses[variant]}
        ${sizeClasses[size]}
        ${className}
      `}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <>
          <div className="spinner w-4 h-4" />
          <span>Loading...</span>
        </>
      ) : (
        children
      )}
    </motion.button>
  );
}

export default Button;
