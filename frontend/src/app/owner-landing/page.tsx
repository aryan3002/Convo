"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  Store,
  Plus,
  ArrowRight,
  Sparkles,
  Users,
  Scissors,
  MessageSquare,
} from "lucide-react";
import { getStoredUserId } from "@/lib/api";

// ──────────────────────────────────────────────────────────
// Landing Page - Shop Selector / Onboarding Entry
// ──────────────────────────────────────────────────────────

export default function OwnerLandingPage() {
  const router = useRouter();
  const [hasUserId, setHasUserId] = useState(false);

  useEffect(() => {
    const userId = getStoredUserId();
    setHasUserId(!!userId);
  }, []);

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
          <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-[#00d4ff]" />
            Multi-tenant
          </span>
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
            className="grid md:grid-cols-2 gap-4 mb-12"
          >
            {/* Create Shop Card */}
            <motion.button
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => router.push("/onboarding")}
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

          {/* Legacy Dashboard Link */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="text-center mt-12"
          >
            <p className="text-xs text-gray-600">
              Looking for the demo dashboard?{" "}
              <a
                href="/owner-legacy"
                className="text-gray-400 hover:text-[#00d4ff] transition-colors"
              >
                Access legacy dashboard →
              </a>
            </p>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
