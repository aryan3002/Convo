"use client";

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import {
  Store,
  Scissors,
  Users,
  Check,
  ChevronRight,
  Plus,
  X,
  Clock,
  DollarSign,
  Sparkles,
  ArrowRight,
  Loader2,
  AlertCircle,
  MessageSquare,
} from "lucide-react";
import {
  getApiBase,
  getShopBySlug,
  getStoredUserId,
  type Shop,
} from "@/lib/api";

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

type SetupStep = "welcome" | "services" | "staff" | "complete";

interface QuickService {
  id?: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
}

interface QuickStylist {
  id?: number;
  name: string;
  work_start: string;
  work_end: string;
}

// ──────────────────────────────────────────────────────────
// Step Components
// ──────────────────────────────────────────────────────────

interface WelcomeStepProps {
  shop: Shop | null;
  onNext: () => void;
  onSkipAll: () => void;
}

function WelcomeStep({ shop, onNext, onSkipAll }: WelcomeStepProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="max-w-lg mx-auto text-center"
    >
      <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 via-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-6">
        <Sparkles className="w-10 h-10 text-[#00d4ff]" />
      </div>

      <h1 className="text-3xl font-bold text-white mb-3">
        Welcome to {shop?.name || "Your Shop"}!
      </h1>
      <p className="text-gray-400 mb-8">
        Let's set up your shop in just a few steps. You can add services and staff
        now, or skip and do it later through the dashboard.
      </p>

      <div className="space-y-3 mb-8">
        {[
          { icon: Scissors, label: "Add your services", desc: "Haircuts, coloring, etc." },
          { icon: Users, label: "Add your staff", desc: "Stylists, barbers, etc." },
          { icon: MessageSquare, label: "Start managing", desc: "Use AI chat to run your shop" },
        ].map((item, i) => (
          <div
            key={i}
            className="flex items-center gap-4 p-4 rounded-xl glass border border-white/5 text-left"
          >
            <div className="w-10 h-10 rounded-lg bg-[#00d4ff]/10 flex items-center justify-center">
              <item.icon className="w-5 h-5 text-[#00d4ff]" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">{item.label}</p>
              <p className="text-xs text-gray-500">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3">
        <button
          onClick={onNext}
          className="w-full py-3 rounded-xl btn-neon text-sm font-medium flex items-center justify-center gap-2"
        >
          Let's Get Started
          <ArrowRight className="w-4 h-4" />
        </button>
        <button
          onClick={onSkipAll}
          className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          Skip setup and go to dashboard →
        </button>
      </div>
    </motion.div>
  );
}

interface ServicesStepProps {
  slug: string;
  userId: string;
  services: QuickService[];
  setServices: React.Dispatch<React.SetStateAction<QuickService[]>>;
  onNext: () => void;
  onSkip: () => void;
}

function ServicesStep({ slug, userId, services, setServices, onNext, onSkip }: ServicesStepProps) {
  const API_BASE = getApiBase();
  const [isAdding, setIsAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", duration: "30", price: "" });

  const handleAdd = async () => {
    if (!form.name.trim() || !form.price.trim()) {
      setError("Please fill in name and price.");
      return;
    }

    const priceNum = parseFloat(form.price);
    if (isNaN(priceNum) || priceNum < 0) {
      setError("Please enter a valid price.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/s/${slug}/owner/services/quick-add`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          name: form.name.trim(),
          duration_minutes: parseInt(form.duration, 10),
          price_cents: Math.round(priceNum * 100),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to add service");
      }

      const newService = await res.json();
      setServices((prev) => [...prev, newService]);
      setForm({ name: "", duration: "30", price: "" });
      setIsAdding(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add service");
    } finally {
      setSaving(false);
    }
  };

  const removeService = (index: number) => {
    setServices((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 50 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -50 }}
      className="max-w-lg mx-auto"
    >
      {/* Progress */}
      <div className="flex items-center gap-2 mb-8 justify-center">
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">1</div>
        <div className="w-12 h-0.5 bg-white/20" />
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-gray-500">2</div>
        <div className="w-12 h-0.5 bg-white/20" />
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-gray-500">3</div>
      </div>

      <h2 className="text-2xl font-bold text-white mb-2 text-center">Add Your Services</h2>
      <p className="text-gray-400 text-sm mb-6 text-center">
        What services does your shop offer? Add a few to get started.
      </p>

      {/* Added Services */}
      {services.length > 0 && (
        <div className="space-y-2 mb-4">
          {services.map((service, i) => (
            <div
              key={service.id || i}
              className="flex items-center justify-between p-3 rounded-xl glass border border-white/5"
            >
              <div className="flex items-center gap-3">
                <Scissors className="w-4 h-4 text-[#00d4ff]" />
                <div>
                  <p className="text-sm font-medium text-white">{service.name}</p>
                  <p className="text-xs text-gray-500">
                    {service.duration_minutes} min • ${(service.price_cents / 100).toFixed(2)}
                  </p>
                </div>
              </div>
              <button
                onClick={() => removeService(i)}
                className="p-1 rounded hover:bg-white/10"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Form */}
      {isAdding ? (
        <div className="glass-card rounded-xl p-4 border border-white/5 mb-6">
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Service name (e.g., Men's Haircut)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 rounded-lg input-glass text-sm"
              autoFocus
            />
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">Duration</label>
                <select
                  value={form.duration}
                  onChange={(e) => setForm({ ...form, duration: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                >
                  <option value="15">15 min</option>
                  <option value="30">30 min</option>
                  <option value="45">45 min</option>
                  <option value="60">1 hour</option>
                  <option value="90">1.5 hours</option>
                  <option value="120">2 hours</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">Price ($)</label>
                <input
                  type="number"
                  placeholder="25.00"
                  value={form.price}
                  onChange={(e) => setForm({ ...form, price: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                  min="0"
                  step="0.01"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertCircle className="w-3 h-3" />
                {error}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={saving}
                className="flex-1 py-2 rounded-lg btn-neon text-sm flex items-center justify-center gap-2"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {saving ? "Adding..." : "Add Service"}
              </button>
              <button
                onClick={() => {
                  setIsAdding(false);
                  setError(null);
                }}
                className="px-4 py-2 rounded-lg glass border border-white/10 text-sm text-gray-400"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsAdding(true)}
          className="w-full py-3 rounded-xl glass border border-dashed border-white/20 text-sm text-gray-400 hover:border-[#00d4ff]/50 hover:text-[#00d4ff] transition-colors flex items-center justify-center gap-2 mb-6"
        >
          <Plus className="w-4 h-4" />
          Add a Service
        </button>
      )}

      {/* Navigation */}
      <div className="flex gap-3">
        <button
          onClick={onSkip}
          className="flex-1 py-3 rounded-xl glass border border-white/10 text-sm text-gray-400 hover:bg-white/5"
        >
          Skip for now
        </button>
        <button
          onClick={onNext}
          className="flex-1 py-3 rounded-xl btn-neon text-sm font-medium flex items-center justify-center gap-2"
        >
          {services.length > 0 ? "Continue" : "Next"}
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  );
}

interface StaffStepProps {
  slug: string;
  userId: string;
  staff: QuickStylist[];
  setStaff: React.Dispatch<React.SetStateAction<QuickStylist[]>>;
  onNext: () => void;
  onSkip: () => void;
}

function StaffStep({ slug, userId, staff, setStaff, onNext, onSkip }: StaffStepProps) {
  const API_BASE = getApiBase();
  const [isAdding, setIsAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", workStart: "09:00", workEnd: "17:00" });

  const handleAdd = async () => {
    if (!form.name.trim()) {
      setError("Please enter a name.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/s/${slug}/owner/stylists/quick-add`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          name: form.name.trim(),
          work_start: form.workStart,
          work_end: form.workEnd,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to add staff");
      }

      const newStaff = await res.json();
      setStaff((prev) => [...prev, newStaff]);
      setForm({ name: "", workStart: "09:00", workEnd: "17:00" });
      setIsAdding(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add staff");
    } finally {
      setSaving(false);
    }
  };

  const removeStaff = (index: number) => {
    setStaff((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 50 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -50 }}
      className="max-w-lg mx-auto"
    >
      {/* Progress */}
      <div className="flex items-center gap-2 mb-8 justify-center">
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">
          <Check className="w-4 h-4" />
        </div>
        <div className="w-12 h-0.5 bg-[#00d4ff]" />
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">2</div>
        <div className="w-12 h-0.5 bg-white/20" />
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-gray-500">3</div>
      </div>

      <h2 className="text-2xl font-bold text-white mb-2 text-center">Add Your Staff</h2>
      <p className="text-gray-400 text-sm mb-6 text-center">
        Who works at your shop? Add your stylists, barbers, or staff members.
      </p>

      {/* Added Staff */}
      {staff.length > 0 && (
        <div className="space-y-2 mb-4">
          {staff.map((member, i) => (
            <div
              key={member.id || i}
              className="flex items-center justify-between p-3 rounded-xl glass border border-white/5"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#a855f7] to-[#ec4899] flex items-center justify-center text-xs font-bold text-white">
                  {member.name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-medium text-white">{member.name}</p>
                  <p className="text-xs text-gray-500">
                    {member.work_start} - {member.work_end}
                  </p>
                </div>
              </div>
              <button
                onClick={() => removeStaff(i)}
                className="p-1 rounded hover:bg-white/10"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Form */}
      {isAdding ? (
        <div className="glass-card rounded-xl p-4 border border-white/5 mb-6">
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Staff member name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 rounded-lg input-glass text-sm"
              autoFocus
            />
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">Work Start</label>
                <select
                  value={form.workStart}
                  onChange={(e) => setForm({ ...form, workStart: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                >
                  {Array.from({ length: 24 }, (_, i) => {
                    const hour = i.toString().padStart(2, "0");
                    return (
                      <option key={hour} value={`${hour}:00`}>
                        {i === 0 ? "12:00 AM" : i < 12 ? `${i}:00 AM` : i === 12 ? "12:00 PM" : `${i - 12}:00 PM`}
                      </option>
                    );
                  })}
                </select>
              </div>
              <div className="flex-1">
                <label className="text-xs text-gray-500 mb-1 block">Work End</label>
                <select
                  value={form.workEnd}
                  onChange={(e) => setForm({ ...form, workEnd: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                >
                  {Array.from({ length: 24 }, (_, i) => {
                    const hour = i.toString().padStart(2, "0");
                    return (
                      <option key={hour} value={`${hour}:00`}>
                        {i === 0 ? "12:00 AM" : i < 12 ? `${i}:00 AM` : i === 12 ? "12:00 PM" : `${i - 12}:00 PM`}
                      </option>
                    );
                  })}
                </select>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-red-400 text-xs">
                <AlertCircle className="w-3 h-3" />
                {error}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleAdd}
                disabled={saving}
                className="flex-1 py-2 rounded-lg btn-neon text-sm flex items-center justify-center gap-2"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {saving ? "Adding..." : "Add Staff"}
              </button>
              <button
                onClick={() => {
                  setIsAdding(false);
                  setError(null);
                }}
                className="px-4 py-2 rounded-lg glass border border-white/10 text-sm text-gray-400"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setIsAdding(true)}
          className="w-full py-3 rounded-xl glass border border-dashed border-white/20 text-sm text-gray-400 hover:border-[#a855f7]/50 hover:text-[#a855f7] transition-colors flex items-center justify-center gap-2 mb-6"
        >
          <Plus className="w-4 h-4" />
          Add Staff Member
        </button>
      )}

      {/* Navigation */}
      <div className="flex gap-3">
        <button
          onClick={onSkip}
          className="flex-1 py-3 rounded-xl glass border border-white/10 text-sm text-gray-400 hover:bg-white/5"
        >
          Skip for now
        </button>
        <button
          onClick={onNext}
          className="flex-1 py-3 rounded-xl btn-neon text-sm font-medium flex items-center justify-center gap-2"
        >
          {staff.length > 0 ? "Continue" : "Next"}
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  );
}

interface CompleteStepProps {
  slug: string;
  servicesCount: number;
  staffCount: number;
}

function CompleteStep({ slug, servicesCount, staffCount }: CompleteStepProps) {
  const router = useRouter();

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="max-w-lg mx-auto text-center"
    >
      {/* Progress Complete */}
      <div className="flex items-center gap-2 mb-8 justify-center">
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">
          <Check className="w-4 h-4" />
        </div>
        <div className="w-12 h-0.5 bg-[#00d4ff]" />
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">
          <Check className="w-4 h-4" />
        </div>
        <div className="w-12 h-0.5 bg-[#00d4ff]" />
        <div className="w-8 h-8 rounded-full bg-[#00d4ff] flex items-center justify-center text-xs font-bold text-black">
          <Check className="w-4 h-4" />
        </div>
      </div>

      <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff] via-[#a855f7] to-[#ec4899] flex items-center justify-center mb-6">
        <Check className="w-10 h-10 text-white" />
      </div>

      <h2 className="text-3xl font-bold text-white mb-3">You're All Set!</h2>
      <p className="text-gray-400 mb-8">
        Your shop is ready to go. Head to your dashboard to start managing bookings
        with AI-powered assistance.
      </p>

      {/* Summary */}
      {(servicesCount > 0 || staffCount > 0) && (
        <div className="glass-card rounded-xl p-4 border border-white/5 mb-8">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">Setup Summary</p>
          <div className="flex justify-center gap-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-[#00d4ff]">{servicesCount}</p>
              <p className="text-xs text-gray-500">Services</p>
            </div>
            <div className="w-px bg-white/10" />
            <div className="text-center">
              <p className="text-2xl font-bold text-[#a855f7]">{staffCount}</p>
              <p className="text-xs text-gray-500">Staff</p>
            </div>
          </div>
        </div>
      )}

      <button
        onClick={() => router.push(`/s/${slug}/owner`)}
        className="w-full py-3 rounded-xl btn-neon text-sm font-medium flex items-center justify-center gap-2"
      >
        <Store className="w-4 h-4" />
        Start Managing Your Shop
        <ArrowRight className="w-4 h-4" />
      </button>

      <p className="text-xs text-gray-500 mt-4">
        You can always add more services and staff from the dashboard.
      </p>
    </motion.div>
  );
}

// ──────────────────────────────────────────────────────────
// Main Page Component
// ──────────────────────────────────────────────────────────

export default function ShopSetupWizard() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const [step, setStep] = useState<SetupStep>("welcome");
  const [shop, setShop] = useState<Shop | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data collected during setup
  const [services, setServices] = useState<QuickService[]>([]);
  const [staff, setStaff] = useState<QuickStylist[]>([]);

  // Load shop and user on mount
  useEffect(() => {
    async function init() {
      setLoading(true);
      try {
        const storedUserId = getStoredUserId();
        if (!storedUserId) {
          // Redirect to owner landing if no user ID
          router.push("/owner-landing");
          return;
        }
        setUserId(storedUserId);

        const shopData = await getShopBySlug(slug);
        setShop(shopData);
      } catch (err) {
        console.error("Failed to load shop:", err);
        setError("Failed to load shop. It may not exist.");
      } finally {
        setLoading(false);
      }
    }

    if (slug) {
      init();
    }
  }, [slug, router]);

  const handleSkipAll = () => {
    router.push(`/s/${slug}/owner`);
  };

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center"
        >
          <Loader2 className="w-10 h-10 text-[#00d4ff] animate-spin mx-auto mb-4" />
          <p className="text-sm text-gray-400">Loading your shop...</p>
        </motion.div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center max-w-md"
        >
          <div className="w-16 h-16 mx-auto rounded-2xl bg-red-500/10 flex items-center justify-center border border-red-500/30 mb-4">
            <AlertCircle className="w-8 h-8 text-red-400" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Setup Error</h2>
          <p className="text-sm text-gray-400 mb-6">{error}</p>
          <button
            onClick={() => router.push("/owner-landing")}
            className="px-6 py-2 rounded-xl btn-neon text-sm"
          >
            Go to Owner Portal
          </button>
        </motion.div>
      </div>
    );
  }

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
              <h1 className="text-lg font-bold text-white">{shop?.name || "Setup"}</h1>
              <p className="text-xs text-gray-500">Shop Setup</p>
            </div>
          </div>
          <button
            onClick={handleSkipAll}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Skip to Dashboard →
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <AnimatePresence mode="wait">
          {step === "welcome" && (
            <WelcomeStep
              key="welcome"
              shop={shop}
              onNext={() => setStep("services")}
              onSkipAll={handleSkipAll}
            />
          )}
          {step === "services" && userId && (
            <ServicesStep
              key="services"
              slug={slug}
              userId={userId}
              services={services}
              setServices={setServices}
              onNext={() => setStep("staff")}
              onSkip={() => setStep("staff")}
            />
          )}
          {step === "staff" && userId && (
            <StaffStep
              key="staff"
              slug={slug}
              userId={userId}
              staff={staff}
              setStaff={setStaff}
              onNext={() => setStep("complete")}
              onSkip={() => setStep("complete")}
            />
          )}
          {step === "complete" && (
            <CompleteStep
              key="complete"
              slug={slug}
              servicesCount={services.length}
              staffCount={staff.length}
            />
          )}
        </AnimatePresence>
      </main>

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
          animate={{ x: [0, -80, -40, 0], y: [0, 60, -20, 0] }}
          transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
        />
      </div>
    </div>
  );
}
