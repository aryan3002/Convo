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
  Lock,
  Unlock,
  Search,
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

// Extracted shared components and hooks
import {
  useOwnerPromos,
  useOwnerAnalytics,
  useOwnerSchedule,
  useOwnerPinManagement,
  useOwnerCustomerLookup,
  useOwnerCallSummaries,
  useOwnerTimeOffRequests,
  useOwnerServiceBookings,
  useOwnerStylistTimeOff,
} from "@/hooks";
import {
  PromoWizard,
  PromosTab,
  AnalyticsDashboard,
  ScheduleGrid,
  PinManagementModal,
  PinStatusButton,
  CustomerLookupCard,
  CallSummariesSection,
  TimeOffApprovalCard,
  ServiceBookingsModal,
  ServiceBookingBadge,
} from "@/components/owner";
import AskConvo from "@/components/AskConvo";
import type { OwnerService, OwnerStylist } from "@/lib/owner-types";
import {
  formatMoney,
  formatTimeLabel,
  formatDateLabel,
  formatDuration,
  minutesToTimeValue,
  summarizeTimeOff,
} from "@/lib/owner-utils";

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
  data?: {
    services?: OwnerService[];
    stylists?: OwnerStylist[];
  };
};

type RightView = "services" | "stylists" | "promos" | "analytics" | "schedule" | "ask";

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

  // Integrated hooks for all features
  const promos = useOwnerPromos(slug);
  const analytics = useOwnerAnalytics(slug);
  const schedule = useOwnerSchedule(slug);
  const pinManagement = useOwnerPinManagement(slug);
  const customerLookup = useOwnerCustomerLookup(slug);
  const callSummaries = useOwnerCallSummaries(slug);
  const timeOffRequests = useOwnerTimeOffRequests(slug);
  const serviceBookings = useOwnerServiceBookings(slug);
  const stylistTimeOff = useOwnerStylistTimeOff(slug);

  // Quick actions
  const quickActions = useMemo(
    () => [
      "Add a service",
      "Change price of a service",
      "Remove a service",
      "Add a stylist",
      "Set stylist off time",
      "Add a specialization",
      "Add promotions",
    ],
    []
  );

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
      // Also fetch promos, analytics when shop loads
      promos.fetchPromos();
      analytics.fetchSummary();
      // Schedule will be fetched when user clicks on Schedule tab
      callSummaries.fetchCallSummaries();
      timeOffRequests.fetchPendingRequests();
      serviceBookings.fetchBookingCounts();
    }
  }, [shop]);

  // Fetch PIN statuses when stylists are loaded
  useEffect(() => {
    if (stylists.length > 0) {
      pinManagement.fetchAllPinStatuses(stylists.map((s) => s.id));
    }
  }, [stylists]);

  // ──────────────────────────────────────────────────────────
  // Chat
  // ──────────────────────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;

    // Handle special actions
    const normalized = text.trim().toLowerCase();
    if (normalized.includes("add promotion")) {
      promos.openWizard();
      return;
    }

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

      // Apply any data updates from response
      if (data.data?.services) {
        setServices(data.data.services as unknown as Service[]);
      }
      if (data.data?.stylists) {
        setStylists(data.data.stylists as unknown as Stylist[]);
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
    <div className="min-h-screen bg-[#0a0e1a] text-white relative">
      {/* Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <motion.div
          className="absolute w-[600px] h-[600px] rounded-full blur-[150px]"
          style={{ background: "rgba(0, 212, 255, 0.08)", top: "-10%", left: "-10%" }}
          animate={{ x: [0, 100, 50, 0], y: [0, -50, 30, 0] }}
          transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full blur-[150px]"
          style={{ background: "rgba(168, 85, 247, 0.08)", top: "30%", right: "-5%" }}
          animate={{ x: [0, -80, 40, 0], y: [0, 60, -30, 0] }}
          transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute w-[400px] h-[400px] rounded-full blur-[150px]"
          style={{ background: "rgba(236, 72, 153, 0.06)", bottom: "-5%", left: "30%" }}
          animate={{ x: [0, 50, -30, 0], y: [0, -40, 60, 0] }}
          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
        />
      </div>

      {/* Grid Background */}
      <div
        className="fixed inset-0 pointer-events-none -z-20 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
        }}
      />

      {/* Modals */}
      <PinManagementModal
        open={pinManagement.modalOpen}
        stylistId={pinManagement.selectedStylistId}
        stylistName={pinManagement.selectedStylistName}
        pinValue={pinManagement.pinValue}
        loading={pinManagement.loading}
        pinStatus={
          pinManagement.selectedStylistId
            ? pinManagement.pinStatuses[pinManagement.selectedStylistId]
            : undefined
        }
        onClose={pinManagement.closeModal}
        onSetPin={pinManagement.setPin}
        onRemovePin={pinManagement.removePin}
        onPinValueChange={pinManagement.setPinValue}
      />

      <ServiceBookingsModal
        open={serviceBookings.modalOpen}
        serviceName={serviceBookings.selectedServiceName}
        bookings={serviceBookings.selectedBookings}
        loading={serviceBookings.loading}
        onClose={serviceBookings.closeModal}
      />

      {/* Selected Booking Modal */}
      {schedule.selectedBooking && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 overlay">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong rounded-2xl shadow-neon p-6 max-w-md w-full relative border border-white/10"
          >
            <button
              onClick={() => schedule.setSelectedBooking(null)}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">Booking details</h3>
              <p className="text-xs text-gray-400">
                {schedule.selectedBooking.secondary_service_name
                  ? `${schedule.selectedBooking.service_name} + ${schedule.selectedBooking.secondary_service_name}`
                  : schedule.selectedBooking.service_name}{" "}
                · {schedule.selectedBooking.customer_name || "Guest"}
              </p>
            </div>
            {schedule.selectedBooking.preferred_style_text && (
              <p className="text-sm text-gray-300 whitespace-pre-wrap mb-4">
                {schedule.selectedBooking.preferred_style_text}
              </p>
            )}
            {schedule.selectedBooking.preferred_style_image_url && (
              <div className="rounded-xl overflow-hidden border border-white/10 bg-black/30">
                <img
                  src={schedule.selectedBooking.preferred_style_image_url}
                  alt="Preferred style"
                  className="w-full max-h-64 object-cover"
                />
              </div>
            )}
            {!schedule.selectedBooking.preferred_style_text &&
              !schedule.selectedBooking.preferred_style_image_url && (
                <p className="text-sm text-gray-500">No preferred style saved for this booking.</p>
              )}
          </motion.div>
        </div>
      )}

      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0a0e1a]/80 border-b border-white/5">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/owner-landing")}
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] via-[#a855f7] to-[#ec4899] flex items-center justify-center shadow-neon hover:scale-105 transition-transform"
              title="Back to Shops"
            >
              <Store className="w-5 h-5 text-white" />
            </button>
            <div>
              <h1 className="text-lg font-bold text-white">{shop?.name || "Dashboard"}</h1>
              <p className="text-xs text-gray-500">Owner Dashboard · Multi-tenant</p>
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
        {/* Left Column - Chat Section */}
        <section className="space-y-6">
          <div className="glass-card rounded-2xl p-6 border border-white/5">
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
                    onClick={() => {
                      if (action === "Add promotions") {
                        promos.openWizard();
                      } else {
                        sendMessage(action);
                      }
                    }}
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

            {/* Call Summaries Section */}
            <CallSummariesSection
              summaries={callSummaries.summaries}
              loading={callSummaries.loading}
              expanded={callSummaries.expanded}
              onToggleExpanded={callSummaries.toggleExpanded}
              onRefresh={callSummaries.refresh}
            />
          </div>

          {/* Time Off Approval Card */}
          <TimeOffApprovalCard
            requests={timeOffRequests.requests}
            stylists={stylists as unknown as OwnerStylist[]}
            loading={timeOffRequests.loading}
            reviewLoading={timeOffRequests.reviewLoading}
            onRefresh={timeOffRequests.fetchPendingRequests}
            onApprove={(id) => timeOffRequests.approveRequest(id, () => schedule.fetchSchedule())}
            onReject={timeOffRequests.rejectRequest}
          />
        </section>

        {/* Right Sidebar */}
        <aside className="space-y-6">
          {/* Tabs */}
          <div className="flex flex-wrap gap-2 p-1 glass rounded-2xl">
            <button
              onClick={() => setRightView("services")}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "services"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Scissors className="w-3 h-3" />
              Services
            </button>
            <button
              onClick={() => setRightView("stylists")}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "stylists"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Users className="w-3 h-3" />
              Stylists
            </button>
            <button
              onClick={() => setRightView("promos")}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "promos"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Tag className="w-3 h-3" />
              Promos
            </button>
            <button
              onClick={() => setRightView("analytics")}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "analytics"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <BarChart3 className="w-3 h-3" />
              Analytics
            </button>
            <button
              onClick={() => {
                setRightView("schedule");
                if (schedule.stylists.length === 0) {
                  schedule.fetchSchedule();
                }
              }}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "schedule"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Calendar className="w-3 h-3" />
              Schedule
            </button>
            <button
              onClick={() => setRightView("ask")}
              className={`flex-1 px-3 py-2 rounded-full text-xs font-medium transition-all flex items-center justify-center gap-1 ${
                rightView === "ask"
                  ? "btn-neon"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <HelpCircle className="w-3 h-3" />
              Ask
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
                {(!services || services.length === 0) && !dataLoading && (
                  <div className="text-xs text-gray-500 text-center py-8">
                    No services configured yet.
                    <br />
                    <span className="text-[#00d4ff]">Try "Add a service" in chat!</span>
                  </div>
                )}
                {dataLoading && (!services || services.length === 0) && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 text-[#00d4ff] animate-spin" />
                  </div>
                )}
                {services && Array.isArray(services) && services.map((svc) => {
                  const count = serviceBookings.bookingCounts[svc.id] || 0;
                  return (
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
                        <ServiceBookingBadge
                          count={count}
                          onClick={() => serviceBookings.fetchServiceBookings(svc.id, svc.name)}
                        />
                      </div>
                    </motion.div>
                  );
                })}
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
                  <p className="text-xs text-gray-500">Hours, specialties, and PIN status.</p>
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
                {(!stylists || stylists.length === 0) && !dataLoading && (
                  <div className="text-xs text-gray-500 text-center py-8">
                    No stylists configured yet.
                    <br />
                    <span className="text-[#a855f7]">Try "Add a stylist" in chat!</span>
                  </div>
                )}
                {dataLoading && (!stylists || stylists.length === 0) && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 text-[#a855f7] animate-spin" />
                  </div>
                )}
                {stylists && Array.isArray(stylists) && stylists.map((stylist) => (
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
                      <div className="flex flex-col gap-2">
                        <PinStatusButton
                          stylistId={stylist.id}
                          stylistName={stylist.name}
                          pinStatus={pinManagement.pinStatuses[stylist.id]}
                          onOpenModal={pinManagement.openModal}
                        />
                        <button
                          type="button"
                          onClick={() => stylistTimeOff.toggleStylistTimeOff(stylist.id)}
                          className="text-[11px] px-2 py-1 rounded-full glass border border-white/10 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
                        >
                          {stylist.time_off_count}{" "}
                          {stylist.time_off_count === 1 ? "day" : "days"} off
                        </button>
                      </div>
                    </div>
                    <AnimatePresence>
                      {stylistTimeOff.openStylistId === stylist.id && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="mt-3 glass rounded-xl px-3 py-2 text-xs text-gray-400 border border-white/5"
                        >
                          {stylistTimeOff.loading &&
                            !stylistTimeOff.timeOffEntries[stylist.id] && (
                              <div className="flex items-center gap-2">
                                <div className="spinner w-3 h-3" />
                                Loading time off...
                              </div>
                            )}
                          {!stylistTimeOff.loading &&
                            (stylistTimeOff.timeOffEntries[stylist.id]?.length ?? 0) === 0 && (
                              <div className="text-gray-500">No time off logged.</div>
                            )}
                          {stylistTimeOff.timeOffEntries[stylist.id]?.length ? (
                            <div className="space-y-2">
                              {summarizeTimeOff(stylistTimeOff.timeOffEntries[stylist.id]).map(
                                (entry) => (
                                  <div
                                    key={`${stylist.id}-${entry.date}`}
                                    className="flex items-start justify-between gap-3"
                                  >
                                    <div>
                                      <div className="text-[11px] font-semibold text-white">
                                        {formatDateLabel(entry.date)}
                                      </div>
                                      <div className="text-[11px] text-gray-500">
                                        {entry.blocks
                                          .map(
                                            (block) =>
                                              `${formatTimeLabel(
                                                minutesToTimeValue(block.start)
                                              )}–${formatTimeLabel(
                                                minutesToTimeValue(block.end)
                                              )}`
                                          )
                                          .join(", ")}
                                      </div>
                                    </div>
                                    <div className="text-[11px] font-semibold text-[#00d4ff]">
                                      {formatDuration(entry.totalMinutes)}
                                    </div>
                                  </div>
                                )
                              )}
                            </div>
                          ) : null}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Promos View */}
          {rightView === "promos" && (
            <PromosTab
              promos={promos.promos}
              services={services as unknown as OwnerService[]}
              actionOpenId={promos.actionOpenId}
              actionLoading={promos.actionLoading}
              onOpenWizard={promos.openWizard}
              onToggleActive={promos.togglePromoActive}
              onRemove={promos.removePromo}
              onSetActionOpenId={promos.setActionOpenId}
            />
          )}

          {/* Analytics View */}
          {rightView === "analytics" && (
            <AnalyticsDashboard
              range={analytics.range}
              summary={analytics.summary}
              loading={analytics.loading}
              aiInsights={analytics.aiInsights}
              aiLoading={analytics.aiLoading}
              aiError={analytics.aiError}
              onChangeRange={analytics.changeRange}
              onFetchAiInsights={analytics.fetchAiInsights}
            />
          )}

          {/* Ask Convo (RAG) View */}
          {rightView === "ask" && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl border border-white/5 h-[600px] overflow-hidden"
            >
              <AskConvo apiBase={`${API_BASE}/s/${slug}`} />
            </motion.div>
          )}

          {/* Customer Lookup Card */}
          <CustomerLookupCard
            identity={customerLookup.identity}
            loading={customerLookup.loading}
            error={customerLookup.error}
            profile={customerLookup.profile}
            onIdentityChange={customerLookup.setIdentity}
            onSearch={customerLookup.lookupCustomer}
          />

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

      {/* Schedule Section - Full Width Below Main Grid */}
      {rightView === "schedule" && (
        <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-10">
          <ScheduleGrid
            date={schedule.date}
            stylists={schedule.stylists}
            bookings={schedule.bookings}
            timeOff={schedule.timeOff}
            loading={schedule.loading}
            styleFilter={schedule.styleFilter}
            selectedBooking={schedule.selectedBooking}
            onDateChange={(newDate) => {
              schedule.changeDate(newDate);
              schedule.fetchSchedule(newDate);
            }}
            onPrevDay={() => {
              const newDate = schedule.goToPrevDay();
              schedule.fetchSchedule(newDate);
            }}
            onNextDay={() => {
              const newDate = schedule.goToNextDay();
              schedule.fetchSchedule(newDate);
            }}
            onStyleFilterChange={schedule.setStyleFilter}
            onSelectBooking={schedule.setSelectedBooking}
            onReschedule={schedule.rescheduleBooking}
            onCancel={schedule.cancelBooking}
          />
        </section>
      )}

      {/* Promo Wizard Modal */}
      <PromoWizard
        open={promos.wizardOpen}
        step={promos.wizardStep}
        error={promos.wizardError}
        saving={promos.saving}
        draft={promos.draft}
        services={services as unknown as OwnerService[]}
        onClose={promos.closeWizard}
        onNext={promos.nextStep}
        onBack={promos.prevStep}
        onCreate={promos.createPromo}
        onUpdateDraft={promos.updateDraft}
      />
    </div>
  );
}
