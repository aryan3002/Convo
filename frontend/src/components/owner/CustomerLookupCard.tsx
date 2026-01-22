"use client";

import React from "react";
import { motion } from "framer-motion";
import { Search, User, AlertCircle } from "lucide-react";
import type { CustomerProfile } from "@/hooks/useOwnerCustomerLookup";

interface CustomerLookupCardProps {
  identity: string;
  loading: boolean;
  error: string | null;
  profile: CustomerProfile | null;
  onIdentityChange: (value: string) => void;
  onSearch: () => void;
}

export function CustomerLookupCard({
  identity,
  loading,
  error,
  profile,
  onIdentityChange,
  onSearch,
}: CustomerLookupCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass-card rounded-2xl p-6 border border-white/5"
    >
      <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
        <Search className="w-4 h-4 text-[#00d4ff]" />
        Customer lookup
      </h2>
      <p className="text-xs text-gray-500 mb-4">Quick profile by email or phone.</p>
      <div className="flex gap-2">
        <input
          type="text"
          value={identity}
          onChange={(e) => onIdentityChange(e.target.value)}
          placeholder="Email or phone number"
          className="flex-1 px-4 py-2 rounded-full input-glass text-xs"
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
        />
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onSearch}
          disabled={!identity.trim() || loading}
          className="px-4 py-2 rounded-full btn-neon text-xs font-medium disabled:opacity-60 flex items-center gap-1"
        >
          {loading ? (
            <>
              <div className="spinner w-3 h-3" />
              Searching...
            </>
          ) : (
            <>
              <Search className="w-3 h-3" />
              Search
            </>
          )}
        </motion.button>
      </div>
      
      {error && (
        <p className="mt-3 text-xs text-red-400 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          {error}
        </p>
      )}
      
      {profile && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 glass rounded-xl p-4 text-xs text-gray-300 space-y-2 border border-white/5"
        >
          <div className="flex justify-between">
            <span className="text-gray-500 flex items-center gap-1">
              <User className="w-3 h-3" /> Customer
            </span>
            <span className="font-medium text-white">
              {profile.name || profile.email || profile.phone || "Guest"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Preferred stylist</span>
            <span className="font-medium">
              {profile.preferred_stylist || "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Last service</span>
            <span className="font-medium">
              {profile.last_service || "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Average spend</span>
            <span className="font-medium text-[#00d4ff]">
              ${(profile.average_spend_cents / 100).toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Total bookings</span>
            <span className="font-medium">
              {profile.total_bookings}
            </span>
          </div>
          {profile.last_booking_at && (
            <div className="flex justify-between">
              <span className="text-gray-500">Last visit</span>
              <span className="font-medium">
                {new Date(profile.last_booking_at).toLocaleDateString()}
              </span>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
