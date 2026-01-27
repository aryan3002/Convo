/**
 * Clerk Sign In Page - Convo Redesigned
 * 
 * Complete redesign with enhanced cyberpunk aesthetics, improved visual hierarchy,
 * and polished animations for a premium user experience.
 */

"use client";

import { SignIn } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

// Enhanced Convo appearance configuration - Premium Cyberpunk Edition
const convoClerkAppearance = {
  variables: {
    // Core color palette
    colorPrimary: "#00d4ff",
    colorText: "#e8edf5",
    colorTextSecondary: "#9ca3af",
    colorBackground: "#0f1629",
    colorInputBackground: "#1a2235",
    colorInputText: "#ffffff",
    colorDanger: "#ef4444",
    borderRadius: "0.75rem",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    fontSize: "15px",
  },
  elements: {
    // Root styling
    rootBox: "w-full",
    card: "bg-transparent shadow-none",
    
    // Header with enhanced gradient
    headerTitle: "text-2xl font-bold bg-gradient-to-r from-[#00d4ff] via-[#a855f7] to-[#ec4899] bg-clip-text text-transparent mb-1 tracking-tight",
    headerSubtitle: "text-gray-400 text-sm font-normal tracking-wide",
    
    // Primary button with premium styling
    formButtonPrimary:
      "bg-gradient-to-r from-[#00d4ff] to-[#8a7cfb] text-white font-semibold py-3 px-6 rounded-xl " +
      "hover:shadow-[0_0_30px_rgba(0,212,255,0.4)] hover:scale-[1.02] active:scale-[0.98] " +
      "transition-all duration-300 border-0 shadow-[0_8px_24px_rgba(0,212,255,0.25)]",
    
    // Input fields with glow effect
    formFieldInput:
      "bg-[#1a2235]/50 backdrop-blur-sm border-2 border-gray-700/50 text-white rounded-xl px-4 py-3 " +
      "focus:border-[#00d4ff] focus:ring-4 focus:ring-[#00d4ff]/20 focus:shadow-[0_0_20px_rgba(0,212,255,0.15)] " +
      "placeholder:text-gray-500 transition-all duration-300 outline-none",
    
    formFieldLabel: "text-gray-300 font-semibold mb-2 text-sm tracking-wide",
    formFieldAction: "text-[#00d4ff] hover:text-[#a855f7] transition-colors duration-300 font-medium text-sm",
    
    // Social buttons with improved contrast
    socialButtonsBlockButton: 
      "bg-[#1a2235]/70 backdrop-blur-sm border-2 border-gray-700/40 font-medium py-3 px-4 rounded-xl " +
      "hover:bg-[#1f2937] hover:border-[#00d4ff]/50 hover:shadow-[0_0_20px_rgba(0,212,255,0.15)] " +
      "transition-all duration-300 !text-white",
    socialButtonsBlockButtonText: "!text-white font-medium",
    socialButtonsProviderIcon: "brightness-110 contrast-110",
    
    // Divider
    dividerLine: "bg-gradient-to-r from-transparent via-gray-600 to-transparent",
    dividerText: "text-gray-400 text-sm font-medium px-4",
    
    // Footer
    footer: "hidden",
    footerActionLink: "text-[#00d4ff] hover:text-[#a855f7] font-medium transition-colors duration-300",
    
    // Alerts
    alert: "bg-red-500/10 border-2 border-red-500/30 rounded-xl text-red-400 p-4",
    alertText: "text-red-300 font-medium text-sm",
    
    // Identity preview
    identityPreview: "bg-[#1a2235]/60 backdrop-blur-sm border-2 border-gray-700/40 rounded-xl",
    identityPreviewText: "text-white font-medium",
    identityPreviewEditButton: "text-[#00d4ff] hover:text-[#a855f7] transition-colors duration-300",
  },
};

type Particle = {
  left: string;
  top: string;
  duration: number;
  delay: number;
};

