"use client";

import React, { useState, useEffect } from "react";
import { DollarSign, Edit2, Check, X, AlertCircle } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface PricingSettings {
  id: number;
  shop_id: number;
  per_mile_rate: number;
  rounding_step: number;
  minimum_fare: number;
  currency: string;
  vehicle_multipliers: Record<string, number>;
  active: boolean;
}

interface PricingSettingsProps {
  slug: string;
}

export function PricingSettings({ slug }: PricingSettingsProps) {
  const [pricing, setPricing] = useState<PricingSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [newRate, setNewRate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchPricing();
  }, [slug]);

  const fetchPricing = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PricingSettings>(`/s/${slug}/owner/cab/pricing`);
      setPricing(data);
      setNewRate(data.per_mile_rate.toString());
    } catch (err: any) {
      console.error("Error fetching pricing:", err);
      setError(err.detail || "Failed to load pricing");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!newRate || isNaN(parseFloat(newRate))) {
      setError("Please enter a valid rate");
      return;
    }

    const rate = parseFloat(newRate);
    if (rate < 0.5 || rate > 50) {
      setError("Rate must be between $0.50 and $50.00");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const updated = await apiFetch<PricingSettings>(
        `/s/${slug}/owner/cab/pricing/rate`,
        {
          method: "PATCH",
          body: { per_mile_rate: rate },
        }
      );
      setPricing(updated);
      setEditing(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      console.error("Error updating pricing:", err);
      setError(err.detail || "Failed to update pricing");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (pricing) {
      setNewRate(pricing.per_mile_rate.toString());
    }
    setEditing(false);
    setError(null);
  };

  if (loading) {
    return (
      <div className="glass rounded-2xl p-6 border border-white/5">
        <div className="animate-pulse">
          <div className="h-4 bg-white/10 rounded w-1/3 mb-4" />
          <div className="h-10 bg-white/10 rounded w-1/2" />
        </div>
      </div>
    );
  }

  if (!pricing) {
    return null;
  }

  return (
    <div className="glass rounded-2xl p-6 border border-white/5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-[#00d4ff]" />
          <h3 className="font-semibold">Pricing Settings</h3>
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="p-2 rounded-lg glass border border-white/10 hover:bg-white/10 transition-colors"
          >
            <Edit2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="mb-4 p-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-400 text-sm flex items-center gap-2">
          <Check className="w-4 h-4 flex-shrink-0" />
          <span>Pricing updated successfully!</span>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Per Mile Rate</label>
          {editing ? (
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg input-glass">
                <span className="text-gray-400">$</span>
                <input
                  type="number"
                  value={newRate}
                  onChange={(e) => setNewRate(e.target.value)}
                  step="0.25"
                  min="0.5"
                  max="50"
                  className="flex-1 bg-transparent outline-none"
                  placeholder="4.00"
                />
                <span className="text-sm text-gray-500">/ mile</span>
              </div>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 rounded-lg btn-neon text-sm disabled:opacity-50"
              >
                {saving ? "..." : <Check className="w-4 h-4" />}
              </button>
              <button
                onClick={handleCancel}
                disabled={saving}
                className="px-4 py-2 rounded-lg glass hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="px-4 py-3 rounded-lg glass">
              <p className="text-2xl font-bold text-[#00d4ff]">
                ${pricing.per_mile_rate.toFixed(2)}
                <span className="text-sm text-gray-400 font-normal ml-2">per mile</span>
              </p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-3 pt-4 border-t border-white/5">
          <div>
            <p className="text-xs text-gray-500 mb-1">Rounding</p>
            <p className="text-sm font-medium">${pricing.rounding_step.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Min Fare</p>
            <p className="text-sm font-medium">${pricing.minimum_fare.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Currency</p>
            <p className="text-sm font-medium">{pricing.currency}</p>
          </div>
        </div>

        <div className="pt-4 border-t border-white/5">
          <p className="text-xs text-gray-500 mb-2">Vehicle Multipliers</p>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(pricing.vehicle_multipliers).map(([type, mult]) => (
              <div key={type} className="px-3 py-2 rounded-lg glass text-xs">
                <p className="text-gray-400 mb-1">
                  {type.replace("_", " ")}
                </p>
                <p className="font-medium">{mult}x</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
