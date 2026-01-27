"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import { useAuth, useUser } from "@clerk/nextjs";
import {
  Car,
  ArrowLeft,
  Building2,
  Mail,
  Phone,
  MessageCircle,
  Check,
  AlertCircle,
  DollarSign,
  RefreshCw,
  LogIn,
} from "lucide-react";
import {
  getShopBySlug,
  getStoredUserId,
  setStoredUserId,
  apiFetch,
  isApiError,
  type Shop,
} from "@/lib/api";
import { useApiClient, useClearLegacyAuth } from "@/lib/api.client";

// Auth status from debug endpoint
interface AuthStatus {
  user_id_from_header: string | null;
  is_authenticated: boolean;
  has_shop_access: boolean;
  user_role: string | null;
  shop_owner_ids: string[];
  error_hint: string | null;
}

export default function CabOwnerSetupPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;

  // Automatically clear old localStorage auth when Clerk is available
  useClearLegacyAuth();

  // Clerk Auth
  const { isLoaded: authLoaded, isSignedIn, userId: clerkUserId } = useAuth();
  const { user: clerkUser } = useUser();
  const apiClient = useApiClient();

  // Auth & shop state
  const [userId, setUserId] = useState<string | null>(null);
  const [shop, setShop] = useState<Shop | null>(null);
  const [shopLoading, setShopLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [showAuthDebug, setShowAuthDebug] = useState(false);

  // Form state
  const [businessName, setBusinessName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [whatsappPhone, setWhatsappPhone] = useState("");

  // Pricing state (optional initial setup)
  const [perMileRate, setPerMileRate] = useState("2.50");
  const [minimumFare, setMinimumFare] = useState("15.00");

  // UI state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Initialize Auth - Use Clerk if signed in, fallback to localStorage
  useEffect(() => {
    if (!authLoaded) return;
    
    if (isSignedIn && clerkUserId) {
      setUserId(clerkUserId);
      // Pre-fill email from Clerk user
      if (clerkUser?.primaryEmailAddress?.emailAddress && !contactEmail) {
        setContactEmail(clerkUser.primaryEmailAddress.emailAddress);
      }
      return;
    }
    
    // Not signed in via Clerk - check localStorage for dev mode
    const storedId = getStoredUserId();
    if (storedId) {
      setUserId(storedId);
    } else {
      // No auth at all - redirect to sign-up
      setAuthError("Please sign up to set up your cab service.");
    }
  }, [authLoaded, isSignedIn, clerkUserId, clerkUser, contactEmail]);

  // Load shop
  useEffect(() => {
    async function loadShop() {
      setShopLoading(true);
      try {
        const shopData = await getShopBySlug(slug);
        setShop(shopData);
      } catch (err) {
        console.error("Failed to load shop:", err);
        setAuthError("Shop not found");
      } finally {
        setShopLoading(false);
      }
    }

    if (slug) {
      loadShop();
    }
  }, [slug]);

  // Check if cab owner already exists
  useEffect(() => {
    async function checkExisting() {
      if (!userId || !shop) return;

      console.log('[Cab Setup] Checking existing cab owner:', { userId, shopId: shop.id, slug });

      try {
        const data = await apiFetch<{
          business_name: string;
          contact_email: string | null;
          contact_phone: string | null;
          whatsapp_phone: string | null;
        }>(`/s/${slug}/owner/cab/owner`);
        
        console.log('[Cab Setup] Found existing cab owner data:', data);
        
        // Pre-fill form with existing data
        setBusinessName(data.business_name || "");
        setContactEmail(data.contact_email || "");
        setContactPhone(data.contact_phone || "");
        setWhatsappPhone(data.whatsapp_phone || "");
      } catch (err) {
        console.log('[Cab Setup] Error checking existing config:', err);
        
        // Not configured yet or not authorized - that's fine for setup page
        // We don't block the UI for these errors since this is the setup page
        if (isApiError(err)) {
          if (err.status === 404) {
            console.log('[Cab Setup] No existing cab owner config (404) - this is expected for new setup');
          } else if (err.status === 403) {
            console.warn('[Cab Setup] Permission denied (403) when checking existing config. This may indicate:', {
              userId,
              shopId: shop.id,
              slug,
              error: err.detail,
              note: 'This is OK for new setup - we will create the cab owner on submit'
            });
            // Show auth debug when we get a 403
            setShowAuthDebug(true);
            // Fetch auth status for debugging
            fetchAuthStatus();
          } else {
            console.log('[Cab Setup] Could not fetch existing config:', err);
          }
        }
      }
    }

    if (userId && shop) {
      checkExisting();
    }
  }, [slug, userId, shop]);

  // Fetch auth status for debugging
  const fetchAuthStatus = async () => {
    try {
      const status = await apiFetch<AuthStatus>(`/s/${slug}/owner/auth-status`);
      setAuthStatus(status);
    } catch (err) {
      console.error('[Cab Setup] Could not fetch auth status:', err);
    }
  };

  // Fix auth by copying correct owner ID
  const fixAuth = (ownerId: string) => {
    setStoredUserId(ownerId);
    setUserId(ownerId);
    setShowAuthDebug(false);
    setAuthStatus(null);
    // Reload the page to apply the fix
    window.location.reload();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userId || !businessName.trim()) return;

    console.log('[Cab Setup] Submitting setup:', {
      userId,
      shopId: shop?.id,
      slug,
      businessName: businessName.trim()
    });

    setSubmitting(true);
    setError(null);

    try {
      // Set up cab owner
      await apiFetch(`/s/${slug}/owner/cab/setup`, {
        method: "POST",
        body: {
          business_name: businessName.trim(),
          contact_email: contactEmail.trim() || null,
          contact_phone: contactPhone.trim() || null,
          whatsapp_phone: whatsappPhone.trim() || null,
        },
      });

      console.log('[Cab Setup] Setup successful!');
      setSuccess(true);
      
      // Redirect to cab dashboard after short delay
      setTimeout(() => {
        router.push(`/s/${slug}/owner/cab`);
      }, 1500);
    } catch (err) {
      console.error("Setup error:", err);
      if (isApiError(err)) {
        if (err.status === 403) {
          setError("Access denied: Your user ID doesn't match the shop owner. Make sure you're logged in with the correct account.");
          // Show auth debug and fetch status
          setShowAuthDebug(true);
          fetchAuthStatus();
        } else if (err.status === 404) {
          setError("Shop not found. Please check the URL.");
        } else {
          setError(err.detail || "Failed to complete setup");
        }
      } else {
        setError("Failed to complete setup. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (shopLoading) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center">
          <div className="spinner mb-4" />
          <p className="text-gray-400">Loading...</p>
        </div>
        <style jsx>{`
          .spinner {
            width: 24px;
            height: 24px;
            border: 2px solid rgba(0, 212, 255, 0.2);
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-400">{authError}</p>
          <button
            onClick={() => router.push("/owner-landing")}
            className="mt-4 px-4 py-2 rounded-lg btn-neon text-sm"
          >
            Back to Shops
          </button>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <div className="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
            <Check className="w-10 h-10 text-green-400" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Setup Complete!</h2>
          <p className="text-gray-400">Redirecting to your cab dashboard...</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white">
      {/* Background effects */}
      <div
        className="fixed inset-0 pointer-events-none -z-20 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Header */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0a0e1a]/80 border-b border-white/5">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => router.push(`/s/${slug}/owner`)}
            className="w-10 h-10 rounded-xl glass border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <Car className="w-5 h-5 text-[#00d4ff]" />
              Set Up Cab Services
            </h1>
            <p className="text-xs text-gray-500">{shop?.name}</p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass rounded-2xl border border-white/5 p-6"
        >
          <h2 className="text-xl font-bold mb-2">Business Information</h2>
          <p className="text-sm text-gray-400 mb-6">
            Configure your cab service for customers to book rides.
          </p>

          {error && (
            <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Auth Debug Panel - shows when there's a 403 error */}
          {showAuthDebug && authStatus && (
            <div className="mb-6 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30">
              <h3 className="font-semibold text-yellow-400 mb-2 flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                Authorization Issue Detected
              </h3>
              <div className="text-sm space-y-2 text-gray-300">
                <p><strong>Your ID:</strong> <code className="text-[#00d4ff]">{authStatus.user_id_from_header || 'Not set'}</code></p>
                <p><strong>Has Access:</strong> {authStatus.has_shop_access ? '✅ Yes' : '❌ No'}</p>
                {authStatus.user_role && <p><strong>Role:</strong> {authStatus.user_role}</p>}
                {authStatus.error_hint && (
                  <p className="text-yellow-400 mt-2">{authStatus.error_hint}</p>
                )}
                {authStatus.shop_owner_ids.length > 0 && !authStatus.has_shop_access && (
                  <div className="mt-3 pt-3 border-t border-yellow-500/20">
                    <p className="font-medium mb-2">Quick Fix - Click to use correct owner ID:</p>
                    <div className="space-y-2">
                      {authStatus.shop_owner_ids.map((ownerId) => (
                        <button
                          key={ownerId}
                          onClick={() => fixAuth(ownerId)}
                          className="w-full text-left px-3 py-2 rounded-lg bg-[#00d4ff]/10 hover:bg-[#00d4ff]/20 border border-[#00d4ff]/30 text-[#00d4ff] transition-colors text-sm"
                        >
                          Use ID: <code>{ownerId}</code>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <button
                onClick={() => setShowAuthDebug(false)}
                className="mt-3 text-xs text-gray-400 hover:text-white"
              >
                Hide debug info
              </button>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Business Name */}
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-[#00d4ff]" />
                Business Name *
              </label>
              <input
                type="text"
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="e.g., Bishop's Airport Transfers"
                required
                className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
              />
            </div>

            {/* Contact Email */}
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                <Mail className="w-4 h-4 text-[#00d4ff]" />
                Contact Email
              </label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder="bookings@yourbusiness.com"
                className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Booking notifications will be sent here
              </p>
            </div>

            {/* Contact Phone */}
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                <Phone className="w-4 h-4 text-[#00d4ff]" />
                Contact Phone
              </label>
              <input
                type="tel"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
                placeholder="+1 555-123-4567"
                className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
              />
            </div>

            {/* WhatsApp Phone */}
            <div>
              <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                <MessageCircle className="w-4 h-4 text-green-400" />
                WhatsApp Number
              </label>
              <input
                type="tel"
                value={whatsappPhone}
                onChange={(e) => setWhatsappPhone(e.target.value)}
                placeholder="+1 555-123-4567"
                className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Optional: For WhatsApp booking notifications
              </p>
            </div>

            <hr className="border-white/10" />

            {/* Pricing Section */}
            <div>
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-[#00d4ff]" />
                Pricing (Optional)
              </h3>
              <p className="text-sm text-gray-400 mb-4">
                You can configure detailed pricing later in the pricing settings.
              </p>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Per Mile Rate ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={perMileRate}
                    onChange={(e) => setPerMileRate(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl input-glass text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Minimum Fare ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={minimumFare}
                    onChange={(e) => setMinimumFare(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl input-glass text-white"
                  />
                </div>
              </div>
            </div>

            {/* Submit Button */}
            <div className="pt-4">
              <button
                type="submit"
                disabled={submitting || !businessName.trim()}
                className="w-full px-6 py-3 rounded-xl btn-neon font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                    Setting up...
                  </>
                ) : (
                  <>
                    <Check className="w-5 h-5" />
                    Complete Setup
                  </>
                )}
              </button>
            </div>
          </form>
        </motion.div>

        {/* Info Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mt-6 glass rounded-2xl border border-white/5 p-6"
        >
          <h3 className="font-semibold mb-3">What happens next?</h3>
          <ul className="space-y-2 text-sm text-gray-400">
            <li className="flex items-start gap-2">
              <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
              <span>Your cab booking page will be available at <code className="text-[#00d4ff]">/s/{slug}/cab/book</code></span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
              <span>You can add drivers and manage bookings from the dashboard</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
              <span>Customers will receive email confirmations for their bookings</span>
            </li>
          </ul>
        </motion.div>
      </main>

      {/* Styles */}
      <style jsx>{`
        .spinner {
          width: 24px;
          height: 24px;
          border: 2px solid rgba(0, 212, 255, 0.2);
          border-top-color: #00d4ff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
          margin: 0 auto;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
