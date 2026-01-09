"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  Send,
  Sparkles,
  Calendar,
  Clock,
  User,
  Users,
  Scissors,
  Tag,
  Phone,
  Mail,
  ChevronDown,
  ChevronRight,
  X,
  Plus,
  Search,
  ArrowLeft,
  ArrowRight,
  Check,
  Pause,
  Play,
  Trash2,
  Gift,
  Percent,
  DollarSign,
  AlertCircle,
  Lock,
  Unlock,
  Shield,
  CheckCircle,
  XCircle,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  Brain,
  RefreshCw,
  Sun,
  Sunset,
  Moon,
} from "lucide-react";

type Role = "user" | "assistant" | "system";

type OwnerMessage = {
  id: string;
  role: Role;
  text: string;
};

type OwnerService = {
  id: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
  availability_rule?: string;
};

type OwnerPromo = {
  id: number;
  shop_id: number;
  type: string;
  trigger_point: string;
  service_id?: number | null;
  discount_type: string;
  discount_value?: number | null;
  constraints_json?: Record<string, any> | null;
  custom_copy?: string | null;
  start_at_utc?: string | null;
  end_at_utc?: string | null;
  active: boolean;
  priority: number;
};

type OwnerStylist = {
  id: number;
  name: string;
  work_start: string;
  work_end: string;
  active: boolean;
  specialties: string[];
  time_off_count: number;
};

type ScheduleBooking = {
  id: string;
  stylist_id: number;
  stylist_name: string;
  service_name: string;
  secondary_service_name?: string | null;
  customer_name: string | null;
  status: "HOLD" | "CONFIRMED" | "EXPIRED";
  preferred_style_text?: string | null;
  preferred_style_image_url?: string | null;
  start_time: string;
  end_time: string;
};

type ScheduleTimeOff = {
  id: number;
  stylist_id: number;
  stylist_name: string;
  start_time: string;
  end_time: string;
  reason?: string | null;
};

type OwnerSchedule = {
  date: string;
  stylists: OwnerStylist[];
  bookings: ScheduleBooking[];
  time_off: ScheduleTimeOff[];
};

type OwnerChatResponse = {
  reply: string;
  action?: { type: string; params?: Record<string, any> } | null;
  data?: {
    services?: OwnerService[];
    stylists?: OwnerStylist[];
    service?: OwnerService;
    schedule?: OwnerSchedule;
    promos?: OwnerPromo[];
    updated_service?: {
      id: number;
      name: string;
      price_cents: number;
    };
  } | null;
};

type CustomerProfile = {
  email: string | null;
  phone?: string | null;
  name: string | null;
  preferred_stylist: string | null;
  last_service: string | null;
  last_stylist: string | null;
  average_spend_cents: number;
  total_bookings: number;
  total_spend_cents: number;
  last_booking_at: string | null;
};

type CallSummary = {
  id: string;
  call_sid: string;
  customer_name: string | null;
  customer_phone: string;
  service: string | null;
  stylist: string | null;
  appointment_date: string | null;
  appointment_time: string | null;
  booking_status: "confirmed" | "not_confirmed" | "follow_up";
  key_notes: string | null;
  created_at: string;
};

type OwnerTimeOffEntry = {
  start_time: string;
  end_time: string;
  date: string;
  reason?: string | null;
};

