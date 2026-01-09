"use client";

import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";

interface CardProps extends Omit<HTMLMotionProps<"div">, "ref"> {
  glass?: boolean;
  hover?: boolean;
  gradient?: boolean;
  children: React.ReactNode;
}

export function Card({
  glass = true,
  hover = false,
  gradient = false,
  children,
  className = "",
  ...props
}: CardProps) {
  const baseClasses = "rounded-2xl overflow-hidden";
  const glassClasses = glass ? "glass-card" : "bg-card border border-border";
  const hoverClasses = hover ? "hover-lift hover:shadow-neon transition-all duration-300" : "";
  const gradientClasses = gradient ? "gradient-border" : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.25, 0.1, 0.25, 1] }}
      className={`${baseClasses} ${glassClasses} ${hoverClasses} ${gradientClasses} ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  );
}

interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export function CardHeader({ children, className = "" }: CardHeaderProps) {
  return (
    <div className={`p-6 pb-0 ${className}`}>
      {children}
    </div>
  );
}

interface CardTitleProps {
  children: React.ReactNode;
  className?: string;
  gradient?: boolean;
}

export function CardTitle({ children, className = "", gradient = false }: CardTitleProps) {
  return (
    <h3 className={`text-xl font-semibold ${gradient ? "gradient-text" : "text-foreground"} ${className}`}>
      {children}
    </h3>
  );
}

interface CardDescriptionProps {
  children: React.ReactNode;
  className?: string;
}

export function CardDescription({ children, className = "" }: CardDescriptionProps) {
  return (
    <p className={`text-sm text-muted-foreground mt-1 ${className}`}>
      {children}
    </p>
  );
}

interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export function CardContent({ children, className = "" }: CardContentProps) {
  return (
    <div className={`p-6 ${className}`}>
      {children}
    </div>
  );
}

interface CardFooterProps {
  children: React.ReactNode;
  className?: string;
}

export function CardFooter({ children, className = "" }: CardFooterProps) {
  return (
    <div className={`p-6 pt-0 ${className}`}>
      {children}
    </div>
  );
}

export default Card;
