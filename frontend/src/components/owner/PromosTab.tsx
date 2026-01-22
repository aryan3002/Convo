"use client";

/**
 * PromosTab - Promotions list and management UI
 * Extracted from legacy /owner/page.tsx
 */

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Tag, Plus, Pause, Play, Trash2 } from "lucide-react";
import type { OwnerPromo, OwnerService } from "@/lib/owner-types";
import {
  formatPromoType,
  formatPromoDiscount,
  formatPromoTrigger,
  formatPromoWindow,
} from "@/lib/owner-utils";

interface PromosTabProps {
  promos: OwnerPromo[];
  services: OwnerService[];
  actionOpenId: number | null;
  actionLoading: boolean;
  onOpenWizard: () => void;
  onToggleActive: (promo: OwnerPromo) => void;
  onRemove: (promoId: number) => void;
  onSetActionOpenId: (id: number | null) => void;
}

function formatPromoServices(promo: OwnerPromo, services: OwnerService[]) {
  if (promo.type !== "SERVICE_COMBO_PROMO") {
    if (!promo.service_id) return "";
    const svc = services.find((s) => s.id === promo.service_id);
    return svc ? `Service: ${svc.name}` : "";
  }
  const comboIds = Array.isArray(promo.constraints_json?.combo_service_ids)
    ? (promo.constraints_json?.combo_service_ids as number[])
    : [];
  if (comboIds.length !== 2) return "";
  const names = comboIds
    .map((id) => services.find((svc) => svc.id === id)?.name)
    .filter(Boolean);
  if (names.length !== 2) return "";
  return `Combo: ${names[0]} + ${names[1]}`;
}

export function PromosTab({
  promos,
  services,
  actionOpenId,
  actionLoading,
  onOpenWizard,
  onToggleActive,
  onRemove,
  onSetActionOpenId,
}: PromosTabProps) {
  const handleRemove = async (promoId: number) => {
    const confirmDelete = window.confirm(
      "Are you sure you want to permanently remove this promotion?"
    );
    if (confirmDelete) {
      onRemove(promoId);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl p-6 border border-white/5"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Tag className="w-4 h-4 text-[#ec4899]" />
            Current promotions
          </h2>
          <p className="text-xs text-gray-500">Live view from the database.</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onOpenWizard}
          className="px-3 py-2 rounded-full btn-neon text-xs flex items-center gap-1"
        >
          <Plus className="w-3 h-3" />
          Add
        </motion.button>
      </div>

      <div className="space-y-3">
        {promos.length === 0 && (
          <div className="text-xs text-gray-500 text-center py-8">
            No promotions configured yet.
            <br />
            <span className="text-[#ec4899]">Click "Add" to create one!</span>
          </div>
        )}
        {promos.map((promo) => (
          <motion.div
            key={promo.id}
            whileHover={{ scale: 1.01 }}
            className="glass rounded-xl p-3 border border-white/5 hover:border-[#ec4899]/30 transition-all cursor-pointer"
            onClick={() =>
              onSetActionOpenId(actionOpenId === promo.id ? null : promo.id)
            }
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSetActionOpenId(actionOpenId === promo.id ? null : promo.id);
              }
            }}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-medium text-white">
                  {formatPromoType(promo.type)}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {formatPromoDiscount(promo)} · {formatPromoTrigger(promo.trigger_point)}
                </p>
                <p className="text-[11px] text-gray-500 mt-1">
                  {formatPromoWindow(promo)}
                </p>
                {formatPromoServices(promo, services) && (
                  <p className="text-[11px] text-gray-500">
                    {formatPromoServices(promo, services)}
                  </p>
                )}
                <p className="text-[11px] text-gray-600 mt-1">ID: {promo.id}</p>
              </div>
              <span
                className={`text-[11px] px-2 py-1 rounded-full ${
                  promo.active
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "glass border border-white/10 text-gray-500"
                }`}
              >
                {promo.active ? "Active" : "Paused"}
              </span>
            </div>
            <AnimatePresence>
              {actionOpenId === promo.id && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="mt-3 flex flex-wrap gap-2"
                >
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleActive(promo);
                    }}
                    disabled={actionLoading}
                    className="px-3 py-1.5 rounded-full text-xs glass border border-white/10 hover:bg-white/10 text-white disabled:opacity-60 flex items-center gap-1 transition-all"
                  >
                    {promo.active ? (
                      <Pause className="w-3 h-3" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    {promo.active ? "Pause" : "Activate"}
                  </button>
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      handleRemove(promo.id);
                    }}
                    disabled={actionLoading}
                    className="px-3 py-1.5 rounded-full text-xs bg-red-500/20 border border-red-500/30 text-red-400 hover:bg-red-500/30 disabled:opacity-60 flex items-center gap-1 transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                    Remove
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
