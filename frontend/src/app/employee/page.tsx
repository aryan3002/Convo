"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Calendar,
  Clock,
  User,
  Check,
  CheckCircle,
  AlertCircle,
  Play,
  Timer,
  XCircle,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Send,
  CalendarPlus,
  Loader2,
  Phone,
  FileText,
  Sparkles,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// Types
type Stylist = {
  id: number;
  name: string;
};

type ScheduleBooking = {
  id: string;
  service_name: string;
  secondary_service_name?: string | null;
  customer_name: string | null;
  customer_phone: string | null;
  start_time: string;
  end_time: string;
  start_at_utc: string;
  end_at_utc: string;
  appointment_status: string;
  acknowledged: boolean;
  internal_notes: string | null;
};

type ScheduleResponse = {
  stylist_id: number;
  stylist_name: string;
  date: string;
  bookings: ScheduleBooking[];
};

type TimeOffRequest = {
  id: number;
  stylist_id: number;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  reviewer: string | null;
};

// Status badge colors
const STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  SCHEDULED: { bg: "bg-blue-500/20", text: "text-blue-400", border: "border-blue-500/30" },
  IN_PROGRESS: { bg: "bg-green-500/20", text: "text-green-400", border: "border-green-500/30" },
  RUNNING_LATE: { bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/30" },
  COMPLETED: { bg: "bg-emerald-500/20", text: "text-emerald-400", border: "border-emerald-500/30" },
  NO_SHOW: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/30" },
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  SCHEDULED: <Clock className="w-3.5 h-3.5" />,
  IN_PROGRESS: <Play className="w-3.5 h-3.5" />,
  RUNNING_LATE: <Timer className="w-3.5 h-3.5" />,
  COMPLETED: <CheckCircle className="w-3.5 h-3.5" />,
  NO_SHOW: <XCircle className="w-3.5 h-3.5" />,
};

const TIME_OFF_STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  PENDING: { bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/30" },
  APPROVED: { bg: "bg-emerald-500/20", text: "text-emerald-400", border: "border-emerald-500/30" },
  REJECTED: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/30" },
};

