"use client";

import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import {
  MessageSquare,
  Send,
  Sparkles,
  Calendar,
  Clock,
  User,
  Users,
  Scissors,
  Tag,
  Phone,
  Store,
  ChevronRight,
  X,
  Plus,
  AlertCircle,
  DollarSign,
  BarChart3,
  HelpCircle,
  LogOut,
  RefreshCw,
  Loader2,
} from "lucide-react";
import {
  getApiBase,
  getShopBySlug,
  getServices,
  getStylists,
  getStoredUserId,
  setStoredUserId,
  clearStoredUserId,
  getErrorMessage,
  isApiError,
  type Shop,
  type Service,
  type Stylist,
} from "@/lib/api";

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

type Role = "user" | "assistant";

type OwnerMessage = {
  id: string;
  role: Role;
  text: string;
};

type OwnerChatResponse = {
  reply: string;
  suggested_chips?: string[];
};

type RightView = "services" | "stylists" | "analytics" | "ask";

// ──────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────

export default function ShopOwnerDashboard() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;
  const API_BASE = getApiBase();

  // Auth & Shop State
  const [userId, setUserId] = useState<string | null>(null);
  const [shop, setShop] = useState<Shop | null>(null);
  const [shopLoading, setShopLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  // Data State
  const [services, setServices] = useState<Service[]>([]);
  const [stylists, setStylists] = useState<Stylist[]>([]);
  const [dataLoading, setDataLoading] = useState(false);

  // Chat State
  const [messages, setMessages] = useState<OwnerMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Welcome to your shop dashboard! I can help you manage services, stylists, and more. What would you like to do?",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedChips, setSuggestedChips] = useState<string[]>([
    "Show my services",
    "List stylists",
    "Add a service",
  ]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // View State
  const [rightView, setRightView] = useState<RightView>("services");

  // Quick actions
  const quickActions = [
    "Show my services",
    "List stylists",
    "Add a service",
    "Add a stylist",
    "View analytics",
  ];

  // ──────────────────────────────────────────────────────────
  // Initialize
  // ──────────────────────────────────────────────────────────

  useEffect(() => {
    const storedId = getStoredUserId();
    if (storedId) {
      setUserId(storedId);
    }
  }, []);

  useEffect(() => {
    async function loadShop() {
      setShopLoading(true);
      setAuthError(null);

      try {
        const shopData = await getShopBySlug(slug);
        setShop(shopData);
      } catch (err) {
        console.error("Failed to load shop:", err);
        if (isApiError(err) && err.status === 404) {
          setAuthError(`Shop "${slug}" not found. It may have been deleted or the URL is incorrect.`);
        } else {
          setAuthError(getErrorMessage(err));
        }
      } finally {
        setShopLoading(false);
      }
    }

    if (slug) {
      loadShop();
    }
  }, [slug]);

  // ──────────────────────────────────────────────────────────
  // Data Fetching
  // ──────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    if (!shop) return;
    setDataLoading(true);

    try {
      const [servicesData, stylistsData] = await Promise.all([
        getServices(slug),
        getStylists(slug),
      ]);
      setServices(servicesData);
      setStylists(stylistsData);
    } catch (err) {
      console.error("Failed to load data:", err);
    } finally {
      setDataLoading(false);
    }
  }, [shop, slug]);

  useEffect(() => {
    if (shop) {
      fetchData();
    }
  }, [shop, fetchData]);

  // ──────────────────────────────────────────────────────────
  // Chat
  // ──────────────────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    if (!userId) {
      setAuthError("Please enter your Owner ID to send messages.");
      return;
    }

    const userMsg: OwnerMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: text.trim(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputValue("");
    setIsLoading(true);
    setSuggestedChips([]);

    try {
      const conversationHistory = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.text,
      }));

      const res = await fetch(`${API_BASE}/s/${slug}/owner/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ messages: conversationHistory }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          setAuthError("Your session has expired. Please re-enter your Owner ID.");
          return;
        }
        if (res.status === 403) {
          setAuthError("You don't have permission to access this shop. Make sure you're the owner.");
          return;
        }
        throw new Error("Failed to get response");
      }

      const data: OwnerChatResponse = await res.json();
      
      const assistantMsg: OwnerMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: data.reply,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      if (data.suggested_chips?.length) {
        setSuggestedChips(data.suggested_chips);
      }

      // Refresh data after chat action
      fetchData();
    } catch (error) {
      console.error("Chat error:", error);
      const errorMsg: OwnerMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: "Sorry, I encountered an error. Please try again.",
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }

  // ──────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────

  function formatMoney(cents: number) {
    return `$${(cents / 100).toFixed(2)}`;
  }

  function handleLogout() {
    clearStoredUserId();
    setUserId(null);
    router.push("/onboarding");
  }

  function handleSetUserId(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const input = form.elements.namedItem("userId") as HTMLInputElement;
    if (input.value.trim()) {
      setStoredUserId(input.value.trim());
      setUserId(input.value.trim());
      setAuthError(null);
    }
  }

  // ──────────────────────────────────────────────────────────
  // Loading State
  // ──────────────────────────────────────────────────────────

  if (shopLoading) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center"
        >
          <Loader2 className="w-10 h-10 text-[#00d4ff] animate-spin mx-auto mb-4" />
          <p className="text-sm text-gray-400">Loading shop...</p>
        </motion.div>
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────
  // Error State
  // ──────────────────────────────────────────────────────────

  if (authError && !shop) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-2xl p-8 max-w-md w-full border border-white/5"
        >
          <div className="text-center">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-red-500/10 flex items-center justify-center border border-red-500/30 mb-4">
              <AlertCircle className="w-8 h-8 text-red-400" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Shop Not Found</h2>
            <p className="text-sm text-gray-400 mb-6">{authError}</p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => router.push("/onboarding")}
                className="px-4 py-2 rounded-xl btn-neon text-sm"
              >
                Create a Shop
              </button>
              <button
                onClick={() => router.push("/owner")}
                className="px-4 py-2 rounded-xl glass border border-white/10 text-gray-300 hover:bg-white/10 text-sm"
              >
                Go to Dashboard
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────
  // User ID Modal
  // ──────────────────────────────────────────────────────────

  if (!userId) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-2xl p-8 max-w-md w-full border border-white/5"
        >
          <div className="text-center mb-6">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 via-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-4">
              <User className="w-8 h-8 text-[#00d4ff]" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Sign In</h2>
            <p className="text-sm text-gray-400">
              Enter your Owner ID to access {shop?.name || "this shop"}
            </p>
          </div>

          <form onSubmit={handleSetUserId} className="space-y-4">
            <input
              name="userId"
              type="text"
              placeholder="Enter your Owner ID"
              className="w-full px-4 py-3 rounded-xl input-glass text-sm"
              autoFocus
            />
            
            {authError && (
              <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/30">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-red-300">{authError}</p>
              </div>
            )}

            <button
              type="submit"
              className="w-full py-3 rounded-xl btn-neon text-sm font-medium"
            >
              Continue
            </button>
          </form>

          <p className="text-xs text-gray-500 text-center mt-4">
            Don't have an account?{" "}
            <button
              onClick={() => router.push("/onboarding")}
              className="text-[#00d4ff] hover:underline"
            >
              Create a shop
            </button>
          </p>
        </motion.div>
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────
  // Main Dashboard
  // ──────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white">
      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0a0e1a]/80 border-b border-white/5">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] via-[#a855f7] to-[#ec4899] flex items-center justify-center shadow-neon">
              <Store className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">{shop?.name || "Dashboard"}</h1>
              <p className="text-xs text-gray-500">Owner Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              {userId}
            </span>
            <button
              onClick={handleLogout}
              className="p-2 rounded-xl glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
              title="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Auth Error Banner */}
      <AnimatePresence>
        {authError && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="bg-red-500/10 border-b border-red-500/30 px-4 py-3"
          >
            <div className="max-w-6xl mx-auto flex items-center gap-3">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              <p className="text-sm text-red-300">{authError}</p>
              <button
                onClick={() => setAuthError(null)}
                className="ml-auto p-1 hover:bg-red-500/20 rounded"
              >
                <X className="w-4 h-4 text-red-400" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid lg:grid-cols-[1.2fr_0.8fr] gap-6">
        {/* Chat Section */}
        <section className="glass-card rounded-2xl p-6 border border-white/5">
          <div className="space-y-4 max-h-96 overflow-y-auto scrollbar-hide">
            {messages.map((msg, index) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm ${
                  msg.role === "assistant"
                    ? "glass border border-white/5 text-gray-200"
                    : "bg-gradient-to-r from-[#00d4ff] to-[#a855f7] text-white ml-auto shadow-neon"
                }`}
              >
                {msg.text}
              </motion.div>
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="spinner" />
                Thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Quick Actions */}
          <div className="mt-6">
            <p className="text-xs text-gray-500 mb-3 flex items-center gap-2">
              <Sparkles className="w-3 h-3 text-[#00d4ff]" />
              Quick actions
            </p>
            <div className="flex flex-wrap gap-2">
              {quickActions.map((action) => (
                <motion.button
                  key={action}
                  whileHover={{ scale: 1.02, y: -1 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => sendMessage(action)}
                  className="px-3 py-2 rounded-full glass border border-white/10 hover:bg-white/10 text-gray-300 hover:text-white text-xs transition-all"
                >
                  {action}
                </motion.button>
              ))}
            </div>
            {suggestedChips.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-500 mb-2">Suggested</p>
                <div className="flex flex-wrap gap-2">
                  {suggestedChips.map((chip) => (
                    <motion.button
                      key={chip}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => sendMessage(chip)}
                      className="px-3 py-2 rounded-full bg-[#00d4ff]/10 text-[#00d4ff] text-xs hover:bg-[#00d4ff]/20 transition-all border border-[#00d4ff]/30"
                    >
                      {chip}
                    </motion.button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="mt-6 flex items-center gap-2">
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage(inputValue);
              }}
              placeholder="Type an owner command..."
              className="flex-1 px-4 py-3 rounded-full input-glass text-sm"
            />
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => sendMessage(inputValue)}
              className="px-5 py-3 rounded-full btn-neon text-sm font-medium flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
              Send
            </motion.button>
          </div>
        </section>

        {/* Right Sidebar */}
        <aside className="space-y-6">
          {/* Tabs */}
          <div className="flex gap-2 p-1 glass rounded-full">
            <button
              onClick={() => setRightView("services")}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === "services"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Scissors className="w-4 h-4" />
              Services
            </button>
            <button
              onClick={() => setRightView("stylists")}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === "stylists"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Users className="w-4 h-4" />
              Stylists
            </button>
          </div>

          {/* Services View */}
          {rightView === "services" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-6 border border-white/5"
            >
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Scissors className="w-4 h-4 text-[#00d4ff]" />
                    Current services
                  </h2>
                  <p className="text-xs text-gray-500">Live view from the database.</p>
                </div>
                <button
                  onClick={fetchData}
                  disabled={dataLoading}
                  className="p-2 rounded-lg glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${dataLoading ? "animate-spin" : ""}`} />
                </button>
              </div>
              <div className="space-y-3">
                {services.length === 0 && !dataLoading && (
                  <div className="text-xs text-gray-500 text-center py-8">
                    No services configured yet.
                    <br />
                    <span className="text-[#00d4ff]">Try "Add a service" in chat!</span>
                  </div>
                )}
                {dataLoading && services.length === 0 && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 text-[#00d4ff] animate-spin" />
                  </div>
                )}
                {services && services.length > 0 && services.map((svc) => (
                  <motion.div
                    key={svc.id}
                    whileHover={{ scale: 1.01 }}
                    className="glass rounded-xl p-3 border border-white/5 hover:border-[#00d4ff]/30 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">{svc.name}</p>
                        <p className="text-xs text-gray-500 flex items-center gap-2 mt-1">
                          <Clock className="w-3 h-3" />
                          {svc.duration_minutes} min
                          <span className="text-[#00d4ff]">·</span>
                          <DollarSign className="w-3 h-3" />
                          {formatMoney(svc.price_cents)}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Stylists View */}
          {rightView === "stylists" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-6 border border-white/5"
            >
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Users className="w-4 h-4 text-[#a855f7]" />
                    Current stylists
                  </h2>
                  <p className="text-xs text-gray-500">Hours and specialties.</p>
                </div>
                <button
                  onClick={fetchData}
                  disabled={dataLoading}
                  className="p-2 rounded-lg glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${dataLoading ? "animate-spin" : ""}`} />
                </button>
              </div>
              <div className="space-y-3">
                {stylists.length === 0 && !dataLoading && (
                  <div className="text-xs text-gray-500 text-center py-8">
                    No stylists configured yet.
                    <br />
                    <span className="text-[#a855f7]">Try "Add a stylist" in chat!</span>
                  </div>
                )}
                {dataLoading && stylists.length === 0 && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 text-[#a855f7] animate-spin" />
                  </div>
                )}
                {stylists && stylists.length > 0 && stylists.map((stylist) => (
                  <motion.div
                    key={stylist.id}
                    whileHover={{ scale: 1.01 }}
                    className="glass rounded-xl p-3 border border-white/5 hover:border-[#a855f7]/30 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">{stylist.name}</p>
                        <p className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                          <Clock className="w-3 h-3" />
                          {stylist.work_start}–{stylist.work_end}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {stylist.specialties.length > 0
                            ? stylist.specialties.join(", ")
                            : "No specialties"}
                        </p>
                      </div>
                      {stylist.time_off_count > 0 && (
                        <span className="text-[11px] px-2 py-1 rounded-full glass border border-white/10 text-gray-400">
                          {stylist.time_off_count} {stylist.time_off_count === 1 ? "day" : "days"} off
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Shop Info Card */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-2xl p-4 border border-white/5"
          >
            <h3 className="text-xs font-semibold text-gray-400 mb-3">Shop Info</h3>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Name</span>
                <span className="text-white">{shop?.name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Slug</span>
                <span className="text-[#00d4ff] font-mono">{shop?.slug}</span>
              </div>
              {shop?.phone && (
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Phone</span>
                  <span className="text-white">{shop.phone}</span>
                </div>
              )}
              {shop?.timezone && (
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Timezone</span>
                  <span className="text-white">{shop.timezone.replace("_", " ")}</span>
                </div>
              )}
              {shop?.category && (
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Category</span>
                  <span className="text-white capitalize">{shop.category}</span>
                </div>
              )}
            </div>
          </motion.div>
        </aside>
      </main>
    </div>
  );
}
