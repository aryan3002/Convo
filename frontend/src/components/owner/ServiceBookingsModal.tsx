"use client";

import React from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import type { ServiceBooking } from "@/hooks/useOwnerServiceBookings";

interface ServiceBookingsModalProps {
  open: boolean;
  serviceName: string;
  bookings: ServiceBooking[];
  loading: boolean;
  onClose: () => void;
}

export function ServiceBookingsModal({
  open,
  serviceName,
  bookings,
  loading,
  onClose,
}: ServiceBookingsModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 overlay">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="glass-strong rounded-2xl shadow-neon p-6 max-w-2xl w-full relative max-h-[80vh] flex flex-col border border-white/10"
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-white">{serviceName}</h3>
          <p className="text-xs text-gray-400">Upcoming bookings (next 7 days)</p>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 scrollbar-hide">
          {loading ? (
            <div className="text-sm text-gray-500 text-center py-8">
              <div className="spinner mx-auto mb-2" />
              Loading...
            </div>
          ) : bookings.length === 0 ? (
            <div className="text-sm text-gray-500 text-center py-8">No bookings found</div>
          ) : (
            bookings.map((booking) => {
              const startDate = new Date(booking.start_time);
              const endDate = new Date(booking.end_time);
              const dateStr = startDate.toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
              });
              const timeStr = `${startDate.toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })} - ${endDate.toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })}`;

              return (
                <div
                  key={booking.id}
                  className="glass rounded-xl p-3 hover:bg-white/5 transition-colors border border-white/5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-sm font-medium text-white">
                          {booking.customer_name || "Guest"}
                        </p>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full ${
                            booking.status === "CONFIRMED"
                              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                              : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                          }`}
                        >
                          {booking.status}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mb-1">
                        {dateStr} · {timeStr}
                      </p>
                      <p className="text-xs text-gray-500">Stylist: {booking.stylist_name}</p>
                      {booking.customer_email && (
                        <p className="text-xs text-gray-600 mt-1">{booking.customer_email}</p>
                      )}
                      {booking.customer_phone && (
                        <p className="text-xs text-gray-600">{booking.customer_phone}</p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </motion.div>
    </div>
  );
}

// Badge button for service cards
interface ServiceBookingBadgeProps {
  count: number;
  onClick: () => void;
}

export function ServiceBookingBadge({ count, onClick }: ServiceBookingBadgeProps) {
  return (
    <button
      type="button"
      onClick={() => count > 0 && onClick()}
      disabled={count === 0}
      className={`text-[11px] px-2 py-1 rounded-full transition-all ${
        count > 0
          ? "bg-[#00d4ff]/10 text-[#00d4ff] hover:bg-[#00d4ff]/20 cursor-pointer border border-[#00d4ff]/30"
          : "glass border border-white/10 text-gray-600 cursor-default"
      }`}
    >
      {count > 0 ? `${count} booking${count === 1 ? "" : "s"}` : "none"}
    </button>
  );
}
