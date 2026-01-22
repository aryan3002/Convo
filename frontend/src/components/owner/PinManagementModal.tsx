"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Shield, CheckCircle, Lock, Unlock } from "lucide-react";
import type { PinStatus } from "@/hooks/useOwnerPinManagement";

interface PinManagementModalProps {
  open: boolean;
  stylistId: number | null;
  stylistName: string;
  pinValue: string;
  loading: boolean;
  pinStatus: PinStatus | undefined;
  onClose: () => void;
  onSetPin: (stylistId: number, pin: string) => void;
  onRemovePin: (stylistId: number) => void;
  onPinValueChange: (value: string) => void;
}

export function PinManagementModal({
  open,
  stylistId,
  stylistName,
  pinValue,
  loading,
  pinStatus,
  onClose,
  onSetPin,
  onRemovePin,
  onPinValueChange,
}: PinManagementModalProps) {
  if (!open || !stylistId) return null;

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center p-4 overlay">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="glass-strong rounded-2xl shadow-neon p-6 max-w-sm w-full relative border border-white/10"
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-[#00d4ff]" />
            Employee PIN
          </h3>
          <p className="text-xs text-gray-400">{stylistName}</p>
        </div>

        {pinStatus?.has_pin ? (
          <div className="space-y-4">
            <div className="glass rounded-xl p-4 border border-emerald-500/20">
              <div className="flex items-center gap-2 text-emerald-400 mb-2">
                <CheckCircle className="w-4 h-4" />
                <span className="text-sm font-medium">PIN is set</span>
              </div>
              <p className="text-xs text-gray-400">
                Set on {new Date(pinStatus.pin_set_at!).toLocaleDateString()}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => onRemovePin(stylistId)}
                disabled={loading}
                className="flex-1 py-2 px-4 rounded-xl text-sm font-medium bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all disabled:opacity-50"
              >
                {loading ? "Removing..." : "Remove PIN"}
              </button>
            </div>
            <div className="border-t border-white/10 pt-4">
              <p className="text-xs text-gray-400 mb-3">Or set a new PIN:</p>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={pinValue}
                  onChange={(e) => onPinValueChange(e.target.value)}
                  placeholder="New PIN (4-8 digits)"
                  maxLength={8}
                  className="flex-1 px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 text-center tracking-widest"
                />
                <button
                  onClick={() => onSetPin(stylistId, pinValue)}
                  disabled={loading || pinValue.length < 4}
                  className="px-4 py-2 rounded-xl text-sm font-medium bg-[#00d4ff]/20 text-[#00d4ff] border border-[#00d4ff]/30 hover:bg-[#00d4ff]/30 transition-all disabled:opacity-50"
                >
                  Update
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-gray-400">
              Set a 4-8 digit PIN so this employee can log in to the Employee Portal.
            </p>
            <input
              type="password"
              value={pinValue}
              onChange={(e) => onPinValueChange(e.target.value)}
              placeholder="Enter PIN (4-8 digits)"
              maxLength={8}
              className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 text-center text-xl tracking-widest"
            />
            <button
              onClick={() => onSetPin(stylistId, pinValue)}
              disabled={loading || pinValue.length < 4}
              className="w-full py-3 px-4 rounded-xl text-sm font-medium bg-gradient-to-r from-[#00d4ff] to-[#00a8cc] text-black hover:shadow-lg hover:shadow-[#00d4ff]/25 transition-all disabled:opacity-50"
            >
              {loading ? "Setting PIN..." : "Set PIN"}
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}

// Button component for stylist card
interface PinStatusButtonProps {
  stylistId: number;
  stylistName: string;
  pinStatus: PinStatus | undefined;
  onOpenModal: (stylistId: number, stylistName: string) => void;
}

export function PinStatusButton({
  stylistId,
  stylistName,
  pinStatus,
  onOpenModal,
}: PinStatusButtonProps) {
  return (
    <button
      type="button"
      onClick={() => onOpenModal(stylistId, stylistName)}
      className={`text-[11px] px-2 py-1 rounded-full flex items-center gap-1 transition-all ${
        pinStatus?.has_pin
          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20"
          : "glass border border-white/10 text-gray-400 hover:bg-white/10 hover:text-white"
      }`}
    >
      {pinStatus?.has_pin ? (
        <>
          <Lock className="w-3 h-3" />
          PIN Set
        </>
      ) : (
        <>
          <Unlock className="w-3 h-3" />
          Set PIN
        </>
      )}
    </button>
  );
}
