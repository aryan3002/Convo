"use client";

/**
 * ScheduleGrid - Full calendar/schedule view with drag-drop
 * Extracted from legacy /owner/page.tsx
 */

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import {
  Calendar,
  Clock,
  User,
  ArrowLeft,
  ArrowRight,
  X,
} from "lucide-react";
import type { OwnerStylist, ScheduleBooking, ScheduleTimeOff } from "@/lib/owner-types";
import { SLOT_MINUTES, ROW_HEIGHT } from "@/lib/owner-types";
import { parseTimeToMinutes, minutesToTimeLabel, minutesToTimeValue } from "@/lib/owner-utils";

interface ScheduleGridProps {
  date: string;
  stylists: OwnerStylist[];
  bookings: ScheduleBooking[];
  timeOff: ScheduleTimeOff[];
  loading: boolean;
  styleFilter: string;
  selectedBooking: ScheduleBooking | null;
  onDateChange: (date: string) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  onStyleFilterChange: (filter: string) => void;
  onSelectBooking: (booking: ScheduleBooking | null) => void;
  onReschedule: (bookingId: string, stylistId: number, startMinutes: number) => void;
  onCancel: (bookingId: string) => void;
}

export function ScheduleGrid({
  date,
  stylists,
  bookings,
  timeOff,
  loading,
  styleFilter,
  selectedBooking,
  onDateChange,
  onPrevDay,
  onNextDay,
  onStyleFilterChange,
  onSelectBooking,
  onReschedule,
  onCancel,
}: ScheduleGridProps) {
  const minWidth = useMemo(() => 140 + (stylists.length || 1) * 180, [stylists]);

  const timeRange = useMemo(() => {
    if (stylists.length === 0) {
      return { start: 9 * 60, end: 19 * 60 + SLOT_MINUTES };
    }
    const start = Math.min(
      ...stylists.map((stylist) => parseTimeToMinutes(stylist.work_start))
    );
    const end = Math.max(
      ...stylists.map((stylist) => parseTimeToMinutes(stylist.work_end))
    );
    return { start, end: end + SLOT_MINUTES };
  }, [stylists]);

  const slots = useMemo(() => {
    const items: number[] = [];
    for (let m = timeRange.start; m < timeRange.end; m += SLOT_MINUTES) {
      items.push(m);
    }
    return items;
  }, [timeRange]);

  return (
    <>
      {/* Booking Detail Modal */}
      {selectedBooking && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 overlay">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong rounded-2xl shadow-neon p-6 max-w-md w-full relative border border-white/10"
          >
            <button
              onClick={() => onSelectBooking(null)}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">Booking details</h3>
              <p className="text-xs text-gray-400">
                {selectedBooking.secondary_service_name
                  ? `${selectedBooking.service_name} + ${selectedBooking.secondary_service_name}`
                  : selectedBooking.service_name}{" "}
                · {selectedBooking.customer_name || "Guest"}
              </p>
            </div>
            {selectedBooking.preferred_style_text && (
              <p className="text-sm text-gray-300 whitespace-pre-wrap mb-4">
                {selectedBooking.preferred_style_text}
              </p>
            )}
            {selectedBooking.preferred_style_image_url && (
              <div className="rounded-xl overflow-hidden border border-white/10 bg-black/30">
                <img
                  src={selectedBooking.preferred_style_image_url}
                  alt="Preferred style"
                  className="w-full max-h-64 object-cover"
                />
              </div>
            )}
            {!selectedBooking.preferred_style_text &&
              !selectedBooking.preferred_style_image_url && (
                <p className="text-sm text-gray-500">
                  No preferred style saved for this booking.
                </p>
              )}
          </motion.div>
        </div>
      )}

      {/* Schedule Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card rounded-2xl p-6 border border-white/5"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#00d4ff]" />
              Schedule
            </h2>
            <p className="text-xs text-gray-500">
              Drag a booking to reschedule or move across stylists. Time off shows in
              soft red, confirmed appointments in neon blue.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={styleFilter}
              onChange={(e) => onStyleFilterChange(e.target.value)}
              placeholder="Filter by style"
              className="px-3 py-2 rounded-full input-glass text-xs"
            />
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onPrevDay}
              className="px-3 py-2 rounded-full glass border border-white/10 text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-all flex items-center"
            >
              <ArrowLeft className="w-4 h-4" />
            </motion.button>
            <input
              type="date"
              value={date}
              onChange={(e) => onDateChange(e.target.value)}
              className="px-3 py-2 rounded-full input-glass text-xs"
            />
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onNextDay}
              className="px-3 py-2 rounded-full glass border border-white/10 text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-all flex items-center"
            >
              <ArrowRight className="w-4 h-4" />
            </motion.button>
          </div>
        </div>

        <div className="mt-6 overflow-auto scrollbar-hide">
          {loading && (
            <div className="text-xs text-gray-500 mb-4 flex items-center gap-2">
              <div className="spinner w-4 h-4" />
              Loading schedule...
            </div>
          )}
          <div className="flex items-center gap-3 text-[11px] text-gray-500 mb-2">
            <span className="inline-flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-red-500/20 border border-red-500/30" />
              Out of office
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-gradient-to-r from-[#00d4ff] to-[#a855f7]" />
              Appointment
            </span>
          </div>

          <div
            className="grid border border-white/5 rounded-2xl overflow-hidden bg-[#0a0e1a]"
            style={{
              minWidth,
              gridTemplateColumns: `140px repeat(${stylists.length || 1}, minmax(180px, 1fr))`,
              gridTemplateRows: `48px repeat(${slots.length}, ${ROW_HEIGHT}px)`,
            }}
          >
            {/* Header row */}
            <div
              className="glass border-b border-white/5 sticky left-0 z-30 text-xs font-medium text-gray-400 flex items-center justify-center"
              style={{ gridColumn: 1 }}
            >
              <Clock className="w-3 h-3 mr-1" />
              Time
            </div>
            {stylists.length === 0 && (
              <div className="col-span-1 glass border-b border-white/5 text-xs text-gray-500 flex items-center justify-center">
                No stylists
              </div>
            )}
            {stylists.map((stylist, index) => (
              <div
                key={stylist.id}
                className="glass border-b border-white/5 text-xs font-medium text-white flex items-center justify-center"
                style={{ gridColumn: index + 2 }}
              >
                <User className="w-3 h-3 mr-1 text-[#a855f7]" />
                {stylist.name}
              </div>
            ))}

            {/* Time slots */}
            {slots.map((slot) => (
              <React.Fragment key={slot}>
                <div
                  className="border-t border-white/5 text-[11px] text-gray-500 pr-2 flex items-start justify-end pt-2 bg-[#0a0e1a] font-semibold sticky left-0 z-20"
                  style={{ gridColumn: 1 }}
                >
                  {minutesToTimeLabel(slot)}
                </div>
                {stylists.map((stylist, index) => {
                  const timeOffBlock = timeOff.find(
                    (block) =>
                      block.stylist_id === stylist.id &&
                      parseTimeToMinutes(block.start_time) <= slot &&
                      parseTimeToMinutes(block.end_time) > slot
                  );
                  const bookingAtSlot = bookings.some((booking) => {
                    if (booking.stylist_id !== stylist.id) return false;
                    const start = parseTimeToMinutes(booking.start_time);
                    const end = parseTimeToMinutes(booking.end_time);
                    return start <= slot && end > slot;
                  });
                  const stylistStart = parseTimeToMinutes(stylist.work_start);
                  const stylistEnd = parseTimeToMinutes(stylist.work_end);
                  const isWithinHours = slot >= stylistStart && slot < stylistEnd;

                  if (timeOffBlock) {
                    return (
                      <div
                        key={`${stylist.id}-${slot}-timeoff`}
                        className="border-t border-white/5 bg-red-500/10 text-red-400 text-[11px] flex items-center justify-center border-l border-red-500/20"
                        style={{ gridColumn: index + 2 }}
                      >
                        Time off
                      </div>
                    );
                  }
                  if (bookingAtSlot) {
                    return null;
                  }
                  return (
                    <div
                      key={`${stylist.id}-${slot}`}
                      className={`border-t border-white/5 ${
                        isWithinHours
                          ? "bg-[#0a0e1a] hover:bg-[#00d4ff]/5 transition-colors"
                          : "bg-white/[0.02]"
                      }`}
                      style={{ gridColumn: index + 2 }}
                      onDragOver={
                        isWithinHours ? (e) => e.preventDefault() : undefined
                      }
                      onDragEnter={
                        isWithinHours
                          ? (e) => {
                              e.currentTarget.style.backgroundColor =
                                "rgba(0, 212, 255, 0.2)";
                            }
                          : undefined
                      }
                      onDragLeave={
                        isWithinHours
                          ? (e) => {
                              e.currentTarget.style.backgroundColor = "";
                            }
                          : undefined
                      }
                      onDrop={
                        isWithinHours
                          ? (e) => {
                              e.preventDefault();
                              e.currentTarget.style.backgroundColor = "";
                              const bookingId = e.dataTransfer.getData("text/plain");
                              if (bookingId) {
                                const booking = bookings.find(
                                  (b) => b.id === bookingId
                                );
                                if (!booking) return;
                                const duration =
                                  parseTimeToMinutes(booking.end_time) -
                                  parseTimeToMinutes(booking.start_time);
                                if (
                                  slot < stylistStart ||
                                  slot + duration > stylistEnd
                                ) {
                                  alert(
                                    "Cannot drop: the booking would extend outside the stylist's working hours."
                                  );
                                  return;
                                }
                                onReschedule(bookingId, stylist.id, slot);
                              }
                            }
                          : undefined
                      }
                    />
                  );
                })}
              </React.Fragment>
            ))}

            {/* Booking blocks */}
            {bookings.map((booking) => {
              const startMinutes = parseTimeToMinutes(booking.start_time);
              const endMinutes = parseTimeToMinutes(booking.end_time);
              const rowStart =
                Math.floor((startMinutes - timeRange.start) / SLOT_MINUTES) + 2;
              const rowSpan = Math.max(
                1,
                Math.ceil((endMinutes - startMinutes) / SLOT_MINUTES)
              );
              const stylistIndex = stylists.findIndex(
                (s) => s.id === booking.stylist_id
              );
              if (stylistIndex === -1) return null;
              const stylist = stylists[stylistIndex];
              const normalizedFilter = styleFilter.trim().toLowerCase();
              const matchesStyle =
                !normalizedFilter ||
                (booking.preferred_style_text || "")
                  .toLowerCase()
                  .includes(normalizedFilter);

              return (
                <div
                  key={booking.id}
                  draggable={stylist.active}
                  onDragStart={(e: React.DragEvent<HTMLDivElement>) => {
                    const dragImage = document.createElement("div");
                    dragImage.style.width = "20px";
                    dragImage.style.height = "20px";
                    dragImage.style.background =
                      "linear-gradient(135deg, #00d4ff, #a855f7)";
                    dragImage.style.borderRadius = "4px";
                    document.body.appendChild(dragImage);
                    e.dataTransfer.setDragImage(dragImage, 10, 10);
                    e.dataTransfer.setData("text/plain", booking.id);
                    setTimeout(() => document.body.removeChild(dragImage), 0);
                  }}
                  onClick={() => onSelectBooking(booking)}
                  className={`bg-gradient-to-r from-[#00d4ff]/20 to-[#a855f7]/20 backdrop-blur-sm text-white text-xs rounded-2xl px-3 py-2 shadow-lg shadow-[#00d4ff]/10 border border-[#00d4ff]/30 z-20 cursor-pointer active:cursor-grabbing hover:border-[#00d4ff]/50 hover:scale-[1.02] transition-all ${
                    normalizedFilter && !matchesStyle ? "opacity-30" : ""
                  }`}
                  style={{
                    gridColumn: stylistIndex + 2,
                    gridRow: `${rowStart} / span ${rowSpan}`,
                    minWidth: 0,
                  }}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-semibold text-xs text-white">
                        {booking.secondary_service_name
                          ? `${booking.service_name} + ${booking.secondary_service_name}`
                          : booking.service_name}
                      </div>
                      <div className="text-[10px] text-gray-300">
                        {booking.start_time}–{booking.end_time}
                      </div>
                      <div className="text-[10px] text-gray-300">
                        {booking.customer_name || "Guest"}
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onCancel(booking.id);
                      }}
                      className="px-2 py-1 text-[9px] bg-red-500/20 border border-red-500/30 text-red-400 rounded hover:bg-red-500/30 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>
    </>
  );
}
