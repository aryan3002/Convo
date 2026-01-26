/**
 * Hook for managing analytics data
 * Extracted from legacy /owner/page.tsx
 */

import { useState, useCallback } from "react";
import type { AnalyticsSummary, AIInsights } from "@/lib/owner-types";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type AnalyticsRange = "7d" | "30d";

export function useOwnerAnalytics(shopSlug?: string) {
  const [range, setRange] = useState<AnalyticsRange>("7d");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // AI Insights
  const [aiInsights, setAiInsights] = useState<AIInsights | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchSummary = useCallback(async (rangeValue: AnalyticsRange = range) => {
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
      const res = await fetch(getEndpoint(`/owner/analytics/summary?range=${rangeValue}`), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: AnalyticsSummary = await res.json();
        setSummary(data);
      } else {
        setError("Failed to fetch analytics");
      }
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, [range, getEndpoint, shopSlug]);

  const changeRange = useCallback((newRange: AnalyticsRange) => {
    setRange(newRange);
    fetchSummary(newRange);
  }, [fetchSummary]);

  const fetchAiInsights = useCallback(async () => {
    if (!summary) return;
    
    setAiLoading(true);
    setAiError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setAiError("Not authenticated");
        setAiLoading(false);
        return;
      }
      const res = await fetch(getEndpoint("/owner/analytics/insights"), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({
          analytics: summary,
          business_context: {
            business_type: "salon",
            has_deposits: false,
            has_reminders: true,
          },
        }),
      });
      if (res.ok) {
        const data: AIInsights = await res.json();
        setAiInsights(data);
      } else {
        const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
        setAiError(errData.detail || "Failed to generate insights");
      }
    } catch (err) {
      console.error("Failed to fetch AI insights:", err);
      setAiError("Network error - could not reach server");
    } finally {
      setAiLoading(false);
    }
  }, [summary, getEndpoint]);

  return {
    // State
    range,
    summary,
    loading,
    error,
    
    // AI State
    aiInsights,
    aiLoading,
    aiError,
    
    // Actions
    fetchSummary,
    changeRange,
    fetchAiInsights,
  };
}
