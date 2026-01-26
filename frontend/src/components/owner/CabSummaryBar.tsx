"use client";

/**
 * CabSummaryBar - Top summary bar for Cab Owner Dashboard
 * 
 * Displays computed business metrics:
 * - Total Rides
 * - Confirmed Revenue (from COMPLETED rides)
 * - Upcoming Revenue (from CONFIRMED rides with future pickup)
 * - Average Ride Price
 * - Acceptance Rate
 * - Cancellation Rate
 * 
 * Supports 7-day and 30-day time range toggle.
 */

import React, { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Car,
  DollarSign,
  TrendingUp,
  Calendar,
  CheckCircle,
  XCircle,
  BarChart3,
  Clock,
  Loader2,
  Info,
} from "lucide-react";
import { apiFetch, isApiError } from "@/lib/api";

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

interface SummaryData {
  total_rides: number;
  confirmed_revenue: number;
  upcoming_revenue: number;
  avg_ride_price: number;
  acceptance_rate: number;
  cancellation_rate: number;
}

interface SummaryResponse {
  data: SummaryData;
  status: string;
  range_days: number;
}

type RangeType = "7d" | "30d";

interface CabSummaryBarProps {
  slug: string;
  className?: string;
}

// ──────────────────────────────────────────────────────────
// Utility Functions
// ──────────────────────────────────────────────────────────

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatCurrencyPrecise(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercentage(value: number): string {
  return `${value.toFixed(1)}%`;
}

// ──────────────────────────────────────────────────────────
// Skeleton Component
// ──────────────────────────────────────────────────────────

function MetricSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-3 w-20 bg-white/10 rounded mb-2" />
      <div className="h-7 w-16 bg-white/10 rounded mb-1" />
      <div className="h-2 w-12 bg-white/5 rounded" />
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Metric Card Component
// ──────────────────────────────────────────────────────────

interface MetricCardProps {
  icon: React.ReactNode;
  title: string;
  value: string;
  subtitle?: string;
  color?: "default" | "green" | "blue" | "yellow" | "red";
  tooltip?: string;
  emphasized?: boolean;
  loading?: boolean;
}

function MetricCard({
  icon,
  title,
  value,
  subtitle,
  color = "default",
  tooltip,
  emphasized = false,
  loading = false,
}: MetricCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const colorClasses = {
    default: "text-white",
    green: "text-emerald-400",
    blue: "text-[#00d4ff]",
    yellow: "text-amber-400",
    red: "text-red-400",
  };

  const bgClasses = {
    default: "from-white/5 to-transparent",
    green: "from-emerald-500/10 to-transparent",
    blue: "from-[#00d4ff]/10 to-transparent",
    yellow: "from-amber-500/10 to-transparent",
    red: "from-red-500/10 to-transparent",
  };

  const iconBgClasses = {
    default: "bg-white/10",
    green: "bg-emerald-500/20",
    blue: "bg-[#00d4ff]/20",
    yellow: "bg-amber-500/20",
    red: "bg-red-500/20",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`
        relative flex-1 min-w-[140px] p-4 rounded-xl
        bg-gradient-to-br ${bgClasses[color]}
        border border-white/5 backdrop-blur-sm
        ${emphasized ? "ring-1 ring-[#00d4ff]/30" : ""}
        transition-all duration-200 hover:border-white/10
      `}
    >
      {/* Icon */}
      <div className={`w-8 h-8 ${iconBgClasses[color]} rounded-lg flex items-center justify-center mb-3`}>
        <span className={colorClasses[color]}>{icon}</span>
      </div>

      {/* Title with optional tooltip */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-xs text-gray-400 font-medium">{title}</span>
        {tooltip && (
          <div className="relative">
            <button
              onMouseEnter={() => setShowTooltip(true)}
              onMouseLeave={() => setShowTooltip(false)}
              onClick={() => setShowTooltip(!showTooltip)}
              className="text-gray-500 hover:text-gray-400 transition-colors"
            >
              <Info className="w-3 h-3" />
            </button>
            <AnimatePresence>
              {showTooltip && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 5 }}
                  className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 
                    px-3 py-2 rounded-lg bg-gray-900 border border-white/10
                    text-xs text-gray-300 whitespace-nowrap shadow-xl"
                >
                  {tooltip}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1">
                    <div className="w-2 h-2 bg-gray-900 border-r border-b border-white/10 rotate-45" />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* Value */}
      {loading ? (
        <MetricSkeleton />
      ) : (
        <>
          <p className={`text-xl font-bold ${colorClasses[color]} ${emphasized ? "text-2xl" : ""}`}>
            {value}
          </p>
          {subtitle && (
            <p className="text-[10px] text-gray-500 mt-0.5">{subtitle}</p>
          )}
        </>
      )}
    </motion.div>
  );
}

// ──────────────────────────────────────────────────────────
// Main Component
// ──────────────────────────────────────────────────────────

export function CabSummaryBar({ slug, className = "" }: CabSummaryBarProps) {
  const [range, setRange] = useState<RangeType>("7d");
  const [data, setData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response: SummaryResponse = await apiFetch(
        `/s/${slug}/owner/cab/summary?range=${range}`
      );
      setData(response.data);
    } catch (err) {
      console.error("Error fetching cab summary:", err);
      if (isApiError(err)) {
        setError(err.detail?.toString() || "Failed to load summary");
      } else {
        setError("Failed to load summary");
      }
      // Set empty data on error so UI still shows
      setData({
        total_rides: 0,
        confirmed_revenue: 0,
        upcoming_revenue: 0,
        avg_ride_price: 0,
        acceptance_rate: 0,
        cancellation_rate: 0,
      });
    } finally {
      setLoading(false);
    }
  }, [slug, range]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const rangeLabel = range === "7d" ? "Last 7 days" : "Last 30 days";

  return (
    <div className={`mb-6 ${className}`}>
      {/* Header with range toggle */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[#00d4ff]" />
          <h2 className="text-sm font-semibold text-white">Business Overview</h2>
          {loading && (
            <Loader2 className="w-4 h-4 text-[#00d4ff] animate-spin" />
          )}
        </div>

        {/* Range Toggle */}
        <div className="flex items-center gap-1 p-1 glass rounded-xl border border-white/10">
          <button
            onClick={() => setRange("7d")}
            disabled={loading}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              range === "7d"
                ? "bg-[#00d4ff] text-black"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            7 Days
          </button>
          <button
            onClick={() => setRange("30d")}
            disabled={loading}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              range === "30d"
                ? "bg-[#00d4ff] text-black"
                : "text-gray-400 hover:text-white hover:bg-white/5"
            }`}
          >
            30 Days
          </button>
        </div>
      </div>

      {/* Error Banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          icon={<Car className="w-4 h-4" />}
          title="Total Rides"
          value={data ? data.total_rides.toString() : "—"}
          subtitle={rangeLabel}
          color="blue"
          loading={loading}
        />

        <MetricCard
          icon={<DollarSign className="w-4 h-4" />}
          title="Confirmed Revenue"
          value={data ? formatCurrency(data.confirmed_revenue) : "—"}
          subtitle="Completed rides"
          color="green"
          emphasized
          tooltip="Revenue from completed rides"
          loading={loading}
        />

        <MetricCard
          icon={<Clock className="w-4 h-4" />}
          title="Upcoming Revenue"
          value={data ? formatCurrency(data.upcoming_revenue) : "—"}
          subtitle="Confirmed rides"
          color="yellow"
          tooltip="Expected revenue from confirmed future rides"
          loading={loading}
        />

        <MetricCard
          icon={<TrendingUp className="w-4 h-4" />}
          title="Avg Ride Price"
          value={data ? formatCurrencyPrecise(data.avg_ride_price) : "—"}
          subtitle="Per ride"
          color="default"
          loading={loading}
        />

        <MetricCard
          icon={<CheckCircle className="w-4 h-4" />}
          title="Acceptance Rate"
          value={data ? formatPercentage(data.acceptance_rate) : "—"}
          subtitle="Bookings accepted"
          color={data && data.acceptance_rate >= 80 ? "green" : data && data.acceptance_rate >= 50 ? "yellow" : "red"}
          tooltip="Percentage of bookings accepted"
          loading={loading}
        />

        <MetricCard
          icon={<XCircle className="w-4 h-4" />}
          title="Cancellation Rate"
          value={data ? formatPercentage(data.cancellation_rate) : "—"}
          subtitle="Bookings cancelled"
          color={data && data.cancellation_rate <= 10 ? "green" : data && data.cancellation_rate <= 25 ? "yellow" : "red"}
          tooltip="Percentage of bookings cancelled"
          loading={loading}
        />
      </div>
    </div>
  );
}

export default CabSummaryBar;
