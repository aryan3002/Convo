"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

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

type OwnerTimeOffEntry = {
  start_time: string;
  end_time: string;
  date: string;
  reason?: string | null;
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
  const [rightView, setRightView] = useState<'services' | 'stylists' | 'promos'>('services');
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
      }
    } finally {
      setScheduleLoading(false);
    }
  }

  useEffect(() => {
    fetchServices();
    fetchSchedule();
  }, [scheduleDate]);

  useEffect(() => {
    fetchPromos();
  }, []);

  useEffect(() => {
    if (services.length > 0) {
      fetchServiceBookingCounts();
    }
  }, [services]);

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
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50">
      {selectedBooking && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-md w-full animate-fadeIn relative">
            <button
              onClick={() => setSelectedBooking(null)}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Booking details</h3>
              <p className="text-xs text-gray-500">
                {selectedBooking.secondary_service_name
                  ? `${selectedBooking.service_name} + ${selectedBooking.secondary_service_name}`
                  : selectedBooking.service_name}{" "}
                · {selectedBooking.customer_name || "Guest"}
              </p>
            </div>
            {selectedBooking.preferred_style_text && (
              <p className="text-sm text-gray-700 whitespace-pre-wrap mb-4">
                {selectedBooking.preferred_style_text}
              </p>
            )}
            {selectedBooking.preferred_style_image_url && (
              <div className="rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
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
          </div>
        </div>
      )}

      {serviceBookingsModalOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-2xl w-full animate-fadeIn relative max-h-[80vh] flex flex-col">
            <button
              onClick={() => {
                setServiceBookingsModalOpen(false);
                setSelectedServiceBookings([]);
              }}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900">{selectedServiceName}</h3>
              <p className="text-xs text-gray-500">Upcoming bookings (next 7 days)</p>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2">
              {serviceBookingsLoading ? (
                <div className="text-sm text-gray-400 text-center py-8">Loading...</div>
              ) : selectedServiceBookings.length === 0 ? (
                <div className="text-sm text-gray-400 text-center py-8">No bookings found</div>
              ) : (
                selectedServiceBookings.map((booking) => {
                  const startDate = new Date(booking.start_time);
                  const endDate = new Date(booking.end_time);
                  const dateStr = startDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
                  const timeStr = `${startDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })} - ${endDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;
                  
                  return (
                    <div key={booking.id} className="border border-gray-100 rounded-xl p-3 hover:bg-gray-50 transition-colors">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="text-sm font-medium text-gray-900">{booking.customer_name || "Guest"}</p>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                              booking.status === "CONFIRMED"
                                ? "bg-green-50 text-green-600"
                                : "bg-yellow-50 text-yellow-600"
                            }`}>
                              {booking.status}
                            </span>
                          </div>
                          <p className="text-xs text-gray-600 mb-1">{dateStr} · {timeStr}</p>
                          <p className="text-xs text-gray-500">Stylist: {booking.stylist_name}</p>
                          {booking.customer_email && (
                            <p className="text-xs text-gray-400 mt-1">{booking.customer_email}</p>
                          )}
                          {booking.customer_phone && (
                            <p className="text-xs text-gray-400">{booking.customer_phone}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
      {promoWizardOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4">
          <div className="w-full max-w-2xl bg-white rounded-3xl shadow-2xl border border-gray-100 p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Add promotion</h3>
                <p className="text-xs text-gray-500">Guided setup with structured options.</p>
              </div>
              <button
                onClick={closePromoWizard}
                className="text-gray-400 hover:text-gray-600 text-sm"
              >
                Close
              </button>
            </div>

            <div className="mt-6 space-y-4">
              {promoWizardStep === 0 && (
                <div>
                  <p className="text-sm font-medium text-gray-900 mb-3">Promotion type</p>
                  <div className="flex flex-wrap gap-2">
                    {PROMO_TYPES.map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setPromoDraft((prev) => ({ ...prev, type: option.value }))
                        }
                        className={`px-4 py-2 rounded-full text-sm ${
                          promoDraft.type === option.value
                            ? "bg-gray-900 text-white"
                            : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                        }`}
                      >
                        {option.label}
                      </button>
                    ))}n                  </div>
                </div>
              )}

              {/* Step 1 removed - trigger point is auto-assigned by system */}

              {promoWizardStep === 1 && (
                <div>
                  <p className="text-sm font-medium text-gray-900 mb-3">Promotion copy</p>
                  <div className="flex gap-2 mb-4">
                    {(["ai", "custom"] as const).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setPromoDraft((prev) => ({ ...prev, copy_mode: mode }))}
                        className={`px-4 py-2 rounded-full text-sm ${
                          promoDraft.copy_mode === mode
                            ? "bg-gray-900 text-white"
                            : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                        }`}
                      >
                        {mode === "ai" ? "AI generated" : "Write my own"}
                      </button>
                    ))}
                  </div>
                  {promoDraft.copy_mode === "custom" && (
                    <textarea
                      value={promoDraft.custom_copy}
                      onChange={(e) =>
                        setPromoDraft((prev) => ({ ...prev, custom_copy: e.target.value }))
                      }
                      className="w-full rounded-2xl border border-gray-200 p-3 text-sm focus:ring-2 focus:ring-gray-200"
                      rows={3}
                      placeholder="Enter the exact promotional line (placeholders like {service_name} are ok)."
                    />
                  )}
                </div>
              )}

              {promoWizardStep === 2 && (
                <div>
                  <p className="text-sm font-medium text-gray-900 mb-3">Discount details</p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {PROMO_DISCOUNTS.map((option) => (
                      <button
                        key={option.value}
                        onClick={() =>
                          setPromoDraft((prev) => ({ ...prev, discount_type: option.value }))
                        }
                        className={`px-4 py-2 rounded-full text-sm ${
                          promoDraft.discount_type === option.value
                            ? "bg-gray-900 text-white"
                            : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                        }`}
                      >
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
                        className="flex-1 rounded-full border border-gray-200 px-4 py-2 text-sm"
                        placeholder={promoDraft.discount_type === "PERCENT" ? "Percent" : "Amount in USD"}
                        min={0}
                      />
                      <span className="text-xs text-gray-500">
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
                      className="w-full rounded-full border border-gray-200 px-4 py-2 text-sm"
                      placeholder="Optional perk description (e.g., free beard trim)"
                    />
                  )}
                </div>
              )}

              {promoWizardStep === 3 && (
                <div className="space-y-4">
                  {promoDraft.type === "SERVICE_COMBO_PROMO" && (
                    <div>
                      <p className="text-sm font-medium text-gray-900 mb-2">Service selection</p>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <select
                          value={promoDraft.service_id ?? ""}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({
                              ...prev,
                              service_id: e.target.value ? Number(e.target.value) : null,
                            }))
                          }
                          className="w-full rounded-full border border-gray-200 px-4 py-2 text-sm"
                        >
                          <option value="">Primary service</option>
                          {services.map((svc) => (
                            <option key={svc.id} value={svc.id}>
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
                          className="w-full rounded-full border border-gray-200 px-4 py-2 text-sm"
                        >
                          <option value="">Secondary service</option>
                          {services.map((svc) => (
                            <option key={svc.id} value={svc.id}>
                              {svc.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      {services.length === 0 && (
                        <p className="text-xs text-red-500 mt-2">
                          Add a service before creating a combo promotion.
                        </p>
                      )}
                    </div>
                  )}
                  {promoDraft.type === "SEASONAL_PROMO" && (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-gray-500">Start date</label>
                        <input
                          type="date"
                          value={promoDraft.start_at}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({ ...prev, start_at: e.target.value }))
                          }
                          className="w-full rounded-full border border-gray-200 px-3 py-2 text-sm"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-gray-500">End date</label>
                        <input
                          type="date"
                          value={promoDraft.end_at}
                          onChange={(e) =>
                            setPromoDraft((prev) => ({ ...prev, end_at: e.target.value }))
                          }
                          className="w-full rounded-full border border-gray-200 px-3 py-2 text-sm"
                        />
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-gray-500">Minimum spend (USD)</label>
                      <input
                        type="number"
                        value={promoDraft.min_spend}
                        onChange={(e) =>
                          setPromoDraft((prev) => ({ ...prev, min_spend: e.target.value }))
                        }
                        className="w-full rounded-full border border-gray-200 px-3 py-2 text-sm"
                        min={0}
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Usage limit per customer</label>
                      <input
                        type="number"
                        value={promoDraft.usage_limit}
                        onChange={(e) =>
                          setPromoDraft((prev) => ({ ...prev, usage_limit: e.target.value }))
                        }
                        className="w-full rounded-full border border-gray-200 px-3 py-2 text-sm"
                        min={0}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 mb-2 block">Valid days</label>
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
                          className={`px-3 py-1 rounded-full text-xs ${
                            promoDraft.valid_days.includes(day.value)
                              ? "bg-gray-900 text-white"
                              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
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
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">Activation</p>
                      <p className="text-xs text-gray-500">Enable or pause the promotion.</p>
                    </div>
                    <button
                      onClick={() =>
                        setPromoDraft((prev) => ({ ...prev, active: !prev.active }))
                      }
                      className={`px-4 py-2 rounded-full text-sm ${
                        promoDraft.active
                          ? "bg-green-600 text-white"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {promoDraft.active ? "Active" : "Paused"}
                    </button>
                  </div>
                </div>
              )}

              {promoWizardError && (
                <div className="rounded-xl bg-red-50 border border-red-100 text-red-700 text-xs px-3 py-2">
                  {promoWizardError}
                </div>
              )}
            </div>

            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={handlePromoBack}
                disabled={promoWizardStep === 0}
                className="px-4 py-2 rounded-full text-sm text-gray-600 border border-gray-200 disabled:opacity-50"
              >
                Back
              </button>
              {promoWizardStep < 4 ? (
                <button
                  onClick={handlePromoNext}
                  className="px-5 py-2 rounded-full bg-gray-900 text-white text-sm"
                >
                  Next
                </button>
              ) : (
                <button
                  onClick={handlePromoCreate}
                  disabled={promoSaving}
                  className="px-5 py-2 rounded-full bg-blue-600 text-white text-sm disabled:opacity-60"
                >
                  {promoSaving ? "Saving..." : "Create promotion"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Owner GPT</h1>
            <p className="text-sm text-gray-500">Service management console</p>
          </div>
          <span className="text-xs px-3 py-1 rounded-full bg-gray-100 text-gray-600">
            Internal only
          </span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid lg:grid-cols-[1.2fr_0.8fr] gap-6">
        <section className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
          <div className="space-y-4 max-h-96 overflow-y-auto">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm ${
                  msg.role === "assistant"
                    ? "bg-gray-100 text-gray-800"
                    : "bg-gray-900 text-white ml-auto"
                }`}
              >
                {msg.text}
              </div>
            ))}
            {isLoading && (
              <div className="text-sm text-gray-400">Thinking...</div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="mt-6">
            <p className="text-xs text-gray-500 mb-3">Quick actions</p>
            <div className="flex flex-wrap gap-2">
              {quickActions.map((action) => (
                <button
                  key={action}
                  onClick={() => {
                    if (action === "Add promotions") {
                      openPromoWizard();
                    } else {
                      sendMessage(action);
                    }
                  }}
                  className="px-3 py-2 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs transition-colors"
                >
                  {action}
                </button>
              ))}
            </div>
            {suggestedChips.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-400 mb-2">Suggested</p>
                <div className="flex flex-wrap gap-2">
                  {suggestedChips.map((chip) => (
                    <button
                      key={chip}
                      onClick={() => sendMessage(chip)}
                      className="px-3 py-2 rounded-full bg-blue-50 text-blue-700 text-xs hover:bg-blue-100 transition-colors"
                    >
                      {chip}
                    </button>
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
              className="flex-1 px-4 py-3 rounded-full border border-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-200"
            />
            <button
              onClick={() => sendMessage(inputValue)}
              className="px-5 py-3 rounded-full bg-gray-900 text-white text-sm font-medium hover:bg-gray-800 transition-colors"
            >
              Send
            </button>
          </div>
        </section>

        <aside className="space-y-6">
          <div className="flex gap-2">
            <button
              onClick={() => setRightView('services')}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                rightView === 'services'
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Services
            </button>
            <button
              onClick={() => setRightView('stylists')}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                rightView === 'stylists'
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Stylists
            </button>
            <button
              onClick={() => setRightView('promos')}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                rightView === 'promos'
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Promotions
            </button>
          </div>

          {rightView === 'services' && (
            <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
              <h2 className="text-sm font-semibold text-gray-900 mb-2">Current services</h2>
              <p className="text-xs text-gray-500 mb-4">Live view from the database.</p>
              <div className="space-y-3">
                {services.length === 0 && (
                  <div className="text-xs text-gray-400">No services loaded yet.</div>
                )}
                {services.map((svc) => {
                  const count = serviceBookingCounts[svc.id] || 0;
                  return (
                    <div key={svc.id} className="border border-gray-100 rounded-2xl p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{svc.name}</p>
                          <p className="text-xs text-gray-500">
                            {svc.duration_minutes} min · {formatMoney(svc.price_cents)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => count > 0 && fetchServiceBookings(svc.id, svc.name)}
                          disabled={count === 0}
                          className={`text-[11px] px-2 py-1 rounded-full transition-colors ${
                            count > 0
                              ? "bg-blue-50 text-blue-600 hover:bg-blue-100 cursor-pointer"
                              : "bg-gray-100 text-gray-500 cursor-default"
                          }`}
                        >
                          {count > 0 ? `${count} booking${count === 1 ? "" : "s"}` : "none"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {rightView === 'stylists' && (
            <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
              <h2 className="text-sm font-semibold text-gray-900 mb-2">Current stylists</h2>
              <p className="text-xs text-gray-500 mb-4">Hours, specialties, and time off.</p>
              <div className="space-y-3">
                {stylists.length === 0 && (
                  <div className="text-xs text-gray-400">No stylists loaded yet.</div>
                )}
              {stylists.map((stylist) => (
                <div key={stylist.id} className="border border-gray-100 rounded-2xl p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{stylist.name}</p>
                      <p className="text-xs text-gray-500">
                        {stylist.work_start}–{stylist.work_end}
                      </p>
                      <p className="text-xs text-gray-500">
                        {stylist.specialties.length > 0
                          ? stylist.specialties.join(", ")
                          : "No specialties"}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const next = timeOffOpenStylistId === stylist.id ? null : stylist.id;
                        setTimeOffOpenStylistId(next);
                        if (next) {
                          fetchTimeOffForStylist(stylist.id);
                        }
                      }}
                      className="text-[11px] px-2 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
                    >
                      {stylist.time_off_count} {stylist.time_off_count === 1 ? "day" : "days"} off
                    </button>
                  </div>
                  {timeOffOpenStylistId === stylist.id && (
                    <div className="mt-3 border border-gray-100 rounded-xl bg-gray-50 px-3 py-2 text-xs text-gray-600">
                      {timeOffLoading && !timeOffEntries[stylist.id] && (
                        <div className="text-gray-400">Loading time off...</div>
                      )}
                      {!timeOffLoading && (timeOffEntries[stylist.id]?.length ?? 0) === 0 && (
                        <div className="text-gray-400">No time off logged.</div>
                      )}
                      {timeOffEntries[stylist.id]?.length ? (
                        <div className="space-y-2">
                          {summarizeTimeOff(timeOffEntries[stylist.id]).map((entry) => (
                            <div key={`${stylist.id}-${entry.date}`} className="flex items-start justify-between gap-3">
                              <div>
                                <div className="text-[11px] font-semibold text-gray-700">
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
                              <div className="text-[11px] font-semibold text-gray-700">
                                {formatDuration(entry.totalMinutes)}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
          )}

          {rightView === 'promos' && (
            <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">Current promotions</h2>
                  <p className="text-xs text-gray-500">Live view from the database.</p>
                </div>
                <button
                  onClick={openPromoWizard}
                  className="px-3 py-2 rounded-full bg-gray-900 text-white text-xs"
                >
                  Add promotion
                </button>
              </div>
              <div className="space-y-3">
                {promos.length === 0 && (
                  <div className="text-xs text-gray-400">No promotions configured yet.</div>
                )}
                {promos.map((promo) => (
                  <div
                    key={promo.id}
                    className="border border-gray-100 rounded-2xl p-3 hover:border-gray-200 transition-colors"
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
                        <p className="text-sm font-medium text-gray-900">
                          {formatPromoType(promo.type)}
                        </p>
                        <p className="text-xs text-gray-500">
                          {formatPromoDiscount(promo)} · {formatPromoTrigger(promo.trigger_point)}
                        </p>
                        <p className="text-[11px] text-gray-400">
                          {formatPromoWindow(promo)}
                        </p>
                        {formatPromoServices(promo) && (
                          <p className="text-[11px] text-gray-500">
                            {formatPromoServices(promo)}
                          </p>
                        )}
                        <p className="text-[11px] text-gray-400">Promo ID: {promo.id}</p>
                      </div>
                      <span
                        className={`text-[11px] px-2 py-1 rounded-full ${
                          promo.active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {promo.active ? "Active" : "Paused"}
                      </span>
                    </div>
                    {promoActionOpenId === promo.id && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            togglePromoActive(promo);
                          }}
                          disabled={promoActionLoading}
                          className="px-3 py-1 rounded-full text-xs bg-gray-900 text-white disabled:opacity-60"
                        >
                          {promo.active ? "Pause" : "Activate"}
                        </button>
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            removePromo(promo.id);
                          }}
                          disabled={promoActionLoading}
                          className="px-3 py-1 rounded-full text-xs bg-red-600 text-white disabled:opacity-60"
                        >
                          Remove
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">Customer lookup</h2>
            <p className="text-xs text-gray-500 mb-4">Quick profile by email or phone.</p>
            <div className="flex gap-2">
              <input
                type="text"
                value={customerLookupIdentity}
                onChange={(e) => setCustomerLookupIdentity(e.target.value)}
                placeholder="Email or phone number"
                className="flex-1 px-4 py-2 rounded-full border border-gray-200 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-100"
                onKeyDown={(e) => e.key === "Enter" && lookupCustomer()}
              />
              <button
                onClick={lookupCustomer}
                disabled={!customerLookupIdentity.trim() || customerLookupLoading}
                className="px-4 py-2 rounded-full bg-blue-600 text-white text-xs font-medium hover:bg-blue-500 transition-colors disabled:opacity-60"
              >
                {customerLookupLoading ? "Searching..." : "Search"}
              </button>
            </div>
            {customerLookupError && (
              <p className="mt-3 text-xs text-red-600">{customerLookupError}</p>
            )}
            {customerProfile && (
              <div className="mt-4 rounded-2xl border border-gray-100 bg-gray-50/70 p-4 text-xs text-gray-700 space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-500">Customer</span>
                  <span className="font-medium">
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
                  <span className="font-medium">
                    {(customerProfile.average_spend_cents / 100).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Total bookings</span>
                  <span className="font-medium">
                    {customerProfile.total_bookings}
                  </span>
                </div>
              </div>
            )}
          </div>
        </aside>
      </main>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-10">
        <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Schedule</h2>
              <p className="text-xs text-gray-500">
                Drag a booking to reschedule or move across stylists. Time off shows in soft red,
                confirmed appointments in deep blue.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={styleFilter}
                onChange={(event) => setStyleFilter(event.target.value)}
                placeholder="Filter by style"
                className="px-3 py-2 rounded-full border border-gray-200 text-xs text-gray-600"
              />
              <button
                onClick={() => {
                  const date = new Date(scheduleDate);
                  date.setDate(date.getDate() - 1);
                  setScheduleDate(date.toISOString().split("T")[0]);
                }}
                className="px-3 py-2 rounded-full border border-gray-200 text-xs text-gray-600"
              >
                Prev
              </button>
              <input
                type="date"
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="px-3 py-2 rounded-full border border-gray-200 text-xs text-gray-600"
              />
              <button
                onClick={() => {
                  const date = new Date(scheduleDate);
                  date.setDate(date.getDate() + 1);
                  setScheduleDate(date.toISOString().split("T")[0]);
                }}
                className="px-3 py-2 rounded-full border border-gray-200 text-xs text-gray-600"
              >
                Next
              </button>
            </div>
          </div>

          <div className="mt-6 overflow-auto">

            {scheduleLoading && (
              <div className="text-xs text-gray-400 mb-4">Loading schedule...</div>
            )}
            <div className="flex items-center gap-3 text-[11px] text-gray-500 mb-2">
              <span className="inline-flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-red-100 border border-red-200" />
                Out of office
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-[#0b1c36]" />
                Appointment
              </span>
            </div>
            <div
              className="grid border border-gray-100 rounded-2xl overflow-hidden bg-gradient-to-b from-white to-gray-50"
              style={{
                minWidth: scheduleMinWidth,
                gridTemplateColumns: `140px repeat(${scheduleStylists.length || 1}, minmax(180px, 1fr))`,
                gridTemplateRows: `48px repeat(${slots.length}, ${ROW_HEIGHT}px)`,
              }}
            >
              <div className="bg-gray-50 border-b border-gray-100 sticky left-0 z-30 text-xs font-medium text-gray-700 flex items-center justify-center" style={{ gridColumn: 1 }}>
                Time
              </div>
              {scheduleStylists.length === 0 && (
                <div className="col-span-1 bg-gray-50 border-b border-gray-100 text-xs text-gray-400 flex items-center justify-center">
                  No stylists
                </div>
              )}
              {scheduleStylists.map((stylist, index) => (
                <div
                  key={stylist.id}
                  className="bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-700 flex items-center justify-center"
                  style={{ gridColumn: index + 2 }}
                >
                  {stylist.name}
                </div>
              ))}

              {slots.map((slot) => (
                <React.Fragment key={slot}>
                  <div className="border-t border-gray-100 text-[11px] text-gray-600 pr-2 flex items-start justify-end pt-2 bg-white font-semibold sticky left-0 z-20" style={{ gridColumn: 1 }}>
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
                          className="border-t border-gray-100 bg-red-50 text-red-700 text-[11px] flex items-center justify-center"
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
                        className={`border-t border-gray-100 ${isWithinHours ? 'bg-white hover:bg-blue-50/30 transition-colors' : 'bg-gray-200'}`}
                        style={{ gridColumn: index + 2 }}
                        onDragOver={isWithinHours ? (event) => event.preventDefault() : undefined}
                        onDragEnter={isWithinHours ? (event) => {
                          event.currentTarget.style.backgroundColor = 'rgba(59, 130, 246, 0.5)';
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
                    onDragStart={(event) => {
                      const dragImage = document.createElement('div');
                      dragImage.style.width = '20px';
                      dragImage.style.height = '20px';
                      dragImage.style.backgroundColor = '#0b1c36';
                      dragImage.style.borderRadius = '4px';
                      document.body.appendChild(dragImage);
                      event.dataTransfer.setDragImage(dragImage, 10, 10);
                      event.dataTransfer.setData("text/plain", booking.id);
                      setTimeout(() => document.body.removeChild(dragImage), 0);
                    }}
                    onClick={() => setSelectedBooking(booking)}
                    className={`bg-[#0b1c36] text-white text-xs rounded-2xl px-3 py-2 shadow-lg border border-blue-900/50 z-20 cursor-pointer active:cursor-grabbing ${
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
                        <div className="font-semibold text-xs">
                          {booking.secondary_service_name
                            ? `${booking.service_name} + ${booking.secondary_service_name}`
                            : booking.service_name}
                        </div>
                        <div className="text-[10px] text-gray-100">
                          {booking.start_time}–{booking.end_time}
                        </div>
                        <div className="text-[10px] text-gray-100">
                          {booking.customer_name || "Guest"}
                        </div>
                      </div>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          cancelBooking(booking.id);
                        }}
                        className="px-2 py-1 text-[9px] bg-red-600 text-white rounded hover:bg-red-700"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
