/**
 * Hook for stylist time off entries (individual stylist view)
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase, getTimezoneOffset } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();
const TZ_OFFSET = getTimezoneOffset();

export type OwnerTimeOffEntry = {
  start_time: string;
  end_time: string;
  date: string;
  reason?: string | null;
};

export function useOwnerStylistTimeOff(shopSlug?: string) {
  const [timeOffEntries, setTimeOffEntries] = useState<Record<number, OwnerTimeOffEntry[]>>({});
  const [openStylistId, setOpenStylistId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchTimeOffForStylist = useCallback(async (stylistId: number) => {
    if (!shopSlug) return [];
    
    // Skip if already loaded
    if (timeOffEntries[stylistId]) return timeOffEntries[stylistId];
    
    setLoading(true);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setLoading(false);
        return [];
      }

      const res = await fetch(
        getEndpoint(`/owner/stylists/${stylistId}/time_off?tz_offset_minutes=${TZ_OFFSET}`),
        {
          headers: { "X-User-Id": userId },
        }
      );
      if (res.ok) {
        const data: OwnerTimeOffEntry[] = await res.json();
        setTimeOffEntries((prev) => ({ ...prev, [stylistId]: data }));
        return data;
      }
    } catch (err) {
      console.error("Failed to fetch time off:", err);
    } finally {
      setLoading(false);
    }
    return [];
  }, [timeOffEntries, getEndpoint, shopSlug]);

  const toggleStylistTimeOff = useCallback((stylistId: number) => {
    const next = openStylistId === stylistId ? null : stylistId;
    setOpenStylistId(next);
    if (next) {
      fetchTimeOffForStylist(stylistId);
    }
  }, [openStylistId, fetchTimeOffForStylist]);

  const refreshStylistTimeOff = useCallback(async (stylistId: number) => {
    // Force refresh by clearing cache first
    setTimeOffEntries((prev) => {
      const { [stylistId]: _, ...rest } = prev;
      return rest;
    });
    return fetchTimeOffForStylist(stylistId);
  }, [fetchTimeOffForStylist]);

  return {
    // State
    timeOffEntries,
    openStylistId,
    loading,

    // Actions
    fetchTimeOffForStylist,
    toggleStylistTimeOff,
    refreshStylistTimeOff,
    setOpenStylistId,
  };
}
