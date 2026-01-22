/**
 * Hook for managing call summaries
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type CallSummary = {
  id: string;
  call_sid: string;
  customer_name: string | null;
  customer_phone: string;
  service: string | null;
  stylist: string | null;
  appointment_date: string | null;
  appointment_time: string | null;
  booking_status: "confirmed" | "not_confirmed" | "follow_up";
  key_notes: string | null;
  created_at: string;
};

export function useOwnerCallSummaries(shopSlug?: string) {
  const [summaries, setSummaries] = useState<CallSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchCallSummaries = useCallback(async (limit: number = 20) => {
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        setSummaries([]);
        setLoading(false);
        return [];
      }

      const res = await fetch(getEndpoint(`/owner/call-summaries?limit=${limit}`), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: CallSummary[] = await res.json();
        setSummaries(data);
        return data;
      } else {
        setSummaries([]);
        const errData = await res.json().catch(() => ({ detail: "Failed to fetch call summaries" }));
        setError(errData.detail || "Failed to fetch call summaries");
        return [];
      }
    } catch (err) {
      console.error("Failed to fetch call summaries:", err);
      setSummaries([]);
      setError("Network error - could not reach server");
      return [];
    } finally {
      setLoading(false);
    }
  }, [getEndpoint]);

  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const newState = !prev;
      // Auto-fetch when expanding if no summaries loaded
      if (newState && summaries.length === 0) {
        fetchCallSummaries();
      }
      return newState;
    });
  }, [summaries.length, fetchCallSummaries]);

  const refresh = useCallback(() => {
    return fetchCallSummaries();
  }, [fetchCallSummaries]);

  return {
    // State
    summaries,
    loading,
    error,
    expanded,

    // Actions
    fetchCallSummaries,
    toggleExpanded,
    setExpanded,
    refresh,
  };
}
