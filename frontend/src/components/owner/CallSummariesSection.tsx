"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Phone, ChevronRight, Scissors, User, Calendar, Clock } from "lucide-react";
import type { CallSummary } from "@/hooks/useOwnerCallSummaries";

interface CallSummariesSectionProps {
  summaries: CallSummary[];
  loading: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  onRefresh: () => void;
}

export function CallSummariesSection({
  summaries,
  loading,
  expanded,
  onToggleExpanded,
  onRefresh,
}: CallSummariesSectionProps) {
  return (
    <div className="mt-6 border-t border-white/5 pt-4">
      <button
        onClick={onToggleExpanded}
        className="flex items-center justify-between w-full text-left group"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#a855f7]/20 flex items-center justify-center">
            <Phone className="w-4 h-4 text-[#a855f7]" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Recent Call Summaries</h3>
            <p className="text-xs text-gray-500">Voice call activity for owner review</p>
          </div>
        </div>
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          className="text-gray-500 group-hover:text-white transition-colors"
        >
          <ChevronRight className="w-4 h-4" />
        </motion.span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="mt-4 space-y-3 max-h-80 overflow-y-auto scrollbar-hide"
          >
            {loading && (
              <div className="text-xs text-gray-500 flex items-center gap-2">
                <div className="spinner w-4 h-4" />
                Loading call summaries...
              </div>
            )}
            {!loading && summaries.length === 0 && (
              <div className="text-xs text-gray-500">No call summaries yet.</div>
            )}
            {summaries.map((summary) => (
              <motion.div
                key={summary.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass rounded-xl p-3 border border-white/5"
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <span className="text-sm font-medium text-white">
                      {summary.customer_name || "Unknown Caller"}
                    </span>
                    <span className="text-xs text-gray-500 ml-2">
                      {summary.customer_phone}
                    </span>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      summary.booking_status === "confirmed"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : summary.booking_status === "follow_up"
                        ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                        : "glass border border-white/10 text-gray-400"
                    }`}
                  >
                    {summary.booking_status === "confirmed"
                      ? "✓ Confirmed"
                      : summary.booking_status === "follow_up"
                      ? "⚡ Follow-up"
                      : "Not booked"}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
                  {summary.service && (
                    <div className="flex items-center gap-1">
                      <Scissors className="w-3 h-3" />
                      {summary.service}
                    </div>
                  )}
                  {summary.stylist && (
                    <div className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {summary.stylist}
                    </div>
                  )}
                  {summary.appointment_date && (
                    <div className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {summary.appointment_date}
                    </div>
                  )}
                  {summary.appointment_time && (
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {summary.appointment_time}
                    </div>
                  )}
                </div>
                {summary.key_notes && (
                  <div className="mt-2 text-xs text-gray-500 italic">
                    {summary.key_notes}
                  </div>
                )}
                <div className="mt-2 text-[10px] text-gray-600">
                  {new Date(summary.created_at).toLocaleString()}
                </div>
              </motion.div>
            ))}
            {summaries.length > 0 && (
              <button
                onClick={onRefresh}
                className="text-xs text-[#00d4ff] hover:underline"
              >
                Refresh
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
