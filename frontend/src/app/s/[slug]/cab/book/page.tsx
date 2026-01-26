"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import {
  Car,
  MapPin,
  Calendar,
  Clock,
  Users,
  Briefcase,
  Plane,
  Phone,
  Mail,
  User,
  Check,
  AlertCircle,
  ChevronRight,
  ArrowLeft,
  DollarSign,
} from "lucide-react";
import { getApiBase, getShopBySlug, type Shop } from "@/lib/api";

type VehicleType = "SEDAN_4" | "SUV" | "VAN";

interface BookingResponse {
  booking_id: string;
  status: string;
  pickup_text: string;
  drop_text: string;
  pickup_time: string;
  vehicle_type: string;
  distance_miles: number;
  duration_minutes: number;
  raw_price: number;
  final_price: number;
  currency: string;
  pricing_breakdown: Record<string, number>;
  message: string;
}

const vehicleOptions: { value: VehicleType; label: string; capacity: string; icon: string }[] = [
  { value: "SEDAN_4", label: "Sedan", capacity: "Up to 4 passengers", icon: "🚗" },
  { value: "SUV", label: "SUV", capacity: "Up to 6 passengers", icon: "🚙" },
  { value: "VAN", label: "Van", capacity: "Up to 10 passengers", icon: "🚐" },
];

