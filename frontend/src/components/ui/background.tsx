"use client";

import React from "react";
import { motion } from "framer-motion";

// Floating Blobs Background
export function FloatingBlobs() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
      {/* Neon Blue Blob */}
      <motion.div
        className="absolute w-[600px] h-[600px] rounded-full blur-[150px]"
        style={{ background: "rgba(0, 212, 255, 0.08)" }}
        animate={{
          x: [0, 100, 50, 0],
          y: [0, -50, 30, 0],
        }}
        transition={{
          duration: 25,
          repeat: Infinity,
          ease: "linear",
        }}
        initial={{ top: "-10%", left: "-10%" }}
      />
      
      {/* Neon Purple Blob */}
      <motion.div
        className="absolute w-[500px] h-[500px] rounded-full blur-[150px]"
        style={{ background: "rgba(168, 85, 247, 0.08)" }}
        animate={{
          x: [0, -80, 40, 0],
          y: [0, 60, -30, 0],
        }}
        transition={{
          duration: 30,
          repeat: Infinity,
          ease: "linear",
        }}
        initial={{ top: "30%", right: "-5%" }}
      />
      
      {/* Neon Pink Blob */}
      <motion.div
        className="absolute w-[400px] h-[400px] rounded-full blur-[150px]"
        style={{ background: "rgba(236, 72, 153, 0.06)" }}
        animate={{
          x: [0, 50, -30, 0],
          y: [0, -40, 60, 0],
        }}
        transition={{
          duration: 20,
          repeat: Infinity,
          ease: "linear",
        }}
        initial={{ bottom: "-5%", left: "30%" }}
      />
    </div>
  );
}

// Grid Background
export function GridBackground() {
  return (
    <div
      className="fixed inset-0 pointer-events-none -z-20 bg-grid opacity-50"
      style={{
        maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
        WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
      }}
    />
  );
}

// Noise Overlay
export function NoiseOverlay() {
  return (
    <div className="fixed inset-0 pointer-events-none -z-5 bg-noise" />
  );
}

// Combined Background Effects
export function BackgroundEffects() {
  return (
    <>
      <FloatingBlobs />
      <GridBackground />
      <NoiseOverlay />
    </>
  );
}

// Gradient Orb - decorative element
interface GradientOrbProps {
  className?: string;
  color?: "blue" | "purple" | "pink";
  size?: "sm" | "md" | "lg";
}

export function GradientOrb({
  className = "",
  color = "blue",
  size = "md",
}: GradientOrbProps) {
  const colors = {
    blue: "from-neon-blue/30 to-transparent",
    purple: "from-neon-purple/30 to-transparent",
    pink: "from-neon-pink/30 to-transparent",
  };

  const sizes = {
    sm: "w-32 h-32",
    md: "w-64 h-64",
    lg: "w-96 h-96",
  };

  return (
    <div
      className={`
        absolute rounded-full blur-[100px]
        bg-gradient-radial ${colors[color]} ${sizes[size]}
        pointer-events-none
        ${className}
      `}
    />
  );
}

// Glowing Line - decorative divider
interface GlowingLineProps {
  className?: string;
  direction?: "horizontal" | "vertical";
}

export function GlowingLine({ className = "", direction = "horizontal" }: GlowingLineProps) {
  const sizeClass = direction === "horizontal" ? "w-full h-px" : "w-px h-full";

  return (
    <div
      className={`
        ${sizeClass}
        bg-gradient-to-r from-transparent via-neon-blue/50 to-transparent
        ${className}
      `}
    />
  );
}

// Neon Circle - decorative element
interface NeonCircleProps {
  className?: string;
  size?: number;
  color?: string;
}

export function NeonCircle({
  className = "",
  size = 100,
  color = "var(--neon-blue)",
}: NeonCircleProps) {
  return (
    <motion.div
      className={`absolute rounded-full border-2 ${className}`}
      style={{
        width: size,
        height: size,
        borderColor: color,
        boxShadow: `0 0 20px ${color}, inset 0 0 20px ${color}`,
      }}
      animate={{
        scale: [1, 1.1, 1],
        opacity: [0.5, 1, 0.5],
      }}
      transition={{
        duration: 3,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    />
  );
}

export default BackgroundEffects;
