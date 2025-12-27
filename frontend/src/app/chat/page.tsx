"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

type Message = {
  id: string;
  role: Role;
  text: string;
};

type Service = {
  id: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
};

type Slot = {
  stylist_id: number;
  stylist_name: string;
  start_time: string; // ISO
  end_time: string; // ISO
};

type HoldResponse = {
  booking_id: string;
  status: "HOLD";
  hold_expires_at: string;
};

type DemoMode = "auto" | "on" | "off";

type Chip = {
  id: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const DEFAULT_TZ_OFFSET_MINUTES = Number(
  process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES ?? "0"
);
const DEMO_MODE: DemoMode =
  (process.env.NEXT_PUBLIC_DEMO_MODE as DemoMode) ?? "auto";

const DEMO_SERVICES: Service[] = [
  { id: 1, name: "Men’s Haircut", duration_minutes: 30, price_cents: 3500 },
  { id: 2, name: "Women’s Haircut", duration_minutes: 45, price_cents: 5500 },
  { id: 3, name: "Beard Trim", duration_minutes: 15, price_cents: 2000 },
  { id: 4, name: "Hair Color", duration_minutes: 90, price_cents: 12000 },
];

const DEMO_STYLISTS = [
  { id: 101, name: "Alex" },
  { id: 102, name: "Jamie" },
];

function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function formatMoneyFromCents(priceCents: number) {
  const value = priceCents / 100;
  return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function toLocalDateInputValue(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatTime(iso: string) {
  const dt = new Date(iso);
  return dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatTimeRange(startIso: string, endIso: string) {
  return `${formatTime(startIso)} – ${formatTime(endIso)}`;
}

function formatDateLabel(dateStr: string) {
  if (!dateStr) return "Select a date";
  const [yyyy, mm, dd] = dateStr.split("-").map(Number);
  if (!yyyy || !mm || !dd) return "Select a date";
  const dt = new Date(yyyy, mm - 1, dd);
  return dt.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function slotChipLabel(slot: Slot) {
  return `${formatTime(slot.start_time)} (${slot.stylist_name})`;
}

function buildDemoSlots(dateStr: string, serviceDurationMinutes: number): Slot[] {
  const baseLocal = new Date(`${dateStr}T10:00:00`);
  const slots: Slot[] = [];
  for (let i = 0; i < 8; i++) {
    const start = new Date(baseLocal.getTime() + i * 60 * 60 * 1000); // every hour
    const end = new Date(start.getTime() + serviceDurationMinutes * 60 * 1000);
    const stylist = DEMO_STYLISTS[i % DEMO_STYLISTS.length];
    slots.push({
      stylist_id: stylist.id,
      stylist_name: stylist.name,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
    });
  }
  return slots;
}

function demoHold(): HoldResponse {
  const expires = new Date(Date.now() + 5 * 60 * 1000);
  return {
    booking_id: `demo_${Math.random().toString(16).slice(2)}_${Date.now()}`,
    status: "HOLD",
    hold_expires_at: expires.toISOString(),
  };
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: uid(),
      role: "assistant",
      text: "Welcome to Bishops Tempe! I can help you book an appointment. What would you like today?",
    },
  ]);

  const [chips, setChips] = useState<Chip[]>([]);

  const [services, setServices] = useState<Service[]>([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [servicesError, setServicesError] = useState<string | null>(null);

  const [selectedService, setSelectedService] = useState<Service | null>(null);

  const [dateStr, setDateStr] = useState<string>(toLocalDateInputValue());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsError, setSlotsError] = useState<string | null>(null);

  const [hold, setHold] = useState<HoldResponse | null>(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [holdError, setHoldError] = useState<string | null>(null);
  const [heldSlot, setHeldSlot] = useState<Slot | null>(null);
  const holdRef = useRef<HoldResponse | null>(null);

  const [confirmLoading, setConfirmLoading] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const [name, setName] = useState("Aryan");
  const [usingDemo, setUsingDemo] = useState<boolean>(DEMO_MODE === "on");

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const nameRef = useRef(name);

  const tzOffset = useMemo(() => {
    const browserAhead = -new Date().getTimezoneOffset();
    return Number.isFinite(DEFAULT_TZ_OFFSET_MINUTES) &&
      DEFAULT_TZ_OFFSET_MINUTES !== 0
      ? DEFAULT_TZ_OFFSET_MINUTES
      : browserAhead;
  }, []);

  // ---------- Chat helpers ----------
  function assistantSay(text: string, nextChips: Chip[] = []) {
    setMessages((prev) => [...prev, { id: uid(), role: "assistant", text }]);
    setChips(nextChips);
  }

  function userSay(text: string) {
    setMessages((prev) => [...prev, { id: uid(), role: "user", text }]);
  }

  function clearChips() {
    setChips([]);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, servicesLoading, slotsLoading, holdLoading, confirmLoading]);

  useEffect(() => {
    nameRef.current = name;
  }, [name]);

  useEffect(() => {
    holdRef.current = hold;
  }, [hold]);

  // ---------- Demo/Backend ----------
  async function isBackendUp(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
      return res.ok;
    } catch {
      return false;
    }
  }

  async function decideDemoMode(): Promise<boolean> {
    if (DEMO_MODE === "on") return true;
    if (DEMO_MODE === "off") return false;
    const up = await isBackendUp();
    return !up;
  }

  async function getServices(): Promise<Service[]> {
    const demo = await decideDemoMode();
    setUsingDemo(demo);
    if (demo) return DEMO_SERVICES;

    const res = await fetch(`${API_BASE}/services`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed to load services (${res.status})`);
    const data: Service[] = await res.json();
    return data.length ? data : DEMO_SERVICES;
  }

  async function getAvailability(service: Service, date: string): Promise<Slot[]> {
    const demo = await decideDemoMode();
    setUsingDemo(demo);
    if (demo) return buildDemoSlots(date, service.duration_minutes);

    const url = new URL(`${API_BASE}/availability`);
    url.searchParams.set("service_id", String(service.id));
    url.searchParams.set("date", date);
    url.searchParams.set("tz_offset_minutes", String(tzOffset));

    const res = await fetch(url.toString(), { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed to load availability (${res.status})`);
    return (await res.json()) as Slot[];
  }

  async function holdBooking(service: Service, slot: Slot): Promise<HoldResponse> {
    const demo = await decideDemoMode();
    setUsingDemo(demo);
    if (demo) return demoHold();

    const start = new Date(slot.start_time);
    const hh = String(start.getHours()).padStart(2, "0");
    const mm = String(start.getMinutes()).padStart(2, "0");
    const startHHMM = `${hh}:${mm}`;

    const res = await fetch(`${API_BASE}/bookings/hold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service_id: service.id,
        date: dateStr,
        start_time: startHHMM,
        stylist_id: slot.stylist_id,
        customer_name: nameRef.current.trim() || null,
        tz_offset_minutes: tzOffset,
      }),
    });

    if (res.status === 409) {
      const msg = await res.json().catch(() => ({}));
      throw new Error(msg?.detail ?? "Slot not available");
    }
    if (!res.ok) throw new Error(`Hold failed (${res.status})`);
    return (await res.json()) as HoldResponse;
  }

  async function confirmBooking(bookingId: string): Promise<void> {
    const demo = await decideDemoMode();
    setUsingDemo(demo);
    if (demo) return;

    const res = await fetch(`${API_BASE}/bookings/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bookingId }),
    });

    if (res.status === 409) {
      const msg = await res.json().catch(() => ({}));
      throw new Error(msg?.detail ?? "Could not confirm booking");
    }
    if (!res.ok) throw new Error(`Confirm failed (${res.status})`);
  }

  // ---------- Flow actions ----------
  function onSelectService(svc: Service) {
    setSelectedService(svc);
    setSlots([]);
    setHold(null);
    holdRef.current = null;
    setHeldSlot(null);
    setConfirmed(false);
    setHoldError(null);
    setConfirmError(null);

    userSay(svc.name);

    const today = new Date();
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const todayStr = toLocalDateInputValue(today);
    const tomorrowStr = toLocalDateInputValue(tomorrow);

    assistantSay(`Great choice. What date works for your ${svc.name}?`, [
      {
        id: "date_today",
        label: "Today",
        onClick: () => {
          setDateStr(todayStr);
          userSay(`Date: ${todayStr}`);
          fetchAvailability(svc, todayStr);
        },
      },
      {
        id: "date_tomorrow",
        label: "Tomorrow",
        onClick: () => {
          setDateStr(tomorrowStr);
          userSay(`Date: ${tomorrowStr}`);
          fetchAvailability(svc, tomorrowStr);
        },
      },
      {
        id: "date_pick",
        label: "Pick a date below ↓",
        onClick: () => clearChips(),
      },
    ]);
  }

  async function fetchAvailability(service: Service, date: string) {
    setSlotsLoading(true);
    setSlotsError(null);
    setSlots([]);
    setHold(null);
    holdRef.current = null;
    setHeldSlot(null);
    setConfirmed(false);
    setConfirmError(null);
    setHoldError(null);

    try {
      const data = await getAvailability(service, date);
      setSlots(data);

      if (data.length) {
        assistantSay(
          `Here are the available times for ${formatDateLabel(date)}. Tap one to hold it.`,
          data.slice(0, 8).map((slot) => ({
            id: `slot_${slot.stylist_id}_${slot.start_time}`,
            label: slotChipLabel(slot),
            onClick: () => onHoldSlot(service, slot),
          }))
        );
      } else {
        assistantSay(
          `No times found for ${formatDateLabel(date)}. Want to try another day?`,
          [
            {
              id: "try_tomorrow",
              label: "Try tomorrow",
              onClick: () => {
                const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
                const tStr = toLocalDateInputValue(tomorrow);
                setDateStr(tStr);
                userSay(`Date: ${tStr}`);
                fetchAvailability(service, tStr);
              },
            },
          ]
        );
      }
    } catch (e: any) {
      setSlotsError(e?.message ?? "Failed to load availability");
      assistantSay("Sorry — I couldn’t load availability.");
    } finally {
      setSlotsLoading(false);
    }
  }

  async function onHoldSlot(service: Service, slot: Slot) {
    setHoldLoading(true);
    setHoldError(null);
    setHold(null);
    holdRef.current = null;
    setHeldSlot(null);
    setConfirmed(false);
    setConfirmError(null);

    userSay(`Book ${service.name} at ${formatTime(slot.start_time)} with ${slot.stylist_name}`);
    assistantSay("Got it — holding that time. Tap Confirm to finalize.", []);

    try {
      const data = await holdBooking(service, slot);
      setHold(data);
      holdRef.current = data;
      setHeldSlot(slot);

      assistantSay("✅ Slot held. Ready to confirm?", [
        {
          id: "confirm_chip",
          label: "Confirm booking",
          onClick: () => onConfirm(),
        },
      ]);
    } catch (e: any) {
      setHoldError(e?.message ?? "Failed to hold slot");
      assistantSay(`Sorry — I couldn’t hold that slot. ${(e?.message ?? "").trim()}`);
    } finally {
      setHoldLoading(false);
    }
  }

  async function onConfirm() {
    const activeHold = holdRef.current;
    if (!activeHold) {
      assistantSay("Please hold a slot before confirming.");
      return;
    }
    setConfirmLoading(true);
    setConfirmError(null);

    userSay("Confirm");

    try {
      await confirmBooking(activeHold.booking_id);
      setConfirmed(true);
      assistantSay(`✅ You’re booked! Your booking ID is ${activeHold.booking_id}.`, []);
    } catch (e: any) {
      setConfirmError(e?.message ?? "Failed to confirm");
      assistantSay(`Sorry — confirmation failed. ${(e?.message ?? "").trim()}`);
    } finally {
      setConfirmLoading(false);
    }
  }

  // ---------- Initial load: show service chips ----------
  useEffect(() => {
    const load = async () => {
      setServicesLoading(true);
      setServicesError(null);
      try {
        const data = await getServices();
        setServices(data);

        assistantSay(
          "What service would you like to book?",
          data.map((svc) => ({
            id: `svc_${svc.id}`,
            label: svc.name,
            onClick: () => onSelectService(svc),
          }))
        );
      } catch (e: any) {
        setServicesError(e?.message ?? "Failed to load services");
      } finally {
        setServicesLoading(false);
      }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- UI ----------
  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 via-neutral-50 to-white">
      <div className="mx-auto max-w-3xl px-4 py-6">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-neutral-500">Convo Salon</p>
            <h1 className="text-3xl font-semibold text-neutral-900">Bishops Tempe</h1>
            <p className="text-sm text-neutral-600">Book your appointment in a few steps.</p>
          </div>

          <div className="flex items-center gap-2">
            {usingDemo && (
              <div className="rounded-full border bg-white px-3 py-1 text-xs text-neutral-600">
                Demo mode
              </div>
            )}
            <div className="rounded-full border bg-white px-3 py-1 text-xs text-neutral-600">
              Chat booking MVP
            </div>
          </div>
        </header>

        <div className="rounded-2xl border bg-white shadow-sm">
          {/* Messages */}
          <div className="h-[60vh] overflow-y-auto p-4">
            <div className="space-y-3">
              {messages.map((m, index) => (
                <div
                  key={m.id}
                  className={["flex", m.role === "user" ? "justify-end" : "justify-start"].join(" ")}
                  style={{
                    animation: "fadeUp 240ms ease both",
                    animationDelay: `${Math.min(index, 6) * 40}ms`,
                  }}
                >
                  <div
                    className={[
                      "max-w-[80%] rounded-2xl px-4 py-2 text-sm transition",
                      m.role === "user" ? "bg-black text-white" : "bg-neutral-100 text-neutral-900",
                    ].join(" ")}
                  >
                    {m.text}
                  </div>
                </div>
              ))}

              {chips.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {chips.map((c) => (
                    <button
                      key={c.id}
                      onClick={c.onClick}
                      disabled={c.disabled}
                      className="rounded-full border bg-white px-3 py-1.5 text-sm text-neutral-900 shadow-sm hover:bg-neutral-50 disabled:opacity-50"
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}

              {(servicesLoading || slotsLoading || holdLoading || confirmLoading) && (
                <div className="text-sm text-neutral-500">Working…</div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Optional: keep your form UI for now */}
          <div className="border-t p-4 space-y-4">
            <div className="rounded-2xl border bg-neutral-50/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-neutral-900">Your booking</h2>
                {confirmed ? (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">Confirmed</span>
                ) : hold ? (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">On hold</span>
                ) : (
                  <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-xs text-neutral-600">Draft</span>
                )}
              </div>

              <div className="mt-3 grid gap-2 text-sm text-neutral-700">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-neutral-500">Name</span>
                  <span className="font-medium text-neutral-900">{name || "Add your name"}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-neutral-500">Service</span>
                  <span className="font-medium text-neutral-900">{selectedService?.name ?? "Select a service"}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-neutral-500">Date</span>
                  <span className="font-medium text-neutral-900">{formatDateLabel(dateStr)}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-neutral-500">Time</span>
                  <span className="font-medium text-neutral-900">
                    {heldSlot ? formatTimeRange(heldSlot.start_time, heldSlot.end_time) : "Choose a time"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-neutral-500">Stylist</span>
                  <span className="font-medium text-neutral-900">{heldSlot?.stylist_name ?? "Any available"}</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">Customer name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-xl border px-3 py-2 text-sm"
                placeholder="Your name"
              />
            </div>

            {servicesError && <div className="text-xs text-red-600">{servicesError}</div>}
            {slotsError && <div className="text-xs text-red-600">{slotsError}</div>}
            {holdError && <div className="text-xs text-red-600">{holdError}</div>}
            {confirmError && <div className="text-xs text-red-600">{confirmError}</div>}

            <div className="text-xs text-neutral-500">
              Frontend calling API at <span className="font-mono">{API_BASE}</span>.
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