function SignInContent() {
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get("redirect_url");
  const [particles, setParticles] = useState<Particle[]>([]);
  
  const afterSignInUrl = redirectUrl || "/onboarding";
  const afterSignUpUrl = redirectUrl || "/onboarding";

  // Generate particle positions on the client only to avoid hydration mismatches
  useEffect(() => {
    const generated = Array.from({ length: 20 }, () => ({
      left: `${Math.random() * 100}%`,
      top: `${Math.random() * 100}%`,
      duration: 5 + Math.random() * 10,
      delay: Math.random() * 5,
    }));
    setParticles(generated);
  }, []);
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0e1a] p-6 relative overflow-hidden">
      {/* Enhanced animated background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* Gradient orbs with smoother animation */}
        <div 
          className="absolute top-[20%] left-[15%] w-[500px] h-[500px] bg-[#00d4ff]/[0.08] rounded-full blur-[120px] animate-pulse"
          style={{ animationDuration: '8s' }}
        />
        <div 
          className="absolute bottom-[25%] right-[20%] w-[450px] h-[450px] bg-[#a855f7]/[0.08] rounded-full blur-[120px] animate-pulse"
          style={{ animationDuration: '10s', animationDelay: '2s' }}
        />
        <div 
          className="absolute top-[45%] right-[35%] w-[400px] h-[400px] bg-[#ec4899]/[0.06] rounded-full blur-[120px] animate-pulse"
          style={{ animationDuration: '12s', animationDelay: '4s' }}
        />
        
        {/* Refined grid pattern */}
        <div 
          className="absolute inset-0 opacity-[0.015]"
          style={{
            backgroundImage: `
              linear-gradient(rgba(0, 212, 255, 0.3) 1px, transparent 1px),
              linear-gradient(90deg, rgba(0, 212, 255, 0.3) 1px, transparent 1px)
            `,
            backgroundSize: '80px 80px'
          }}
        />
        
        {/* Subtle scanline effect */}
        <div 
          className="absolute inset-0 opacity-[0.02]"
          style={{
            backgroundImage: 'linear-gradient(0deg, transparent 50%, rgba(0, 212, 255, 0.5) 50%)',
            backgroundSize: '100% 4px',
            animation: 'scanline 8s linear infinite'
          }}
        />
      </div>
      
      {/* Main content container */}
      <div className="w-full max-w-[420px] relative z-10">
        {/* Enhanced logo and header */}
        <div className="mb-6 text-center space-y-2">
          {/* Logo with glow effect */}
          <div className="inline-block relative">
            <div className="absolute inset-0 bg-gradient-to-r from-[#00d4ff] via-[#a855f7] to-[#ec4899] blur-2xl opacity-30 animate-pulse" style={{ animationDuration: '4s' }} />
            <h1 className="relative text-5xl font-black bg-gradient-to-r from-[#00d4ff] via-[#a855f7] to-[#ec4899] bg-clip-text text-transparent tracking-tight">
              Convo
            </h1>
          </div>
          
          {/* Subtitle */}
          <p className="text-gray-400 text-base font-light tracking-wide">
            AI-Powered Cab Services Platform
          </p>
          
          {/* Decorative line */}
          <div className="flex justify-center pt-1">
            <div className="h-[2px] w-28 bg-gradient-to-r from-transparent via-[#00d4ff] to-transparent rounded-full" />
          </div>
        </div>
        
        {/* Main card with enhanced glassmorphism */}
        <div className="relative group">
          {/* Animated border glow */}
          <div 
            className="absolute -inset-[1px] bg-gradient-to-r from-[#00d4ff] via-[#a855f7] to-[#ec4899] rounded-2xl opacity-0 group-hover:opacity-100 blur-sm transition-opacity duration-500"
            style={{
              background: 'linear-gradient(90deg, #00d4ff, #a855f7, #ec4899, #00d4ff)',
              backgroundSize: '200% 100%',
              animation: 'gradient-shift 3s ease infinite'
            }}
          />
          
          {/* Card content */}
          <div className="relative bg-gradient-to-br from-[#0f1629]/95 via-[#1a2235]/90 to-[#0f1629]/95 backdrop-blur-2xl rounded-2xl border border-gray-700/40 p-6 shadow-2xl">
            <SignIn 
              appearance={convoClerkAppearance}
              forceRedirectUrl={afterSignInUrl}
              signUpUrl="/sign-up"
              fallbackRedirectUrl={afterSignInUrl}
            />
          </div>
        </div>
        
        {/* Enhanced footer */}
        <div className="mt-5 text-center">
          <p className="text-gray-400 text-sm">
            Don&apos;t have an account?{" "}
            <a 
              href={redirectUrl ? `/sign-up?redirect_url=${encodeURIComponent(redirectUrl)}` : "/sign-up"} 
              className="font-semibold bg-gradient-to-r from-[#00d4ff] to-[#a855f7] bg-clip-text text-transparent hover:brightness-125 transition-all duration-300 relative inline-block group"
            >
              Sign up
              <span className="absolute bottom-0 left-0 w-0 h-[2px] bg-gradient-to-r from-[#00d4ff] to-[#a855f7] group-hover:w-full transition-all duration-300 rounded-full" />
            </a>
          </p>
        </div>
        
        {/* Floating particles effect (optional) */}
        {particles.length > 0 && (
          <div className="fixed inset-0 pointer-events-none overflow-hidden">
            {particles.map((p, i) => (
              <div
                key={i}
                className="absolute w-1 h-1 bg-[#00d4ff]/30 rounded-full"
                style={{
                  left: p.left,
                  top: p.top,
                  animation: `float ${p.duration}s ease-in-out infinite`,
                  animationDelay: `${p.delay}s`,
                }}
              />
            ))}
          </div>
        )}
      </div>
      
      {/* Keyframe animations */}
      <style jsx>{`
        @keyframes gradient-shift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        
        @keyframes scanline {
          0% { transform: translateY(-100%); }
          100% { transform: translateY(100%); }
        }
        
        @keyframes float {
          0%, 100% {
            transform: translateY(0) translateX(0);
            opacity: 0;
          }
          10%, 90% {
            opacity: 0.3;
          }
          50% {
            transform: translateY(-100px) translateX(50px);
            opacity: 0.6;
          }
        }
      `}</style>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[#0a0e1a]">
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-[#00d4ff] to-[#a855f7] blur-xl opacity-50 animate-pulse" />
          <div className="relative text-2xl font-bold bg-gradient-to-r from-[#00d4ff] to-[#a855f7] bg-clip-text text-transparent">
            Loading...
          </div>
        </div>
      </div>
    }>
      <SignInContent />
    </Suspense>
  );
}
