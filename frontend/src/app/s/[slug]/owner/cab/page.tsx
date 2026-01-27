"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import { useAuth, useUser } from "@clerk/nextjs";
import {
  Car,
  MapPin,
  Clock,
  DollarSign,
  Check,
  X,
  ArrowLeft,
  RefreshCw,
  ChevronRight,
  Plane,
  Users,
  Briefcase,
  Calendar,
  AlertCircle,
  Edit2,
  User,
  Plus,
  Phone,
  WifiOff,
  ShieldOff,
  ServerOff,
  CheckCircle2,
} from "lucide-react";
import {
  getShopBySlug,
  getStoredUserId,
  apiFetch,
  isApiError,
  type Shop,
} from "@/lib/api";
import { useApiClient, useClearLegacyAuth } from "@/lib/api.client";
import { CabSummaryBar } from "@/components/owner/CabSummaryBar";

// Check if we're in development mode
const isDev = process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_CAB_DEV_TOOLS === "true";

// Error types for structured error handling
type ErrorType = "auth" | "permission" | "not_found" | "network" | "server" | "validation" | null;

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

interface CabOwner {
  id: string;
  shop_id: number;
  business_name: string;
  contact_email?: string;
  contact_phone?: string;
  whatsapp_phone?: string;
  is_active: boolean;
}

interface CabDriver {
  id: string;
  cab_owner_id: string;
  name: string;
  phone: string;
  whatsapp_phone?: string;
  status: "ACTIVE" | "INACTIVE";
}

interface CabBooking {
  id: string;
  pickup_text: string;
  drop_text: string;
  pickup_time: string;
  vehicle_type: string;
  flight_number?: string;
  passengers?: number;
  luggage?: number;
  customer_name?: string;
  customer_email?: string;
  customer_phone?: string;
  distance_miles?: number;
  duration_minutes?: number;
  raw_price?: number;
  final_price?: number;
  original_price?: number;
  price_override?: number;
  status: "PENDING" | "CONFIRMED" | "COMPLETED" | "REJECTED" | "CANCELLED";
  created_at: string;
  confirmed_at?: string;
  rejected_at?: string;
  rejection_reason?: string;
  assigned_driver_id?: number;
  assigned_driver?: CabDriver;
  assigned_at?: string;
}

interface CabBookingListResponse {
  items: CabBooking[];
  total: number;
  page: number;
  page_size: number;
}

type TabType = "requests" | "rides" | "drivers";

// ──────────────────────────────────────────────────────────
// Helper Functions
// ──────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatVehicleType(type: string): string {
  switch (type) {
    case "SEDAN_4":
      return "Sedan (4 pax)";
    case "SUV":
      return "SUV (6 pax)";
    case "VAN":
      return "Van (8+ pax)";
    default:
      return type;
  }
}

// ──────────────────────────────────────────────────────────
// Error Classification Helper
// ──────────────────────────────────────────────────────────

function getErrorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail === null || detail === undefined) return 'An error occurred';
  if (Array.isArray(detail)) {
    // Pydantic validation errors come as array
    return detail.map(e => typeof e === 'object' ? ((e as Record<string, unknown>).msg as string) || JSON.stringify(e) : String(e)).join(', ');
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    return (obj.message as string) || (obj.msg as string) || (obj.error as string) || JSON.stringify(detail);
  }
  return String(detail);
}

function classifyError(err: unknown): { type: ErrorType; message: string } {
  if (isApiError(err)) {
    const message = getErrorMessage(err.detail);
    switch (err.status) {
      case 401:
        return { type: "auth", message: "Please log in to access this page." };
      case 403:
        return { type: "permission", message: message || "You don't have permission to access this shop." };
      case 404:
        return { type: "not_found", message: message || "Resource not found." };
      case 422:
        return { type: "server", message: `Validation error: ${message}` };
      case 503:
        return { type: "network", message: "Backend server is unavailable." };
      default:
        if (err.status >= 500) {
          return { type: "server", message: message || "Server error occurred." };
        }
        return { type: "server", message: message || "Request failed." };
    }
  }
  if (err instanceof Error) {
    return { type: "network", message: err.message };
  }
  return { type: "network", message: "Network error. Please check your connection." };
}

// ──────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────

