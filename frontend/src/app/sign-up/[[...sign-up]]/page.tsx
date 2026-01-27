/**
 * Clerk Sign Up Page - Convo Styled
 * 
 * This page renders Clerk's SignUp component with Convo's futuristic dark UI/UX.
 * Supports redirect_url query param to return users to their intended destination.
 * 
 * Use Cases:
 * - "Create New Cab Service" button → /sign-up?redirect_url=/s/<slug>/owner/cab/setup
 * - Generic signup → /sign-up (redirects to /onboarding)
 */

"use client";

import { SignUp } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

// Convo appearance configuration for Clerk components - Neon Cyberpunk Edition
const convoClerkAppearance = {
  variables: {
    // Colors matching Convo's dark theme with neon accents
    colorPrimary: "#00d4ff", // neon-blue
    colorText: "hsl(210, 40%, 98%)", // foreground
    colorTextSecondary: "hsl(215, 20%, 65%)", // muted-foreground
    colorBackground: "rgba(15, 22, 41, 0.6)", // card-raw with transparency
    colorInputBackground: "rgba(33, 45, 71, 0.5)", // secondary with transparency
    colorInputText: "hsl(210, 40%, 98%)",
    colorDanger: "hsl(0, 84%, 60%)", // destructive
    borderRadius: "0.75rem",
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
  },
  elements: {
    // Root card styling with glassmorphism - REMOVED EXTRA BORDER
    card: "bg-gradient-to-br from-[#0f1629]/90 via-[#1a2235]/80 to-[#0f1629]/90 backdrop-blur-2xl shadow-2xl shadow-[#a855f7]/20",
    rootBox: "w-full",
    
    // Header styling with animated gradient
    headerTitle: "text-2xl font-bold bg-gradient-to-r from-[#a855f7] via-[#ec4899] to-[#00d4ff] bg-clip-text text-transparent",
    headerSubtitle: "text-[hsl(215,20%,65%)] tracking-wide",
    
    // Form elements with glow effects
    formButtonPrimary: 
      "bg-gradient-to-r from-[#a855f7] via-[#ec4899] to-[#00d4ff] hover:from-[#00d4ff] hover:via-[#7c3aed] hover:to-[#a855f7] " +
      "text-white font-bold transition-all duration-500 transform hover:scale-[1.02] " +
      "shadow-[0_0_20px_rgba(168,85,247,0.5)] hover:shadow-[0_0_30px_rgba(0,212,255,0.6)] " +
      "border border-[#a855f7]/50 hover:border-[#00d4ff]/50",
    formFieldInput: 
      "bg-[hsl(217,33%,17%)]/50 backdrop-blur-sm border border-[hsl(217,33%,25%)] text-white " +
      "focus:border-[#a855f7] focus:ring-2 focus:ring-[#a855f7]/40 focus:shadow-[0_0_15px_rgba(168,85,247,0.3)] " +
      "placeholder:text-[hsl(215,20%,55%)] transition-all duration-300",
    formFieldLabel: "text-[hsl(210,40%,98%)] font-semibold tracking-wide",
    formFieldAction: "text-[#a855f7] hover:text-[#00d4ff] transition-colors duration-300 font-medium",
    
    // Social buttons with hover glow - WHITE TEXT FOR VISIBILITY
    socialButtonsBlockButton: 
      "bg-[hsl(217,33%,17%)]/60 backdrop-blur-sm border border-[hsl(217,33%,25%)] text-white " +
      "hover:bg-[hsl(217,33%,22%)]/80 hover:border-[#a855f7]/60 hover:shadow-[0_0_15px_rgba(168,85,247,0.2)] " +
      "transition-all duration-300 transform hover:scale-[1.02]",
    socialButtonsBlockButtonText: "text-white font-semibold",
    socialButtonsProviderIcon__google: "brightness-100",
    
    // Divider with subtle glow
    dividerLine: "bg-gradient-to-r from-transparent via-[#a855f7]/30 to-transparent",
    dividerText: "text-[hsl(215,20%,65%)] px-3",
    
    // Footer
    footer: "hidden",
    footerActionLink: "text-[#a855f7] hover:text-[#00d4ff] transition-colors duration-300",
    
    // Identity preview with glow
    identityPreview: "bg-[hsl(217,33%,17%)]/60 backdrop-blur-sm border border-[#a855f7]/30",
    identityPreviewText: "text-white font-medium",
    identityPreviewEditButton: "text-[#a855f7] hover:text-[#00d4ff] transition-colors duration-300",
    
    // Alert/Error styling with neon effect
    alert: "bg-[hsl(0,84%,60%)]/20 backdrop-blur-sm border border-[hsl(0,84%,60%)]/50 text-[hsl(0,84%,70%)] shadow-[0_0_15px_rgba(239,68,68,0.2)]",
    alertText: "text-[hsl(0,84%,70%)] font-medium",
  },
};

