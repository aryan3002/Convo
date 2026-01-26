/**
 * Hook for managing schedule/calendar data
 * Extracted from legacy /owner/page.tsx
 */

import { useState, useCallback, useMemo } from "react";
import type { OwnerSchedule, OwnerStylist, ScheduleBooking } from "@/lib/owner-types";
import { SLOT_MINUTES } from "@/lib/owner-types";
import { getApiBase, getTimezoneOffset, parseTimeToMinutes, minutesToTimeValue } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();
const TZ_OFFSET = getTimezoneOffset();

export function useOwnerSchedule(shopSlug?: string) {
  const [schedule, setSchedule] = useState<OwnerSchedule | null>(null);
  const [date, setDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Selection state
  const [selectedBooking, setSelectedBooking] = useState<ScheduleBooking | null>(null);
  const [styleFilter, setStyleFilter] = useState("");

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchSchedule = useCallback(async (targetDate = date) => {
    if (!shopSlug) return;
    
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }
      const res = await fetch(
        getEndpoint(`/owner/schedule?date=${targetDate}&tz_offset_minutes=${TZ_OFFSET}`),
        {
          headers: {
            "X-User-Id": userId,
          },
        }
      );
      if (res.ok) {
        const data: OwnerSchedule = await res.json();
        setSchedule(data);
      } else {
        setError("Failed to fetch schedule");
        console.error("Schedule fetch failed:", res.status, res.statusText);
      }
    } catch (err) {
      console.error("Failed to fetch schedule:", err);
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, [date, getEndpoint, shopSlug]);

  const changeDate = useCallback((newDate: string) => {
    setDate(newDate);
  }, []);

  const goToPrevDay = useCallback(() => {
    const d = new Date(date);
    d.setDate(d.getDate() - 1);
    const newDate = d.toISOString().split("T")[0];
    setDate(newDate);
    return newDate;
  }, [date]);

  const goToNextDay = useCallback(() => {
    const d = new Date(date);
    d.setDate(d.getDate() + 1);
    const newDate = d.toISOString().split("T")[0];
    setDate(newDate);
    return newDate;
  }, [date]);

  const rescheduleBooking = useCallback(async (
    bookingId: string,
    stylistId: number,
    startMinutes: number
  ) => {
    try {
      const userId = getStoredUserId();
      if (!userId) throw new Error("Not authenticated");
      const res = await fetch(getEndpoint("/owner/bookings/reschedule"), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          booking_id: bookingId,
          stylist_id: stylistId,
          date: date,
          start_time: minutesToTimeValue(startMinutes),
          tz_offset_minutes: TZ_OFFSET,
        }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to reschedule");
      }
      await fetchSchedule(date);
    } catch (err) {
      console.error("Failed to reschedule booking:", err);
      throw err;
    }
  }, [date, getEndpoint, fetchSchedule]);

  const cancelBooking = useCallback(async (bookingId: string) => {
    try {
      const userId = getStoredUserId();
      if (!userId) throw new Error("Not authenticated");
      await fetch(getEndpoint("/owner/bookings/cancel"), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ booking_id: bookingId }),
      });
      await fetchSchedule(date);
    } catch (err) {
      console.error("Failed to cancel booking:", err);
      throw err;
    }
  }, [date, getEndpoint, fetchSchedule]);

  // Derived state
  const stylists = useMemo(
    () => (schedule?.stylists ?? []).sort((a, b) => a.id - b.id),
    [schedule?.stylists]
  );

  const bookings = schedule?.bookings ?? [];
  const timeOff = schedule?.time_off ?? [];

  const minWidth = useMemo(
    () => 140 + (stylists.length || 1) * 180,
    [stylists]
  );

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

  return {
    // State
    schedule,
    date,
    loading,
    error,
    selectedBooking,
    styleFilter,
    
    // Derived
    stylists,
    bookings,
    timeOff,
    minWidth,
    timeRange,
    slots,
    
    // Actions
    fetchSchedule,
    changeDate,
    goToPrevDay,
    goToNextDay,
    rescheduleBooking,
    cancelBooking,
    setSelectedBooking,
    setStyleFilter,
    setSchedule,
  };
}
