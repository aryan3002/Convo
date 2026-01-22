/**
 * Hook for managing time off requests (pending approval)
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type TimeOffRequestItem = {
  id: number;
  stylist_id: number;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  reviewer: string | null;
};

export function useOwnerTimeOffRequests(shopSlug?: string) {
  const [requests, setRequests] = useState<TimeOffRequestItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewLoading, setReviewLoading] = useState<number | null>(null);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchPendingRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        setRequests([]);
        setLoading(false);
        return [];
      }

      const res = await fetch(getEndpoint("/time-off-requests?status_filter=PENDING"), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: TimeOffRequestItem[] = await res.json();
        setRequests(data);
        return data;
      } else {
        setRequests([]);
        const errData = await res.json().catch(() => ({ detail: "Failed to fetch requests" }));
        setError(errData.detail || "Failed to fetch time off requests");
        return [];
      }
    } catch (err) {
      console.error("Failed to fetch time-off requests:", err);
      setRequests([]);
      setError("Network error - could not reach server");
      return [];
    } finally {
      setLoading(false);
    }
  }, [getEndpoint]);

  const reviewRequest = useCallback(async (
    requestId: number, 
    action: "approve" | "reject",
    reviewer: string = "Owner",
    onSuccess?: () => void
  ) => {
    setReviewLoading(requestId);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        setReviewLoading(null);
        return false;
      }

      const res = await fetch(getEndpoint(`/time-off-requests/${requestId}/review`), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ action, reviewer }),
      });
      if (res.ok) {
        await fetchPendingRequests();
        onSuccess?.();
        return true;
      } else {
        const errData = await res.json().catch(() => ({ detail: "Failed to review request" }));
        setError(errData.detail || "Failed to review request");
        return false;
      }
    } catch (err) {
      console.error("Failed to review time-off request:", err);
      setError("Network error - could not reach server");
      return false;
    } finally {
      setReviewLoading(null);
    }
  }, [getEndpoint, fetchPendingRequests]);

  const approveRequest = useCallback((requestId: number, onSuccess?: () => void) => {
    return reviewRequest(requestId, "approve", "Owner", onSuccess);
  }, [reviewRequest]);

  const rejectRequest = useCallback((requestId: number, onSuccess?: () => void) => {
    return reviewRequest(requestId, "reject", "Owner", onSuccess);
  }, [reviewRequest]);

  return {
    // State
    requests,
    loading,
    error,
    reviewLoading,

    // Actions
    fetchPendingRequests,
    reviewRequest,
    approveRequest,
    rejectRequest,
  };
}
