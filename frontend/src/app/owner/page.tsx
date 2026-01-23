"use client";

/**
 * DEPRECATED: Legacy Owner Dashboard
 * 
 * This page has been deprecated in favor of the multi-tenant owner dashboard.
 * All functionality now lives at /s/{slug}/owner for proper tenant isolation.
 * 
 * Redirects to /owner-landing where users can:
 * 1. Create a new shop via onboarding
 * 2. Access an existing shop by entering its slug
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Store, ArrowRight } from "lucide-react";

export default function LegacyOwnerRedirect() {
  const router = useRouter();

  useEffect(() => {
    // Auto-redirect after a short delay to show the message
    const timer = setTimeout(() => {
      router.replace("/owner-landing");
    }, 2000);

    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        {/* Icon */}
        <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 via-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-6">
          <Store className="w-8 h-8 text-[#00d4ff]" />
        </div>

        {/* Message */}
        <h1 className="text-xl font-bold text-white mb-3">
          Owner Dashboard Has Moved
        </h1>
        <p className="text-gray-400 text-sm mb-6">
          We&apos;ve upgraded to a multi-tenant system. You&apos;ll be redirected to the new owner portal.
        </p>

        {/* Loading indicator */}
        <div className="flex items-center justify-center gap-2 text-[#00d4ff] mb-6">
          <div className="w-1.5 h-1.5 rounded-full bg-[#00d4ff] animate-pulse" />
          <div className="w-1.5 h-1.5 rounded-full bg-[#00d4ff] animate-pulse" style={{ animationDelay: "0.2s" }} />
          <div className="w-1.5 h-1.5 rounded-full bg-[#00d4ff] animate-pulse" style={{ animationDelay: "0.4s" }} />
        </div>

        {/* Manual redirect button */}
        <button
          onClick={() => router.replace("/owner-landing")}
          className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-[#00d4ff] to-[#a855f7] text-white font-medium text-sm flex items-center gap-2 mx-auto hover:shadow-neon transition-all"
        >
          Go to Owner Portal
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
