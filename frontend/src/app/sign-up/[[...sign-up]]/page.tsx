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

// Convo appearance configuration for Clerk components
const convoClerkAppearance = {
  variables: {
    // Colors matching Convo's dark theme
    colorPrimary: "#00d4ff", // neon-blue
    colorText: "hsl(210, 40%, 98%)", // foreground
    colorTextSecondary: "hsl(215, 20%, 65%)", // muted-foreground
    colorBackground: "#0f1629", // card-raw
    colorInputBackground: "hsl(217, 33%, 17%)", // secondary
    colorInputText: "hsl(210, 40%, 98%)",
    colorDanger: "hsl(0, 84%, 60%)", // destructive
    borderRadius: "0.75rem",
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
  },
  elements: {
    // Root card styling
    card: "bg-[#0f1629] border border-[hsl(217,33%,17%)] shadow-2xl shadow-[#00d4ff]/10",
    rootBox: "w-full",
    
    // Header styling
    headerTitle: "text-2xl font-bold bg-gradient-to-r from-[#00d4ff] to-[#a855f7] bg-clip-text text-transparent",
    headerSubtitle: "text-[hsl(215,20%,65%)]",
    
    // Form elements
    formButtonPrimary: 
      "bg-gradient-to-r from-[#00d4ff] to-[#a855f7] hover:from-[#a855f7] hover:to-[#ec4899] " +
      "text-[#0a0e1a] font-semibold transition-all duration-300 " +
      "shadow-lg shadow-[#00d4ff]/25 hover:shadow-[#a855f7]/30",
    formFieldInput: 
      "bg-[hsl(217,33%,17%)] border-[hsl(217,33%,17%)] text-white " +
      "focus:border-[#00d4ff] focus:ring-2 focus:ring-[#00d4ff]/20 " +
      "placeholder:text-[hsl(215,20%,65%)]",
    formFieldLabel: "text-[hsl(210,40%,98%)] font-medium",
    formFieldAction: "text-[#00d4ff] hover:text-[#a855f7]",
    
    // Social buttons
    socialButtonsBlockButton: 
      "bg-[hsl(217,33%,17%)] border-[hsl(217,33%,17%)] text-white " +
      "hover:bg-[hsl(217,33%,22%)] hover:border-[#00d4ff]/50 transition-all duration-200",
    socialButtonsBlockButtonText: "text-white font-medium",
    
    // Divider
    dividerLine: "bg-[hsl(217,33%,17%)]",
    dividerText: "text-[hsl(215,20%,65%)]",
    
    // Footer
    footer: "hidden", // We'll show our own footer
    footerActionLink: "text-[#00d4ff] hover:text-[#a855f7]",
    
    // Identity preview
    identityPreview: "bg-[hsl(217,33%,17%)] border-[hsl(217,33%,17%)]",
    identityPreviewText: "text-white",
    identityPreviewEditButton: "text-[#00d4ff] hover:text-[#a855f7]",
    
    // Alert/Error styling
    alert: "bg-[hsl(0,84%,60%)]/10 border-[hsl(0,84%,60%)] text-[hsl(0,84%,60%)]",
    alertText: "text-[hsl(0,84%,60%)]",
  },
};

function SignUpContent() {
  const searchParams = useSearchParams();
  const redirectUrl = searchParams.get("redirect_url");
  
  // Determine where to go after sign up
  // Priority: redirect_url param > default onboarding
  const afterSignUpUrl = redirectUrl || "/onboarding";
  const afterSignInUrl = redirectUrl || "/onboarding";
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0e1a] p-4">
      {/* Background gradient effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-[#a855f7]/5 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-[#00d4ff]/5 rounded-full blur-3xl" />
      </div>
      
      <div className="w-full max-w-md relative z-10">
        {/* Logo & Header */}
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-[#00d4ff] via-[#a855f7] to-[#ec4899] bg-clip-text text-transparent mb-2">
            Convo
          </h1>
          <p className="text-[hsl(215,20%,65%)]">Create Your Cab Services Platform</p>
        </div>
        
        {/* Clerk SignUp with Convo styling */}
        <div className="backdrop-blur-xl bg-[#0f1629]/80 rounded-2xl border border-[hsl(217,33%,17%)] p-1 shadow-2xl shadow-[#a855f7]/10">
          <SignUp 
            appearance={convoClerkAppearance}
            forceRedirectUrl={afterSignUpUrl}
            signInUrl="/sign-in"
            fallbackRedirectUrl={afterSignUpUrl}
          />
        </div>
        
        {/* Custom footer */}
        <p className="text-center text-sm text-[hsl(215,20%,65%)] mt-6">
          Already have an account?{" "}
          <a 
            href={redirectUrl ? `/sign-in?redirect_url=${encodeURIComponent(redirectUrl)}` : "/sign-in"} 
            className="font-semibold text-[#00d4ff] hover:text-[#a855f7] transition-colors"
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
