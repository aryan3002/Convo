"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useUser, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import { useApiClient } from "@/lib/clerk-api";
import {
  Store,
  Plus,
  ArrowRight,
  Sparkles,
  Users,
  Scissors,
  MessageSquare,
  UserCircle,
  Car,
  LogIn,
} from "lucide-react";

// ──────────────────────────────────────────────────────────
// Landing Page - Shop Selector / Onboarding Entry
// ──────────────────────────────────────────────────────────

export default function OwnerLandingPage() {
  const router = useRouter();
  const { user, isLoaded } = useUser();
  const apiClient = useApiClient();
  const [userShops, setUserShops] = useState<any[]>([]);
  const [loadingShops, setLoadingShops] = useState(false);
  const userId = user?.id;

  // Fetch user's shops when signed in - only once per user
  useEffect(() => {
    if (!isLoaded || !userId) {
      console.log("Skipping shop fetch - not loaded or no user", { isLoaded, hasUser: !!userId });
      return;
    }

    let isMounted = true;

    async function fetchUserShops(currentUserId: string) {
      setLoadingShops(true);
      try {
        console.log("Fetching shops for user:", currentUserId);
        const response = await fetch(`/api/backend/users/${currentUserId}/shops`, {
          headers: {
            'Content-Type': 'application/json',
          },
        });
        
        if (!response.ok) {
          throw new Error(`Failed to fetch shops: ${response.status}`);
        }
        
        const shops = await response.json();
        console.log("Fetched shops:", shops);
        
        if (isMounted) {
          setUserShops(Array.isArray(shops) ? shops : []);
        }
      } catch (error) {
        console.error("Failed to fetch user shops:", error);
        if (isMounted) {
          setUserShops([]);
        }
      } finally {
        if (isMounted) {
          setLoadingShops(false);
        }
      }
    }

    fetchUserShops(userId);

    return () => {
      isMounted = false;
    };
  }, [isLoaded, userId]);

  const features = [
    {
      icon: MessageSquare,
      title: "AI-Powered Chat",
      description: "Manage your shop through natural conversation",
      color: "#00d4ff",
    },
    {
      icon: Scissors,
      title: "Service Management",
      description: "Add, edit, and track your services",
      color: "#a855f7",
    },
    {
      icon: Users,
      title: "Stylist Scheduling",
      description: "Coordinate your team's availability",
      color: "#ec4899",
    },
  ];

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0a0e1a]/80 border-b border-white/5">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] via-[#a855f7] to-[#ec4899] flex items-center justify-center shadow-neon">
              <Store className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Convo</h1>
              <p className="text-xs text-gray-500">Owner Portal</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* My Shops - Show when user is logged in (with loading/empty state) */}
            {isLoaded && user && (
              <div className="relative group">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="text-xs px-4 py-2 rounded-full glass border border-white/10 text-white hover:border-[#00d4ff]/50 transition-all flex items-center gap-2"
                >
                  <Store className="w-3 h-3 text-[#00d4ff]" />
                  {loadingShops ? "Loading..." : `My Shops (${userShops.length})`}
                </motion.button>
                {/* Dropdown - only show when there are shops */}
                {userShops.length > 0 && (
                  <div className="absolute right-0 mt-2 w-64 glass-card rounded-xl border border-white/10 shadow-2xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
                    <div className="p-2 space-y-1">
                      {userShops.map((shop) => (
                        <button
                          key={shop.id}
                          onClick={() => router.push(`/s/${shop.slug}/owner`)}
                          className="w-full text-left px-3 py-2 rounded-lg hover:bg-white/5 transition-colors"
                        >
                          <div className="text-sm font-medium text-white">{shop.name}</div>
                          <div className="text-xs text-gray-400">/{shop.slug}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {/* Clerk Authentication */}
            {isLoaded && user ? (
              <UserButton afterSignOutUrl="/owner-landing" />
            ) : (
              <div className="flex items-center gap-2">
                <SignInButton mode="modal" forceRedirectUrl="/owner-landing">
                  <div className="text-xs px-4 py-2 rounded-full glass border border-white/10 text-gray-400 hover:text-white hover:border-[#00d4ff]/50 transition-all flex items-center gap-2 cursor-pointer">
                    <LogIn className="w-3 h-3 text-[#00d4ff]" />
                    Sign In
                  </div>
                </SignInButton>
                <SignUpButton mode="modal" forceRedirectUrl="/onboarding">
                  <div className="text-xs px-4 py-2 rounded-full bg-gradient-to-r from-[#00d4ff] to-[#a855f7] text-white font-medium transition-all flex items-center gap-2 shadow-neon cursor-pointer">
                    <Sparkles className="w-3 h-3" />
                    Sign Up
                  </div>
                </SignUpButton>
              </div>
            )}
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => router.push("/employee")}
              className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 hover:text-white hover:border-[#a855f7]/50 transition-all flex items-center gap-1.5"
            >
              <UserCircle className="w-3 h-3 text-[#a855f7]" />
              Employee Portal
            </motion.button>
            <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-[#00d4ff]" />
              Multi-tenant
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl">
          {/* Hero */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center mb-12"
          >
            <motion.div
              initial={{ scale: 0.8 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.2, type: "spring" }}
              className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 via-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-6"
            >
              <Store className="w-10 h-10 text-[#00d4ff]" />
            </motion.div>
            <h2 className="text-3xl font-bold text-white mb-4">
              Welcome to Convo
            </h2>
            <p className="text-gray-400 max-w-md mx-auto">
              The AI-powered booking system for salons, barbershops, and beauty
              businesses. Create your shop to get started.
            </p>
          </motion.div>

          {/* Action Cards */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="grid md:grid-cols-2 gap-4 mb-8"
          >
            {/* Create Shop Card */}
            <motion.button
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => {
                if (!isLoaded || !user) {
                  // Redirect to sign up if not logged in
                  router.push("/sign-up?redirect_url=" + encodeURIComponent("/onboarding"));
                } else {
                  router.push("/onboarding");
                }
              }}
              className="glass-card rounded-2xl p-6 border border-white/5 text-left hover:border-[#00d4ff]/30 transition-all group"
            >
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#00d4ff]/20 to-[#a855f7]/20 flex items-center justify-center border border-white/10 mb-4 group-hover:shadow-neon transition-all">
                <Plus className="w-6 h-6 text-[#00d4ff]" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Create a New Shop
              </h3>
              <p className="text-sm text-gray-400 mb-4">
                Set up your business in minutes with our guided onboarding.
                {!isLoaded || !user ? " (Sign in required)" : ""}
              </p>
              <span className="text-sm text-[#00d4ff] flex items-center gap-1 group-hover:gap-2 transition-all">
                Get started <ArrowRight className="w-4 h-4" />
              </span>
            </motion.button>

            {/* Access Shop Card */}
            <motion.div
              whileHover={{ scale: 1.02, y: -2 }}
              className="glass-card rounded-2xl p-6 border border-white/5 text-left"
            >
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-4">
                <Store className="w-6 h-6 text-[#a855f7]" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">
                Access Your Shop
              </h3>
              <p className="text-sm text-gray-400 mb-4">
                Enter your shop slug to access the owner dashboard.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const input = form.elements.namedItem("slug") as HTMLInputElement;
                  if (input.value.trim()) {
                    router.push(`/s/${input.value.trim()}/owner`);
                  }
                }}
                className="flex gap-2"
              >
                <input
                  name="slug"
                  type="text"
                  placeholder="your-shop-slug"
                  className="flex-1 px-3 py-2 rounded-lg input-glass text-sm"
                />
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg btn-neon text-sm flex items-center gap-1"
                >
                  Go <ArrowRight className="w-3 h-3" />
                </button>
              </form>
            </motion.div>
          </motion.div>

          {/* Cab Owner Card - Full Width */}
          <motion.button
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => {
              if (!isLoaded || !user) {
                // Redirect to sign up if not logged in
                router.push("/sign-up?redirect_url=" + encodeURIComponent("/onboarding/cab"));
              } else {
                router.push("/onboarding/cab");
              }
            }}
            className="w-full glass-card rounded-2xl p-5 border border-white/5 hover:border-[#10b981]/30 transition-all group mb-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#10b981]/20 to-[#06b6d4]/20 flex items-center justify-center border border-white/10 group-hover:shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all">
                <Car className="w-6 h-6 text-[#10b981]" />
              </div>
              <div className="text-left">
                <h3 className="text-base font-semibold text-white">
                  I Run a Cab Service
                </h3>
                <p className="text-xs text-gray-400">
                  Set up your cab/taxi business with driver management and ride booking
                  {!isLoaded || !user ? " (Sign in required)" : ""}
                </p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-500 group-hover:text-[#10b981] group-hover:translate-x-1 transition-all" />
          </motion.button>

          {/* Employee Portal Card */}
          <motion.button
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => router.push("/employee")}
            className="w-full glass-card rounded-2xl p-5 border border-white/5 hover:border-[#ec4899]/30 transition-all group mb-12 flex items-center justify-between"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#ec4899]/20 to-[#f97316]/20 flex items-center justify-center border border-white/10 group-hover:shadow-[0_0_20px_rgba(236,72,153,0.3)] transition-all">
                <UserCircle className="w-6 h-6 text-[#ec4899]" />
              </div>
              <div className="text-left">
                <h3 className="text-base font-semibold text-white">
                  Employee Portal
                </h3>
                <p className="text-xs text-gray-400">
                  For stylists and staff members to view their schedules
                </p>
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-gray-500 group-hover:text-[#ec4899] group-hover:translate-x-1 transition-all" />
          </motion.button>

          {/* Features */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <p className="text-xs text-gray-500 text-center mb-6 uppercase tracking-wide">
              What you can do with Convo
            </p>
            <div className="grid md:grid-cols-3 gap-4">
              {features.map((feature, index) => (
                <motion.div
                  key={feature.title}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 + index * 0.1 }}
                  className="glass rounded-xl p-4 border border-white/5 text-center"
                >
                  <div
                    className="w-10 h-10 mx-auto rounded-lg flex items-center justify-center mb-3"
                    style={{ backgroundColor: `${feature.color}20` }}
                  >
                    <feature.icon
                      className="w-5 h-5"
                      style={{ color: feature.color }}
                    />
                  </div>
                  <h4 className="text-sm font-medium text-white mb-1">
                    {feature.title}
                  </h4>
                  <p className="text-xs text-gray-500">{feature.description}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Help Text */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="text-center mt-12"
          >
            <p className="text-xs text-gray-600">
              Need help?{" "}
              <span className="text-gray-400">
                Contact support@convo.ai
              </span>
            </p>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
