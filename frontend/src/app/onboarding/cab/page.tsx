"use client";

import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import {
  Car,
  User,
  Phone,
  Mail,
  Clock,
  ArrowRight,
  Sparkles,
  AlertCircle,
  CheckCircle,
  Loader2,
  ArrowLeft,
} from "lucide-react";
import {
  createShop,
  setStoredUserId,
  getErrorMessage,
  isApiError,
} from "@/lib/api";
import { useApiClient } from "@/lib/clerk-api";

// ──────────────────────────────────────────────────────────
// Cab Onboarding - Creates shop with category="cab"
// ──────────────────────────────────────────────────────────

interface FormData {
  ownerUserId: string;
  businessName: string;
  email: string;
  phone: string;
  timezone: string;
}

const initialFormData: FormData = {
  ownerUserId: "",
  businessName: "",
  email: "",
  phone: "",
  timezone: "America/Phoenix",
};

const TIMEZONES = [
  { value: "America/New_York", label: "Eastern (New York)" },
  { value: "America/Chicago", label: "Central (Chicago)" },
  { value: "America/Denver", label: "Mountain (Denver)" },
  { value: "America/Los_Angeles", label: "Pacific (Los Angeles)" },
  { value: "America/Phoenix", label: "Arizona (No DST)" },
  { value: "Pacific/Honolulu", label: "Hawaii" },
  { value: "America/Anchorage", label: "Alaska" },
];

