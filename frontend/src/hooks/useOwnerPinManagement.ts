/**
 * Hook for managing stylist PIN codes
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type PinStatus = {
  has_pin: boolean;
  pin_set_at: string | null;
};

export function useOwnerPinManagement(shopSlug?: string) {
  const [pinStatuses, setPinStatuses] = useState<Record<number, PinStatus>>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedStylistId, setSelectedStylistId] = useState<number | null>(null);
  const [selectedStylistName, setSelectedStylistName] = useState("");
  const [pinValue, setPinValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchPinStatus = useCallback(async (stylistId: number) => {
    try {
      const userId = getStoredUserId();
      if (!userId) {
        return;
      }

      const res = await fetch(getEndpoint(`/stylists/${stylistId}/pin-status`), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data = await res.json();
        setPinStatuses((prev) => ({
          ...prev,
          [stylistId]: { has_pin: data.has_pin, pin_set_at: data.pin_set_at },
        }));
      }
    } catch (err) {
      console.error("Failed to fetch PIN status:", err);
    }
  }, [getEndpoint]);

  const fetchAllPinStatuses = useCallback(async (stylistIds: number[]) => {
    for (const stylistId of stylistIds) {
      await fetchPinStatus(stylistId);
    }
  }, [fetchPinStatus]);

  const setPin = useCallback(async (stylistId: number, pin: string) => {
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        setLoading(false);
        return false;
      }

      const res = await fetch(getEndpoint(`/stylists/${stylistId}/pin`), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ pin }),
      });
      if (res.ok) {
        await fetchPinStatus(stylistId);
        setModalOpen(false);
        setPinValue("");
        return true;
      } else {
        const errData = await res.json().catch(() => ({ detail: "Failed to set PIN" }));
        setError(errData.detail || "Failed to set PIN");
        return false;
      }
    } catch (err) {
      console.error("Failed to set PIN:", err);
      setError("Network error - could not set PIN");
      return false;
    } finally {
      setLoading(false);
    }
  }, [getEndpoint, fetchPinStatus]);

  const removePin = useCallback(async (stylistId: number) => {
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Authentication required. Please log in.");
        setLoading(false);
        return false;
      }

      const res = await fetch(getEndpoint(`/stylists/${stylistId}/pin`), {
        method: "DELETE",
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        await fetchPinStatus(stylistId);
        setModalOpen(false);
        return true;
      } else {
        setError("Failed to remove PIN");
        return false;
      }
    } catch (err) {
      console.error("Failed to remove PIN:", err);
      setError("Network error - could not remove PIN");
      return false;
    } finally {
      setLoading(false);
    }
  }, [getEndpoint, fetchPinStatus]);

  const openModal = useCallback((stylistId: number, stylistName: string) => {
    setSelectedStylistId(stylistId);
    setSelectedStylistName(stylistName);
    setPinValue("");
    setError(null);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setPinValue("");
    setError(null);
  }, []);

  return {
    // State
    pinStatuses,
    modalOpen,
    selectedStylistId,
    selectedStylistName,
    pinValue,
    loading,
    error,

    // Actions
    fetchPinStatus,
    fetchAllPinStatuses,
    setPin,
    removePin,
    openModal,
    closeModal,
    setPinValue,
  };
}