export default function EmployeePage() {
  // Auth state
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [stylistId, setStylistId] = useState<number | null>(null);
  const [stylistName, setStylistName] = useState<string>("");

  // Login form state
  const [stylists, setStylists] = useState<Stylist[]>([]);
  const [selectedStylistId, setSelectedStylistId] = useState<number | null>(null);
  const [pin, setPin] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // Schedule state
  const [scheduleDate, setScheduleDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);

  // Booking actions state
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [editingNotesId, setEditingNotesId] = useState<string | null>(null);
  const [notesValue, setNotesValue] = useState("");

  // Time off state
  const [timeOffRequests, setTimeOffRequests] = useState<TimeOffRequest[]>([]);
  const [timeOffLoading, setTimeOffLoading] = useState(false);
  const [showTimeOffForm, setShowTimeOffForm] = useState(false);
  const [timeOffStartDate, setTimeOffStartDate] = useState("");
  const [timeOffEndDate, setTimeOffEndDate] = useState("");
  const [timeOffReason, setTimeOffReason] = useState("");
  const [timeOffSubmitting, setTimeOffSubmitting] = useState(false);

  // Restore session from localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedToken = localStorage.getItem("employee_token");
      const savedId = localStorage.getItem("employee_stylist_id");
      const savedName = localStorage.getItem("employee_stylist_name");
      if (savedToken && savedId) {
        setToken(savedToken);
        setStylistId(parseInt(savedId));
        setStylistName(savedName || "");
        setIsLoggedIn(true);
      }
    }
  }, []);

  // Fetch stylists for login
  useEffect(() => {
    if (!isLoggedIn) {
      fetchStylists();
    }
  }, [isLoggedIn]);

  // Fetch schedule when logged in or date changes
  useEffect(() => {
    if (isLoggedIn && token) {
      fetchSchedule();
    }
  }, [isLoggedIn, token, scheduleDate]);

  // Fetch time off when logged in
  useEffect(() => {
    if (isLoggedIn && token) {
      fetchTimeOffRequests();
    }
  }, [isLoggedIn, token]);

  async function fetchStylists() {
    try {
      const res = await fetch(`${API_BASE}/stylists-for-login`);
      if (res.ok) {
        const data: Stylist[] = await res.json();
        setStylists(data);
        if (data.length > 0) {
          setSelectedStylistId(data[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch stylists:", err);
    }
  }

  async function handleLogin() {
    if (!selectedStylistId || !pin.trim()) {
      setLoginError("Please select your name and enter your PIN");
      return;
    }
    setLoginLoading(true);
    setLoginError("");
    try {
      const res = await fetch(`${API_BASE}/employee/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stylist_id: selectedStylistId, pin }),
      });
      if (!res.ok) {
        const data = await res.json();
        setLoginError(data.detail || "Login failed");
        return;
      }
      const data = await res.json();
      setToken(data.token);
      setStylistId(data.stylist_id);
      setStylistName(data.stylist_name);
      setIsLoggedIn(true);
      // Save to localStorage
      localStorage.setItem("employee_token", data.token);
      localStorage.setItem("employee_stylist_id", data.stylist_id.toString());
      localStorage.setItem("employee_stylist_name", data.stylist_name);
      setPin("");
    } catch (err) {
      setLoginError("Connection error. Please try again.");
    } finally {
      setLoginLoading(false);
    }
  }

  function handleLogout() {
    setIsLoggedIn(false);
    setToken(null);
    setStylistId(null);
    setStylistName("");
    setSchedule(null);
    setTimeOffRequests([]);
    localStorage.removeItem("employee_token");
    localStorage.removeItem("employee_stylist_id");
    localStorage.removeItem("employee_stylist_name");
  }

  async function fetchSchedule() {
    setScheduleLoading(true);
    try {
      const res = await fetch(`${API_BASE}/employee/schedule?date_str=${scheduleDate}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: ScheduleResponse = await res.json();
        setSchedule(data);
      } else if (res.status === 401) {
        handleLogout();
      }
    } catch (err) {
      console.error("Failed to fetch schedule:", err);
    } finally {
      setScheduleLoading(false);
    }
  }

  async function fetchTimeOffRequests() {
    setTimeOffLoading(true);
    try {
      const res = await fetch(`${API_BASE}/employee/time-off`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: TimeOffRequest[] = await res.json();
        setTimeOffRequests(data);
      }
    } catch (err) {
      console.error("Failed to fetch time-off requests:", err);
    } finally {
      setTimeOffLoading(false);
    }
  }

  async function acknowledgeBooking(bookingId: string) {
    setActionLoading(bookingId);
    try {
      const res = await fetch(`${API_BASE}/employee/acknowledge`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ booking_id: bookingId }),
      });
      if (res.ok) {
        fetchSchedule();
      }
    } catch (err) {
      console.error("Failed to acknowledge booking:", err);
    } finally {
      setActionLoading(null);
    }
  }

  async function updateStatus(bookingId: string, status: string) {
    setActionLoading(bookingId);
    try {
      const res = await fetch(`${API_BASE}/employee/status`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ booking_id: bookingId, status }),
      });
      if (res.ok) {
        fetchSchedule();
      }
    } catch (err) {
      console.error("Failed to update status:", err);
    } finally {
      setActionLoading(null);
    }
  }

  async function saveNotes(bookingId: string) {
    setActionLoading(bookingId);
    try {
      const res = await fetch(`${API_BASE}/employee/notes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ booking_id: bookingId, notes: notesValue }),
      });
      if (res.ok) {
        fetchSchedule();
        setEditingNotesId(null);
        setNotesValue("");
      }
    } catch (err) {
      console.error("Failed to save notes:", err);
    } finally {
      setActionLoading(null);
    }
  }

  async function submitTimeOffRequest() {
    if (!timeOffStartDate || !timeOffEndDate) {
      return;
    }
    setTimeOffSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/employee/time-off`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          start_date: timeOffStartDate,
          end_date: timeOffEndDate,
          reason: timeOffReason || null,
        }),
      });
      if (res.ok) {
        fetchTimeOffRequests();
        setShowTimeOffForm(false);
        setTimeOffStartDate("");
        setTimeOffEndDate("");
        setTimeOffReason("");
      }
    } catch (err) {
      console.error("Failed to submit time-off request:", err);
    } finally {
      setTimeOffSubmitting(false);
    }
  }

  function changeDate(delta: number) {
    const date = new Date(scheduleDate);
    date.setDate(date.getDate() + delta);
    setScheduleDate(date.toISOString().split("T")[0]);
  }

  function formatDateDisplay(dateStr: string) {
    const date = new Date(dateStr + "T12:00:00");
    const today = new Date();
    const todayStr = today.toISOString().split("T")[0];
    if (dateStr === todayStr) {
      return "Today";
    }
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (dateStr === tomorrow.toISOString().split("T")[0]) {
      return "Tomorrow";
    }
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  }

  // ────────────────────────────────────────────────────────────────
  // Login Screen
  // ────────────────────────────────────────────────────────────────
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4 relative overflow-hidden">
        {/* Animated Background Gradient */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[200%] h-[100%] opacity-30">
            <div className="absolute inset-0 bg-gradient-to-b from-[#00d4ff]/20 via-transparent to-transparent" />
          </div>
          <div className="absolute -top-40 -left-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
          <div className="absolute -bottom-40 -right-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
        </div>
        {/* Grid Background */}
        <div
          className="fixed inset-0 pointer-events-none opacity-30"
          style={{
            backgroundImage:
              "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
            maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
            WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
          }}
        />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-sm"
        >
          <div className="glass-strong rounded-3xl p-8 border border-white/10 shadow-neon">
            <div className="text-center mb-8">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring" }}
                className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#00d4ff]/20 to-[#00d4ff]/5 border border-[#00d4ff]/30 mb-4"
              >
                <Sparkles className="w-8 h-8 text-[#00d4ff]" />
              </motion.div>
              <h1 className="text-2xl font-bold text-white mb-2">Employee Portal</h1>
              <p className="text-sm text-gray-400">Sign in to view your schedule</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs text-gray-400 mb-2">Select Your Name</label>
                <select
                  value={selectedStylistId || ""}
                  onChange={(e) => setSelectedStylistId(Number(e.target.value))}
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white focus:outline-none focus:border-[#00d4ff]/50 focus:ring-1 focus:ring-[#00d4ff]/30 transition-all"
                >
                  <option value="" disabled className="bg-[#0a0a0f]">
                    Select...
                  </option>
                  {stylists.map((s) => (
                    <option key={s.id} value={s.id} className="bg-[#0a0a0f]">
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-2">PIN</label>
                <input
                  type="password"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                  placeholder="Enter your PIN"
                  maxLength={8}
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 focus:ring-1 focus:ring-[#00d4ff]/30 transition-all text-center text-2xl tracking-[0.5em]"
                />
              </div>

              {loginError && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
                >
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{loginError}</span>
                </motion.div>
              )}

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleLogin}
                disabled={loginLoading || !selectedStylistId || !pin}
                className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-[#00d4ff] to-[#00a8cc] text-black font-semibold hover:shadow-lg hover:shadow-[#00d4ff]/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loginLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  <>Sign In</>
                )}
              </motion.button>
            </div>

            {stylists.length === 0 && (
              <p className="text-center text-xs text-gray-500 mt-6">
                No employees have PINs set up yet. Contact your manager.
              </p>
            )}
          </div>
        </motion.div>
      </div>
    );
  }

  // ────────────────────────────────────────────────────────────────
  // Main Dashboard
  // ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0f] relative">
      {/* Animated Background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[200%] h-[100%] opacity-30">
          <div className="absolute inset-0 bg-gradient-to-b from-[#00d4ff]/20 via-transparent to-transparent" />
        </div>
        <div className="absolute -top-40 -left-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-80 h-80 bg-[#00d4ff]/10 rounded-full blur-[120px]" />
      </div>
      {/* Grid Background */}
      <div
        className="fixed inset-0 pointer-events-none -z-10 opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
        }}
      />

      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-white/5">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff]/20 to-[#00d4ff]/5 border border-[#00d4ff]/30 flex items-center justify-center">
              <User className="w-5 h-5 text-[#00d4ff]" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">{stylistName}</h1>
              <p className="text-xs text-gray-400">Employee Portal</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-6 relative z-10">
        {/* Date Navigation */}
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => changeDate(-1)}
            className="p-2 rounded-xl hover:bg-white/5 text-gray-400 hover:text-white transition-all"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-white/5 border border-white/10">
            <Calendar className="w-5 h-5 text-[#00d4ff]" />
            <span className="text-white font-medium">{formatDateDisplay(scheduleDate)}</span>
            <input
              type="date"
              value={scheduleDate}
              onChange={(e) => setScheduleDate(e.target.value)}
              className="absolute opacity-0 w-0 h-0"
              id="date-picker"
            />
          </div>
          <button
            onClick={() => changeDate(1)}
            className="p-2 rounded-xl hover:bg-white/5 text-gray-400 hover:text-white transition-all"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>

        {/* Schedule Section */}
        <section className="glass-strong rounded-2xl border border-white/10 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-[#00d4ff]" />
              Today's Schedule
            </h2>
            {scheduleLoading && <Loader2 className="w-5 h-5 text-[#00d4ff] animate-spin" />}
          </div>

          {!scheduleLoading && schedule?.bookings.length === 0 && (
            <div className="text-center py-12">
              <Calendar className="w-12 h-12 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No appointments scheduled for this day</p>
            </div>
          )}

          <div className="space-y-4">
            <AnimatePresence mode="popLayout">
              {schedule?.bookings.map((booking, index) => {
                const statusColors = STATUS_COLORS[booking.appointment_status] || STATUS_COLORS.SCHEDULED;
                const isLoading = actionLoading === booking.id;

                return (
                  <motion.div
                    key={booking.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ delay: index * 0.05 }}
                    className="glass rounded-xl p-4 border border-white/5 hover:border-white/10 transition-all"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                      {/* Time Column */}
                      <div className="flex-shrink-0 text-center sm:text-left">
                        <div className="text-lg font-bold text-white">{booking.start_time}</div>
                        <div className="text-xs text-gray-500">to {booking.end_time}</div>
                      </div>

                      {/* Details Column */}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <h3 className="text-white font-medium">
                            {booking.service_name}
                            {booking.secondary_service_name && (
                              <span className="text-gray-400"> + {booking.secondary_service_name}</span>
                            )}
                          </h3>
                          <span
                            className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full ${statusColors.bg} ${statusColors.text} border ${statusColors.border}`}
                          >
                            {STATUS_ICONS[booking.appointment_status]}
                            {booking.appointment_status.replace("_", " ")}
                          </span>
                          {booking.acknowledged && (
                            <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                              <Check className="w-3 h-3" />
                              Acknowledged
                            </span>
                          )}
                        </div>

                        <div className="flex flex-wrap items-center gap-3 text-sm text-gray-400 mb-3">
                          <span className="flex items-center gap-1">
                            <User className="w-4 h-4" />
                            {booking.customer_name || "Guest"}
                          </span>
                          {booking.customer_phone && (
                            <span className="flex items-center gap-1">
                              <Phone className="w-4 h-4" />
                              {booking.customer_phone}
                            </span>
                          )}
                        </div>

                        {/* Internal Notes */}
                        {editingNotesId === booking.id ? (
                          <div className="flex items-center gap-2 mb-3">
                            <input
                              type="text"
                              value={notesValue}
                              onChange={(e) => setNotesValue(e.target.value)}
                              placeholder="Add notes..."
                              className="flex-1 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50"
                            />
                            <button
                              onClick={() => saveNotes(booking.id)}
                              disabled={isLoading}
                              className="p-2 rounded-lg bg-[#00d4ff]/20 text-[#00d4ff] hover:bg-[#00d4ff]/30 transition-all disabled:opacity-50"
                            >
                              {isLoading ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Send className="w-4 h-4" />
                              )}
                            </button>
                            <button
                              onClick={() => {
                                setEditingNotesId(null);
                                setNotesValue("");
                              }}
                              className="p-2 rounded-lg hover:bg-white/5 text-gray-400"
                            >
                              <XCircle className="w-4 h-4" />
                            </button>
                          </div>
                        ) : booking.internal_notes ? (
                          <div
                            onClick={() => {
                              setEditingNotesId(booking.id);
                              setNotesValue(booking.internal_notes || "");
                            }}
                            className="flex items-start gap-2 text-sm text-gray-400 bg-white/5 rounded-lg px-3 py-2 mb-3 cursor-pointer hover:bg-white/10 transition-all"
                          >
                            <FileText className="w-4 h-4 flex-shrink-0 mt-0.5" />
                            <span className="flex-1">{booking.internal_notes}</span>
                            <Edit3 className="w-4 h-4 flex-shrink-0" />
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              setEditingNotesId(booking.id);
                              setNotesValue("");
                            }}
                            className="text-xs text-gray-500 hover:text-gray-300 mb-3 flex items-center gap-1"
                          >
                            <Edit3 className="w-3 h-3" />
                            Add notes
                          </button>
                        )}

                        {/* Actions */}
                        <div className="flex flex-wrap items-center gap-2">
                          {!booking.acknowledged && (
                            <button
                              onClick={() => acknowledgeBooking(booking.id)}
                              disabled={isLoading}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all disabled:opacity-50"
                            >
                              {isLoading ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Check className="w-3.5 h-3.5" />
                              )}
                              Acknowledge
                            </button>
                          )}

                          {/* Status buttons */}
                          {booking.appointment_status !== "COMPLETED" &&
                            booking.appointment_status !== "NO_SHOW" && (
                              <div className="flex items-center gap-1">
                                {booking.appointment_status === "SCHEDULED" && (
                                  <button
                                    onClick={() => updateStatus(booking.id, "IN_PROGRESS")}
                                    disabled={isLoading}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30 transition-all disabled:opacity-50"
                                  >
                                    <Play className="w-3.5 h-3.5" />
                                    Start
                                  </button>
                                )}
                                {booking.appointment_status === "IN_PROGRESS" && (
                                  <>
                                    <button
                                      onClick={() => updateStatus(booking.id, "RUNNING_LATE")}
                                      disabled={isLoading}
                                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 transition-all disabled:opacity-50"
                                    >
                                      <Timer className="w-3.5 h-3.5" />
                                      Running Late
                                    </button>
                                    <button
                                      onClick={() => updateStatus(booking.id, "COMPLETED")}
                                      disabled={isLoading}
                                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all disabled:opacity-50"
                                    >
                                      <CheckCircle className="w-3.5 h-3.5" />
                                      Complete
                                    </button>
                                  </>
                                )}
                                {booking.appointment_status === "RUNNING_LATE" && (
                                  <button
                                    onClick={() => updateStatus(booking.id, "COMPLETED")}
                                    disabled={isLoading}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all disabled:opacity-50"
                                  >
                                    <CheckCircle className="w-3.5 h-3.5" />
                                    Complete
                                  </button>
                                )}
                                <button
                                  onClick={() => updateStatus(booking.id, "NO_SHOW")}
                                  disabled={isLoading}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all disabled:opacity-50"
                                >
                                  <XCircle className="w-3.5 h-3.5" />
                                  No-Show
                                </button>
                              </div>
                            )}
                        </div>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        </section>

        {/* Time Off Section */}
        <section className="glass-strong rounded-2xl border border-white/10 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <CalendarPlus className="w-5 h-5 text-[#00d4ff]" />
              Time Off Requests
            </h2>
            <button
              onClick={() => setShowTimeOffForm(!showTimeOffForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#00d4ff]/20 text-[#00d4ff] border border-[#00d4ff]/30 hover:bg-[#00d4ff]/30 transition-all"
            >
              <CalendarPlus className="w-3.5 h-3.5" />
              Request Time Off
            </button>
          </div>

          {/* New Request Form */}
          <AnimatePresence>
            {showTimeOffForm && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="glass rounded-xl p-4 mb-4 border border-white/5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">Start Date</label>
                      <input
                        type="date"
                        value={timeOffStartDate}
                        onChange={(e) => setTimeOffStartDate(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-[#00d4ff]/50"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">End Date</label>
                      <input
                        type="date"
                        value={timeOffEndDate}
                        onChange={(e) => setTimeOffEndDate(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white focus:outline-none focus:border-[#00d4ff]/50"
                      />
                    </div>
                  </div>
                  <div className="mb-4">
                    <label className="block text-xs text-gray-400 mb-1">Reason (optional)</label>
                    <input
                      type="text"
                      value={timeOffReason}
                      onChange={(e) => setTimeOffReason(e.target.value)}
                      placeholder="e.g., Vacation, Personal day"
                      className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowTimeOffForm(false)}
                      className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={submitTimeOffRequest}
                      disabled={timeOffSubmitting || !timeOffStartDate || !timeOffEndDate}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-[#00d4ff]/20 text-[#00d4ff] border border-[#00d4ff]/30 hover:bg-[#00d4ff]/30 transition-all disabled:opacity-50"
                    >
                      {timeOffSubmitting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                      Submit Request
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Requests List */}
          {timeOffLoading ? (
            <div className="text-center py-8">
              <Loader2 className="w-6 h-6 text-[#00d4ff] animate-spin mx-auto" />
            </div>
          ) : timeOffRequests.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <p>No time off requests yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {timeOffRequests.map((request) => {
                const statusColors =
                  TIME_OFF_STATUS_COLORS[request.status] || TIME_OFF_STATUS_COLORS.PENDING;
                return (
                  <div
                    key={request.id}
                    className="glass rounded-xl p-4 border border-white/5 hover:border-white/10 transition-all"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white font-medium">
                            {new Date(request.start_date).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                            })}
                            {request.start_date !== request.end_date && (
                              <>
                                {" "}
                                -{" "}
                                {new Date(request.end_date).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                })}
                              </>
                            )}
                          </span>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full ${statusColors.bg} ${statusColors.text} border ${statusColors.border}`}
                          >
                            {request.status}
                          </span>
                        </div>
                        {request.reason && (
                          <p className="text-sm text-gray-400">{request.reason}</p>
                        )}
                        {request.reviewed_at && (
                          <p className="text-xs text-gray-500 mt-1">
                            Reviewed by {request.reviewer || "Owner"} on{" "}
                            {new Date(request.reviewed_at).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
