/**
 * Hook for managing service booking counts
 * Multi-tenant version with shop slug support
 */

import { useState, useCallback } from "react";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

export type ServiceBooking = {
  id: string;
  customer_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  stylist_name: string;
  status: string;
  start_time: string;
  end_time: string;
};

export function useOwnerServiceBookings(shopSlug?: string) {
  const [bookingCounts, setBookingCounts] = useState<Record<number, number>>({});
  const [selectedBookings, setSelectedBookings] = useState<ServiceBooking[]>([]);
  const [selectedServiceName, setSelectedServiceName] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [countsLoading, setCountsLoading] = useState(false);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchBookingCounts = useCallback(async () => {
    if (!shopSlug) return {};
    
    setCountsLoading(true);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setCountsLoading(false);
        return {};
      }

      const res = await fetch(getEndpoint("/services/booking-counts"), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: { service_id: number; upcoming_bookings: number }[] = await res.json();
        const counts: Record<number, number> = {};
        data.forEach((item) => {
          counts[item.service_id] = item.upcoming_bookings;
        });
        setBookingCounts(counts);
        return counts;
      }
    } catch (err) {
      console.error("Failed to fetch booking counts:", err);
    } finally {
      setCountsLoading(false);
    }
    return {};
  }, [getEndpoint, shopSlug]);

  const fetchServiceBookings = useCallback(async (serviceId: number, serviceName: string) => {
    setLoading(true);
    setSelectedServiceName(serviceName);
    setModalOpen(true);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setSelectedBookings([]);
        setLoading(false);
        return [];
      }

      const res = await fetch(getEndpoint(`/services/${serviceId}/bookings`), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: ServiceBooking[] = await res.json();
        setSelectedBookings(data);
        return data;
      } else {
        setSelectedBookings([]);
        return [];
      }
    } catch (err) {
      console.error("Failed to fetch service bookings:", err);
      setSelectedBookings([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, [getEndpoint]);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setSelectedBookings([]);
  }, []);

  return {
    // State
    bookingCounts,
    selectedBookings,
    selectedServiceName,
    modalOpen,
    loading,
    countsLoading,

    // Actions
    fetchBookingCounts,
    fetchServiceBookings,
    closeModal,
  };
}