function SignUpContent() {
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get("redirect_url");
  
  // Determine where to go after sign up
  // Priority: redirect_url param > default onboarding
  const afterSignUpUrl = redirectUrl || "/onboarding";
  const afterSignInUrl = redirectUrl || "/onboarding";
   relative overflow-hidden">
      {/* Animated Background gradient effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" suppressHydrationWarning>
        <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-[#a855f7]/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-[#00d4ff]/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 right-1/2 w-96 h-96 bg-[#ec4899]/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
        
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(168,85,247,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(168,85,247,0.03)_1px,transparent_1px)] bg-[size:50px_50px]" />
      </div>
      
      <div className="w-full max-w-md relative z-10">
        {/* Logo & Header with glow */}
        <div className="mb-8 text-center space-y-3">
          <div className="inline-block">
            <h1 className="text-5xl font-black bg-gradient-to-r from-[#a855f7] via-[#ec4899] to-[#00d4ff] bg-clip-text text-transparent mb-2 drop-shadow-[0_0_30px_rgba(168,85,247,0.5)]">
              Convo
            </h1>
          </div>
          <p className="text-[hsl(215,20%,65%)] text-lg tracking-wide">
            Create Your Cab Services Platform
          </p>
          <div className="h-[2px] w-24 mx-auto bg-gradient-to-r from-transparent via-[#a855f7] to-transparent" />
        </div>
        
        {/* Glassmorphism container with neon border */}
        <div className="relative group">
          {/* Glow effect behind card */}
          <div className="absolute -inset-0.5 bg-gradient-to-r from-[#a855f7] via-[#ec4899] to-[#00d4ff] rounded-2xl blur opacity-30 group-hover:opacity-50 transition-opacity duration-500" />
          
          {/* Main card with glassmorphism */}
          <div className="relative backdrop-blur-2xl bg-gradient-to-br from-[#0f1629]/90 via-[#1a2235]/70 to-[#0f1629]/90 rounded-2xl border border-[#a855f7]/30 p-1 shadow-2xl shadow-[#a855f7]/20">
            <SignUp 
              appearance={convoClerkAppearance}
              forceRedirectUrl={afterSignUpUrl}
              signInUrl="/sign-in"
              fallbackRedirectUrl={afterSignUpUrl}
            />
          </div>
        </div>
        
        {/* Custom footer with hover effect */}
        <p className="text-center text-sm text-[hsl(215,20%,65%)] mt-8">
          Already have an account?{" "}
          <a 
            href={redirectUrl ? `/sign-in?redirect_url=${encodeURIComponent(redirectUrl)}` : "/sign-in"} 
            className="font-semibold text-[#a855f7] hover:text-[#00d4ff] transition-all duration-300 hover:drop-shadow-[0_0_8px_rgba(168,85,247,0.8)] relative group"
          >
            Sign in
            <span className="absolute -bottom-1 left-0 w-0 h-[2px] bg-gradient-to-r from-[#a855f7] to-[#00d4ff] group-hover:w-full transition-all duration-300" />me="font-semibold text-[#00d4ff] hover:text-[#a855f7] transition-colors"
          >
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}

export default function SignUpPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[#0a0e1a]">
        <div className="animate-pulse text-[#a855f7]">Loading...</div>
      </div>
    }>
      <SignUpContent />
    </Suspense>
  );
}
