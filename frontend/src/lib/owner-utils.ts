/**
 * Shared utility functions for Owner Dashboard
 * Extracted from legacy /owner/page.tsx for reuse
 */

import type { OwnerTimeOffEntry, OwnerPromo } from "./owner-types";
import { PROMO_TYPES, PROMO_TRIGGERS } from "./owner-types";

/**
 * Generate a unique ID with optional prefix
 */
export function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

/**
 * Format cents to USD currency string
 */
export function formatMoney(priceCents: number) {
  return (priceCents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

/**
 * Parse time string (HH:MM or HH:MM AM/PM) to minutes since midnight
 */
export function parseTimeToMinutes(value: string) {
  if (!value) return 0;
  const raw = value.trim().toLowerCase();
  const match = raw.match(/^(\d{1,2}):(\d{2})(?:\s*(am|pm))?$/);
  if (!match) return 0;
  let hour = Number(match[1]);
  const minute = Number(match[2]);
  const meridiem = match[3];
  if (meridiem) {
    if (hour === 12) hour = 0;
    if (meridiem === "pm") hour += 12;
  }
  return hour * 60 + minute;
}

/**
 * Format time string to 12-hour format with AM/PM
 */
export function formatTimeLabel(value: string) {
  if (!value) return "";
  const [hourStr, minuteStr] = value.split(":");
  const hour = Number(hourStr);
  const minute = Number(minuteStr);
  const meridiem = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minute.toString().padStart(2, "0")} ${meridiem}`;
}

/**
 * Format date string (YYYY-MM-DD) to readable format
 */
export function formatDateLabel(value: string) {
  if (!value) return "";
  const [yyyy, mm, dd] = value.split("-").map(Number);
  const dt = new Date(yyyy, mm - 1, dd);
  return dt.toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

/**
 * Format duration in minutes to human readable string
 */
export function formatDuration(minutes: number) {
  const hrs = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hrs && mins) return `${hrs}h ${mins}m`;
  if (hrs) return `${hrs}h`;
  return `${mins}m`;
}

/**
 * Convert minutes to HH:MM time string
 */
export function minutesToTimeValue(minutes: number) {
  const hour = Math.floor(minutes / 60) % 24;
  const min = minutes % 60;
  return `${hour.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`;
}

/**
 * Convert minutes to 12-hour time label
 */
export function minutesToTimeLabel(minutes: number) {
  const hour = Math.floor(minutes / 60);
  const min = minutes % 60;
  const suffix = hour >= 12 ? "PM" : "AM";
  const displayHour = ((hour + 11) % 12) + 1;
  return `${displayHour}:${min.toString().padStart(2, "0")} ${suffix}`;
}

/**
 * Summarize time off entries by date with merged blocks
 */
export function summarizeTimeOff(entries: OwnerTimeOffEntry[]) {
  const byDate: Record<string, { start: number; end: number }[]> = {};
  
  const addBlock = (date: string, start: number, end: number) => {
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push({ start, end });
  };

  const addDays = (dateStr: string, days: number) => {
    const [yyyy, mm, dd] = dateStr.split("-").map(Number);
    const dt = new Date(yyyy, mm - 1, dd);
    dt.setDate(dt.getDate() + days);
    return dt.toISOString().split("T")[0];
  };

  entries.forEach((entry) => {
    const start = parseTimeToMinutes(entry.start_time);
    const end = parseTimeToMinutes(entry.end_time);
    if (end <= start) {
      addBlock(entry.date, start, 24 * 60);
      addBlock(addDays(entry.date, 1), 0, end);
    } else {
      addBlock(entry.date, start, end);
    }
  });

  return Object.entries(byDate).map(([date, blocks]) => {
    blocks.sort((a, b) => a.start - b.start);
    const merged: { start: number; end: number }[] = [];
    for (const block of blocks) {
      const last = merged[merged.length - 1];
      if (last && block.start <= last.end) {
        last.end = Math.max(last.end, block.end);
      } else {
        merged.push({ ...block });
      }
    }
    const totalMinutes = merged.reduce((sum, block) => sum + (block.end - block.start), 0);
    return {
      date,
      blocks: merged,
      totalMinutes,
    };
  });
}

/**
 * Format promo trigger point to human readable label
 */
export function formatPromoTrigger(trigger: string) {
  return PROMO_TRIGGERS.find((item) => item.value === trigger)?.label || trigger;
}

/**
 * Format promo type to human readable label
 */
export function formatPromoType(type: string) {
  return PROMO_TYPES.find((item) => item.value === type)?.label || type;
}

/**
 * Format promo discount to human readable string
 */
export function formatPromoDiscount(promo: OwnerPromo) {
  if (promo.discount_type === "PERCENT") {
    return `${promo.discount_value ?? 0}% off`;
  }
  if (promo.discount_type === "FIXED") {
    const cents = promo.discount_value ?? 0;
    return `${formatMoney(cents)} off`;
  }
  if (promo.discount_type === "FREE_ADDON") {
    return "Free add-on";
  }
  if (promo.discount_type === "BUNDLE") {
    return "Bundle perk";
  }
  return promo.discount_type;
}

/**
 * Format promo validity window
 */
export function formatPromoWindow(promo: OwnerPromo) {
  if (!promo.start_at_utc || !promo.end_at_utc) return "Always on";
  const start = new Date(promo.start_at_utc);
  const end = new Date(promo.end_at_utc);
  return `${start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  })}–${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

/**
 * Get timezone offset in minutes
 */
export function getTimezoneOffset() {
  return Number(process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES) || -new Date().getTimezoneOffset();
}

/**
 * Get API base URL
 */
export function getApiBase() {
  return process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
}