export default function CabManagementPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  // Automatically clear old localStorage auth when Clerk is available
  useClearLegacyAuth();

  // Clerk Auth
  const { isLoaded: authLoaded, isSignedIn, userId: clerkUserId } = useAuth();
  const { user: clerkUser } = useUser();
  const apiClient = useApiClient();

  // Auth & Shop State - use Clerk user ID or fall back to localStorage in dev
  const [userId, setUserId] = useState<string | null>(null);
  const [shop, setShop] = useState<Shop | null>(null);
  const [shopLoading, setShopLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authErrorType, setAuthErrorType] = useState<ErrorType>(null);
  
  // Cab Owner State
  const [cabOwner, setCabOwner] = useState<CabOwner | null>(null);
  const [cabOwnerLoading, setCabOwnerLoading] = useState(true);

  // Tab & Data State
  const [activeTab, setActiveTab] = useState<TabType>("requests");
  const [requests, setRequests] = useState<CabBooking[]>([]);
  const [rides, setRides] = useState<CabBooking[]>([]);
  const [drivers, setDrivers] = useState<CabDriver[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorType, setErrorType] = useState<ErrorType>(null);
  
  // Dev Tools State
  const [creatingTestBooking, setCreatingTestBooking] = useState(false);

  // Modal State
  const [selectedBooking, setSelectedBooking] = useState<CabBooking | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [priceOverrideValue, setPriceOverrideValue] = useState("");
  const [showPriceOverride, setShowPriceOverride] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);
  
  // Driver Modal State
  const [showAddDriverModal, setShowAddDriverModal] = useState(false);
  const [newDriverName, setNewDriverName] = useState("");
  const [newDriverPhone, setNewDriverPhone] = useState("");
  const [newDriverWhatsapp, setNewDriverWhatsapp] = useState("");
  const [driverLoading, setDriverLoading] = useState(false);
  
  // Driver Assignment State
  const [selectedDriverId, setSelectedDriverId] = useState<string>("");

  // ──────────────────────────────────────────────────────────
  // Initialize Auth - Use Clerk if signed in, fallback to localStorage
  // ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (authLoaded && isSignedIn && clerkUserId) {
      setUserId(clerkUserId);
      return;
    }
    
    // Fallback to localStorage for dev mode
    if (authLoaded && !isSignedIn) {
      const storedId = getStoredUserId();
      if (storedId) {
        setUserId(storedId);
      }
    }
  }, [authLoaded, isSignedIn, clerkUserId]);

  useEffect(() => {
    async function loadShop() {
      setShopLoading(true);
      setAuthError(null);

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

  // Check if cab owner exists for this shop
  useEffect(() => {
    async function checkCabOwner() {
      if (!userId || !shop) return;
      setCabOwnerLoading(true);
      
      try {
        const data = await apiFetch<CabOwner>(`/s/${slug}/owner/cab/owner`);
        setCabOwner(data);
      } catch (err) {
        if (isApiError(err) && err.status === 404) {
          // No cab owner - this is expected for shops without cab services
          // Don't log error as it's not actually an error condition
          router.push(`/s/${slug}/owner/cab/setup`);
          return;
        }
        // Only log unexpected errors
        console.error("Error checking cab owner:", err);
      } finally {
        setCabOwnerLoading(false);
      }
    }
    
    if (userId && shop) {
      checkCabOwner();
    }
  }, [slug, userId, shop, router]);

  // ──────────────────────────────────────────────────────────
  // Data Fetching
  // ──────────────────────────────────────────────────────────

  const fetchRequests = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    setErrorType(null);

    try {
      const data: CabBookingListResponse = await apiFetch(`/s/${slug}/owner/cab/requests`);
      // Map booking_id to id for compatibility with the UI
      const mappedItems: CabBooking[] = data.items.map((item: any) => ({
        id: item.booking_id || item.id,  // Use booking_id from API, fallback to id
        pickup_text: item.pickup_text,
        drop_text: item.drop_text,
        pickup_time: item.pickup_time,
        vehicle_type: item.vehicle_type,
        flight_number: item.flight_number,
        passengers: item.passengers,
        luggage: item.luggage,
        customer_name: item.customer_name,
        customer_email: item.customer_email,
        customer_phone: item.customer_phone,
        distance_miles: item.distance_miles,
        duration_minutes: item.duration_minutes,
        raw_price: item.raw_price,
        final_price: item.final_price,
        original_price: item.original_price,
        price_override: item.price_override,
        status: item.status,
        created_at: item.created_at,
        confirmed_at: item.confirmed_at,
        rejected_at: item.rejected_at,
        rejection_reason: item.rejection_reason,
        assigned_driver_id: item.assigned_driver_id,
        assigned_driver: item.assigned_driver,
        assigned_at: item.assigned_at,
      }));
      setRequests(mappedItems);
    } catch (err) {
      console.error("Error fetching requests:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
      setRequests([]);
    } finally {
      setLoading(false);
    }
  }, [slug, userId]);

  const fetchRides = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    setErrorType(null);

    try {
      const data: CabBookingListResponse = await apiFetch(
        `/s/${slug}/owner/cab/rides?upcoming_only=true`
      );
      // Map booking_id to id for compatibility with the UI
      const mappedItems: CabBooking[] = data.items.map((item: any) => ({
        id: item.booking_id || item.id,  // Use booking_id from API, fallback to id
        pickup_text: item.pickup_text,
        drop_text: item.drop_text,
        pickup_time: item.pickup_time,
        vehicle_type: item.vehicle_type,
        flight_number: item.flight_number,
        passengers: item.passengers,
        luggage: item.luggage,
        customer_name: item.customer_name,
        customer_email: item.customer_email,
        customer_phone: item.customer_phone,
        distance_miles: item.distance_miles,
        duration_minutes: item.duration_minutes,
        raw_price: item.raw_price,
        final_price: item.final_price,
        original_price: item.original_price,
        price_override: item.price_override,
        status: item.status,
        created_at: item.created_at,
        confirmed_at: item.confirmed_at,
        rejected_at: item.rejected_at,
        rejection_reason: item.rejection_reason,
        assigned_driver_id: item.assigned_driver_id,
        assigned_driver: item.assigned_driver,
        assigned_at: item.assigned_at,
      }));
      setRides(mappedItems);
    } catch (err) {
      console.error("Error fetching rides:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
      setRides([]);
    } finally {
      setLoading(false);
    }
  }, [slug, userId]);

  const fetchDrivers = useCallback(async () => {
    if (!userId) return;
    setDriverLoading(true);

    try {
      const data = await apiFetch<{ items: CabDriver[] }>(`/s/${slug}/owner/cab/drivers`);
      setDrivers(data.items || []);
    } catch (err) {
      console.error("Error fetching drivers:", err);
      // Don't block UI for driver fetch errors
    } finally {
      setDriverLoading(false);
    }
  }, [slug, userId]);

  // Fetch all data on initial load
  useEffect(() => {
    if (userId) {
      // Always fetch drivers on initial load (needed for driver assignment dropdown)
      fetchDrivers();
    }
  }, [userId, fetchDrivers]);

  // Fetch tab-specific data when tab changes
  useEffect(() => {
    if (userId && activeTab === "requests") {
      fetchRequests();
    } else if (userId && activeTab === "rides") {
      fetchRides();
    } else if (userId && activeTab === "drivers") {
      // Drivers already loaded on initial mount, but refresh when viewing the tab
      fetchDrivers();
    }
  }, [userId, activeTab, fetchRequests, fetchRides, fetchDrivers]);

  // ──────────────────────────────────────────────────────────
  // DEV Test Tools
  // ──────────────────────────────────────────────────────────

  const createTestBooking = async () => {
    if (!isDev || !userId) return;
    setCreatingTestBooking(true);

    try {
      // Create pickup time as ISO datetime (tomorrow at 10:00 AM)
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(10, 0, 0, 0);

      const testBooking = {
        // Required fields matching CabBookingCreateRequest
        pickup_text: "123 Main St, Phoenix, AZ 85001",
        drop_text: "Phoenix Sky Harbor Airport, PHX, Phoenix, AZ",
        pickup_time: tomorrow.toISOString(),
        vehicle_type: "SEDAN_4",
        
        // Optional customer info
        customer_name: "Test Passenger",
        customer_email: "test@example.com",
        customer_phone: "+16025551234",
        passengers: 2,
        luggage: 1,
        notes: "[DEV TEST] Auto-generated test booking",
      };

      console.log('[Test Booking] Submitting:', testBooking);

      await apiFetch(`/s/${slug}/cab/book`, {
        method: "POST",
        body: testBooking,
        userId: false, // Public booking endpoint doesn't need auth
      });

      console.log('[Test Booking] Success!');
      // Refresh requests
      fetchRequests();
    } catch (err) {
      console.error("Error creating test booking:", err);
      const { type, message } = classifyError(err);
      setError(typeof message === 'string' ? message : 'Failed to create test booking');
      setErrorType(type);
    } finally {
      setCreatingTestBooking(false);
    }
  };

  // ──────────────────────────────────────────────────────────
  // Actions
  // ──────────────────────────────────────────────────────────

  const handleConfirm = async (bookingId: string | undefined) => {
    if (!userId || !bookingId) {
      setError("Invalid booking ID");
      setErrorType("validation");
      return;
    }
    setActionLoading(true);

    try {
      await apiFetch(
        `/s/${slug}/owner/cab/requests/${bookingId}/confirm`,
        { method: "POST" }
      );

      setSelectedBooking(null);
      await fetchRequests();  // Refresh pending requests
      await fetchRides();      // Refresh confirmed rides
    } catch (err) {
      console.error("Error confirming booking:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (bookingId: string | undefined) => {
    if (!userId || !bookingId) {
      setError("Invalid booking ID");
      setErrorType("validation");
      return;
    }
    setActionLoading(true);

    try {
      await apiFetch(
        `/s/${slug}/owner/cab/requests/${bookingId}/reject?reason=${encodeURIComponent(rejectReason)}`,
        { method: "POST" }
      );

      setSelectedBooking(null);
      setShowRejectModal(false);
      setRejectReason("");
      await fetchRequests();
    } catch (err) {
      console.error("Error rejecting booking:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePriceOverride = async (bookingId: string) => {
    if (!userId || !priceOverrideValue) return;
    setActionLoading(true);

    try {
      const updatedBooking = await apiFetch<CabBooking>(
        `/s/${slug}/owner/cab/requests/${bookingId}/override-price`,
        {
          method: "POST",
          body: { price: parseFloat(priceOverrideValue) },
        }
      );

      setSelectedBooking(updatedBooking);
      setShowPriceOverride(false);
      setPriceOverrideValue("");
      await fetchRequests();
    } catch (err) {
      console.error("Error overriding price:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setActionLoading(false);
    }
  };

  // ──────────────────────────────────────────────────────────
  // Driver Management
  // ──────────────────────────────────────────────────────────

  const handleAddDriver = async () => {
    if (!userId || !newDriverName || !newDriverPhone) return;
    setDriverLoading(true);

    try {
      await apiFetch(`/s/${slug}/owner/cab/drivers`, {
        method: "POST",
        body: {
          name: newDriverName,
          phone: newDriverPhone,
          whatsapp_phone: newDriverWhatsapp || undefined,
        },
      });

      setShowAddDriverModal(false);
      setNewDriverName("");
      setNewDriverPhone("");
      setNewDriverWhatsapp("");
      await fetchDrivers();
    } catch (err) {
      console.error("Error adding driver:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setDriverLoading(false);
    }
  };

  const handleToggleDriverStatus = async (driverId: string, currentStatus: string) => {
    if (!userId) return;
    setDriverLoading(true);

    const newStatus = currentStatus === "ACTIVE" ? "INACTIVE" : "ACTIVE";

    try {
      await apiFetch(`/s/${slug}/owner/cab/drivers/${driverId}`, {
        method: "PATCH",
        body: { status: newStatus },
      });

      await fetchDrivers();
    } catch (err) {
      console.error("Error updating driver status:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setDriverLoading(false);
    }
  };

  const handleAssignDriver = async (bookingId: string, driverId: string) => {
    console.log("Assigning driver:", { bookingId, driverId, selectedBooking });
    
    if (!userId || !bookingId || !driverId) {
      console.error("Validation failed:", { userId, bookingId, driverId });
      setError("Invalid booking or driver ID");
      setErrorType("validation");
      return;
    }
    setActionLoading(true);

    try {
      const response: any = await apiFetch(
        `/s/${slug}/owner/cab/requests/${bookingId}/assign-driver`,
        {
          method: "POST",
          body: { driver_id: driverId },
        }
      );

      // Map the response to match CabBooking interface
      const updatedBooking: CabBooking = {
        id: response.booking_id || bookingId,
        pickup_text: response.pickup_text || selectedBooking?.pickup_text || "",
        drop_text: response.drop_text || selectedBooking?.drop_text || "",
        pickup_time: response.pickup_time || selectedBooking?.pickup_time || "",
        vehicle_type: response.vehicle_type || selectedBooking?.vehicle_type || "SEDAN_4",
        status: response.status || "CONFIRMED",
        created_at: response.created_at || selectedBooking?.created_at || new Date().toISOString(),
        assigned_driver_id: response.assigned_driver_id,
        assigned_driver: response.assigned_driver,
        assigned_at: response.assigned_at,
        distance_miles: selectedBooking?.distance_miles,
        duration_minutes: selectedBooking?.duration_minutes,
        final_price: selectedBooking?.final_price,
        customer_name: selectedBooking?.customer_name,
        customer_phone: selectedBooking?.customer_phone,
        customer_email: selectedBooking?.customer_email,
      };

      setSelectedBooking(updatedBooking);
      setSelectedDriverId("");
      await fetchRides();
    } catch (err) {
      console.error("Error assigning driver:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCompleteRide = async (bookingId: string) => {
    if (!userId || !bookingId) {
      setError("Invalid booking ID");
      setErrorType("validation");
      return;
    }
    setActionLoading(true);

    try {
      const response: any = await apiFetch(
        `/s/${slug}/owner/cab/rides/${bookingId}/complete`,
        {
          method: "POST",
        }
      );

      // Update the selected booking with the new status
      if (selectedBooking) {
        setSelectedBooking({
          ...selectedBooking,
          status: "COMPLETED",
        });
      }

      // Refresh the rides list
      await fetchRides();
      
      // Close the modal after a short delay to show the success state
      setTimeout(() => {
        setSelectedBooking(null);
      }, 500);
    } catch (err) {
      console.error("Error completing ride:", err);
      const { type, message } = classifyError(err);
      setError(message);
      setErrorType(type);
    } finally {
      setActionLoading(false);
    }
  };

  // ──────────────────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────────────────

  if (shopLoading) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center">
          <div className="spinner mb-4" />
          <p className="text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (authError) {
    const AuthIcon = authErrorType === "permission" ? ShieldOff 
      : authErrorType === "network" ? WifiOff 
      : authErrorType === "server" ? ServerOff 
      : AlertCircle;
    const errorColor = authErrorType === "permission" || authErrorType === "auth" 
      ? "text-yellow-400" 
      : authErrorType === "network" 
      ? "text-orange-400" 
      : "text-red-400";
    
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
        <div className="text-center">
          <AuthIcon className={`w-12 h-12 ${errorColor} mx-auto mb-4`} />
          <p className={errorColor}>{authError}</p>
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

  const currentList = activeTab === "requests" ? requests : rides;

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
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push(`/s/${slug}/owner`)}
              className="w-10 h-10 rounded-xl glass border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-lg font-bold flex items-center gap-2">
                <Car className="w-5 h-5 text-[#00d4ff]" />
                Cab Services
              </h1>
              <p className="text-xs text-gray-500">{shop?.name} · Manage bookings</p>
            </div>
          </div>
          <button
            onClick={() => (activeTab === "requests" ? fetchRequests() : fetchRides())}
            disabled={loading}
            className="p-2 rounded-lg glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
        {/* Summary Bar - Business Metrics */}
        <CabSummaryBar slug={slug} />

        {/* DEV Test Tools */}
        {isDev && (
          <div className="mb-6 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-yellow-400">
                <AlertCircle className="w-4 h-4" />
                <span className="text-sm font-medium">DEV MODE</span>
              </div>
              <button
                onClick={createTestBooking}
                disabled={creatingTestBooking}
                className="px-3 py-1.5 rounded-lg bg-yellow-500/20 text-yellow-400 text-sm font-medium hover:bg-yellow-500/30 transition-colors disabled:opacity-50"
              >
                {creatingTestBooking ? "Creating..." : "➕ Create Test Booking"}
              </button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 mb-6 p-1 glass rounded-2xl w-fit">
          <button
            onClick={() => setActiveTab("requests")}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "requests"
                ? "btn-neon"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Clock className="w-4 h-4" />
            Pending Requests
            {requests.length > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-[#00d4ff]/20 text-[#00d4ff] text-xs">
                {requests.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("rides")}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "rides"
                ? "btn-neon"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Calendar className="w-4 h-4" />
            Confirmed Rides
            {rides.length > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-xs">
                {rides.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("drivers")}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "drivers"
                ? "btn-neon"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <User className="w-4 h-4" />
            Drivers
            {drivers.length > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400 text-xs">
                {drivers.length}
              </span>
            )}
          </button>
        </div>

        {/* Error */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`mb-6 p-4 rounded-xl flex items-center gap-3 ${
              errorType === "auth" || errorType === "permission"
                ? "bg-yellow-500/10 border border-yellow-500/30 text-yellow-400"
                : errorType === "network"
                ? "bg-orange-500/10 border border-orange-500/30 text-orange-400"
                : "bg-red-500/10 border border-red-500/30 text-red-400"
            }`}
          >
            {errorType === "network" ? (
              <WifiOff className="w-5 h-5 flex-shrink-0" />
            ) : errorType === "permission" ? (
              <ShieldOff className="w-5 h-5 flex-shrink-0" />
            ) : errorType === "server" ? (
              <ServerOff className="w-5 h-5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
            )}
            <span>{error}</span>
            <button
              onClick={() => {
                setError(null);
                setErrorType(null);
              }}
              className="ml-auto p-1 hover:bg-white/10 rounded transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-12">
            <div className="spinner mb-4" />
            <p className="text-gray-400">Loading...</p>
          </div>
        )}

        {/* Empty State for Requests/Rides */}
        {!loading && activeTab !== "drivers" && currentList.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-12 glass rounded-2xl border border-white/5"
          >
            <Car className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-400 mb-2">
              {activeTab === "requests"
                ? "No pending requests"
                : "No upcoming rides"}
            </h3>
            <p className="text-sm text-gray-500">
              {activeTab === "requests"
                ? "New booking requests will appear here"
                : "Confirmed rides will appear here"}
            </p>
          </motion.div>
        )}

        {/* Drivers Tab Content */}
        {activeTab === "drivers" && (
          <div className="space-y-4">
            {/* Add Driver Button */}
            <div className="flex justify-end">
              <button
                onClick={() => setShowAddDriverModal(true)}
                className="px-4 py-2 rounded-xl btn-neon text-sm font-medium flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Add Driver
              </button>
            </div>

            {/* Drivers List */}
            {driverLoading ? (
              <div className="text-center py-12">
                <div className="spinner mb-4" />
                <p className="text-gray-400">Loading drivers...</p>
              </div>
            ) : drivers.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-center py-12 glass rounded-2xl border border-white/5"
              >
                <User className="w-12 h-12 text-gray-600 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-400 mb-2">
                  No drivers yet
                </h3>
                <p className="text-sm text-gray-500 mb-4">
                  Add drivers to assign them to cab bookings
                </p>
                <button
                  onClick={() => setShowAddDriverModal(true)}
                  className="px-4 py-2 rounded-xl btn-neon text-sm font-medium"
                >
                  Add Your First Driver
                </button>
              </motion.div>
            ) : (
              <AnimatePresence mode="popLayout">
                {drivers.map((driver) => (
                  <motion.div
                    key={driver.id}
                    layout
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="glass-card rounded-2xl p-5 border border-white/5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-full bg-purple-500/20 flex items-center justify-center">
                          <User className="w-6 h-6 text-purple-400" />
                        </div>
                        <div>
                          <h3 className="font-medium">{driver.name}</h3>
                          <div className="flex items-center gap-3 text-sm text-gray-400">
                            <span className="flex items-center gap-1">
                              <Phone className="w-3 h-3" />
                              {driver.phone}
                            </span>
                            {driver.whatsapp_phone && (
                              <span className="text-green-400">📱 WhatsApp</span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span
                          className={`px-2 py-1 rounded-full text-xs ${
                            driver.status === "ACTIVE"
                              ? "bg-green-500/20 text-green-400"
                              : "bg-gray-500/20 text-gray-400"
                          }`}
                        >
                          {driver.status}
                        </span>
                        <button
                          onClick={() => handleToggleDriverStatus(driver.id, driver.status)}
                          disabled={driverLoading}
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                            driver.status === "ACTIVE"
                              ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                              : "bg-green-500/20 text-green-400 hover:bg-green-500/30"
                          }`}
                        >
                          {driver.status === "ACTIVE" ? "Deactivate" : "Activate"}
                        </button>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>
        )}

        {/* Booking List */}
        {!loading && activeTab !== "drivers" && currentList.length > 0 && (
          <div className="space-y-4">
            <AnimatePresence mode="popLayout">
              {currentList.map((booking, index) => (
                <motion.div
                  key={booking.id || `booking-${index}`}
                  layout
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  onClick={() => {
                    // Ensure the booking has an id field (map booking_id to id if needed)
                    const bookingWithId = {
                      ...booking,
                      id: booking.id || (booking as any).booking_id
                    };
                    console.log("Selected booking:", bookingWithId);
                    setSelectedBooking(bookingWithId);
                  }}
                  className="glass-card rounded-2xl p-5 border border-white/5 cursor-pointer hover:border-[#00d4ff]/30 transition-all group"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      {/* Route */}
                      <div className="flex items-center gap-2 mb-3">
                        <div className="flex items-center gap-1 text-sm">
                          <MapPin className="w-4 h-4 text-green-400 flex-shrink-0" />
                          <span className="truncate">{booking.pickup_text}</span>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
                        <div className="flex items-center gap-1 text-sm">
                          <MapPin className="w-4 h-4 text-red-400 flex-shrink-0" />
                          <span className="truncate">{booking.drop_text}</span>
                        </div>
                      </div>

                      {/* Details Row */}
                      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatDate(booking.pickup_time)}
                        </span>
                        <span className="flex items-center gap-1">
                          <Car className="w-3 h-3" />
                          {formatVehicleType(booking.vehicle_type)}
                        </span>
                        {booking.distance_miles && (
                          <span>{booking.distance_miles} mi</span>
                        )}
                        {booking.flight_number && (
                          <span className="flex items-center gap-1">
                            <Plane className="w-3 h-3" />
                            {booking.flight_number}
                          </span>
                        )}
                      </div>

                      {/* Customer */}
                      {booking.customer_name && (
                        <p className="text-xs text-gray-500 mt-2">
                          {booking.customer_name}
                          {booking.customer_phone && ` · ${booking.customer_phone}`}
                        </p>
                      )}
                    </div>

                    {/* Price & Status */}
                    <div className="text-right flex-shrink-0">
                      <p className="text-lg font-bold text-[#00d4ff]">
                        ${booking.final_price?.toFixed(2) || "—"}
                      </p>
                      {booking.price_override && (
                        <p className="text-xs text-yellow-400">Price adjusted</p>
                      )}
                      <div
                        className={`mt-1 px-2 py-0.5 rounded-full text-xs inline-block ${
                          booking.status === "PENDING"
                            ? "bg-yellow-500/20 text-yellow-400"
                            : booking.status === "CONFIRMED"
                            ? "bg-green-500/20 text-green-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {booking.status}
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </main>

      {/* Booking Detail Modal */}
      <AnimatePresence>
        {selectedBooking && (
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4"
            onClick={() => setSelectedBooking(null)}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-strong rounded-2xl shadow-neon p-6 max-w-lg w-full relative border border-white/10 max-h-[90vh] overflow-y-auto"
            >
              {/* Close Button */}
              <button
                onClick={() => setSelectedBooking(null)}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Header */}
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <Car className="w-5 h-5 text-[#00d4ff]" />
                  <h2 className="text-lg font-bold">Booking Details</h2>
                </div>
                <p className="text-xs text-gray-500">
                  ID: {selectedBooking?.id?.slice(0, 8) || 'N/A'}...
                </p>
              </div>

              {/* Route */}
              <div className="space-y-3 mb-6">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center flex-shrink-0">
                    <MapPin className="w-4 h-4 text-green-400" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Pickup</p>
                    <p className="text-sm">{selectedBooking.pickup_text}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0">
                    <MapPin className="w-4 h-4 text-red-400" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Drop-off</p>
                    <p className="text-sm">{selectedBooking.drop_text}</p>
                  </div>
                </div>
              </div>

              {/* Trip Info */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="glass rounded-xl p-3">
                  <p className="text-xs text-gray-500 mb-1">Pickup Time</p>
                  <p className="text-sm font-medium">
                    {formatDate(selectedBooking.pickup_time)}
                  </p>
                </div>
                <div className="glass rounded-xl p-3">
                  <p className="text-xs text-gray-500 mb-1">Vehicle</p>
                  <p className="text-sm font-medium">
                    {formatVehicleType(selectedBooking.vehicle_type)}
                  </p>
                </div>
                {selectedBooking.distance_miles && (
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-gray-500 mb-1">Distance</p>
                    <p className="text-sm font-medium">
                      {selectedBooking.distance_miles} miles
                    </p>
                  </div>
                )}
                {selectedBooking.duration_minutes && (
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-gray-500 mb-1">Est. Duration</p>
                    <p className="text-sm font-medium">
                      ~{selectedBooking.duration_minutes} min
                    </p>
                  </div>
                )}
                {selectedBooking.flight_number && (
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-gray-500 mb-1">Flight</p>
                    <p className="text-sm font-medium flex items-center gap-1">
                      <Plane className="w-3 h-3" />
                      {selectedBooking.flight_number}
                    </p>
                  </div>
                )}
                {selectedBooking.passengers && (
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-gray-500 mb-1">Passengers</p>
                    <p className="text-sm font-medium flex items-center gap-1">
                      <Users className="w-3 h-3" />
                      {selectedBooking.passengers}
                    </p>
                  </div>
                )}
                {selectedBooking.luggage && (
                  <div className="glass rounded-xl p-3">
                    <p className="text-xs text-gray-500 mb-1">Luggage</p>
                    <p className="text-sm font-medium flex items-center gap-1">
                      <Briefcase className="w-3 h-3" />
                      {selectedBooking.luggage} bags
                    </p>
                  </div>
                )}
              </div>

              {/* Customer Info */}
              {(selectedBooking.customer_name || selectedBooking.customer_email || selectedBooking.customer_phone) && (
                <div className="mb-6">
                  <h3 className="text-xs text-gray-500 mb-2">Customer</h3>
                  <div className="glass rounded-xl p-3 space-y-1">
                    {selectedBooking.customer_name && (
                      <p className="text-sm">{selectedBooking.customer_name}</p>
                    )}
                    {selectedBooking.customer_email && (
                      <p className="text-xs text-gray-400">{selectedBooking.customer_email}</p>
                    )}
                    {selectedBooking.customer_phone && (
                      <p className="text-xs text-gray-400">{selectedBooking.customer_phone}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Pricing */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs text-gray-500">Pricing</h3>
                  {selectedBooking.status === "PENDING" && !showPriceOverride && (
                    <button
                      onClick={() => {
                        setShowPriceOverride(true);
                        setPriceOverrideValue(selectedBooking.final_price?.toString() || "");
                      }}
                      className="text-xs text-[#00d4ff] hover:underline flex items-center gap-1"
                    >
                      <Edit2 className="w-3 h-3" />
                      Override
                    </button>
                  )}
                </div>
                
                {showPriceOverride ? (
                  <div className="glass rounded-xl p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400">$</span>
                      <input
                        type="number"
                        value={priceOverrideValue}
                        onChange={(e) => setPriceOverrideValue(e.target.value)}
                        className="flex-1 px-3 py-2 rounded-lg input-glass text-sm"
                        placeholder="Enter new price"
                        step="0.01"
                        min="0"
                      />
                      <button
                        onClick={() => handlePriceOverride(selectedBooking.id)}
                        disabled={actionLoading || !priceOverrideValue}
                        className="px-3 py-2 rounded-lg btn-neon text-sm disabled:opacity-50"
                      >
                        {actionLoading ? "..." : "Save"}
                      </button>
                      <button
                        onClick={() => {
                          setShowPriceOverride(false);
                          setPriceOverrideValue("");
                        }}
                        className="px-3 py-2 rounded-lg glass text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="glass rounded-xl p-4 flex items-center justify-between">
                    <div>
                      {selectedBooking.price_override && selectedBooking.original_price && (
                        <p className="text-xs text-gray-500 line-through mb-1">
                          ${selectedBooking.original_price.toFixed(2)}
                        </p>
                      )}
                      <p className="text-2xl font-bold text-[#00d4ff]">
                        ${selectedBooking.final_price?.toFixed(2) || "—"}
                      </p>
                    </div>
                    {selectedBooking.price_override && (
                      <span className="px-2 py-1 rounded-full bg-yellow-500/20 text-yellow-400 text-xs">
                        Adjusted
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Actions */}
              {selectedBooking.status === "PENDING" && selectedBooking.id && (
                <div className="flex gap-3">
                  <button
                    onClick={() => handleConfirm(selectedBooking.id)}
                    disabled={actionLoading}
                    className="flex-1 px-4 py-3 rounded-xl bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    <Check className="w-5 h-5" />
                    Confirm Booking
                  </button>
                  <button
                    onClick={() => setShowRejectModal(true)}
                    disabled={actionLoading}
                    className="flex-1 px-4 py-3 rounded-xl bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    <X className="w-5 h-5" />
                    Reject
                  </button>
                </div>
              )}

              {/* Status Badge for Confirmed/Rejected/Completed */}
              {selectedBooking.status !== "PENDING" && (
                <div className="space-y-3">
                  <div
                    className={`text-center py-3 rounded-xl ${
                      selectedBooking.status === "CONFIRMED"
                        ? "bg-green-500/20 text-green-400"
                        : selectedBooking.status === "COMPLETED"
                        ? "bg-[#00d4ff]/20 text-[#00d4ff]"
                        : "bg-red-500/20 text-red-400"
                    }`}
                  >
                    <p className="font-medium">{selectedBooking.status}</p>
                    {selectedBooking.confirmed_at && (
                      <p className="text-xs opacity-70 mt-1">
                        Confirmed {formatDate(selectedBooking.confirmed_at)}
                      </p>
                    )}
                    {selectedBooking.rejection_reason && (
                      <p className="text-xs opacity-70 mt-1">
                        Reason: {selectedBooking.rejection_reason}
                      </p>
                    )}
                  </div>

                  {/* Mark as Complete button for CONFIRMED rides */}
                  {selectedBooking.status === "CONFIRMED" && selectedBooking.id && (
                    <button
                      onClick={() => handleCompleteRide(selectedBooking.id)}
                      disabled={actionLoading}
                      className="w-full px-4 py-3 rounded-xl bg-[#00d4ff]/20 text-[#00d4ff] hover:bg-[#00d4ff]/30 transition-colors flex items-center justify-center gap-2 disabled:opacity-50 font-medium"
                    >
                      <CheckCircle2 className="w-5 h-5" />
                      {actionLoading ? "Marking..." : "Mark as Complete"}
                    </button>
                  )}
                </div>
              )}

              {/* Driver Assignment (for confirmed bookings) */}
              {selectedBooking.status === "CONFIRMED" && (
                <div className="glass rounded-xl p-4 mt-4">
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Assign Driver</h4>
                  {selectedBooking.assigned_driver ? (
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-green-500/20 flex items-center justify-center">
                        <User className="w-5 h-5 text-green-400" />
                      </div>
                      <div>
                        <p className="font-medium">{selectedBooking.assigned_driver.name}</p>
                        <p className="text-sm text-gray-400">{selectedBooking.assigned_driver.phone}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <select
                        value={selectedDriverId}
                        onChange={(e) => setSelectedDriverId(e.target.value)}
                        className="flex-1 px-3 py-2 rounded-lg input-glass text-sm"
                      >
                        <option value="">Select a driver...</option>
                        {drivers.filter(d => d.status === "ACTIVE").map((driver) => (
                          <option key={driver.id} value={driver.id}>
                            {driver.name} - {driver.phone}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => {
                          console.log("Assign button clicked", {
                            selectedBookingId: selectedBooking.id,
                            selectedBooking: selectedBooking,
                            selectedDriverId: selectedDriverId,
                            hasId: !!selectedBooking.id
                          });
                          if (selectedDriverId && selectedBooking.id) {
                            handleAssignDriver(selectedBooking.id, selectedDriverId);
                          } else {
                            console.error("Missing ID:", { 
                              bookingId: selectedBooking.id, 
                              driverId: selectedDriverId 
                            });
                            setError("Please select a driver and ensure booking has valid ID");
                            setErrorType("validation");
                          }
                        }}
                        disabled={!selectedDriverId || actionLoading}
                        className="px-4 py-2 rounded-lg btn-neon text-sm disabled:opacity-50"
                      >
                        Assign
                      </button>
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Add Driver Modal */}
      <AnimatePresence>
        {showAddDriverModal && (
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center p-4"
            onClick={() => setShowAddDriverModal(false)}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-strong rounded-2xl shadow-neon p-6 max-w-md w-full relative border border-white/10"
            >
              <h3 className="text-lg font-bold mb-4">Add New Driver</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Name *</label>
                  <input
                    type="text"
                    value={newDriverName}
                    onChange={(e) => setNewDriverName(e.target.value)}
                    placeholder="Driver's full name"
                    className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Phone *</label>
                  <input
                    type="tel"
                    value={newDriverPhone}
                    onChange={(e) => setNewDriverPhone(e.target.value)}
                    placeholder="+1234567890"
                    className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                  />
                </div>
                
                <div>
                  <label className="block text-sm text-gray-400 mb-1">WhatsApp (optional)</label>
                  <input
                    type="tel"
                    value={newDriverWhatsapp}
                    onChange={(e) => setNewDriverWhatsapp(e.target.value)}
                    placeholder="+1234567890"
                    className="w-full px-3 py-2 rounded-lg input-glass text-sm"
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={handleAddDriver}
                  disabled={driverLoading || !newDriverName || !newDriverPhone}
                  className="flex-1 px-4 py-2 rounded-xl btn-neon text-sm disabled:opacity-50"
                >
                  {driverLoading ? "Adding..." : "Add Driver"}
                </button>
                <button
                  onClick={() => {
                    setShowAddDriverModal(false);
                    setNewDriverName("");
                    setNewDriverPhone("");
                    setNewDriverWhatsapp("");
                  }}
                  className="flex-1 px-4 py-2 rounded-xl glass hover:bg-white/10 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Reject Modal */}
      <AnimatePresence>
        {showRejectModal && selectedBooking && (
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center p-4"
            onClick={() => setShowRejectModal(false)}
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-strong rounded-2xl shadow-neon p-6 max-w-md w-full relative border border-white/10"
            >
              <h3 className="text-lg font-bold mb-4">Reject Booking?</h3>
              <p className="text-sm text-gray-400 mb-4">
                Please provide a reason for rejecting this booking request.
              </p>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Reason for rejection (optional)"
                rows={3}
                className="w-full px-3 py-2 rounded-lg input-glass text-sm mb-4 resize-none"
              />
              <div className="flex gap-3">
                <button
                  onClick={() => handleReject(selectedBooking.id)}
                  disabled={actionLoading}
                  className="flex-1 px-4 py-2 rounded-xl bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-50"
                >
                  {actionLoading ? "Rejecting..." : "Confirm Rejection"}
                </button>
                <button
                  onClick={() => {
                    setShowRejectModal(false);
                    setRejectReason("");
                  }}
                  className="flex-1 px-4 py-2 rounded-xl glass hover:bg-white/10 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Spinner Style */}
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
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
}
