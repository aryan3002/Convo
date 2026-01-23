"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  Store,
  User,
  Phone,
  MapPin,
  Clock,
  Tag,
  ArrowRight,
  Sparkles,
  AlertCircle,
  CheckCircle,
  Loader2,
  MapPinned,
  XCircle,
} from "lucide-react";
import {
  createShop,
  setStoredUserId,
  getErrorMessage,
  isApiError,
} from "@/lib/api";
import { geocodeAddress, isValidCoordinates } from "@/lib/geocoding";

// ──────────────────────────────────────────────────────────
// Form State
// ──────────────────────────────────────────────────────────

interface FormData {
  ownerUserId: string;
  shopName: string;
  phone: string;
  timezone: string;
  address: string;
  category: string;
  // Phase 3: Location coordinates from geocoding
  latitude?: number;
  longitude?: number;
}

// Geocoding status for visual feedback
type GeocodingStatus = 'idle' | 'loading' | 'success' | 'error';

const initialFormData: FormData = {
  ownerUserId: "",
  shopName: "",
  phone: "",
  timezone: "America/Phoenix",
  address: "",
  category: "",
  latitude: undefined,
  longitude: undefined,
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

const CATEGORIES = [
  { value: "barbershop", label: "Barbershop" },
  { value: "salon", label: "Hair Salon" },
  { value: "spa", label: "Spa" },
  { value: "nails", label: "Nail Salon" },
  { value: "beauty", label: "Beauty Studio" },
  { value: "wellness", label: "Wellness Center" },
  { value: "other", label: "Other" },
];

// ──────────────────────────────────────────────────────────
// Page Component
// ──────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const [formData, setFormData] = useState<FormData>(initialFormData);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Phase 3: Geocoding state
  const [geocodingStatus, setGeocodingStatus] = useState<GeocodingStatus>('idle');
  const [geocodingError, setGeocodingError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof FormData>(field: K, value: FormData[K]) => {
      setFormData((prev) => ({ ...prev, [field]: value }));
      setError(null);
      
      // Clear geocoding status when address changes
      if (field === 'address') {
        setGeocodingStatus('idle');
        setGeocodingError(null);
        // Clear previous coordinates when address is edited
        setFormData((prev) => ({ ...prev, latitude: undefined, longitude: undefined }));
      }
    },
    []
  );

  // Phase 3: Handle address blur to trigger geocoding
  const handleAddressBlur = useCallback(async () => {
    const address = formData.address.trim();
    
    // Skip if address is too short or empty
    if (!address || address.length < 10) {
      return;
    }
    
    // Skip if we already have valid coordinates for this address
    if (formData.latitude && formData.longitude && geocodingStatus === 'success') {
      return;
    }
    
    setGeocodingStatus('loading');
    setGeocodingError(null);
    
    try {
      const result = await geocodeAddress(address);
      
      if (result && isValidCoordinates(result.lat, result.lon)) {
        setFormData((prev) => ({
          ...prev,
          latitude: result.lat,
          longitude: result.lon,
        }));
        setGeocodingStatus('success');
        console.log(`[Onboarding] Geocoded address to: ${result.lat}, ${result.lon}`);
      } else {
        setGeocodingStatus('error');
        setGeocodingError('Could not find location. You can still create your shop.');
      }
    } catch (err) {
      console.error('[Onboarding] Geocoding error:', err);
      setGeocodingStatus('error');
      setGeocodingError('Location lookup failed. You can still create your shop.');
    }
  }, [formData.address, formData.latitude, formData.longitude, geocodingStatus]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate required fields
    if (!formData.ownerUserId.trim()) {
      setError("Owner ID is required.");
      return;
    }
    if (!formData.shopName.trim()) {
      setError("Shop name is required.");
      return;
    }

    setIsSubmitting(true);

    try {
      const shop = await createShop({
        owner_user_id: formData.ownerUserId.trim(),
        name: formData.shopName.trim(),
        phone: formData.phone.trim() || undefined,
        timezone: formData.timezone || undefined,
        address: formData.address.trim() || undefined,
        category: formData.category || undefined,
        // Phase 3: Include geocoded coordinates
        latitude: formData.latitude,
        longitude: formData.longitude,
      });

      // Store the owner user ID for future API calls
      setStoredUserId(formData.ownerUserId.trim());

      setSuccess(`Shop "${shop.name}" created successfully! Redirecting to setup...`);

      // Redirect to the shop setup wizard
      setTimeout(() => {
        router.push(`/s/${shop.slug}/setup`);
      }, 1500);
    } catch (err) {
      console.error("Failed to create shop:", err);
      
      if (isApiError(err)) {
        if (err.status === 409) {
          setError("A shop with this name already exists. Please choose a different name.");
        } else if (err.status === 422) {
          setError(err.detail || "Invalid input. Please check your form data.");
        } else {
          setError(getErrorMessage(err));
        }
      } else {
        setError("Failed to create shop. Please try again.");
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
              className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] via-[#a855f7] to-[#ec4899] flex items-center justify-center shadow-neon hover:scale-105 transition-transform"
              title="Back to Home"
            >
              <Store className="w-5 h-5 text-white" />
            </button>
            <div>
              <h1 className="text-lg font-bold text-white">Convo</h1>
              <p className="text-xs text-gray-500">Shop Onboarding</p>
            </div>
          </div>
          <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-[#00d4ff]" />
            New shop setup
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
          {/* Card */}
          <div className="glass-card rounded-2xl p-8 border border-white/5">
            <div className="text-center mb-8">
              <motion.div
                initial={{ scale: 0.8 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring" }}
                className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 via-[#a855f7]/20 to-[#ec4899]/20 flex items-center justify-center border border-white/10 mb-4"
              >
                <Store className="w-8 h-8 text-[#00d4ff]" />
              </motion.div>
              <h2 className="text-2xl font-bold text-white mb-2">
                Create Your Shop
              </h2>
              <p className="text-sm text-gray-400">
                Set up your business in Convo to manage bookings, services, and
                staff.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Owner ID */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <User className="w-4 h-4 text-[#00d4ff]" />
                    Owner ID <span className="text-[#ec4899]">*</span>
                  </span>
                </label>
                <input
                  type="text"
                  value={formData.ownerUserId}
                  onChange={(e) => updateField("ownerUserId", e.target.value)}
                  placeholder="your-unique-owner-id"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                  disabled={isSubmitting}
                />
                <p className="text-xs text-gray-500 mt-1.5">
                  A unique identifier for your owner account. Keep this safe!
                </p>
              </div>

              {/* Shop Name */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <Store className="w-4 h-4 text-[#a855f7]" />
                    Shop Name <span className="text-[#ec4899]">*</span>
                  </span>
                </label>
                <input
                  type="text"
                  value={formData.shopName}
                  onChange={(e) => updateField("shopName", e.target.value)}
                  placeholder="Classic Cuts Barbershop"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                  disabled={isSubmitting}
                />
                <p className="text-xs text-gray-500 mt-1.5">
                  This will create your shop URL: /s/classic-cuts-barbershop
                </p>
              </div>

              {/* Phone */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <Phone className="w-4 h-4 text-[#34d399]" />
                    Phone Number
                  </span>
                </label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => updateField("phone", e.target.value)}
                  placeholder="+1 (555) 123-4567"
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm"
                  disabled={isSubmitting}
                />
              </div>

              {/* Timezone */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-[#00d4ff]" />
                    Timezone
                  </span>
                </label>
                <select
                  value={formData.timezone}
                  onChange={(e) => updateField("timezone", e.target.value)}
                  className="w-full px-4 py-3 rounded-xl input-glass text-sm bg-transparent appearance-none cursor-pointer"
                  disabled={isSubmitting}
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz.value} value={tz.value} className="bg-[#0f1629]">
                      {tz.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Address */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-[#ec4899]" />
                    Address
                  </span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={formData.address}
                    onChange={(e) => updateField("address", e.target.value)}
                    onBlur={handleAddressBlur}
                    placeholder="123 Main St, City, State 12345"
                    className="w-full px-4 py-3 rounded-xl input-glass text-sm pr-10"
                    disabled={isSubmitting}
                  />
                  {/* Geocoding Status Icons */}
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    {geocodingStatus === 'loading' && (
                      <Loader2 className="w-4 h-4 text-[#00d4ff] animate-spin" />
                    )}
                    {geocodingStatus === 'success' && (
                      <MapPinned className="w-4 h-4 text-emerald-400" />
                    )}
                    {geocodingStatus === 'error' && (
                      <XCircle className="w-4 h-4 text-amber-400" />
                    )}
                  </div>
                </div>
                {/* Geocoding Feedback */}
                {geocodingStatus === 'success' && formData.latitude && formData.longitude && (
                  <p className="text-xs text-emerald-400/80 mt-1.5 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" />
                    Location found ({formData.latitude.toFixed(4)}, {formData.longitude.toFixed(4)})
                  </p>
                )}
                {geocodingStatus === 'error' && geocodingError && (
                  <p className="text-xs text-amber-400/80 mt-1.5 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {geocodingError}
                  </p>
                )}
                {geocodingStatus === 'idle' && (
                  <p className="text-xs text-gray-500 mt-1.5">
                    Enter a full address to enable location-based discovery
                  </p>
                )}
              </div>

              {/* Category */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  <span className="flex items-center gap-2">
                    <Tag className="w-4 h-4 text-[#a855f7]" />
                    Business Category
                  </span>
                </label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((cat) => (
                    <button
                      key={cat.value}
                      type="button"
                      onClick={() => updateField("category", cat.value)}
                      disabled={isSubmitting}
                      className={`px-3 py-2 rounded-full text-xs transition-all ${
                        formData.category === cat.value
                          ? "btn-neon"
                          : "glass border border-white/10 text-gray-300 hover:bg-white/10 hover:text-white"
                      }`}
                    >
                      {cat.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Error Message */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30"
                  >
                    <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-red-400">
                        Error
                      </p>
                      <p className="text-xs text-red-300/80 mt-0.5">{error}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Success Message */}
              <AnimatePresence>
                {success && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex items-start gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30"
                  >
                    <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-emerald-400">
                        Success!
                      </p>
                      <p className="text-xs text-emerald-300/80 mt-0.5">
                        {success}
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Submit Button */}
              <motion.button
                type="submit"
                disabled={isSubmitting || !!success}
                whileHover={{ scale: isSubmitting ? 1 : 1.02 }}
                whileTap={{ scale: isSubmitting ? 1 : 0.98 }}
                className="w-full py-4 rounded-xl btn-neon text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating shop...
                  </>
                ) : success ? (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    Redirecting...
                  </>
                ) : (
                  <>
                    Create Shop
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </motion.button>
            </form>
          </div>

          {/* Footer Help Text */}
          <p className="text-xs text-gray-500 text-center mt-6">
            Already have a shop?{" "}
            <button
              onClick={() => router.push("/owner")}
              className="text-[#00d4ff] hover:underline"
            >
              Go to dashboard
            </button>
          </p>
        </motion.div>
      </main>
    </div>
  );
}
