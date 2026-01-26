/**
 * Hook for managing promotions
 * Extracted from legacy /owner/page.tsx
 */

import { useState, useCallback } from "react";
import type { OwnerPromo, PromoDraft } from "@/lib/owner-types";
import { getApiBase } from "@/lib/owner-utils";
import { getStoredUserId } from "@/lib/api";

const API_BASE = getApiBase();

const DEFAULT_PROMO_DRAFT: PromoDraft = {
  type: null,
  trigger_point: null,
  copy_mode: "ai",
  custom_copy: "",
  discount_type: null,
  discount_value: "",
  min_spend: "",
  usage_limit: "",
  valid_days: [],
  service_id: null,
  combo_secondary_service_id: null,
  start_at: "",
  end_at: "",
  active: true,
  priority: 0,
  perk_description: "",
};

export function useOwnerPromos(shopSlug?: string) {
  const [promos, setPromos] = useState<OwnerPromo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Wizard state
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardError, setWizardError] = useState("");
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<PromoDraft>(DEFAULT_PROMO_DRAFT);

  // Action state
  const [actionOpenId, setActionOpenId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const getEndpoint = useCallback((path: string) => {
    if (shopSlug) {
      return `${API_BASE}/s/${shopSlug}${path}`;
    }
    return `${API_BASE}${path}`;
  }, [shopSlug]);

  const fetchPromos = useCallback(async () => {
    // Don't fetch if no slug provided (e.g., cab shops)
    if (!shopSlug) {
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const userId = getStoredUserId();
      if (!userId) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }
      const res = await fetch(getEndpoint("/owner/promos"), {
        headers: { "X-User-Id": userId },
      });
      if (res.ok) {
        const data: OwnerPromo[] = await res.json();
        setPromos(data);
      } else {
        setError("Failed to fetch promotions");
      }
    } catch (err) {
      console.error("Failed to fetch promos:", err);
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }, [getEndpoint, shopSlug]);

  const resetWizard = useCallback(() => {
    setWizardStep(0);
    setWizardError("");
    setDraft(DEFAULT_PROMO_DRAFT);
  }, []);

  const openWizard = useCallback(() => {
    resetWizard();
    setWizardOpen(true);
  }, [resetWizard]);

  const closeWizard = useCallback(() => {
    setWizardOpen(false);
  }, []);

  const updateDraft = useCallback((updates: Partial<PromoDraft>) => {
    setDraft((prev) => ({ ...prev, ...updates }));
  }, []);

  const nextStep = useCallback(() => {
    setWizardError("");
    
    if (wizardStep === 0 && !draft.type) {
      setWizardError("Select a promotion type to continue.");
      return false;
    }
    if (wizardStep === 1 && draft.copy_mode === "custom" && !draft.custom_copy.trim()) {
      setWizardError("Add your custom promo copy or switch to AI copy.");
      return false;
    }
    if (wizardStep === 2) {
      if (!draft.discount_type) {
        setWizardError("Select a discount type.");
        return false;
      }
      if (["PERCENT", "FIXED"].includes(draft.discount_type) && !draft.discount_value.trim()) {
        setWizardError("Enter a discount value.");
        return false;
      }
    }
    if (wizardStep === 3) {
      if (
        draft.type === "SERVICE_COMBO_PROMO" &&
        (!draft.service_id ||
          !draft.combo_secondary_service_id ||
          draft.service_id === draft.combo_secondary_service_id)
      ) {
        setWizardError("Select two different services for the combo promotion.");
        return false;
      }
      if (draft.type === "SEASONAL_PROMO" && (!draft.start_at || !draft.end_at)) {
        setWizardError("Seasonal promotions need a start and end date.");
        return false;
      }
    }
    
    setWizardStep((step) => Math.min(step + 1, 4));
    return true;
  }, [wizardStep, draft]);

  const prevStep = useCallback(() => {
    setWizardError("");
    setWizardStep((step) => Math.max(step - 1, 0));
  }, []);

  const createPromo = useCallback(async (): Promise<OwnerPromo | null> => {
    setWizardError("");
    
    if (!draft.type || !draft.discount_type) {
      setWizardError("Complete the required fields before saving.");
      return null;
    }

    let discountValue: number | null = null;
    if (draft.discount_type === "PERCENT") {
      discountValue = Number(draft.discount_value || 0);
    }
    if (draft.discount_type === "FIXED") {
      discountValue = Math.round(Number(draft.discount_value || 0) * 100);
    }
    if (["PERCENT", "FIXED"].includes(draft.discount_type) && (!discountValue || discountValue <= 0)) {
      setWizardError("Discount value must be greater than zero.");
      return null;
    }

    const constraints: Record<string, unknown> = {};
    if (draft.min_spend.trim()) {
      const minSpend = Number(draft.min_spend);
      if (!Number.isNaN(minSpend)) {
        constraints.min_spend_cents = Math.round(minSpend * 100);
      }
    }
    if (draft.usage_limit.trim()) {
      const usageLimit = Number(draft.usage_limit);
      if (!Number.isNaN(usageLimit)) {
        constraints.usage_limit_per_customer = usageLimit;
      }
    }
    if (draft.valid_days.length) {
      constraints.valid_days_of_week = draft.valid_days;
    }
    if (draft.perk_description.trim()) {
      constraints.perk_description = draft.perk_description.trim();
    }
    if (
      draft.type === "SERVICE_COMBO_PROMO" &&
      draft.service_id &&
      draft.combo_secondary_service_id
    ) {
      constraints.combo_service_ids = [
        draft.service_id,
        draft.combo_secondary_service_id,
      ];
    }

    const payload = {
      type: draft.type,
      service_id: draft.service_id,
      discount_type: draft.discount_type,
      discount_value: discountValue,
      constraints_json: Object.keys(constraints).length ? constraints : null,
      custom_copy: draft.copy_mode === "custom" ? draft.custom_copy.trim() : null,
      start_at: draft.start_at || null,
      end_at: draft.end_at || null,
      active: draft.active,
      priority: draft.priority,
    };

    setSaving(true);
    try {
      const userId = getStoredUserId();
      if (!userId) throw new Error("Not authenticated");
      const res = await fetch(getEndpoint("/owner/promos"), {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to save promotion.");
      }
      const created: OwnerPromo = await res.json();
      await fetchPromos();
      closeWizard();
      return created;
    } catch (err) {
      setWizardError(err instanceof Error ? err.message : "Unable to save the promotion.");
      return null;
    } finally {
      setSaving(false);
    }
  }, [draft, getEndpoint, fetchPromos, closeWizard]);

  const togglePromoActive = useCallback(async (promo: OwnerPromo) => {
    setActionLoading(true);
    try {
      const userId = getStoredUserId();
      if (!userId) throw new Error("Not authenticated");
      const res = await fetch(getEndpoint(`/owner/promos/${promo.id}`), {
        method: "PATCH",
        headers: { 
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ active: !promo.active }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to update promotion.");
      }
      await fetchPromos();
    } catch (err) {
      console.error("Failed to update promo:", err);
      throw err;
    } finally {
      setActionLoading(false);
    }
  }, [getEndpoint, fetchPromos]);

  const removePromo = useCallback(async (promoId: number) => {
    setActionLoading(true);
    try {
      const userId = getStoredUserId();
      if (!userId) throw new Error("Not authenticated");
      const res = await fetch(getEndpoint(`/owner/promos/${promoId}`), {
        method: "DELETE",
        headers: { "X-User-Id": userId },
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to remove promotion.");
      }
      await fetchPromos();
      setActionOpenId(null);
    } catch (err) {
      console.error("Failed to remove promo:", err);
      throw err;
    } finally {
      setActionLoading(false);
    }
  }, [getEndpoint, fetchPromos]);

  return {
    // State
    promos,
    loading,
    error,
    
    // Wizard state
    wizardOpen,
    wizardStep,
    wizardError,
    saving,
    draft,
    
    // Action state
    actionOpenId,
    actionLoading,
    
    // Actions
    fetchPromos,
    openWizard,
    closeWizard,
    resetWizard,
    updateDraft,
    nextStep,
    prevStep,
    createPromo,
    togglePromoActive,
    removePromo,
    setActionOpenId,
  };
}
