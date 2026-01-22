"use client";

import React from "react";
import { motion } from "framer-motion";
import { Calendar, CheckCircle, XCircle } from "lucide-react";
import type { TimeOffRequestItem } from "@/hooks/useOwnerTimeOffRequests";
import type { OwnerStylist } from "@/lib/owner-types";

interface TimeOffApprovalCardProps {
  requests: TimeOffRequestItem[];
  stylists: OwnerStylist[];
  loading: boolean;
  reviewLoading: number | null;
  onRefresh: () => void;
  onApprove: (requestId: number) => void;
  onReject: (requestId: number) => void;
}

export function TimeOffApprovalCard({
  requests,
  stylists,
  loading,
  reviewLoading,
  onRefresh,
  onApprove,
  onReject,
}: TimeOffApprovalCardProps) {
  return (
    <div className="glass-card rounded-2xl p-4 border border-white/5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <Calendar className="w-4 h-4 text-amber-400" />
          Pending Time Off Requests
        </h3>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="text-xs text-gray-400 hover:text-[#00d4ff] transition-colors"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {loading && requests.length === 0 ? (
        <div className="text-xs text-gray-500 flex items-center gap-2">
          <div className="spinner w-4 h-4" />
          Loading...
        </div>
      ) : requests.length === 0 ? (
        <div className="text-xs text-gray-500 py-4 text-center">
          No pending requests
        </div>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto scrollbar-hide">
          {requests.map((request) => {
            const stylist = stylists.find((s) => s.id === request.stylist_id);
            return (
              <motion.div
                key={request.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass rounded-xl p-3 border border-amber-500/20"
              >
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <span className="text-sm font-medium text-white">
                      {stylist?.name || `Stylist #${request.stylist_id}`}
                    </span>
                    <span className="text-xs text-amber-400 ml-2 px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30">
                      Pending
                    </span>
                  </div>
                </div>
                <div className="text-xs text-gray-400 mb-2">
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {new Date(request.start_date).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                    {request.start_date !== request.end_date && (
                      <>
                        {" - "}
                        {new Date(request.end_date).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        })}
                      </>
                    )}
                  </span>
                  {request.reason && (
                    <p className="mt-1 text-gray-500 italic">{request.reason}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => onApprove(request.id)}
                    disabled={reviewLoading === request.id}
                    className="flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all flex items-center justify-center gap-1 disabled:opacity-50"
                  >
                    <CheckCircle className="w-3 h-3" />
                    Approve
                  </button>
                  <button
                    onClick={() => onReject(request.id)}
                    disabled={reviewLoading === request.id}
                    className="flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all flex items-center justify-center gap-1 disabled:opacity-50"
                  >
                    <XCircle className="w-3 h-3" />
                    Reject
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
