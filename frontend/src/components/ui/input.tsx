"use client";

import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ReactNode;
  error?: string;
}

export function Input({ icon, error, className = "", ...props }: InputProps) {
  return (
    <div className="relative">
      {icon && (
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
          {icon}
        </div>
      )}
      <input
        className={`
          w-full h-10 px-4 ${icon ? "pl-10" : ""}
          rounded-xl
          input-glass
          text-sm
          placeholder:text-muted-foreground
          ${error ? "border-red-500/50 focus:border-red-500" : ""}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="mt-1 text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: string;
}

export function Textarea({ error, className = "", ...props }: TextareaProps) {
  return (
    <div className="relative">
      <textarea
        className={`
          w-full p-4
          rounded-xl
          input-glass
          text-sm
          placeholder:text-muted-foreground
          resize-none
          ${error ? "border-red-500/50 focus:border-red-500" : ""}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="mt-1 text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}

export default Input;