type TimeOffRequestItem = {
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

type PromoDraft = {
  type: string | null;
  trigger_point: string | null;
  copy_mode: "custom" | "ai";
  custom_copy: string;
  discount_type: string | null;
  discount_value: string;
  min_spend: string;
  usage_limit: string;
  valid_days: number[];
  service_id: number | null;
  combo_secondary_service_id: number | null;
  start_at: string;
  end_at: string;
  active: boolean;
  priority: number;
  perk_description: string;
};

// Analytics Types
type ServiceAnalytics = {
  service_id: number;
  service_name: string;
  bookings: number;
  completed: number;
  no_shows: number;
  no_show_rate: number;
  estimated_revenue_cents: number;
};

type StylistAnalytics = {
  stylist_id: number;
  stylist_name: string;
  bookings: number;
  completed: number;
  no_shows: number;
  acknowledgement_rate: number;
};

type TimeOfDayDistribution = {
  morning: number;
  afternoon: number;
  evening: number;
};

type AnalyticsSummary = {
  range_days: number;
  start_date: string;
  end_date: string;
  bookings_total: number;
  completed_count: number;
  no_show_count: number;
  cancellation_count: number;
  no_show_rate: number;
  estimated_revenue_cents: number;
  by_service: ServiceAnalytics[];
  by_stylist: StylistAnalytics[];
  time_distribution: TimeOfDayDistribution;
  prev_bookings_total: number;
  bookings_delta: number;
  prev_no_show_rate: number;
  no_show_rate_delta: number;
};

type Anomaly = {
  metric: string;
  direction: "increase" | "decrease";
  value: string;
  likely_causes: string[];
  confidence: "low" | "medium" | "high";
};

type Insight = {
  title: string;
  explanation: string;
  supporting_data: string[];
  confidence: "low" | "medium" | "high";
};

type Recommendation = {
  action: string;
  expected_impact: string;
  risk: "low" | "medium" | "high";
  requires_owner_confirmation: boolean;
};

type AIInsights = {
  executive_summary: string[];
  anomalies: Anomaly[];
  insights: Insight[];
  recommendations: Recommendation[];
  questions_for_owner: string[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TZ_OFFSET =
  Number(process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES) || -new Date().getTimezoneOffset();
const SLOT_MINUTES = 30;
const ROW_HEIGHT = 60;

const PROMO_TYPES = [
  { value: "FIRST_USER_PROMO", label: "First-time customer" },
  { value: "DAILY_PROMO", label: "Daily offer" },
  { value: "SEASONAL_PROMO", label: "Seasonal campaign" },
  { value: "SERVICE_COMBO_PROMO", label: "Service combo" },
];

const PROMO_TRIGGERS = [
  { value: "AT_CHAT_START", label: "At chat start" },
  { value: "AFTER_EMAIL_CAPTURE", label: "After email capture" },
  { value: "AFTER_SERVICE_SELECTED", label: "After service selected" },
  { value: "AFTER_SLOT_SHOWN", label: "After slots shown" },
  { value: "AFTER_HOLD_CREATED", label: "After hold created" },
];

const PROMO_DISCOUNTS = [
  { value: "PERCENT", label: "Percent off" },
  { value: "FIXED", label: "Fixed amount off" },
];

const DAY_OPTIONS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function formatMoney(priceCents: number) {
  return (priceCents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

export default function OwnerPage() {
  const [messages, setMessages] = useState<OwnerMessage[]>([
    {
      id: uid(),
      role: "assistant",
      text: "Hi! I can help you manage services and stylists. What would you like to change?",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [services, setServices] = useState<OwnerService[]>([]);
  const [stylists, setStylists] = useState<OwnerStylist[]>([]);
  const [promos, setPromos] = useState<OwnerPromo[]>([]);
  const [rightView, setRightView] = useState<'services' | 'stylists' | 'promos' | 'analytics'>('services');
  const [schedule, setSchedule] = useState<OwnerSchedule | null>(null);
  const [scheduleDate, setScheduleDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<ScheduleBooking | null>(null);
  const [styleFilter, setStyleFilter] = useState("");
  const [timeOffOpenStylistId, setTimeOffOpenStylistId] = useState<number | null>(null);
  const [timeOffLoading, setTimeOffLoading] = useState(false);
  const [timeOffEntries, setTimeOffEntries] = useState<Record<number, OwnerTimeOffEntry[]>>({});
  const [customerLookupEmail, setCustomerLookupEmail] = useState("");
  const [customerLookupIdentity, setCustomerLookupIdentity] = useState(""); // Can be email or phone
  const [customerLookupLoading, setCustomerLookupLoading] = useState(false);
  const [customerLookupError, setCustomerLookupError] = useState("");
  const [customerProfile, setCustomerProfile] = useState<CustomerProfile | null>(null);
  const [suggestedChips, setSuggestedChips] = useState<string[]>([]);
  const [promoWizardOpen, setPromoWizardOpen] = useState(false);
  const [promoWizardStep, setPromoWizardStep] = useState(0);
  const [promoWizardError, setPromoWizardError] = useState("");
  const [promoSaving, setPromoSaving] = useState(false);
  const [promoActionOpenId, setPromoActionOpenId] = useState<number | null>(null);
  const [promoActionLoading, setPromoActionLoading] = useState(false);
  const [promoDraft, setPromoDraft] = useState<PromoDraft>({
    type: null,
    trigger_point: null,
    copy_mode: "ai",
    custom_copy: "",
    discount_type: null,
    discount_value: "",
    min_spend: "",
    usage_limit: "",
    valid_days: [],
    service_id: null,
    combo_secondary_service_id: null,
    start_at: "",
    end_at: "",
    active: true,
    priority: 0,
    perk_description: "",
  });
  const [serviceBookingCounts, setServiceBookingCounts] = useState<Record<number, number>>({});
  const [selectedServiceBookings, setSelectedServiceBookings] = useState<any[]>([]);
  const [serviceBookingsModalOpen, setServiceBookingsModalOpen] = useState(false);
  const [selectedServiceName, setSelectedServiceName] = useState("");
  const [serviceBookingsLoading, setServiceBookingsLoading] = useState(false);
  
  // Call Summaries - Internal owner feature
  const [callSummaries, setCallSummaries] = useState<CallSummary[]>([]);
  const [callSummariesLoading, setCallSummariesLoading] = useState(false);
  const [callSummariesExpanded, setCallSummariesExpanded] = useState(false);

  // PIN Management
  const [pinModalOpen, setPinModalOpen] = useState(false);
  const [pinStylistId, setPinStylistId] = useState<number | null>(null);
  const [pinStylistName, setPinStylistName] = useState("");
  const [pinValue, setPinValue] = useState("");
  const [pinLoading, setPinLoading] = useState(false);
  const [pinStatuses, setPinStatuses] = useState<Record<number, { has_pin: boolean; pin_set_at: string | null }>>({});

  // Time Off Requests (pending approval)
  const [pendingTimeOffRequests, setPendingTimeOffRequests] = useState<TimeOffRequestItem[]>([]);
  const [timeOffRequestsLoading, setTimeOffRequestsLoading] = useState(false);
  const [timeOffReviewLoading, setTimeOffReviewLoading] = useState<number | null>(null);

  // Analytics state
  const [analyticsRange, setAnalyticsRange] = useState<"7d" | "30d">("7d");
  const [analyticsSummary, setAnalyticsSummary] = useState<AnalyticsSummary | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [aiInsights, setAiInsights] = useState<AIInsights | null>(null);
  const [aiInsightsLoading, setAiInsightsLoading] = useState(false);
  const [aiInsightsError, setAiInsightsError] = useState("");

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function fetchServiceBookingCounts() {
    try {
      const res = await fetch(`${API_BASE}/services/booking-counts`);
      if (!res.ok) return;
      const data: { service_id: number; upcoming_bookings: number }[] = await res.json();
      const counts: Record<number, number> = {};
      data.forEach((item) => {
        counts[item.service_id] = item.upcoming_bookings;
      });
      setServiceBookingCounts(counts);
    } catch (err) {
      console.error("Failed to fetch booking counts:", err);
    }
  }

  async function fetchServiceBookings(serviceId: number, serviceName: string) {
    setServiceBookingsLoading(true);
    setSelectedServiceName(serviceName);
    setServiceBookingsModalOpen(true);
    try {
      const res = await fetch(`${API_BASE}/services/${serviceId}/bookings`);
      if (!res.ok) {
        setSelectedServiceBookings([]);
        return;
      }
      const data = await res.json();
      setSelectedServiceBookings(data);
    } catch (err) {
      console.error("Failed to fetch service bookings:", err);
      setSelectedServiceBookings([]);
    } finally {
      setServiceBookingsLoading(false);
    }
  }

  async function fetchCallSummaries() {
    setCallSummariesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/owner/call-summaries?limit=20`);
      if (!res.ok) {
        setCallSummaries([]);
        return;
      }
      const data: CallSummary[] = await res.json();
      setCallSummaries(data);
    } catch (err) {
      console.error("Failed to fetch call summaries:", err);
      setCallSummaries([]);
    } finally {
      setCallSummariesLoading(false);
    }
  }

  async function fetchPinStatus(stylistId: number) {
    try {
      const res = await fetch(`${API_BASE}/stylists/${stylistId}/pin-status`);
      if (res.ok) {
        const data = await res.json();
        setPinStatuses((prev) => ({
          ...prev,
          [stylistId]: { has_pin: data.has_pin, pin_set_at: data.pin_set_at },
        }));
      }
    } catch (err) {
      console.error("Failed to fetch PIN status:", err);
    }
  }

  async function fetchAllPinStatuses() {
    for (const stylist of stylists) {
      await fetchPinStatus(stylist.id);
    }
  }

  async function setPin(stylistId: number, pin: string) {
    setPinLoading(true);
    try {
      const res = await fetch(`${API_BASE}/stylists/${stylistId}/pin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      if (res.ok) {
        await fetchPinStatus(stylistId);
        setPinModalOpen(false);
        setPinValue("");
      }
    } catch (err) {
      console.error("Failed to set PIN:", err);
    } finally {
      setPinLoading(false);
    }
  }

  async function removePin(stylistId: number) {
    setPinLoading(true);
    try {
      const res = await fetch(`${API_BASE}/stylists/${stylistId}/pin`, {
        method: "DELETE",
      });
      if (res.ok) {
        await fetchPinStatus(stylistId);
        setPinModalOpen(false);
      }
    } catch (err) {
      console.error("Failed to remove PIN:", err);
    } finally {
      setPinLoading(false);
    }
  }

  async function fetchPendingTimeOffRequests() {
    setTimeOffRequestsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/time-off-requests?status_filter=PENDING`);
      if (res.ok) {
        const data: TimeOffRequestItem[] = await res.json();
        setPendingTimeOffRequests(data);
      }
    } catch (err) {
      console.error("Failed to fetch time-off requests:", err);
    } finally {
      setTimeOffRequestsLoading(false);
    }
  }

  async function reviewTimeOffRequest(requestId: number, action: "approve" | "reject") {
    setTimeOffReviewLoading(requestId);
    try {
      const res = await fetch(`${API_BASE}/time-off-requests/${requestId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reviewer: "Owner" }),
      });
      if (res.ok) {
        await fetchPendingTimeOffRequests();
        // Refresh schedule if approved (time off block created)
        if (action === "approve") {
          fetchSchedule();
        }
      }
    } catch (err) {
      console.error("Failed to review time-off request:", err);
    } finally {
      setTimeOffReviewLoading(null);
    }
  }

  // Analytics functions
  async function fetchAnalyticsSummary(range: "7d" | "30d") {
    setAnalyticsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/owner/analytics/summary?range=${range}`);
      if (res.ok) {
        const data: AnalyticsSummary = await res.json();
        setAnalyticsSummary(data);
      }
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
    } finally {
      setAnalyticsLoading(false);
    }
  }

  async function fetchAiInsights() {
    if (!analyticsSummary) return;
    setAiInsightsLoading(true);
    setAiInsightsError("");
    try {
      const res = await fetch(`${API_BASE}/owner/analytics/insights`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analytics: analyticsSummary,
          business_context: {
            business_type: "salon",
            has_deposits: false,
            has_reminders: true,
          },
        }),
      });
      if (res.ok) {
        const data: AIInsights = await res.json();
        setAiInsights(data);
      } else {
        const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
        setAiInsightsError(errData.detail || "Failed to generate insights");
      }
    } catch (err) {
      console.error("Failed to fetch AI insights:", err);
      setAiInsightsError("Network error - could not reach server");
    } finally {
      setAiInsightsLoading(false);
    }
  }

  // Auto-fetch analytics when tab selected or range changes
  useEffect(() => {
    if (rightView === "analytics") {
      fetchAnalyticsSummary(analyticsRange);
    }
  }, [rightView, analyticsRange]);

  const quickActions = useMemo(
    () => [
      "Add a service",
      "Change price of a service",
      "Remove a service",
      "Add a stylist",
      "Set stylist off time",
      "Add a specialization",
      "Add promotions",
    ],
    []
  );

  const scheduleStylists = useMemo(
    () => (schedule?.stylists ?? stylists).sort((a, b) => a.id - b.id),
    [schedule?.stylists, stylists]
  );
  const scheduleBookings = schedule?.bookings ?? [];
  const scheduleTimeOff = schedule?.time_off ?? [];

  const scheduleMinWidth = useMemo(
    () => 140 + (scheduleStylists.length || 1) * 180,
    [scheduleStylists]
  );

  function applyOwnerData(data?: OwnerChatResponse["data"]) {
    if (!data) return;
    if (data.services) {
      setServices(data.services);
    } else if (data.service) {
      setServices((prev) => {
        const existing = prev.find((svc) => svc.id === data.service?.id);
        if (existing) {
          return prev.map((svc) => (svc.id === data.service?.id ? data.service! : svc));
        }
        return [...prev, data.service!];
      });
    }
    if (data.stylists) {
      setStylists(data.stylists);
      setSuggestedChips(
        data.stylists.map((stylist) => `Set time off for ${stylist.name}`)
      );
      if (schedule) {
        setSchedule({...schedule, stylists: data.stylists});
      }
    }
    if (data.schedule) {
      setSchedule(data.schedule);
      setScheduleDate(data.schedule.date);
    }
    if (data.promos) {
      setPromos(data.promos);
    }
    if (data?.updated_service) {
      const updated = data.updated_service;
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: `Updated ${updated.name} to ${formatMoney(updated.price_cents)}.`,
        },
      ]);
    }
  }

  async function fetchServices() {
    try {
      const res = await fetch(`${API_BASE}/services`);
      if (res.ok) {
        const data: OwnerService[] = await res.json();
        setServices(data);
      }
    } catch {
      // ignore; UI will show empty state
    }
  }

  async function fetchPromos() {
    try {
      const res = await fetch(`${API_BASE}/owner/promos`);
      if (res.ok) {
        const data: OwnerPromo[] = await res.json();
        setPromos(data);
      }
    } catch {
      // ignore; UI will show empty state
    }
  }

  async function fetchTimeOffForStylist(stylistId: number) {
    if (timeOffEntries[stylistId]) return;
    setTimeOffLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/owner/stylists/${stylistId}/time_off?tz_offset_minutes=${TZ_OFFSET}`
      );
      if (res.ok) {
        const data: OwnerTimeOffEntry[] = await res.json();
        setTimeOffEntries((prev) => ({ ...prev, [stylistId]: data }));
      }
    } finally {
      setTimeOffLoading(false);
    }
  }

  async function fetchSchedule(date = scheduleDate) {
    setScheduleLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/owner/schedule?date=${date}&tz_offset_minutes=${TZ_OFFSET}`
      );
      if (res.ok) {
        const data: OwnerSchedule = await res.json();
        setSchedule(data);
        if (data.stylists?.length) {
          setStylists(data.stylists);
        }
      } else {
        console.error("Schedule fetch failed:", res.status, res.statusText);
      }
    } catch (error) {
      console.error("Failed to fetch schedule:", error);
    } finally {
      setScheduleLoading(false);
    }
  }

  useEffect(() => {
    if (typeof window !== 'undefined') {
      fetchServices();
      fetchSchedule();
    }
  }, [scheduleDate]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      fetchPromos();
      fetchCallSummaries();
      fetchPendingTimeOffRequests();
    }
  }, []);

  useEffect(() => {
    if (services.length > 0) {
      fetchServiceBookingCounts();
    }
  }, [services]);

  useEffect(() => {
    if (stylists.length > 0) {
      fetchAllPinStatuses();
    }
  }, [stylists]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    const normalized = text.trim().toLowerCase();
    if (normalized.includes("add promotion")) {
      openPromoWizard();
      return;
    }
    setSuggestedChips([]);
    setInputValue("");
    const userMsg: OwnerMessage = { id: uid(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const conversationHistory = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.text,
      }));

      const res = await fetch(`${API_BASE}/owner/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conversationHistory }),
      });

      if (res.ok) {
        const data: OwnerChatResponse = await res.json();
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "assistant", text: data.reply },
        ]);
        applyOwnerData(data.data);
        // Auto-refresh services or stylists if the message likely modified them
        if (text.toLowerCase().includes('service') || text.toLowerCase().includes('add') || text.toLowerCase().includes('remove') || text.toLowerCase().includes('change') || text.toLowerCase().includes('price')) {
          sendSilentMessage("List services");
        }
        if (text.toLowerCase().includes('stylist') || text.toLowerCase().includes('add') || text.toLowerCase().includes('set') || text.toLowerCase().includes('specialization')) {
          sendSilentMessage("List stylists");
        }
        if (text.toLowerCase().includes('promo')) {
          fetchPromos();
        }
      } else {
        throw new Error("API error");
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: "I couldn't reach the owner assistant. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  async function sendSilentMessage(text: string) {
    try {
      const conversationHistory = messages.map((m) => ({
        role: m.role,
        content: m.text,
      }));
      const res = await fetch(`${API_BASE}/owner/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conversationHistory }),
      });
      if (res.ok) {
        const data: OwnerChatResponse = await res.json();
        applyOwnerData(data.data);
      }
    } catch {}
  }

  function resetPromoWizard() {
    setPromoWizardStep(0);
    setPromoWizardError("");
    setPromoDraft({
      type: null,
      trigger_point: null,
      copy_mode: "ai",
      custom_copy: "",
      discount_type: null,
      discount_value: "",
      min_spend: "",
      usage_limit: "",
      valid_days: [],
      service_id: null,
      combo_secondary_service_id: null,
      start_at: "",
      end_at: "",
      active: true,
      priority: 0,
      perk_description: "",
    });
  }

  function openPromoWizard() {
    resetPromoWizard();
    setPromoWizardOpen(true);
  }

  function closePromoWizard() {
    setPromoWizardOpen(false);
  }

  useEffect(() => {
    sendSilentMessage("List services");
  }, []);

  function parseTimeToMinutes(value: string) {
    if (!value) return 0;
    const raw = value.trim().toLowerCase();
    const match = raw.match(/^(\d{1,2}):(\d{2})(?:\s*(am|pm))?$/);
    if (!match) return 0;
    let hour = Number(match[1]);
    const minute = Number(match[2]);
    const meridiem = match[3];
    if (meridiem) {
      if (hour === 12) hour = 0;
      if (meridiem === "pm") hour += 12;
    }
    return hour * 60 + minute;
  }

  function formatTimeLabel(value: string) {
    if (!value) return "";
    const [hourStr, minuteStr] = value.split(":");
    const hour = Number(hourStr);
    const minute = Number(minuteStr);
    const meridiem = hour >= 12 ? "PM" : "AM";
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minute.toString().padStart(2, "0")} ${meridiem}`;
  }

  function formatDateLabel(value: string) {
    if (!value) return "";
    const [yyyy, mm, dd] = value.split("-").map(Number);
    const dt = new Date(yyyy, mm - 1, dd);
    return dt.toLocaleDateString("en-US", { month: "long", day: "numeric" });
  }

  function formatDuration(minutes: number) {
    const hrs = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (hrs && mins) return `${hrs}h ${mins}m`;
    if (hrs) return `${hrs}h`;
    return `${mins}m`;
  }

  function summarizeTimeOff(entries: OwnerTimeOffEntry[]) {
    const byDate: Record<string, { start: number; end: number }[]> = {};
    const addBlock = (date: string, start: number, end: number) => {
      if (!byDate[date]) byDate[date] = [];
      byDate[date].push({ start, end });
    };

    const addDays = (dateStr: string, days: number) => {
      const [yyyy, mm, dd] = dateStr.split("-").map(Number);
      const dt = new Date(yyyy, mm - 1, dd);
      dt.setDate(dt.getDate() + days);
      return dt.toISOString().split("T")[0];
    };

    entries.forEach((entry) => {
      const start = parseTimeToMinutes(entry.start_time);
      const end = parseTimeToMinutes(entry.end_time);
      if (end <= start) {
        addBlock(entry.date, start, 24 * 60);
        addBlock(addDays(entry.date, 1), 0, end);
      } else {
        addBlock(entry.date, start, end);
      }
    });

    return Object.entries(byDate).map(([date, blocks]) => {
      blocks.sort((a, b) => a.start - b.start);
      const merged: { start: number; end: number }[] = [];
      for (const block of blocks) {
        const last = merged[merged.length - 1];
        if (last && block.start <= last.end) {
          last.end = Math.max(last.end, block.end);
        } else {
          merged.push({ ...block });
        }
      }
      const totalMinutes = merged.reduce((sum, block) => sum + (block.end - block.start), 0);
      return {
        date,
        blocks: merged,
        totalMinutes,
      };
    });
  }

  function minutesToTimeLabel(minutes: number) {
    const hour = Math.floor(minutes / 60);
    const min = minutes % 60;
    const suffix = hour >= 12 ? "PM" : "AM";
    const displayHour = ((hour + 11) % 12) + 1;
    return `${displayHour}:${min.toString().padStart(2, "0")} ${suffix}`;
  }

  function minutesToTimeValue(minutes: number) {
    const hour = Math.floor(minutes / 60) % 24;
    const min = minutes % 60;
    return `${hour.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`;
  }

  const timeRange = useMemo(() => {
    if (scheduleStylists.length === 0) {
      return { start: 9 * 60, end: 19 * 60 + SLOT_MINUTES };
    }
    const start = Math.min(
      ...scheduleStylists.map((stylist) => parseTimeToMinutes(stylist.work_start))
    );
    const end = Math.max(
      ...scheduleStylists.map((stylist) => parseTimeToMinutes(stylist.work_end))
    );
    return { start, end: end + SLOT_MINUTES };
  }, [scheduleStylists]);

  const slots = useMemo(() => {
    const items = [];
    for (let m = timeRange.start; m < timeRange.end; m += SLOT_MINUTES) {
      items.push(m);
    }
    return items;
  }, [timeRange]);

  async function rescheduleBooking(
    bookingId: string,
    stylistId: number,
    startMinutes: number
  ) {
    try {
      const res = await fetch(`${API_BASE}/owner/bookings/reschedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          booking_id: bookingId,
          stylist_id: stylistId,
          date: scheduleDate,
          start_time: minutesToTimeValue(startMinutes),
          tz_offset_minutes: TZ_OFFSET,
        }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to reschedule");
      }
      fetchSchedule(scheduleDate);
    } catch (error) {
      console.error("Failed to reschedule booking:", error);
      alert(`Failed to reschedule booking: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async function cancelBooking(bookingId: string) {
    await fetch(`${API_BASE}/owner/bookings/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bookingId }),
    });
    fetchSchedule(scheduleDate);
  }

  async function lookupCustomer() {
    const identity = (customerLookupIdentity || customerLookupEmail).trim();
    if (!identity || customerLookupLoading) return;
    setCustomerLookupLoading(true);
    setCustomerLookupError("");
    setCustomerProfile(null);
    try {
      // Use the new identity lookup endpoint
      const url = new URL(`${API_BASE}/customers/lookup/identity`);
      url.searchParams.set("identity", identity);
      const res = await fetch(url.toString());
      
      if (!res.ok) {
        const isPhone = /^[\d\s\-\+\(\)]+$/.test(identity);
        setCustomerLookupError(`No customer found for that ${isPhone ? 'phone number' : 'email'}.`);
        return;
      }
      const data: CustomerProfile = await res.json();
      setCustomerProfile(data);
    } catch {
      setCustomerLookupError("Could not load customer profile.");
    } finally {
      setCustomerLookupLoading(false);
    }
  }

  function formatPromoTrigger(trigger: string) {
    return PROMO_TRIGGERS.find((item) => item.value === trigger)?.label || trigger;
  }

  function formatPromoType(type: string) {
    return PROMO_TYPES.find((item) => item.value === type)?.label || type;
  }

  function formatPromoDiscount(promo: OwnerPromo) {
    if (promo.discount_type === "PERCENT") {
      return `${promo.discount_value ?? 0}% off`;
    }
    if (promo.discount_type === "FIXED") {
      const cents = promo.discount_value ?? 0;
      return `${formatMoney(cents)} off`;
    }
    if (promo.discount_type === "FREE_ADDON") {
      return "Free add-on";
    }
    if (promo.discount_type === "BUNDLE") {
      return "Bundle perk";
    }
    return promo.discount_type;
  }

  function formatPromoWindow(promo: OwnerPromo) {
    if (!promo.start_at_utc || !promo.end_at_utc) return "Always on";
    const start = new Date(promo.start_at_utc);
    const end = new Date(promo.end_at_utc);
    return `${start.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    })}–${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  }

  function formatPromoServices(promo: OwnerPromo) {
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

  function handlePromoNext() {
    setPromoWizardError("");
    if (promoWizardStep === 0 && !promoDraft.type) {
      setPromoWizardError("Select a promotion type to continue.");
      return;
    }
    // Step 1 is now copy mode (trigger point removed - system auto-assigns)
    if (promoWizardStep === 1 && promoDraft.copy_mode === "custom" && !promoDraft.custom_copy.trim()) {
      setPromoWizardError("Add your custom promo copy or switch to AI copy.");
      return;
    }
    if (promoWizardStep === 2) {
      if (!promoDraft.discount_type) {
        setPromoWizardError("Select a discount type.");
        return;
      }
      if (["PERCENT", "FIXED"].includes(promoDraft.discount_type) && !promoDraft.discount_value.trim()) {
        setPromoWizardError("Enter a discount value.");
        return;
      }
    }
    if (promoWizardStep === 3) {
      if (
        promoDraft.type === "SERVICE_COMBO_PROMO" &&
        (!promoDraft.service_id ||
          !promoDraft.combo_secondary_service_id ||
          promoDraft.service_id === promoDraft.combo_secondary_service_id)
      ) {
        setPromoWizardError("Select two different services for the combo promotion.");
        return;
      }
      if (promoDraft.type === "SEASONAL_PROMO" && (!promoDraft.start_at || !promoDraft.end_at)) {
        setPromoWizardError("Seasonal promotions need a start and end date.");
        return;
      }
    }
    setPromoWizardStep((step) => Math.min(step + 1, 4));
  }

  function handlePromoBack() {
    setPromoWizardError("");
    setPromoWizardStep((step) => Math.max(step - 1, 0));
  }

  async function handlePromoCreate() {
    setPromoWizardError("");
    if (!promoDraft.type || !promoDraft.discount_type) {
      setPromoWizardError("Complete the required fields before saving.");
      return;
    }

    let discountValue: number | null = null;
    if (promoDraft.discount_type === "PERCENT") {
      discountValue = Number(promoDraft.discount_value || 0);
    }
    if (promoDraft.discount_type === "FIXED") {
      discountValue = Math.round(Number(promoDraft.discount_value || 0) * 100);
    }
    if (["PERCENT", "FIXED"].includes(promoDraft.discount_type) && (!discountValue || discountValue <= 0)) {
      setPromoWizardError("Discount value must be greater than zero.");
      return;
    }

    const constraints: Record<string, any> = {};
    if (promoDraft.min_spend.trim()) {
      const minSpend = Number(promoDraft.min_spend);
      if (!Number.isNaN(minSpend)) {
        constraints.min_spend_cents = Math.round(minSpend * 100);
      }
    }
    if (promoDraft.usage_limit.trim()) {
      const usageLimit = Number(promoDraft.usage_limit);
      if (!Number.isNaN(usageLimit)) {
        constraints.usage_limit_per_customer = usageLimit;
      }
    }
    if (promoDraft.valid_days.length) {
      constraints.valid_days_of_week = promoDraft.valid_days;
    }
    if (promoDraft.perk_description.trim()) {
      constraints.perk_description = promoDraft.perk_description.trim();
    }
    if (
      promoDraft.type === "SERVICE_COMBO_PROMO" &&
      promoDraft.service_id &&
      promoDraft.combo_secondary_service_id
    ) {
      constraints.combo_service_ids = [
        promoDraft.service_id,
        promoDraft.combo_secondary_service_id,
      ];
    }

    const payload = {
      type: promoDraft.type,
      // trigger_point is auto-assigned by backend based on promo type
      service_id: promoDraft.service_id,
      discount_type: promoDraft.discount_type,
      discount_value: discountValue,
      constraints_json: Object.keys(constraints).length ? constraints : null,
      custom_copy: promoDraft.copy_mode === "custom" ? promoDraft.custom_copy.trim() : null,
      start_at: promoDraft.start_at || null,
      end_at: promoDraft.end_at || null,
      active: promoDraft.active,
      priority: promoDraft.priority,
    };

    setPromoSaving(true);
    try {
      const res = await fetch(`${API_BASE}/owner/promos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to save promotion.");
      }
      const created: OwnerPromo = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: `Promotion saved: ${formatPromoType(created.type)} (${formatPromoTrigger(
            created.trigger_point
          )}).`,
        },
      ]);
      fetchPromos();
      closePromoWizard();
    } catch (error) {
      setPromoWizardError(
        error instanceof Error ? error.message : "Unable to save the promotion."
      );
    } finally {
      setPromoSaving(false);
    }
  }

  async function togglePromoActive(promo: OwnerPromo) {
    setPromoActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/owner/promos/${promo.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !promo.active }),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to update promotion.");
      }
      await fetchPromos();
    } catch (error) {
      console.error("Failed to update promo:", error);
      alert(error instanceof Error ? error.message : "Unable to update promotion.");
    } finally {
      setPromoActionLoading(false);
    }
  }

  async function removePromo(promoId: number) {
    const confirmDelete = window.confirm("Are you sure you want to permanently remove this promotion?");
    if (!confirmDelete) return;
    setPromoActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/owner/promos/${promoId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Unable to remove promotion.");
      }
      await fetchPromos();
      setPromoActionOpenId(null);
    } catch (error) {
      console.error("Failed to remove promo:", error);
      alert(error instanceof Error ? error.message : "Unable to remove promotion.");
    } finally {
      setPromoActionLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white relative">
      {/* Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <motion.div
          className="absolute w-[600px] h-[600px] rounded-full blur-[150px]"
          style={{ background: "rgba(0, 212, 255, 0.08)", top: "-10%", left: "-10%" }}
          animate={{ x: [0, 100, 50, 0], y: [0, -50, 30, 0] }}
          transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full blur-[150px]"
          style={{ background: "rgba(168, 85, 247, 0.08)", top: "30%", right: "-5%" }}
          animate={{ x: [0, -80, 40, 0], y: [0, 60, -30, 0] }}
          transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute w-[400px] h-[400px] rounded-full blur-[150px]"
          style={{ background: "rgba(236, 72, 153, 0.06)", bottom: "-5%", left: "30%" }}
          animate={{ x: [0, 50, -30, 0], y: [0, -40, 60, 0] }}
          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
        />
      </div>
      {/* Grid Background */}
      <div
        className="fixed inset-0 pointer-events-none -z-20 opacity-30"
        style={{
          backgroundImage: "linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          maskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, transparent 70%)",
        }}
      />
      {selectedBooking && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 overlay">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong rounded-2xl shadow-neon p-6 max-w-md w-full relative border border-white/10"
          >
            <button
              onClick={() => setSelectedBooking(null)}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">Booking details</h3>
              <p className="text-xs text-gray-400">
                {selectedBooking.secondary_service_name
                  ? `${selectedBooking.service_name} + ${selectedBooking.secondary_service_name}`
                  : selectedBooking.service_name}{" "}
                · {selectedBooking.customer_name || "Guest"}
              </p>
            </div>
            {selectedBooking.preferred_style_text && (
              <p className="text-sm text-gray-300 whitespace-pre-wrap mb-4">
                {selectedBooking.preferred_style_text}
              </p>
            )}
            {selectedBooking.preferred_style_image_url && (
              <div className="rounded-xl overflow-hidden border border-white/10 bg-black/30">
                <img
                  src={selectedBooking.preferred_style_image_url}
                  alt="Preferred style"
                  className="w-full max-h-64 object-cover"
                />
              </div>
            )}
            {!selectedBooking.preferred_style_text &&
              !selectedBooking.preferred_style_image_url && (
                <p className="text-sm text-gray-500">No preferred style saved for this booking.</p>
              )}
          </motion.div>
        </div>
      )}

      {/* PIN Management Modal */}
      {pinModalOpen && pinStylistId && (
        <div className="fixed inset-0 z-[130] flex items-center justify-center p-4 overlay">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong rounded-2xl shadow-neon p-6 max-w-sm w-full relative border border-white/10"
          >
            <button
              onClick={() => {
                setPinModalOpen(false);
                setPinValue("");
              }}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Shield className="w-5 h-5 text-[#00d4ff]" />
                Employee PIN
              </h3>
              <p className="text-xs text-gray-400">{pinStylistName}</p>
            </div>

            {pinStatuses[pinStylistId]?.has_pin ? (
              <div className="space-y-4">
                <div className="glass rounded-xl p-4 border border-emerald-500/20">
                  <div className="flex items-center gap-2 text-emerald-400 mb-2">
                    <CheckCircle className="w-4 h-4" />
                    <span className="text-sm font-medium">PIN is set</span>
                  </div>
                  <p className="text-xs text-gray-400">
                    Set on {new Date(pinStatuses[pinStylistId].pin_set_at!).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => removePin(pinStylistId)}
                    disabled={pinLoading}
                    className="flex-1 py-2 px-4 rounded-xl text-sm font-medium bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all disabled:opacity-50"
                  >
                    {pinLoading ? "Removing..." : "Remove PIN"}
                  </button>
                </div>
                <div className="border-t border-white/10 pt-4">
                  <p className="text-xs text-gray-400 mb-3">Or set a new PIN:</p>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={pinValue}
                      onChange={(e) => setPinValue(e.target.value)}
                      placeholder="New PIN (4-8 digits)"
                      maxLength={8}
                      className="flex-1 px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 text-center tracking-widest"
                    />
                    <button
                      onClick={() => setPin(pinStylistId, pinValue)}
                      disabled={pinLoading || pinValue.length < 4}
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
                  onChange={(e) => setPinValue(e.target.value)}
                  placeholder="Enter PIN (4-8 digits)"
                  maxLength={8}
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-[#00d4ff]/50 text-center text-xl tracking-widest"
                />
                <button
                  onClick={() => setPin(pinStylistId, pinValue)}
                  disabled={pinLoading || pinValue.length < 4}
                  className="w-full py-3 px-4 rounded-xl text-sm font-medium bg-gradient-to-r from-[#00d4ff] to-[#00a8cc] text-black hover:shadow-lg hover:shadow-[#00d4ff]/25 transition-all disabled:opacity-50"
                >
                  {pinLoading ? "Setting PIN..." : "Set PIN"}
                </button>
              </div>
            )}
          </motion.div>
        </div>
      )}

      {serviceBookingsModalOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 overlay">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="glass-strong rounded-2xl shadow-neon p-6 max-w-2xl w-full relative max-h-[80vh] flex flex-col border border-white/10"
          >
            <button
              onClick={() => {
                setServiceBookingsModalOpen(false);
                setSelectedServiceBookings([]);
              }}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">{selectedServiceName}</h3>
              <p className="text-xs text-gray-400">Upcoming bookings (next 7 days)</p>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 scrollbar-hide">
              {serviceBookingsLoading ? (
                <div className="text-sm text-gray-500 text-center py-8">
                  <div className="spinner mx-auto mb-2" />
                  Loading...
                </div>
              ) : selectedServiceBookings.length === 0 ? (
                <div className="text-sm text-gray-500 text-center py-8">No bookings found</div>
              ) : (
                selectedServiceBookings.map((booking) => {
                  const startDate = new Date(booking.start_time);
                  const endDate = new Date(booking.end_time);
                  const dateStr = startDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
                  const timeStr = `${startDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })} - ${endDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
                  
                  return (
                    <div key={booking.id} className="glass rounded-xl p-3 hover:bg-white/5 transition-colors border border-white/5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="text-sm font-medium text-white">{booking.customer_name || "Guest"}</p>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                              booking.status === "CONFIRMED"
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                            }`}>
                              {booking.status}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400 mb-1">{dateStr} · {timeStr}</p>
                          <p className="text-xs text-gray-500">Stylist: {booking.stylist_name}</p>
                          {booking.customer_email && (
                            <p className="text-xs text-gray-600 mt-1">{booking.customer_email}</p>
                          )}
                          {booking.customer_phone && (
                            <p className="text-xs text-gray-600">{booking.customer_phone}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </motion.div>
        </div>
      )}
      {promoWizardOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center overlay px-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="w-full max-w-2xl glass-strong rounded-2xl shadow-neon border border-white/10 p-6"
          >
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Gift className="w-5 h-5 text-[#00d4ff]" />
                  Add promotion
                </h3>
                <p className="text-xs text-gray-400">Guided setup with structured options.</p>
              </div>
              <button
                onClick={closePromoWizard}
                className="p-2 rounded-xl hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="mt-6 space-y-4">
              {promoWizardStep === 0 && (
                <div>
                  <p className="text-sm font-medium text-white mb-3">Promotion type</p>
                  <div className="flex flex-wrap gap-2">
                    {PROMO_TYPES.map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setPromoDraft((prev) => ({ ...prev, type: option.value }))
                        }
                        className={`px-4 py-2 rounded-full text-sm transition-all ${
                          promoDraft.type === option.value
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

              {/* Step 1 removed - trigger point is auto-assigned by system */}

              {promoWizardStep === 1 && (
                <div>
                  <p className="text-sm font-medium text-white mb-3">Promotion copy</p>
                  <div className="flex gap-2 mb-4">
                    {(["ai", "custom"] as const).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setPromoDraft((prev) => ({ ...prev, copy_mode: mode }))}
                        className={`px-4 py-2 rounded-full text-sm transition-all ${
                          promoDraft.copy_mode === mode
                            ? "btn-neon"
                            : "glass border border-white/10 text-gray-300 hover:bg-white/10"
                        }`}
                      >
                        {mode === "ai" ? "✨ AI generated" : "✍️ Write my own"}
                      </button>
                    ))}
                  </div>
                  {promoDraft.copy_mode === "custom" && (
                    <textarea
                      value={promoDraft.custom_copy}
                      onChange={(e) =>
                        setPromoDraft((prev) => ({ ...prev, custom_copy: e.target.value }))
                      }
                      className="w-full rounded-xl input-glass p-3 text-sm"
                      rows={3}
                      placeholder="Enter the exact promotional line (placeholders like {service_name} are ok)."
                    />
                  )}
                </div>
              )}

              {promoWizardStep === 2 && (
                <div>
                  <p className="text-sm font-medium text-white mb-3">Discount details</p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {PROMO_DISCOUNTS.map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setPromoDraft((prev) => ({ ...prev, discount_type: option.value }))
                        }
                        className={`px-4 py-2 rounded-full text-sm transition-all flex items-center gap-2 ${
                          promoDraft.discount_type === option.value
                            ? "btn-neon"
                            : "glass border border-white/10 text-gray-300 hover:bg-white/10"
                        }`}
                      >
                        {option.value === "PERCENT" ? <Percent className="w-4 h-4" /> : <DollarSign className="w-4 h-4" />}
                        {option.label}
                      </button>
                    ))}
                  </div>
                  {promoDraft.discount_type && ["PERCENT", "FIXED"].includes(promoDraft.discount_type) && (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={promoDraft.discount_value}
                        onChange={(e) =>
                          setPromoDraft((prev) => ({
                            ...prev,
                            discount_value: e.target.value,
                          }))
                        }
                        className="flex-1 rounded-full input-glass px-4 py-2 text-sm"
                        placeholder={promoDraft.discount_type === "PERCENT" ? "Percent" : "Amount in USD"}
                        min={0}
                      />
                      <span className="text-xs text-gray-400">
                        {promoDraft.discount_type === "PERCENT" ? "%" : "USD"}
                      </span>
                    </div>
                  )}
                  {promoDraft.discount_type && ["FREE_ADDON", "BUNDLE"].includes(promoDraft.discount_type) && (
                    <input
                      type="text"
                      value={promoDraft.perk_description}
                      onChange={(e) =>
                        setPromoDraft((prev) => ({ ...prev, perk_description: e.target.value }))
                      }
                      className="w-full rounded-full input-glass px-4 py-2 text-sm"
                      placeholder="Optional perk description (e.g., free beard trim)"
                    />
                  )}
                </div>
              )}

              {promoWizardStep === 3 && (
                <div className="space-y-4">
                  {promoDraft.type === "SERVICE_COMBO_PROMO" && (
                    <div>
                      <p className="text-sm font-medium text-white mb-2">Service selection</p>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <select
                          value={promoDraft.service_id ?? ""}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({
                              ...prev,
                              service_id: e.target.value ? Number(e.target.value) : null,
                            }))
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
                          value={promoDraft.combo_secondary_service_id ?? ""}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({
                              ...prev,
                              combo_secondary_service_id: e.target.value ? Number(e.target.value) : null,
                            }))
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
                  {promoDraft.type === "SEASONAL_PROMO" && (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">Start date</label>
                        <input
                          type="date"
                          value={promoDraft.start_at}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({ ...prev, start_at: e.target.value }))
                          }
                          className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-400 mb-1 block">End date</label>
                        <input
                          type="date"
                          value={promoDraft.end_at}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({ ...prev, end_at: e.target.value }))
                          }
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
                        value={promoDraft.min_spend}
                        onChange={(e) =>
                          setPromoDraft((prev) => ({ ...prev, min_spend: e.target.value }))
                        }
                        className="w-full rounded-xl input-glass px-3 py-2 text-sm"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-400 mb-1 block">Usage limit per customer</label>
                      <input
                        type="number"
                        value={promoDraft.usage_limit}
                        onChange={(e) =>
                          setPromoDraft((prev) => ({ ...prev, usage_limit: e.target.value }))
                        }
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
                          onClick={() =>
                            setPromoDraft((prev) => {
                              const exists = prev.valid_days.includes(day.value);
                              return {
                                ...prev,
                                valid_days: exists
                                  ? prev.valid_days.filter((d) => d !== day.value)
                                  : [...prev.valid_days, day.value],
                              };
                            })
                          }
                          className={`px-3 py-1 rounded-full text-xs transition-all ${
                            promoDraft.valid_days.includes(day.value)
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

              {promoWizardStep === 4 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between glass rounded-xl p-4">
                    <div>
                      <p className="text-sm font-medium text-white">Activation</p>
                      <p className="text-xs text-gray-400">Enable or pause the promotion.</p>
                    </div>
                    <button
                      onClick={() =>
                        setPromoDraft((prev) => ({ ...prev, active: !prev.active }))
                      }
                      className={`px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-2 ${
                        promoDraft.active
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : "glass border border-white/10 text-gray-400"
                      }`}
                    >
                      {promoDraft.active ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
                      {promoDraft.active ? "Active" : "Paused"}
                    </button>
                  </div>
                </div>
              )}

              {promoWizardError && (
                <div className="rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {promoWizardError}
                </div>
              )}
            </div>

            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={handlePromoBack}
                disabled={promoWizardStep === 0}
                className="px-4 py-2 rounded-full text-sm glass border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" />
                Back
              </button>
              {promoWizardStep < 4 ? (
                <button
                  onClick={handlePromoNext}
                  className="px-5 py-2 rounded-full btn-neon text-sm flex items-center gap-2"
                >
                  Next
                  <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handlePromoCreate}
                  disabled={promoSaving}
                  className="px-5 py-2 rounded-full btn-neon text-sm disabled:opacity-60 flex items-center gap-2"
                >
                  {promoSaving ? (
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
      )}
      <header className="sticky top-0 z-50 glass border-b border-white/5">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#00d4ff] to-[#a855f7] flex items-center justify-center shadow-glow-blue">
              <MessageSquare className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold gradient-text">Owner GPT</h1>
              <p className="text-xs text-gray-500">Service management console</p>
            </div>
          </div>
          <span className="text-xs px-3 py-1.5 rounded-full glass border border-white/10 text-gray-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Internal only
          </span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid lg:grid-cols-[1.2fr_0.8fr] gap-6">
        <section className="glass-card rounded-2xl p-6 border border-white/5">
          <div className="space-y-4 max-h-96 overflow-y-auto scrollbar-hide">
            {messages.map((msg, index) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: index * 0.05 }}
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm ${
                  msg.role === "assistant"
                    ? "glass border border-white/5 text-gray-200"
                    : "bg-gradient-to-r from-[#00d4ff] to-[#a855f7] text-white ml-auto shadow-neon"
                }`}
              >
                {msg.text}
              </motion.div>
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="spinner" />
                Thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="mt-6">
            <p className="text-xs text-gray-500 mb-3 flex items-center gap-2">
              <Sparkles className="w-3 h-3 text-[#00d4ff]" />
              Quick actions
            </p>
            <div className="flex flex-wrap gap-2">
              {quickActions.map((action) => (
                <motion.button
                  key={action}
                  whileHover={{ scale: 1.02, y: -1 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    if (action === "Add promotions") {
                      openPromoWizard();
                    } else {
                      sendMessage(action);
                    }
                  }}
                  className="px-3 py-2 rounded-full glass border border-white/10 hover:bg-white/10 text-gray-300 hover:text-white text-xs transition-all"
                >
                  {action}
                </motion.button>
              ))}
            </div>
            {suggestedChips.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-500 mb-2">Suggested</p>
                <div className="flex flex-wrap gap-2">
                  {suggestedChips.map((chip) => (
                    <motion.button
                      key={chip}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => sendMessage(chip)}
                      className="px-3 py-2 rounded-full bg-[#00d4ff]/10 text-[#00d4ff] text-xs hover:bg-[#00d4ff]/20 transition-all border border-[#00d4ff]/30"
                    >
                      {chip}
                    </motion.button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 flex items-center gap-2">
            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") sendMessage(inputValue);
              }}
              placeholder="Type an owner command..."
              className="flex-1 px-4 py-3 rounded-full input-glass text-sm"
            />
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => sendMessage(inputValue)}
              className="px-5 py-3 rounded-full btn-neon text-sm font-medium flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
              Send
            </motion.button>
          </div>

          {/* Call Summaries Section - Collapsible */}
          <div className="mt-6 border-t border-white/5 pt-4">
            <button
              onClick={() => {
                setCallSummariesExpanded(!callSummariesExpanded);
                if (!callSummariesExpanded && callSummaries.length === 0) {
                  fetchCallSummaries();
                }
              }}
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
                animate={{ rotate: callSummariesExpanded ? 90 : 0 }}
                className="text-gray-500 group-hover:text-white transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </motion.span>
            </button>

            <AnimatePresence>
              {callSummariesExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="mt-4 space-y-3 max-h-80 overflow-y-auto scrollbar-hide"
                >
                  {callSummariesLoading && (
                    <div className="text-xs text-gray-500 flex items-center gap-2">
                      <div className="spinner w-4 h-4" />
                      Loading call summaries...
                    </div>
                  )}
                  {!callSummariesLoading && callSummaries.length === 0 && (
                    <div className="text-xs text-gray-500">No call summaries yet.</div>
                  )}
                  {callSummaries.map((summary) => (
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
                  {callSummaries.length > 0 && (
                    <button
                      onClick={fetchCallSummaries}
                      className="text-xs text-[#00d4ff] hover:underline"
                    >
                      Refresh
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Time Off Requests Section */}
          <div className="glass-card rounded-2xl p-4 border border-white/5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Calendar className="w-4 h-4 text-amber-400" />
                Pending Time Off Requests
              </h3>
              <button
                onClick={fetchPendingTimeOffRequests}
                disabled={timeOffRequestsLoading}
                className="text-xs text-gray-400 hover:text-[#00d4ff] transition-colors"
              >
                {timeOffRequestsLoading ? "Loading..." : "Refresh"}
              </button>
            </div>

            {timeOffRequestsLoading && pendingTimeOffRequests.length === 0 ? (
              <div className="text-xs text-gray-500 flex items-center gap-2">
                <div className="spinner w-4 h-4" />
                Loading...
              </div>
            ) : pendingTimeOffRequests.length === 0 ? (
              <div className="text-xs text-gray-500 py-4 text-center">
                No pending requests
              </div>
            ) : (
              <div className="space-y-3 max-h-64 overflow-y-auto scrollbar-hide">
                {pendingTimeOffRequests.map((request) => {
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
                          {new Date(request.start_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                          {request.start_date !== request.end_date && (
                            <> - {new Date(request.end_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</>
                          )}
                        </span>
                        {request.reason && (
                          <p className="mt-1 text-gray-500 italic">{request.reason}</p>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => reviewTimeOffRequest(request.id, "approve")}
                          disabled={timeOffReviewLoading === request.id}
                          className="flex-1 py-1.5 px-3 rounded-lg text-xs font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all flex items-center justify-center gap-1 disabled:opacity-50"
                        >
                          <CheckCircle className="w-3 h-3" />
                          Approve
                        </button>
                        <button
                          onClick={() => reviewTimeOffRequest(request.id, "reject")}
                          disabled={timeOffReviewLoading === request.id}
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
        </section>

        <aside className="space-y-6">
          <div className="flex gap-2 p-1 glass rounded-full">
            <button
              onClick={() => setRightView('services')}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === 'services'
                  ? 'btn-neon'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Scissors className="w-4 h-4" />
              Services
            </button>
            <button
              onClick={() => setRightView('stylists')}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === 'stylists'
                  ? 'btn-neon'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Users className="w-4 h-4" />
              Stylists
            </button>
            <button
              onClick={() => setRightView('promos')}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === 'promos'
                  ? 'btn-neon'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Tag className="w-4 h-4" />
              Promos
            </button>
            <button
              onClick={() => setRightView('analytics')}
              className={`flex-1 px-4 py-2 rounded-full text-sm font-medium transition-all flex items-center justify-center gap-2 ${
                rightView === 'analytics'
                  ? 'btn-neon'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              Analytics
            </button>
          </div>

          {rightView === 'services' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-6 border border-white/5"
            >
              <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <Scissors className="w-4 h-4 text-[#00d4ff]" />
                Current services
              </h2>
              <p className="text-xs text-gray-500 mb-4">Live view from the database.</p>
              <div className="space-y-3">
                {services.length === 0 && (
                  <div className="text-xs text-gray-500">No services loaded yet.</div>
                )}
                {services.map((svc) => {
                  const count = serviceBookingCounts[svc.id] || 0;
                  return (
                    <motion.div
                      key={svc.id}
                      whileHover={{ scale: 1.01 }}
                      className="glass rounded-xl p-3 border border-white/5 hover:border-[#00d4ff]/30 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-white">{svc.name}</p>
                          <p className="text-xs text-gray-500 flex items-center gap-2 mt-1">
                            <Clock className="w-3 h-3" />
                            {svc.duration_minutes} min
                            <span className="text-[#00d4ff]">·</span>
                            <DollarSign className="w-3 h-3" />
                            {formatMoney(svc.price_cents)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => count > 0 && fetchServiceBookings(svc.id, svc.name)}
                          disabled={count === 0}
                          className={`text-[11px] px-2 py-1 rounded-full transition-all ${
                            count > 0
                              ? "bg-[#00d4ff]/10 text-[#00d4ff] hover:bg-[#00d4ff]/20 cursor-pointer border border-[#00d4ff]/30"
                              : "glass border border-white/10 text-gray-600 cursor-default"
                          }`}
                        >
                          {count > 0 ? `${count} booking${count === 1 ? "" : "s"}` : "none"}
                        </button>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {rightView === 'stylists' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-6 border border-white/5"
            >
              <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                <Users className="w-4 h-4 text-[#a855f7]" />
                Current stylists
              </h2>
              <p className="text-xs text-gray-500 mb-4">Hours, specialties, and time off.</p>
              <div className="space-y-3">
                {stylists.length === 0 && (
                  <div className="text-xs text-gray-500">No stylists loaded yet.</div>
                )}
              {stylists.map((stylist) => (
                <motion.div
                  key={stylist.id}
                  whileHover={{ scale: 1.01 }}
                  className="glass rounded-xl p-3 border border-white/5 hover:border-[#a855f7]/30 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-white">{stylist.name}</p>
                      <p className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                        <Clock className="w-3 h-3" />
                        {stylist.work_start}–{stylist.work_end}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {stylist.specialties.length > 0
                          ? stylist.specialties.join(", ")
                          : "No specialties"}
                      </p>
                    </div>
                    <div className="flex flex-col gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setPinStylistId(stylist.id);
                          setPinStylistName(stylist.name);
                          setPinValue("");
                          setPinModalOpen(true);
                        }}
                        className={`text-[11px] px-2 py-1 rounded-full flex items-center gap-1 transition-all ${
                          pinStatuses[stylist.id]?.has_pin
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20"
                            : "glass border border-white/10 text-gray-400 hover:bg-white/10 hover:text-white"
                        }`}
                      >
                        {pinStatuses[stylist.id]?.has_pin ? (
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
                      <button
                        type="button"
                        onClick={() => {
                          const next = timeOffOpenStylistId === stylist.id ? null : stylist.id;
                          setTimeOffOpenStylistId(next);
                          if (next) {
                            fetchTimeOffForStylist(stylist.id);
                          }
                        }}
                        className="text-[11px] px-2 py-1 rounded-full glass border border-white/10 text-gray-400 hover:bg-white/10 hover:text-white transition-all"
                      >
                        {stylist.time_off_count} {stylist.time_off_count === 1 ? "day" : "days"} off
                      </button>
                    </div>
                  </div>
                  <AnimatePresence>
                    {timeOffOpenStylistId === stylist.id && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="mt-3 glass rounded-xl px-3 py-2 text-xs text-gray-400 border border-white/5"
                      >
                        {timeOffLoading && !timeOffEntries[stylist.id] && (
                          <div className="flex items-center gap-2">
                            <div className="spinner w-3 h-3" />
                            Loading time off...
                          </div>
                        )}
                        {!timeOffLoading && (timeOffEntries[stylist.id]?.length ?? 0) === 0 && (
                          <div className="text-gray-500">No time off logged.</div>
                        )}
                        {timeOffEntries[stylist.id]?.length ? (
                          <div className="space-y-2">
                            {summarizeTimeOff(timeOffEntries[stylist.id]).map((entry) => (
                              <div key={`${stylist.id}-${entry.date}`} className="flex items-start justify-between gap-3">
                                <div>
                                  <div className="text-[11px] font-semibold text-white">
                                    {formatDateLabel(entry.date)}
                                  </div>
                                  <div className="text-[11px] text-gray-500">
                                    {entry.blocks
                                      .map(
                                        (block) =>
                                          `${formatTimeLabel(minutesToTimeValue(block.start))}–${formatTimeLabel(
                                            minutesToTimeValue(block.end)
                                          )}`
                                      )
                                      .join(", ")}
                                  </div>
                                </div>
                                <div className="text-[11px] font-semibold text-[#00d4ff]">
                                  {formatDuration(entry.totalMinutes)}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              ))}
            </div>
          </motion.div>
          )}

          {rightView === 'promos' && (
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
                  onClick={openPromoWizard}
                  className="px-3 py-2 rounded-full btn-neon text-xs flex items-center gap-1"
                >
                  <Plus className="w-3 h-3" />
                  Add
                </motion.button>
              </div>
              <div className="space-y-3">
                {promos.length === 0 && (
                  <div className="text-xs text-gray-500">No promotions configured yet.</div>
                )}
                {promos.map((promo) => (
                  <motion.div
                    key={promo.id}
                    whileHover={{ scale: 1.01 }}
                    className="glass rounded-xl p-3 border border-white/5 hover:border-[#ec4899]/30 transition-all cursor-pointer"
                    onClick={() =>
                      setPromoActionOpenId((prev) => (prev === promo.id ? null : promo.id))
                    }
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        setPromoActionOpenId((prev) => (prev === promo.id ? null : promo.id));
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
                        {formatPromoServices(promo) && (
                          <p className="text-[11px] text-gray-500">
                            {formatPromoServices(promo)}
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
                      {promoActionOpenId === promo.id && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="mt-3 flex flex-wrap gap-2"
                        >
                          <button
                            onClick={(event) => {
                              event.stopPropagation();
                              togglePromoActive(promo);
                            }}
                            disabled={promoActionLoading}
                            className="px-3 py-1.5 rounded-full text-xs glass border border-white/10 hover:bg-white/10 text-white disabled:opacity-60 flex items-center gap-1 transition-all"
                          >
                            {promo.active ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                            {promo.active ? "Pause" : "Activate"}
                          </button>
                          <button
                            onClick={(event) => {
                              event.stopPropagation();
                              removePromo(promo.id);
                            }}
                            disabled={promoActionLoading}
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
          )}

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
                value={customerLookupIdentity}
                onChange={(e) => setCustomerLookupIdentity(e.target.value)}
                placeholder="Email or phone number"
                className="flex-1 px-4 py-2 rounded-full input-glass text-xs"
                onKeyDown={(e) => e.key === "Enter" && lookupCustomer()}
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={lookupCustomer}
                disabled={!customerLookupIdentity.trim() || customerLookupLoading}
                className="px-4 py-2 rounded-full btn-neon text-xs font-medium disabled:opacity-60 flex items-center gap-1"
              >
                {customerLookupLoading ? (
                  <><div className="spinner w-3 h-3" /> Searching...</>
                ) : (
                  <><Search className="w-3 h-3" /> Search</>
                )}
              </motion.button>
            </div>
            {customerLookupError && (
              <p className="mt-3 text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {customerLookupError}
              </p>
            )}
            {customerProfile && (
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
                    {customerProfile.name || customerProfile.email || customerProfile.phone || "Guest"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Preferred stylist</span>
                  <span className="font-medium">
                    {customerProfile.preferred_stylist || "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Last service</span>
                  <span className="font-medium">
                    {customerProfile.last_service || "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Average spend</span>
                  <span className="font-medium text-[#00d4ff]">
                    {(customerProfile.average_spend_cents / 100).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Total bookings</span>
                  <span className="font-medium">
                    {customerProfile.total_bookings}
                  </span>
                </div>
              </motion.div>
            )}
          </motion.div>

          {/* Analytics Tab Content */}
          {rightView === 'analytics' && (
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
                    onClick={() => setAnalyticsRange("7d")}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                      analyticsRange === "7d"
                        ? "btn-neon"
                        : "glass border border-white/10 text-gray-400 hover:text-white"
                    }`}
                  >
                    7 Days
                  </button>
                  <button
                    onClick={() => setAnalyticsRange("30d")}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                      analyticsRange === "30d"
                        ? "btn-neon"
                        : "glass border border-white/10 text-gray-400 hover:text-white"
                    }`}
                  >
                    30 Days
                  </button>
                </div>
              </div>

              {analyticsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="spinner w-6 h-6" />
                  <span className="ml-3 text-sm text-gray-400">Loading analytics...</span>
                </div>
              ) : analyticsSummary ? (
                <>
                  {/* KPI Cards */}
                  <div className="grid grid-cols-2 gap-3">
                    {/* Total Bookings */}
                    <div className="glass rounded-xl p-4 border border-white/5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-gray-500">Total Bookings</span>
                        {analyticsSummary.bookings_delta !== 0 && (
                          <span className={`text-xs flex items-center gap-0.5 ${analyticsSummary.bookings_delta > 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {analyticsSummary.bookings_delta > 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                            {Math.abs(analyticsSummary.bookings_delta).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <p className="text-2xl font-bold text-white">{analyticsSummary.bookings_total}</p>
                      <p className="text-[10px] text-gray-500 mt-1">vs {analyticsSummary.prev_bookings_total} prev</p>
                    </div>

                    {/* Revenue */}
                    <div className="glass rounded-xl p-4 border border-white/5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-gray-500">Est. Revenue</span>
                        <DollarSign className="w-3 h-3 text-emerald-400" />
                      </div>
                      <p className="text-2xl font-bold text-emerald-400">
                        {formatMoney(analyticsSummary.estimated_revenue_cents)}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-1">from {analyticsSummary.completed_count} completed</p>
                    </div>

                    {/* No-Show Rate */}
                    <div className="glass rounded-xl p-4 border border-white/5">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-gray-500">No-Show Rate</span>
                        {analyticsSummary.no_show_rate_delta !== 0 && (
                          <span className={`text-xs flex items-center gap-0.5 ${analyticsSummary.no_show_rate_delta < 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {analyticsSummary.no_show_rate_delta < 0 ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                            {Math.abs(analyticsSummary.no_show_rate_delta).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <p className={`text-2xl font-bold ${analyticsSummary.no_show_rate > 15 ? "text-red-400" : "text-white"}`}>
                        {analyticsSummary.no_show_rate.toFixed(1)}%
                      </p>
                      <p className="text-[10px] text-gray-500 mt-1">{analyticsSummary.no_show_count} no-shows</p>
                    </div>

                    {/* Time Distribution */}
                    <div className="glass rounded-xl p-4 border border-white/5">
                      <span className="text-xs text-gray-500 mb-2 block">Peak Hours</span>
                      <div className="flex gap-2 text-[10px]">
                        <div className="flex items-center gap-1">
                          <Sun className="w-3 h-3 text-yellow-400" />
                          <span className="text-gray-400">{analyticsSummary.time_distribution.morning}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Sunset className="w-3 h-3 text-orange-400" />
                          <span className="text-gray-400">{analyticsSummary.time_distribution.afternoon}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Moon className="w-3 h-3 text-purple-400" />
                          <span className="text-gray-400">{analyticsSummary.time_distribution.evening}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Service Breakdown */}
                  {analyticsSummary.by_service.length > 0 && (
                    <div>
                      <h3 className="text-xs font-medium text-white mb-3 flex items-center gap-2">
                        <Scissors className="w-3 h-3 text-[#00d4ff]" />
                        By Service
                      </h3>
                      <div className="space-y-2">
                        {analyticsSummary.by_service.slice(0, 5).map((svc) => (
                          <div key={svc.service_id} className="glass rounded-lg p-3 border border-white/5">
                            <div className="flex justify-between items-center">
                              <span className="text-xs text-white font-medium">{svc.service_name}</span>
                              <span className="text-xs text-gray-400">{svc.bookings} bookings</span>
                            </div>
                            <div className="flex gap-4 mt-1 text-[10px] text-gray-500">
                              <span>{svc.completed} completed</span>
                              <span className={svc.no_show_rate > 20 ? "text-red-400" : ""}>{svc.no_shows} no-shows</span>
                              <span className="text-emerald-400">{formatMoney(svc.estimated_revenue_cents)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Stylist Breakdown */}
                  {analyticsSummary.by_stylist.length > 0 && (
                    <div>
                      <h3 className="text-xs font-medium text-white mb-3 flex items-center gap-2">
                        <Users className="w-3 h-3 text-[#00d4ff]" />
                        By Stylist
                      </h3>
                      <div className="space-y-2">
                        {analyticsSummary.by_stylist.map((sty) => (
                          <div key={sty.stylist_id} className="glass rounded-lg p-3 border border-white/5">
                            <div className="flex justify-between items-center">
                              <span className="text-xs text-white font-medium">{sty.stylist_name}</span>
                              <span className="text-xs text-gray-400">{sty.bookings} bookings</span>
                            </div>
                            <div className="flex gap-4 mt-1 text-[10px] text-gray-500">
                              <span>{sty.completed} completed</span>
                              <span>{sty.no_shows} no-shows</span>
                              <span className={sty.acknowledgement_rate >= 80 ? "text-emerald-400" : "text-yellow-400"}>
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
                        onClick={fetchAiInsights}
                        disabled={aiInsightsLoading}
                        className="px-3 py-1.5 rounded-full text-xs font-medium bg-purple-500/20 border border-purple-500/30 text-purple-300 hover:bg-purple-500/30 transition-all flex items-center gap-1.5 disabled:opacity-50"
                      >
                        {aiInsightsLoading ? (
                          <><RefreshCw className="w-3 h-3 animate-spin" /> Analyzing...</>
                        ) : (
                          <><Sparkles className="w-3 h-3" /> Generate Insights</>
                        )}
                      </motion.button>
                    </div>

                    {aiInsightsError && (
                      <div className="glass rounded-lg p-3 border border-red-500/30 text-xs text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-3 h-3" />
                        {aiInsightsError}
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
                            <h4 className="text-[11px] font-semibold text-purple-300 mb-2">Summary</h4>
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
                                  <span className={a.direction === "increase" ? "text-emerald-400" : "text-red-400"}>
                                    {a.direction === "increase" ? "↑" : "↓"} {a.metric}
                                  </span>
                                  : {a.value}
                                  {a.likely_causes.length > 0 && (
                                    <span className="text-gray-500 ml-1">(Possible: {a.likely_causes.join(", ")})</span>
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
                              <div key={i} className="glass rounded-lg p-3 border border-white/5">
                                <div className="flex items-center gap-2 mb-1">
                                  <Lightbulb className="w-3 h-3 text-yellow-400" />
                                  <span className="text-xs font-medium text-white">{ins.title}</span>
                                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                                    ins.confidence === "high" ? "bg-emerald-500/20 text-emerald-400" :
                                    ins.confidence === "medium" ? "bg-yellow-500/20 text-yellow-400" :
                                    "bg-gray-500/20 text-gray-400"
                                  }`}>
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
                            <h4 className="text-[11px] font-semibold text-emerald-300 mb-2">Recommendations</h4>
                            <div className="space-y-2">
                              {aiInsights.recommendations.map((rec, i) => (
                                <div key={i} className="glass rounded-lg p-3 border border-emerald-500/20">
                                  <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                      <p className="text-xs text-white">{rec.action}</p>
                                      <p className="text-[10px] text-gray-500 mt-1">
                                        Expected: {rec.expected_impact}
                                      </p>
                                    </div>
                                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                                      rec.risk === "low" ? "bg-emerald-500/20 text-emerald-400" :
                                      rec.risk === "medium" ? "bg-yellow-500/20 text-yellow-400" :
                                      "bg-red-500/20 text-red-400"
                                    }`}>
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
                            <h4 className="text-[11px] font-semibold text-gray-400 mb-2">Questions to Consider</h4>
                            <ul className="text-xs text-gray-500 space-y-1">
                              {aiInsights.questions_for_owner.map((q, i) => (
                                <li key={i}>• {q}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </motion.div>
                    )}

                    {!aiInsights && !aiInsightsLoading && !aiInsightsError && (
                      <p className="text-xs text-gray-500 text-center py-4">
                        Click "Generate Insights" to get AI-powered analysis of your business data.
                      </p>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-xs text-gray-500 text-center py-8">No data available for the selected period.</p>
              )}
            </motion.div>
          )}
        </aside>
      </main>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card rounded-2xl p-6 border border-white/5"
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Calendar className="w-4 h-4 text-[#00d4ff]" />
                Schedule
              </h2>
              <p className="text-xs text-gray-500">
                Drag a booking to reschedule or move across stylists. Time off shows in soft red,
                confirmed appointments in neon blue.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={styleFilter}
                onChange={(event) => setStyleFilter(event.target.value)}
                placeholder="Filter by style"
                className="px-3 py-2 rounded-full input-glass text-xs"
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => {
                  const date = new Date(scheduleDate);
                  date.setDate(date.getDate() - 1);
                  setScheduleDate(date.toISOString().split("T")[0]);
                }}
                className="px-3 py-2 rounded-full glass border border-white/10 text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-all flex items-center"
              >
                <ArrowLeft className="w-4 h-4" />
              </motion.button>
              <input
                type="date"
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="px-3 py-2 rounded-full input-glass text-xs"
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => {
                  const date = new Date(scheduleDate);
                  date.setDate(date.getDate() + 1);
                  setScheduleDate(date.toISOString().split("T")[0]);
                }}
                className="px-3 py-2 rounded-full glass border border-white/10 text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-all flex items-center"
              >
                <ArrowRight className="w-4 h-4" />
              </motion.button>
            </div>
          </div>

          <div className="mt-6 overflow-auto scrollbar-hide">

            {scheduleLoading && (
              <div className="text-xs text-gray-500 mb-4 flex items-center gap-2">
                <div className="spinner w-4 h-4" />
                Loading schedule...
              </div>
            )}
            <div className="flex items-center gap-3 text-[11px] text-gray-500 mb-2">
              <span className="inline-flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-red-500/20 border border-red-500/30" />
                Out of office
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-gradient-to-r from-[#00d4ff] to-[#a855f7]" />
                Appointment
              </span>
            </div>
            <div
              className="grid border border-white/5 rounded-2xl overflow-hidden bg-[#0a0e1a]"
              style={{
                minWidth: scheduleMinWidth,
                gridTemplateColumns: `140px repeat(${scheduleStylists.length || 1}, minmax(180px, 1fr))`,
                gridTemplateRows: `48px repeat(${slots.length}, ${ROW_HEIGHT}px)`,
              }}
            >
              <div className="glass border-b border-white/5 sticky left-0 z-30 text-xs font-medium text-gray-400 flex items-center justify-center" style={{ gridColumn: 1 }}>
                <Clock className="w-3 h-3 mr-1" />
                Time
              </div>
              {scheduleStylists.length === 0 && (
                <div className="col-span-1 glass border-b border-white/5 text-xs text-gray-500 flex items-center justify-center">
                  No stylists
                </div>
              )}
              {scheduleStylists.map((stylist, index) => (
                <div
                  key={stylist.id}
                  className="glass border-b border-white/5 text-xs font-medium text-white flex items-center justify-center"
                  style={{ gridColumn: index + 2 }}
                >
                  <User className="w-3 h-3 mr-1 text-[#a855f7]" />
                  {stylist.name}
                </div>
              ))}

              {slots.map((slot) => (
                <React.Fragment key={slot}>
                  <div className="border-t border-white/5 text-[11px] text-gray-500 pr-2 flex items-start justify-end pt-2 bg-[#0a0e1a] font-semibold sticky left-0 z-20" style={{ gridColumn: 1 }}>
                    {minutesToTimeLabel(slot)}
                  </div>
                  {scheduleStylists.map((stylist, index) => {
                    // Check if this stylist has time off for this slot
                    const timeOff = scheduleTimeOff.find(
                      (block) =>
                        block.stylist_id === stylist.id &&
                        parseTimeToMinutes(block.start_time) <= slot &&
                        parseTimeToMinutes(block.end_time) > slot
                    );
                    const bookingAtSlot = scheduleBookings.some((booking) => {
                      if (booking.stylist_id !== stylist.id) return false;
                      const start = parseTimeToMinutes(booking.start_time);
                      const end = parseTimeToMinutes(booking.end_time);
                      return start <= slot && end > slot;
                    });
                    const stylistStart = parseTimeToMinutes(stylist.work_start);
                    const stylistEnd = parseTimeToMinutes(stylist.work_end);
                    const isWithinHours = slot >= stylistStart && slot < stylistEnd;
                    if (timeOff) {
                      return (
                        <div
                          key={`${stylist.id}-${slot}-timeoff`}
                          className="border-t border-white/5 bg-red-500/10 text-red-400 text-[11px] flex items-center justify-center border-l border-red-500/20"
                          style={{ gridColumn: index + 2 }}
                        >
                          Time off
                        </div>
                      );
                    }
                    if (bookingAtSlot) {
                      return null;
                    }
                    return (
                      <div
                        key={`${stylist.id}-${slot}`}
                        className={`border-t border-white/5 ${isWithinHours ? 'bg-[#0a0e1a] hover:bg-[#00d4ff]/5 transition-colors' : 'bg-white/[0.02]'}`}
                        style={{ gridColumn: index + 2 }}
                        onDragOver={isWithinHours ? (event) => event.preventDefault() : undefined}
                        onDragEnter={isWithinHours ? (event) => {
                          event.currentTarget.style.backgroundColor = 'rgba(0, 212, 255, 0.2)';
                        } : undefined}
                        onDragLeave={isWithinHours ? (event) => {
                          event.currentTarget.style.backgroundColor = '';
                        } : undefined}
                        onDrop={isWithinHours ? (event) => {
                          event.preventDefault();
                          event.currentTarget.style.backgroundColor = '';
                          const bookingId = event.dataTransfer.getData("text/plain");
                          if (bookingId) {
                            const booking = scheduleBookings.find(b => b.id === bookingId);
                            if (!booking) return;
                            const duration =
                              parseTimeToMinutes(booking.end_time) -
                              parseTimeToMinutes(booking.start_time);
                            if (slot < stylistStart || slot + duration > stylistEnd) {
                              alert("Cannot drop: the booking would extend outside the stylist's working hours.");
                              return;
                            }
                            rescheduleBooking(bookingId, stylist.id, slot);
                          }
                        } : undefined}
                      />
                    );
                  })}
                </React.Fragment>
              ))}

              {scheduleBookings.map((booking) => {
                const startMinutes = parseTimeToMinutes(booking.start_time);
                const endMinutes = parseTimeToMinutes(booking.end_time);
                const rowStart = Math.floor((startMinutes - timeRange.start) / SLOT_MINUTES) + 2;
                const rowSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / SLOT_MINUTES));
                const stylistIndex = scheduleStylists.findIndex(
                  (stylist) => stylist.id === booking.stylist_id
                );
                if (stylistIndex === -1) return null;
                const stylist = scheduleStylists[stylistIndex];
                const normalizedFilter = styleFilter.trim().toLowerCase();
                const matchesStyle =
                  !normalizedFilter ||
                  (booking.preferred_style_text || "").toLowerCase().includes(normalizedFilter);
                return (
                  <div
                    key={booking.id}
                    draggable={stylist.active}
                    onDragStart={(event: React.DragEvent<HTMLDivElement>) => {
                      const dragImage = document.createElement('div');
                      dragImage.style.width = '20px';
                      dragImage.style.height = '20px';
                      dragImage.style.background = 'linear-gradient(135deg, #00d4ff, #a855f7)';
                      dragImage.style.borderRadius = '4px';
                      document.body.appendChild(dragImage);
                      event.dataTransfer.setDragImage(dragImage, 10, 10);
                      event.dataTransfer.setData("text/plain", booking.id);
                      setTimeout(() => document.body.removeChild(dragImage), 0);
                    }}
                    onClick={() => setSelectedBooking(booking)}
                    className={`bg-gradient-to-r from-[#00d4ff]/20 to-[#a855f7]/20 backdrop-blur-sm text-white text-xs rounded-2xl px-3 py-2 shadow-lg shadow-[#00d4ff]/10 border border-[#00d4ff]/30 z-20 cursor-pointer active:cursor-grabbing hover:border-[#00d4ff]/50 hover:scale-[1.02] transition-all ${
                      normalizedFilter && !matchesStyle ? "opacity-30" : ""
                    }`}
                    style={{
                      gridColumn: stylistIndex + 2,
                      gridRow: `${rowStart} / span ${rowSpan}`,
                      minWidth: 0,
                    }}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-semibold text-xs text-white">
                          {booking.secondary_service_name
                            ? `${booking.service_name} + ${booking.secondary_service_name}`
                            : booking.service_name}
                        </div>
                        <div className="text-[10px] text-gray-300">
                          {booking.start_time}–{booking.end_time}
                        </div>
                        <div className="text-[10px] text-gray-300">
                          {booking.customer_name || "Guest"}
                        </div>
                      </div>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          cancelBooking(booking.id);
                        }}
                        className="px-2 py-1 text-[9px] bg-red-500/20 border border-red-500/30 text-red-400 rounded hover:bg-red-500/30 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </motion.div>
      </section>
    </div>
  );
}
