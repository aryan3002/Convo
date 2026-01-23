"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2,
  Search,
  Loader2,
  Store,
  ArrowRight,
  Sparkles,
  MapPin,
  Clock,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type Shop = {
  id: number;
  slug: string;
  name: string;
  timezone?: string;
  address?: string;
};

export default function EmployeeShopSelectionPage() {
  const router = useRouter();
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [recentShop, setRecentShop] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const recent = localStorage.getItem("employee_recent_shop");
      if (recent) {
        setRecentShop(recent);
      }
    }
  }, []);

  useEffect(() => {
    fetchShops();
  }, []);

  async function fetchShops() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/registry/shops`);
      if (res.ok) {
        const data = await res.json();
        setShops(data);
      } else {
        const fallbackRes = await fetch(`${API_BASE}/shops`);
        if (fallbackRes.ok) {
          const data = await fallbackRes.json();
          setShops(data);
        } else {
          setError("Unable to load shops. Please try again.");
        }
      }
    } catch (err) {
      console.error("Failed to fetch shops:", err);
      setError("Connection error. Please check if the server is running.");
    } finally {
      setLoading(false);
    }
  }

  function selectShop(slug: string) {
    localStorage.setItem("employee_recent_shop", slug);
    router.push(`/employee/${slug}`);
  }

  const filteredShops = shops.filter(
    (shop) =>
      shop.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      shop.slug.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const hasRecentShop = recentShop && shops.find((s) => s.slug === recentShop);

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[200%] h-[100%] opacity-30">
          <div className="absolute inset-0 bg-gradient-to-b from-[#00d4ff]/20 via-transparent to-transparent" />
        </div>
        <div className="absolute -top-40 -left-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
      </div>
      <div
        className="fixed inset-0 pointer-events-none opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md relative z-10"
      >
        <div className="glass-strong rounded-3xl p-8 border border-white/10 shadow-neon">
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.2, type: "spring" }}
              className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 to-[#00d4ff]/5 border border-[#00d4ff]/30 mb-4"
            >
              <Sparkles className="w-8 h-8 text-[#00d4ff]" />
            </motion.div>
            <h1 className="text-2xl font-bold text-white mb-2">Employee Portal</h1>
            <p className="text-sm text-gray-400">Select your shop to sign in</p>
          </div>

          {hasRecentShop && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="mb-6"
            >
              <p className="text-xs text-gray-500 mb-2">Continue where you left off</p>
              <button
                onClick={() => selectShop(recentShop!)}
                className="w-full flex items-center justify-between p-4 rounded-xl bg-[#00d4ff]/10 border border-[#00d4ff]/30 hover:bg-[#00d4ff]/20 transition-all group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#00d4ff]/20 flex items-center justify-center">
                    <Clock className="w-5 h-5 text-[#00d4ff]" />
                  </div>
                  <div className="text-left">
                    <p className="text-white font-medium">
                      {shops.find((s) => s.slug === recentShop)?.name || recentShop}
                    </p>
                    <p className="text-xs text-gray-400">Recent shop</p>
                  </div>
                </div>
                <ArrowRight className="w-5 h-5 text-[#00d4ff] group-hover:translate-x-1 transition-transform" />
              </button>
            </motion.div>
          )}

          {hasRecentShop && (
            <div className="flex items-center gap-4 mb-6">
              <div className="flex-1 h-px bg-white/10" />
              <span className="text-xs text-gray-500">or select a shop</span>
              <div className="flex-1 h-px bg-white/10" />
            </div>
          )}

          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search shops..."
              className="w-full pl-10 pr-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 focus:ring-1 focus:ring-[#00d4ff]/30 transition-all"
            />
          </div>

          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {loading ? (
              <div className="text-center py-8">
                <Loader2 className="w-8 h-8 text-[#00d4ff] animate-spin mx-auto mb-2" />
                <p className="text-sm text-gray-400">Loading shops...</p>
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <Store className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-sm text-red-400">{error}</p>
                <button
                  onClick={fetchShops}
                  className="mt-3 text-sm text-[#00d4ff] hover:text-[#00d4ff]/80 transition-colors"
                >
                  Try again
                </button>
              </div>
            ) : filteredShops.length === 0 ? (
              <div className="text-center py-8">
                <Store className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-sm text-gray-400">
                  {searchQuery ? "No shops found" : "No shops available"}
                </p>
              </div>
            ) : (
              <AnimatePresence>
                {filteredShops.map((shop, index) => (
                  <motion.button
                    key={shop.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    onClick={() => selectShop(shop.slug)}
                    className="w-full flex items-center justify-between p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/10 transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center">
                        <Building2 className="w-5 h-5 text-[#00d4ff]" />
                      </div>
                      <div className="text-left">
                        <p className="text-white font-medium">{shop.name}</p>
                        <p className="text-xs text-gray-500 flex items-center gap-1">
                          {shop.address ? (
                            <>
                              <MapPin className="w-3 h-3" />
                              {shop.address}
                            </>
                          ) : (
                            shop.slug
                          )}
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="w-5 h-5 text-gray-500 group-hover:text-[#00d4ff] group-hover:translate-x-1 transition-all" />
                  </motion.button>
                ))}
              </AnimatePresence>
            )}
          </div>

          <div className="mt-6 pt-4 border-t border-white/10">
            <p className="text-xs text-gray-500 mb-2">Or enter shop URL slug directly:</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const formData = new FormData(e.target as HTMLFormElement);
                const slug = formData.get("manual-slug") as string;
                if (slug?.trim()) {
                  selectShop(slug.trim().toLowerCase());
                }
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                name="manual-slug"
                placeholder="e.g., downtown-salon"
                className="flex-1 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50"
              />
              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-[#00d4ff]/20 text-[#00d4ff] border border-[#00d4ff]/30 hover:bg-[#00d4ff]/30 transition-all text-sm font-medium"
              >
                Go
              </button>
            </form>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
