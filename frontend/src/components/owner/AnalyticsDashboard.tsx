"use client";

/**
 * AnalyticsDashboard - Full analytics tab with KPIs and AI insights
 * Extracted from legacy /owner/page.tsx
 */

import React from "react";
import { motion } from "framer-motion";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Scissors,
  Users,
  Sun,
  Sunset,
  Moon,
  Brain,
  RefreshCw,
  Sparkles,
  AlertCircle,
  Lightbulb,
} from "lucide-react";
import type { AnalyticsSummary, AIInsights } from "@/lib/owner-types";
import { formatMoney } from "@/lib/owner-utils";

type AnalyticsRange = "7d" | "30d";

interface AnalyticsDashboardProps {
  range: AnalyticsRange;
  summary: AnalyticsSummary | null;
  loading: boolean;
  aiInsights: AIInsights | null;
  aiLoading: boolean;
  aiError: string | null;
  onChangeRange: (range: AnalyticsRange) => void;
  onFetchAiInsights: () => void;
}

export function AnalyticsDashboard({
  range,
  summary,
  loading,
  aiInsights,
  aiLoading,
  aiError,
  onChangeRange,
  onFetchAiInsights,
}: AnalyticsDashboardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl p-6 border border-white/5 space-y-6"
    >
      {/* Header with range selector */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-[#00d4ff]" />
          Analytics Dashboard
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => onChangeRange("7d")}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
              range === "7d"
                ? "btn-neon"
                : "glass border border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            7 Days
          </button>
          <button
            onClick={() => onChangeRange("30d")}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
              range === "30d"
                ? "btn-neon"
                : "glass border border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            30 Days
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="spinner w-6 h-6" />
          <span className="ml-3 text-sm text-gray-400">Loading analytics...</span>
        </div>
      ) : summary ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 gap-3">
            {/* Total Bookings */}
            <div className="glass rounded-xl p-4 border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">Total Bookings</span>
                {summary.bookings_delta !== 0 && (
                  <span
                    className={`text-xs flex items-center gap-0.5 ${
                      summary.bookings_delta > 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {summary.bookings_delta > 0 ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : (
                      <TrendingDown className="w-3 h-3" />
                    )}
                    {Math.abs(summary.bookings_delta).toFixed(1)}%
                  </span>
                )}
              </div>
              <p className="text-2xl font-bold text-white">{summary.bookings_total}</p>
              <p className="text-[10px] text-gray-500 mt-1">
                vs {summary.prev_bookings_total} prev
              </p>
            </div>

            {/* Revenue */}
            <div className="glass rounded-xl p-4 border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">Est. Revenue</span>
                <DollarSign className="w-3 h-3 text-emerald-400" />
              </div>
              <p className="text-2xl font-bold text-emerald-400">
                {formatMoney(summary.estimated_revenue_cents)}
              </p>
              <p className="text-[10px] text-gray-500 mt-1">
                from {summary.completed_count} completed
              </p>
            </div>

            {/* No-Show Rate */}
            <div className="glass rounded-xl p-4 border border-white/5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">No-Show Rate</span>
                {summary.no_show_rate_delta !== 0 && (
                  <span
                    className={`text-xs flex items-center gap-0.5 ${
                      summary.no_show_rate_delta < 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {summary.no_show_rate_delta < 0 ? (
                      <TrendingDown className="w-3 h-3" />
                    ) : (
                      <TrendingUp className="w-3 h-3" />
                    )}
                    {Math.abs(summary.no_show_rate_delta).toFixed(1)}%
                  </span>
                )}
              </div>
              <p
                className={`text-2xl font-bold ${
                  summary.no_show_rate > 15 ? "text-red-400" : "text-white"
                }`}
              >
                {summary.no_show_rate.toFixed(1)}%
              </p>
              <p className="text-[10px] text-gray-500 mt-1">
                {summary.no_show_count} no-shows
              </p>
            </div>

            {/* Time Distribution */}
            <div className="glass rounded-xl p-4 border border-white/5">
              <span className="text-xs text-gray-500 mb-2 block">Peak Hours</span>
              <div className="flex gap-2 text-[10px]">
                <div className="flex items-center gap-1">
                  <Sun className="w-3 h-3 text-yellow-400" />
                  <span className="text-gray-400">
                    {summary.time_distribution.morning}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Sunset className="w-3 h-3 text-orange-400" />
                  <span className="text-gray-400">
                    {summary.time_distribution.afternoon}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Moon className="w-3 h-3 text-purple-400" />
                  <span className="text-gray-400">
                    {summary.time_distribution.evening}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Service Breakdown */}
          {summary.by_service.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-white mb-3 flex items-center gap-2">
                <Scissors className="w-3 h-3 text-[#00d4ff]" />
                By Service
              </h3>
              <div className="space-y-2">
                {summary.by_service.slice(0, 5).map((svc) => (
                  <div
                    key={svc.service_id}
                    className="glass rounded-lg p-3 border border-white/5"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-white font-medium">
                        {svc.service_name}
                      </span>
                      <span className="text-xs text-gray-400">
                        {svc.bookings} bookings
                      </span>
                    </div>
                    <div className="flex gap-4 mt-1 text-[10px] text-gray-500">
                      <span>{svc.completed} completed</span>
                      <span className={svc.no_show_rate > 20 ? "text-red-400" : ""}>
                        {svc.no_shows} no-shows
                      </span>
                      <span className="text-emerald-400">
                        {formatMoney(svc.estimated_revenue_cents)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stylist Breakdown */}
          {summary.by_stylist.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-white mb-3 flex items-center gap-2">
                <Users className="w-3 h-3 text-[#00d4ff]" />
                By Stylist
              </h3>
              <div className="space-y-2">
                {summary.by_stylist.map((sty) => (
                  <div
                    key={sty.stylist_id}
                    className="glass rounded-lg p-3 border border-white/5"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-white font-medium">
                        {sty.stylist_name}
                      </span>
                      <span className="text-xs text-gray-400">
                        {sty.bookings} bookings
                      </span>
                    </div>
                    <div className="flex gap-4 mt-1 text-[10px] text-gray-500">
                      <span>{sty.completed} completed</span>
                      <span>{sty.no_shows} no-shows</span>
                      <span
                        className={
                          sty.acknowledgement_rate >= 80
                            ? "text-emerald-400"
                            : "text-yellow-400"
                        }
                      >
                        {sty.acknowledgement_rate.toFixed(0)}% ack rate
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Insights Section */}
          <div className="border-t border-white/5 pt-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-medium text-white flex items-center gap-2">
                <Brain className="w-4 h-4 text-purple-400" />
                AI Insights
              </h3>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={onFetchAiInsights}
                disabled={aiLoading}
                className="px-3 py-1.5 rounded-full text-xs font-medium bg-purple-500/20 border border-purple-500/30 text-purple-300 hover:bg-purple-500/30 transition-all flex items-center gap-1.5 disabled:opacity-50"
              >
                {aiLoading ? (
                  <>
                    <RefreshCw className="w-3 h-3 animate-spin" /> Analyzing...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3 h-3" /> Generate Insights
                  </>
                )}
              </motion.button>
            </div>

            {aiError && (
              <div className="glass rounded-lg p-3 border border-red-500/30 text-xs text-red-400 flex items-center gap-2">
                <AlertCircle className="w-3 h-3" />
                {aiError}
              </div>
            )}

            {aiInsights && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-4"
              >
                {/* Executive Summary */}
                {aiInsights.executive_summary.length > 0 && (
                  <div className="glass rounded-lg p-4 border border-purple-500/20">
                    <h4 className="text-[11px] font-semibold text-purple-300 mb-2">
                      Summary
                    </h4>
                    <ul className="text-xs text-gray-300 space-y-1">
                      {aiInsights.executive_summary.map((s, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-purple-400 mt-0.5">•</span>
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Anomalies */}
                {aiInsights.anomalies.length > 0 && (
                  <div className="glass rounded-lg p-4 border border-yellow-500/20">
                    <h4 className="text-[11px] font-semibold text-yellow-300 mb-2 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3" /> Anomalies Detected
                    </h4>
                    <div className="space-y-2">
                      {aiInsights.anomalies.map((a, i) => (
                        <div key={i} className="text-xs text-gray-300">
                          <span
                            className={
                              a.direction === "increase"
                                ? "text-emerald-400"
                                : "text-red-400"
                            }
                          >
                            {a.direction === "increase" ? "↑" : "↓"} {a.metric}
                          </span>
                          : {a.value}
                          {a.likely_causes.length > 0 && (
                            <span className="text-gray-500 ml-1">
                              (Possible: {a.likely_causes.join(", ")})
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Insights */}
                {aiInsights.insights.length > 0 && (
                  <div className="space-y-2">
                    {aiInsights.insights.map((ins, i) => (
                      <div
                        key={i}
                        className="glass rounded-lg p-3 border border-white/5"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Lightbulb className="w-3 h-3 text-yellow-400" />
                          <span className="text-xs font-medium text-white">
                            {ins.title}
                          </span>
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                              ins.confidence === "high"
                                ? "bg-emerald-500/20 text-emerald-400"
                                : ins.confidence === "medium"
                                ? "bg-yellow-500/20 text-yellow-400"
                                : "bg-gray-500/20 text-gray-400"
                            }`}
                          >
                            {ins.confidence}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-400">{ins.explanation}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Recommendations */}
                {aiInsights.recommendations.length > 0 && (
                  <div>
                    <h4 className="text-[11px] font-semibold text-emerald-300 mb-2">
                      Recommendations
                    </h4>
                    <div className="space-y-2">
                      {aiInsights.recommendations.map((rec, i) => (
                        <div
                          key={i}
                          className="glass rounded-lg p-3 border border-emerald-500/20"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <p className="text-xs text-white">{rec.action}</p>
                              <p className="text-[10px] text-gray-500 mt-1">
                                Expected: {rec.expected_impact}
                              </p>
                            </div>
                            <span
                              className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                                rec.risk === "low"
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : rec.risk === "medium"
                                  ? "bg-yellow-500/20 text-yellow-400"
                                  : "bg-red-500/20 text-red-400"
                              }`}
                            >
                              {rec.risk} risk
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Questions */}
                {aiInsights.questions_for_owner.length > 0 && (
                  <div className="glass rounded-lg p-3 border border-white/5">
                    <h4 className="text-[11px] font-semibold text-gray-400 mb-2">
                      Questions to Consider
                    </h4>
                    <ul className="text-xs text-gray-500 space-y-1">
                      {aiInsights.questions_for_owner.map((q, i) => (
                        <li key={i}>• {q}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </motion.div>
            )}

            {!aiInsights && !aiLoading && !aiError && (
              <p className="text-xs text-gray-500 text-center py-4">
                Click "Generate Insights" to get AI-powered analysis of your business
                data.
              </p>
            )}
          </div>
        </>
      ) : (
        <p className="text-xs text-gray-500 text-center py-8">
          No data available for the selected period.
        </p>
      )}
    </motion.div>
  );
}