export default function CabOnboardingPage() {
  const router = useRouter();
  const { user, isLoaded } = useUser();
  const apiClient = useApiClient();
  const [formData, setFormData] = useState<FormData>(initialFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Initialize form with Clerk user ID
  useEffect(() => {
    if (isLoaded && user) {
      setFormData(prev => ({
        ...prev,
        ownerUserId: user.id, // Clerk user ID
        email: user.primaryEmailAddress?.emailAddress || "",
      }));
    } else if (isLoaded && !user) {
      // Redirect to sign-up if not logged in
      router.push('/sign-up?redirect_url=' + encodeURIComponent('/onboarding/cab'));
    }
  }, [isLoaded, user, router]);

  const updateField = useCallback(
    <K extends keyof FormData>(field: K, value: FormData[K]) => {
      setFormData((prev) => ({ ...prev, [field]: value }));
      setError(null);
    },
    []
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate required fields
    if (!formData.ownerUserId.trim()) {
      setError("Owner ID is required (e.g., your email or unique identifier).");
      return;
    }
    if (!formData.businessName.trim()) {
      setError("Business name is required.");
      return;
    }

    // Normalize phone number: if 10 digits, add +1 prefix
    let normalizedPhone: string | undefined = undefined;
    const rawPhone = formData.phone.trim().replace(/\D/g, ""); // Remove non-digits
    if (rawPhone.length === 10) {
      normalizedPhone = `+1${rawPhone}`;
    } else if (rawPhone.length === 11 && rawPhone.startsWith("1")) {
      normalizedPhone = `+${rawPhone}`;
    } else if (rawPhone.length > 0) {
      // If phone provided but doesn't match expected format, include + if missing
      normalizedPhone = rawPhone.startsWith("+") ? rawPhone : `+${rawPhone}`;
    }
    // If empty, leave as undefined (phone is optional)

    setIsSubmitting(true);

    try {
      const shop = await apiClient.fetch('/shops', {
        method: 'POST',
        body: JSON.stringify({
          owner_user_id: formData.ownerUserId.trim(),
          name: formData.businessName.trim(),
          phone_number: normalizedPhone,
          timezone: formData.timezone || "America/Phoenix",
          category: "cab", // Key: this creates a cab service shop
        }),
      });

      setSuccess(`Cab service "${shop.name}" created! Redirecting to setup...`);

      // Redirect to the CAB-specific setup wizard
      setTimeout(() => {
        router.push(`/s/${shop.slug}/owner/cab/setup`);
      }, 1500);
    } catch (err) {
      console.error("Failed to create cab service:", err);

      if (isApiError(err)) {
        if (err.status === 409) {
          setError(
            "A business with this name already exists. Please choose a different name."
          );
        } else if (err.status === 422) {
          // Backend validation error - show detail from error response
          const errorDetail = typeof err.detail === 'string' 
            ? err.detail 
            : JSON.stringify(err.detail);
          console.error("[422] Backend validation error:", errorDetail);
          setError(errorDetail || "Invalid input. Please check your form data.");
        } else {
          const errorMsg = getErrorMessage(err);
          console.error(`[${err.status}] API Error:`, errorMsg);
          setError(errorMsg);
        }
      } else {
        const errorMsg = err instanceof Error ? err.message : "Failed to create cab service. Please try again.";
        console.error("Non-API error:", errorMsg, err);
        setError(errorMsg);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0a0e1a]/80 border-b border-white/5">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/owner-landing")}
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#10b981] via-[#06b6d4] to-[#0ea5e9] flex items-center justify-center shadow-neon hover:scale-105 transition-transform"
              title="Back to Home"
            >
              <Car className="w-5 h-5 text-white" />
            </button>
            <div>
              <h1 className="text-lg font-bold text-white">Convo</h1>
              <p className="text-xs text-gray-500">Cab Service Onboarding</p>
            </div>
          </div>
          <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-[#10b981]" />
            New cab service
          </span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="w-full max-w-lg"
        >
          {/* Back Link */}
          <motion.button
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            onClick={() => router.push("/owner-landing")}
            className="flex items-center gap-2 text-gray-400 hover:text-white mb-6 text-sm transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to options
          </motion.button>

          {/* Card */}
          <div className="glass-card rounded-2xl p-8 border border-white/5">
            <div className="text-center mb-8">
              <motion.div
                initial={{ scale: 0.8 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring" }}
                className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-[#10b981]/20 via-[#06b6d4]/20 to-[#0ea5e9]/20 flex items-center justify-center border border-white/10 mb-4"
              >
                <Car className="w-8 h-8 text-[#10b981]" />
              </motion.div>
              <h2 className="text-2xl font-bold text-white mb-2">
                Start Your Cab Service
              </h2>
              <p className="text-gray-400 text-sm">
                Set up your taxi/cab business with driver management and ride booking.
              </p>
            </div>

            {/* Status Messages */}
            <AnimatePresence mode="wait">
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3"
                >
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-400">{error}</p>
                </motion.div>
              )}
              {success && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="mb-6 p-4 rounded-xl bg-green-500/10 border border-green-500/20 flex items-start gap-3"
                >
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-green-400">{success}</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Owner ID */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <User className="w-4 h-4 inline mr-2 text-[#10b981]" />
                  Your ID *
                </label>
                <input
                  type="text"
                  value={formData.ownerUserId}
                  onChange={(e) => updateField("ownerUserId", e.target.value)}
                  placeholder="e.g., your email or unique identifier"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                  required
                />
                <p className="text-xs text-gray-500 mt-1">
                  This identifies you as the owner. Use your email for easy recall.
                </p>
              </div>

              {/* Business Name */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <Car className="w-4 h-4 inline mr-2 text-[#06b6d4]" />
                  Business Name *
                </label>
                <input
                  type="text"
                  value={formData.businessName}
                  onChange={(e) => updateField("businessName", e.target.value)}
                  placeholder="e.g., City Express Cabs"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                  required
                />
              </div>

              {/* Phone */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <Phone className="w-4 h-4 inline mr-2 text-[#0ea5e9]" />
                  Phone (optional)
                </label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => updateField("phone", e.target.value)}
                  placeholder="e.g., +1 555-123-4567"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                />
              </div>

              {/* Timezone */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <Clock className="w-4 h-4 inline mr-2 text-[#8b5cf6]" />
                  Timezone
                </label>
                <select
                  value={formData.timezone}
                  onChange={(e) => updateField("timezone", e.target.value)}
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm appearance-none cursor-pointer"
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value}>
                      {tz.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Submit Button */}
              <motion.button
                type="submit"
                disabled={isSubmitting}
                whileHover={{ scale: isSubmitting ? 1 : 1.02 }}
                whileTap={{ scale: isSubmitting ? 1 : 0.98 }}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-[#10b981] via-[#06b6d4] to-[#0ea5e9] text-white font-semibold shadow-lg hover:shadow-[0_0_30px_rgba(16,185,129,0.4)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Creating Cab Service...
                  </>
                ) : (
                  <>
                    Create Cab Service
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </motion.button>
            </form>

            {/* Info */}
            <p className="text-xs text-gray-500 text-center mt-6">
              After creating your cab service, you&apos;ll be able to add drivers and
              configure ride booking.
            </p>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