export default function CabBookPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params?.slug as string;
  const API_BASE = getApiBase();

  // Shop state
  const [shop, setShop] = useState<Shop | null>(null);
  const [shopLoading, setShopLoading] = useState(true);
  const [shopError, setShopError] = useState<string | null>(null);

  // Form state
  const [pickupLocation, setPickupLocation] = useState("");
  const [dropoffLocation, setDropoffLocation] = useState("");
  const [pickupDate, setPickupDate] = useState("");
  const [pickupTime, setPickupTime] = useState("");
  const [vehicleType, setVehicleType] = useState<VehicleType>("SEDAN_4");
  const [passengers, setPassengers] = useState(1);
  const [luggage, setLuggage] = useState(0);
  const [flightNumber, setFlightNumber] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [notes, setNotes] = useState("");

  // UI state
  const [step, setStep] = useState<"form" | "confirm" | "success">("form");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bookingResult, setBookingResult] = useState<BookingResponse | null>(null);

  // Set default date to tomorrow
  useEffect(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    setPickupDate(tomorrow.toISOString().split("T")[0]);
    setPickupTime("10:00");
  }, []);

  // Load shop
  useEffect(() => {
    async function loadShop() {
      setShopLoading(true);
      try {
        const shopData = await getShopBySlug(slug);
        setShop(shopData);
      } catch (err) {
        console.error("Failed to load shop:", err);
        setShopError("Shop not found");
      } finally {
        setShopLoading(false);
      }
    }

    if (slug) {
      loadShop();
    }
  }, [slug]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pickupLocation || !dropoffLocation || !pickupDate || !pickupTime) {
      setError("Please fill in all required fields");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const pickupDateTime = new Date(`${pickupDate}T${pickupTime}`);

      const res = await fetch(`${API_BASE}/s/${slug}/cab/book`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          pickup_text: pickupLocation,
          drop_text: dropoffLocation,
          pickup_time: pickupDateTime.toISOString(),
          vehicle_type: vehicleType,
          passengers: passengers,
          luggage: luggage,
          flight_number: flightNumber || undefined,
          customer_name: customerName || undefined,
          customer_email: customerEmail || undefined,
          customer_phone: customerPhone || undefined,
          notes: notes || undefined,
          channel: "WEB",
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to create booking");
      }

      const data: BookingResponse = await res.json();
      setBookingResult(data);
      setStep("success");
    } catch (err) {
      console.error("Booking error:", err);
      setError(err instanceof Error ? err.message : "Failed to create booking");
    } finally {
      setSubmitting(false);
    }
  };

  const formatDuration = (minutes: number) => {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    }
    return `${mins} min`;
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
            width: 32px;
            height: 32px;
            border: 3px solid rgba(0, 212, 255, 0.2);
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

  if (shopError) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center p-4">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-400 mb-4">{shopError}</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 rounded-lg btn-neon text-sm"
          >
            Go Home
          </button>
        </div>
      </div>
    );
  }

  // Success State
  if (step === "success" && bookingResult) {
    return (
      <div className="min-h-screen bg-[#0a0e1a] text-white">
        <div
          className="fixed inset-0 pointer-events-none -z-20 opacity-30"
          style={{
            backgroundImage:
              "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        <div className="max-w-lg mx-auto px-4 py-12">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center mb-8"
          >
            <div className="w-20 h-20 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
              <Check className="w-10 h-10 text-green-400" />
            </div>
            <h1 className="text-2xl font-bold mb-2">Booking Confirmed!</h1>
            <p className="text-gray-400">
              Your ride request has been submitted successfully.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass rounded-2xl border border-white/5 p-6 space-y-4"
          >
            {/* Route */}
            <div className="flex items-start gap-3">
              <div className="flex flex-col items-center gap-1">
                <div className="w-3 h-3 rounded-full bg-green-400" />
                <div className="w-0.5 h-8 bg-gray-600" />
                <div className="w-3 h-3 rounded-full bg-red-400" />
              </div>
              <div className="flex-1 space-y-4">
                <div>
                  <p className="text-xs text-gray-500">Pickup</p>
                  <p className="text-sm">{bookingResult.pickup_text}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Drop-off</p>
                  <p className="text-sm">{bookingResult.drop_text}</p>
                </div>
              </div>
            </div>

            <hr className="border-white/10" />

            {/* Trip Details */}
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-xs text-gray-500">Distance</p>
                <p className="font-medium">{bookingResult.distance_miles.toFixed(1)} mi</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Duration</p>
                <p className="font-medium">{formatDuration(bookingResult.duration_minutes)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Vehicle</p>
                <p className="font-medium">{bookingResult.vehicle_type}</p>
              </div>
            </div>

            <hr className="border-white/10" />

            {/* Price */}
            <div className="text-center">
              <p className="text-xs text-gray-500">Estimated Fare</p>
              <p className="text-3xl font-bold text-[#00d4ff]">
                ${bookingResult.final_price.toFixed(2)}
              </p>
              <p className="text-xs text-gray-500 mt-1">{bookingResult.message}</p>
            </div>

            {/* Booking ID */}
            <div className="text-center pt-2">
              <p className="text-xs text-gray-500">Booking Reference</p>
              <p className="font-mono text-sm text-[#00d4ff]">
                {bookingResult.booking_id.slice(0, 8).toUpperCase()}
              </p>
            </div>
          </motion.div>

          {/* What's Next */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="mt-6 glass rounded-2xl border border-white/5 p-6"
          >
            <h3 className="font-semibold mb-3">What happens next?</h3>
            <ul className="space-y-2 text-sm text-gray-400">
              <li className="flex items-start gap-2">
                <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                <span>You'll receive a confirmation email with your booking details</span>
              </li>
              <li className="flex items-start gap-2">
                <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                <span>The driver will contact you before pickup</span>
              </li>
              <li className="flex items-start gap-2">
                <Check className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                <span>Payment is collected at the end of your ride</span>
              </li>
            </ul>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mt-6 text-center"
          >
            <button
              onClick={() => {
                setStep("form");
                setBookingResult(null);
                setPickupLocation("");
                setDropoffLocation("");
              }}
              className="px-6 py-3 rounded-xl btn-neon font-medium"
            >
              Book Another Ride
            </button>
          </motion.div>
        </div>
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
            onClick={() => router.push(`/s/${slug}`)}
            className="w-10 h-10 rounded-xl glass border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <Car className="w-5 h-5 text-[#00d4ff]" />
              Book a Ride
            </h1>
            <p className="text-xs text-gray-500">{shop?.name}</p>
          </div>
        </div>
      </header>

      {/* Main Form */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 py-6">
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 flex items-center gap-3"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </motion.div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Route Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-2xl border border-white/5 p-6"
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <MapPin className="w-5 h-5 text-[#00d4ff]" />
              Route
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Pickup Location *
                </label>
                <input
                  type="text"
                  value={pickupLocation}
                  onChange={(e) => setPickupLocation(e.target.value)}
                  placeholder="Enter pickup address or airport"
                  required
                  className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
                />
              </div>

              <div className="flex justify-center">
                <ChevronRight className="w-5 h-5 text-gray-500 rotate-90" />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Drop-off Location *
                </label>
                <input
                  type="text"
                  value={dropoffLocation}
                  onChange={(e) => setDropoffLocation(e.target.value)}
                  placeholder="Enter destination address"
                  required
                  className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
                />
              </div>
            </div>
          </motion.div>

          {/* Date & Time Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="glass rounded-2xl border border-white/5 p-6"
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-[#00d4ff]" />
              When
            </h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Pickup Date *
                </label>
                <input
                  type="date"
                  value={pickupDate}
                  onChange={(e) => setPickupDate(e.target.value)}
                  min={new Date().toISOString().split("T")[0]}
                  required
                  className="w-full px-4 py-3 rounded-xl input-glass text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Pickup Time *
                </label>
                <input
                  type="time"
                  value={pickupTime}
                  onChange={(e) => setPickupTime(e.target.value)}
                  required
                  className="w-full px-4 py-3 rounded-xl input-glass text-white"
                />
              </div>
            </div>
          </motion.div>

          {/* Vehicle Selection */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass rounded-2xl border border-white/5 p-6"
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Car className="w-5 h-5 text-[#00d4ff]" />
              Vehicle Type
            </h2>

            <div className="grid grid-cols-3 gap-3">
              {vehicleOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setVehicleType(option.value)}
                  className={`p-4 rounded-xl border transition-all ${
                    vehicleType === option.value
                      ? "border-[#00d4ff] bg-[#00d4ff]/10"
                      : "border-white/10 glass hover:border-white/20"
                  }`}
                >
                  <div className="text-2xl mb-2">{option.icon}</div>
                  <div className="font-medium">{option.label}</div>
                  <div className="text-xs text-gray-400">{option.capacity}</div>
                </button>
              ))}
            </div>
          </motion.div>

          {/* Trip Details */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="glass rounded-2xl border border-white/5 p-6"
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Users className="w-5 h-5 text-[#00d4ff]" />
              Trip Details
            </h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Passengers
                </label>
                <select
                  value={passengers}
                  onChange={(e) => setPassengers(Number(e.target.value))}
                  className="w-full px-4 py-3 rounded-xl input-glass text-white"
                >
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                    <option key={n} value={n}>
                      {n} {n === 1 ? "passenger" : "passengers"}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                  <Briefcase className="w-4 h-4" />
                  Luggage
                </label>
                <select
                  value={luggage}
                  onChange={(e) => setLuggage(Number(e.target.value))}
                  className="w-full px-4 py-3 rounded-xl input-glass text-white"
                >
                  {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                    <option key={n} value={n}>
                      {n} {n === 1 ? "piece" : "pieces"}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mt-4">
              <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                <Plane className="w-4 h-4" />
                Flight Number (optional)
              </label>
              <input
                type="text"
                value={flightNumber}
                onChange={(e) => setFlightNumber(e.target.value)}
                placeholder="e.g., AA1234"
                className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                For airport pickups - we'll monitor your flight status
              </p>
            </div>
          </motion.div>

          {/* Contact Info */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-2xl border border-white/5 p-6"
          >
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <User className="w-5 h-5 text-[#00d4ff]" />
              Your Information
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Your Name
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="John Smith"
                  className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                    <Mail className="w-4 h-4" />
                    Email
                  </label>
                  <input
                    type="email"
                    value={customerEmail}
                    onChange={(e) => setCustomerEmail(e.target.value)}
                    placeholder="john@example.com"
                    className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    Phone
                  </label>
                  <input
                    type="tel"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                    placeholder="+1 555-123-4567"
                    className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Special Requests (optional)
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Child seat required, wheelchair accessible, etc."
                  rows={3}
                  className="w-full px-4 py-3 rounded-xl input-glass text-white placeholder-gray-500 resize-none"
                />
              </div>
            </div>
          </motion.div>

          {/* Submit Button */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
          >
            <button
              type="submit"
              disabled={submitting || !pickupLocation || !dropoffLocation}
              className="w-full px-6 py-4 rounded-xl btn-neon font-medium text-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  Getting your quote...
                </>
              ) : (
                <>
                  <DollarSign className="w-5 h-5" />
                  Get Quote & Book
                </>
              )}
            </button>
            <p className="text-center text-xs text-gray-500 mt-3">
              Free cancellation up to 24 hours before pickup
            </p>
          </motion.div>
        </form>
      </main>
    </div>
  );
}
