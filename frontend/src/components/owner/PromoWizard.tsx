"use client";

/**
 * PromoWizard - 5-step promotion creation wizard
 * Extracted from legacy /owner/page.tsx
 */

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Gift,
  ArrowLeft,
  ArrowRight,
  Check,
  Pause,
  Play,
  Percent,
  DollarSign,
  AlertCircle,
} from "lucide-react";
import type { PromoDraft, OwnerService } from "@/lib/owner-types";
import { PROMO_TYPES, PROMO_DISCOUNTS, DAY_OPTIONS } from "@/lib/owner-types";

interface PromoWizardProps {
  open: boolean;
  step: number;
  error: string;
  saving: boolean;
  draft: PromoDraft;
  services: OwnerService[];
  onClose: () => void;
  onNext: () => void;
  onBack: () => void;
  onCreate: () => void;
  onUpdateDraft: (updates: Partial<PromoDraft>) => void;
}

export function PromoWizard({
  open,
  step,
  error,
  saving,
  draft,
  services,
  onClose,
  onNext,
  onBack,
  onCreate,
  onUpdateDraft,
}: PromoWizardProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center overlay px-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-2xl glass-strong rounded-2xl shadow-neon border border-white/10 p-6"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Gift className="w-5 h-5 text-[#00d4ff]" />
              Add promotion
            </h3>
            <p className="text-xs text-gray-400">Guided setup with structured options.</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-6 space-y-4">
          {/* Step 0: Promo Type */}
          {step === 0 && (
            <div>
              <p className="text-sm font-medium text-white mb-3">Promotion type</p>
              <div className="flex flex-wrap gap-2">
                {PROMO_TYPES.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => onUpdateDraft({ type: option.value })}
                    className={`px-4 py-2 rounded-full text-sm transition-all ${
                      draft.type === option.value
                        ? "btn-neon"
                        : "glass border border-white/10 text-gray-300 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 1: Copy Mode */}
          {step === 1 && (
            <div>
              <p className="text-sm font-medium text-white mb-3">Promotion copy</p>
              <div className="flex gap-2 mb-4">
                {(["ai", "custom"] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => onUpdateDraft({ copy_mode: mode })}
                    className={`px-4 py-2 rounded-full text-sm transition-all ${
                      draft.copy_mode === mode
                        ? "btn-neon"
                        : "glass border border-white/10 text-gray-300 hover:bg-white/10"
                    }`}
                  >
                    {mode === "ai" ? "✨ AI generated" : "✍️ Write my own"}
                  </button>
                ))}
              </div>
              {draft.copy_mode === "custom" && (
                <textarea
                  value={draft.custom_copy}
                  onChange={(e) => onUpdateDraft({ custom_copy: e.target.value })}
                  className="w-full rounded-xl input-glass p-3 text-sm"
                  rows={3}
                  placeholder="Enter the exact promotional line (placeholders like {service_name} are ok)."
                />
              )}
            </div>
          )}

          {/* Step 2: Discount Details */}
          {step === 2 && (
            <div>
              <p className="text-sm font-medium text-white mb-3">Discount details</p>
              <div className="flex flex-wrap gap-2 mb-4">
                {PROMO_DISCOUNTS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => onUpdateDraft({ discount_type: option.value })}
                    className={`px-4 py-2 rounded-full text-sm transition-all flex items-center gap-2 ${
                      draft.discount_type === option.value
                        ? "btn-neon"
                        : "glass border border-white/10 text-gray-300 hover:bg-white/10"
                    }`}
                  >
                    {option.value === "PERCENT" ? <Percent className="w-4 h-4" /> : <DollarSign className="w-4 h-4" />}
                    {option.label}
                  </button>
                ))}
              </div>
              {draft.discount_type && ["PERCENT", "FIXED"].includes(draft.discount_type) && (
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={draft.discount_value}
                    onChange={(e) => onUpdateDraft({ discount_value: e.target.value })}
                    className="flex-1 rounded-full input-glass px-4 py-2 text-sm"
                    placeholder={draft.discount_type === "PERCENT" ? "Percent" : "Amount in USD"}
                    min={0}
                  />
                  <span className="text-xs text-gray-400">
                    {draft.discount_type === "PERCENT" ? "%" : "USD"}
                  </span>
                </div>
              )}
              {draft.discount_type && ["FREE_ADDON", "BUNDLE"].includes(draft.discount_type) && (
                <input
                  type="text"
                  value={draft.perk_description}
                  onChange={(e) => onUpdateDraft({ perk_description: e.target.value })}
                  className="w-full rounded-full input-glass px-4 py-2 text-sm"
                  placeholder="Optional perk description (e.g., free beard trim)"
                />
              )}
            </div>
          )}

          {/* Step 3: Constraints */}
          {step === 3 && (
            <div className="space-y-4">
              {draft.type === "SERVICE_COMBO_PROMO" && (
                <div>
                  <p className="text-sm font-medium text-white mb-2">Service selection</p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <select
                      value={draft.service_id ?? ""}
                      onChange={(e) =>
                        onUpdateDraft({ service_id: e.target.value ? Number(e.target.value) : null })
                      }
                      className="w-full rounded-xl input-glass px-4 py-2 text-sm bg-transparent"
                    >
                      <option value="" className="bg-[#0f1629]">Primary service</option>
                      {services.map((svc) => (
                        <option key={svc.id} value={svc.id} className="bg-[#0f1629]">
                          {svc.name}
                        </option>
                      ))}
                    </select>
                    <select
                      value={draft.combo_secondary_service_id ?? ""}
                      onChange={(e) =>
                        onUpdateDraft({
                          combo_secondary_service_id: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                      className="w-full rounded-xl input-glass px-4 py-2 text-sm bg-transparent"
                    >
                      <option value="" className="bg-[#0f1629]">Secondary service</option>
                      {services.map((svc) => (
                        <option key={svc.id} value={svc.id} className="bg-[#0f1629]">
                          {svc.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {services.length === 0 && (
                    <p className="text-xs text-red-400 mt-2 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" />
                      Add a service before creating a combo promotion.
                    </p>
                  )}
                </div>
              )}
              {draft.type === "SEASONAL_PROMO" && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">Start date</label>
                    <input
                      type="date"
                      value={draft.start_at}
                      onChange={(e) => onUpdateDraft({ start_at: e.target.value })}
                      className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">End date</label>
                    <input
                      type="date"
                      value={draft.end_at}
                      onChange={(e) => onUpdateDraft({ end_at: e.target.value })}
                      className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Minimum spend (USD)</label>
                  <input
                    type="number"
                    value={draft.min_spend}
                    onChange={(e) => onUpdateDraft({ min_spend: e.target.value })}
                    className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                    min={0}
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Usage limit per customer</label>
                  <input
                    type="number"
                    value={draft.usage_limit}
                    onChange={(e) => onUpdateDraft({ usage_limit: e.target.value })}
                    className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                    min={0}
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-2 block">Valid days</label>
                <div className="flex flex-wrap gap-2">
                  {DAY_OPTIONS.map((day) => (
                    <button
                      key={day.value}
                      onClick={() => {
                        const exists = draft.valid_days.includes(day.value);
                        onUpdateDraft({
                          valid_days: exists
                            ? draft.valid_days.filter((d) => d !== day.value)
                            : [...draft.valid_days, day.value],
                        });
                      }}
                      className={`px-3 py-1 rounded-full text-xs transition-all ${
                        draft.valid_days.includes(day.value)
                          ? "bg-[#00d4ff] text-black font-medium"
                          : "glass border border-white/10 text-gray-400 hover:bg-white/10"
                      }`}
                    >
                      {day.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Activation */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between glass rounded-xl p-4">
                <div>
                  <p className="text-sm font-medium text-white">Activation</p>
                  <p className="text-xs text-gray-400">Enable or pause the promotion.</p>
                </div>
                <button
                  onClick={() => onUpdateDraft({ active: !draft.active })}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-2 ${
                    draft.active
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : "glass border border-white/10 text-gray-400"
                  }`}
                >
                  {draft.active ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                  {draft.active ? "Active" : "Paused"}
                </button>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-6 flex items-center justify-between">
          <button
            onClick={onBack}
            disabled={step === 0}
            className="px-4 py-2 rounded-full text-sm glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          {step < 4 ? (
            <button
              onClick={onNext}
              className="px-5 py-2 rounded-full btn-neon text-sm flex items-center gap-2"
            >
              Next
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={onCreate}
              disabled={saving}
              className="px-5 py-2 rounded-full btn-neon text-sm disabled:opacity-60 flex items-center gap-2"
            >
              {saving ? (
                <>
                  <div className="spinner w-4 h-4" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  Create promotion
                </>
              )}
            </button>
          )}
        </div>
      </motion.div>
    </div>
  );
}
