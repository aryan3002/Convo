/**
 * Hook for customer lookup functionality
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type CustomerProfile = {
  email: string | null;
  phone?: string | null;
  name: string | null;
  preferred_stylist: string | null;
  last_service: string | null;
  last_stylist: string | null;
  average_spend_cents: number;
  total_bookings: number;
  total_spend_cents: number;
  last_booking_at: string | null;
};

export function useOwnerCustomerLookup(shopSlug?: string) {
  const [identity, setIdentity] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<CustomerProfile | null>(null);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const lookupCustomer = useCallback(async (searchIdentity?: string) => {
    const search = (searchIdentity || identity).trim();
    if (!search) {
      setError("Please enter an email or phone number");
      return null;
    }

    setLoading(true);
    setError(null);
    setProfile(null);

    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        return null;
      }

      // Determine if it's email or phone
      const isEmail = search.includes("@");
      const queryParam = isEmail ? `email=${encodeURIComponent(search)}` : `phone=${encodeURIComponent(search)}`;
      
      const res = await fetch(getEndpoint(`/owner/customer-profile?${queryParam}`), {
        headers: { "X-User-Id": userId },
      });
      
      if (res.ok) {
        const data: CustomerProfile = await res.json();
        setProfile(data);
        return data;
      } else if (res.status === 404) {
        setError("Customer not found");
        return null;
      } else {
        const errData = await res.json().catch(() => ({ detail: "Failed to lookup customer" }));
        setError(errData.detail || "Failed to lookup customer");
        return null;
      }
    } catch (err) {
      console.error("Failed to lookup customer:", err);
      setError("Network error - could not reach server");
      return null;
    } finally {
      setLoading(false);
    }
  }, [identity, getEndpoint]);

  const clearProfile = useCallback(() => {
    setProfile(null);
    setError(null);
  }, []);

  const reset = useCallback(() => {
    setIdentity("");
    setProfile(null);
    setError(null);
  }, []);

  return {
    // State
    identity,
    loading,
    error,
    profile,

    // Actions
    setIdentity,
    lookupCustomer,
    clearProfile,
    reset,
  };
}
