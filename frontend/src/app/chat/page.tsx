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
  end_time: string;   // ISO
};

type HoldResponse = {
  booking_id: string;
  status: "HOLD";
  hold_expires_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const DEFAULT_TZ_OFFSET_MINUTES = Number(process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES ?? "0");

function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function formatMoneyINRFromCents(priceCents: number) {
  // If your backend uses cents, treat as generic minor units.
  // You can swap to INR formatting later once you standardize currency.
  const value = priceCents / 100;
  return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function toLocalDateInputValue(d = new Date()) {
  // YYYY-MM-DD in local time
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatTime(iso: string) {
  const dt = new Date(iso);
  return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatTimeRange(startIso: string, endIso: string) {
  return `${formatTime(startIso)} – ${formatTime(endIso)}`;
}

function formatDateLabel(dateStr: string) {
  if (!dateStr) return "Select a date";
  const [yyyy, mm, dd] = dateStr.split("-").map(Number);
  if (!yyyy || !mm || !dd) return "Select a date";
  const dt = new Date(yyyy, mm - 1, dd);
  return dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    { id: uid(), role: "assistant", text: "Welcome to Bishops Tempe! I can help you book an appointment. What would you like today?" },
  ]);

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

  const [confirmLoading, setConfirmLoading] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const [name, setName] = useState("Aryan");

  const bottomRef = useRef<HTMLDivElement | null>(null);

  const tzOffset = useMemo(() => {
    // Prefer env override for MVP; fallback to browser offset (note: browser offset is opposite sign)
    // Browser: minutes behind UTC. We need minutes ahead of UTC.
    const browserAhead = -new Date().getTimezoneOffset();
    return Number.isFinite(DEFAULT_TZ_OFFSET_MINUTES) && DEFAULT_TZ_OFFSET_MINUTES !== 0
      ? DEFAULT_TZ_OFFSET_MINUTES
      : browserAhead;
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, servicesLoading, slotsLoading, holdLoading, confirmLoading]);

  // Load services on mount
  useEffect(() => {
    const load = async () => {
      setServicesLoading(true);
      setServicesError(null);
      try {
        const res = await fetch(`${API_BASE}/services`);
        if (!res.ok) throw new Error(`Failed to load services (${res.status})`);
        const data: Service[] = await res.json();
        setServices(data);
      } catch (e: any) {
        setServicesError(e?.message ?? "Failed to load services");
      } finally {
        setServicesLoading(false);
      }
    };
    load();
  }, []);

  async function fetchAvailability(serviceId: number, date: string) {
    setSlotsLoading(true);
    setSlotsError(null);
    setSlots([]);
    try {
      const url = new URL(`${API_BASE}/availability`);
      url.searchParams.set("service_id", String(serviceId));
      url.searchParams.set("date", date);
      url.searchParams.set("tz_offset_minutes", String(tzOffset));

      const res = await fetch(url.toString());
      if (!res.ok) throw new Error(`Failed to load availability (${res.status})`);
      const data: Slot[] = await res.json();
      setSlots(data);

      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: data.length
            ? `Here are the available times for ${formatDateLabel(dateStr)}. Tap one to hold it.`
            : `No times found for ${formatDateLabel(dateStr)}. Want to try another day?`,
        },
      ]);
    } catch (e: any) {
      setSlotsError(e?.message ?? "Failed to load availability");
      setMessages((prev) => [...prev, { id: uid(), role: "assistant", text: "Sorry — I couldn’t load availability." }]);
    } finally {
      setSlotsLoading(false);
    }
  }

  function onSelectService(svc: Service) {
    setSelectedService(svc);
    setSlots([]);
    setHold(null);
    setHeldSlot(null);
    setConfirmed(false);
    setHoldError(null);
    setConfirmError(null);

    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", text: svc.name },
      { id: uid(), role: "assistant", text: `Great choice. What date works for your ${svc.name}?` },
    ]);
  }

  function onAskAvailability() {
    if (!selectedService) return;
    setMessages((prev) => [...prev, { id: uid(), role: "user", text: `Date: ${dateStr}` }]);
    fetchAvailability(selectedService.id, dateStr);
  }

  async function onHoldSlot(slot: Slot) {
    if (!selectedService) return;

    setHoldLoading(true);
    setHoldError(null);
    setHold(null);
    setHeldSlot(null);
    setConfirmed(false);
    setConfirmError(null);

    const start = new Date(slot.start_time);
    const hh = String(start.getHours()).padStart(2, "0");
    const mm = String(start.getMinutes()).padStart(2, "0");
    const startHHMM = `${hh}:${mm}`;

    setMessages((prev) => [
      ...prev,
      { id: uid(), role: "user", text: `Book ${selectedService.name} at ${formatTime(slot.start_time)} with ${slot.stylist_name}` },
      { id: uid(), role: "assistant", text: "Got it — holding that time for a few minutes. What name should I use for the booking?" },
    ]);

    try {
      const res = await fetch(`${API_BASE}/bookings/hold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_id: selectedService.id,
          date: dateStr,
          start_time: startHHMM,
          stylist_id: slot.stylist_id,
          customer_name: name,
          tz_offset_minutes: tzOffset,
        }),
      });

      if (res.status === 409) {
        const msg = await res.json().catch(() => ({}));
        throw new Error(msg?.detail ?? "Slot not available");
      }
      if (!res.ok) throw new Error(`Hold failed (${res.status})`);

      const data: HoldResponse = await res.json();
      setHold(data);
      setHeldSlot(slot);

      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          text: "All set. I’m holding the slot. Tap “Confirm booking” to finalize.",
        },
      ]);

      // Refresh availability to hide held slot
      fetchAvailability(selectedService.id, dateStr);
    } catch (e: any) {
      setHoldError(e?.message ?? "Failed to hold slot");
      setHeldSlot(null);
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: `Sorry — I couldn’t hold that slot. ${e?.message ?? ""}`.trim() },
      ]);
    } finally {
      setHoldLoading(false);
    }
  }

  async function onConfirm() {
    if (!hold) return;
    setConfirmLoading(true);
    setConfirmError(null);

    try {
      const res = await fetch(`${API_BASE}/bookings/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ booking_id: hold.booking_id }),
      });

      if (res.status === 409) {
        const msg = await res.json().catch(() => ({}));
        throw new Error(msg?.detail ?? "Could not confirm booking");
      }
      if (!res.ok) throw new Error(`Confirm failed (${res.status})`);

      setConfirmed(true);
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: `✅ You’re booked! Your booking ID is ${hold.booking_id}.` },
      ]);
    } catch (e: any) {
      setConfirmError(e?.message ?? "Failed to confirm");
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", text: `Sorry — confirmation failed. ${e?.message ?? ""}`.trim() },
      ]);
    } finally {
      setConfirmLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 via-neutral-50 to-white">
      <div className="mx-auto max-w-3xl px-4 py-6">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-neutral-500">Convo Salon</p>
            <h1 className="text-3xl font-semibold text-neutral-900">Bishops Tempe</h1>
            <p className="text-sm text-neutral-600">Book your appointment in a few steps.</p>
          </div>
          <div className="rounded-full border bg-white px-3 py-1 text-xs text-neutral-600">Chat booking MVP</div>
        </header>

        <div className="rounded-2xl border bg-white shadow-sm">
          {/* Messages */}
          <div className="h-[60vh] overflow-y-auto p-4">
            <div className="space-y-3">
              {messages.map((m, index) => (
                <div
                  key={m.id}
                  className={[
                    "flex",
                    m.role === "user" ? "justify-end" : "justify-start",
                  ].join(" ")}
                  style={{
                    animation: "fadeUp 240ms ease both",
                    animationDelay: `${Math.min(index, 6) * 40}ms`,
                  }}
                >
                  <div
                    className={[
                      "max-w-[80%] rounded-2xl px-4 py-2 text-sm transition",
                      m.role === "user"
                        ? "bg-black text-white"
                        : "bg-neutral-100 text-neutral-900",
                    ].join(" ")}
                  >
                    {m.text}
                  </div>
                </div>
              ))}

              {(servicesLoading || slotsLoading || holdLoading || confirmLoading) && (
                <div className="text-sm text-neutral-500">Working…</div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Controls */}
          <div className="border-t p-4 space-y-4">
            <div
              className="rounded-2xl border bg-neutral-50/70 p-4"
              style={{ animation: "fadeIn 300ms ease both" }}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-neutral-900">Your booking</h2>
                {confirmed ? (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
                    Confirmed
                  </span>
                ) : hold ? (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
                    On hold
                  </span>
                ) : (
                  <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-xs text-neutral-600">
                    Draft
                  </span>
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
              {hold && (
                <div className="mt-3 text-xs text-amber-700">
                  Holding this slot for a few minutes.
                </div>
              )}
              {confirmed && hold && heldSlot && (
                <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                  You’re all set for {formatDateLabel(dateStr)} at {formatTimeRange(heldSlot.start_time, heldSlot.end_time)}.
                </div>
              )}
            </div>

            {/* Name */}
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">Customer name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-xl border px-3 py-2 text-sm"
                placeholder="Your name"
              />
            </div>

            {/* Services */}
            <div>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium">1) Choose a service</h2>
                {servicesError && <span className="text-xs text-red-600">{servicesError}</span>}
              </div>

              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {services.map((s, index) => (
                  <button
                    key={s.id}
                    onClick={() => onSelectService(s)}
                    className={[
                      "rounded-2xl border px-4 py-3 text-left text-sm transition hover:border-neutral-500",
                      selectedService?.id === s.id
                        ? "border-black bg-neutral-50"
                        : "border-neutral-200 bg-white",
                    ].join(" ")}
                    style={{
                      animation: "fadeUp 260ms ease both",
                      animationDelay: `${Math.min(index, 6) * 40}ms`,
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-medium text-neutral-900">{s.name}</div>
                      {selectedService?.id === s.id && (
                        <span className="rounded-full bg-black px-2 py-0.5 text-[10px] uppercase tracking-wide text-white">
                          Selected
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-neutral-600">
                      {s.duration_minutes} min · {formatMoneyINRFromCents(s.price_cents)}
                    </div>
                  </button>
                ))}
                {servicesLoading && (
                  <div className="text-sm text-neutral-500">Loading services…</div>
                )}
                {!servicesLoading && services.length === 0 && (
                  <div className="text-sm text-neutral-500">
                    No services yet. We’ll show options as soon as they’re available.
                  </div>
                )}
              </div>
            </div>

            {/* Date */}
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">2) Pick a date</h2>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="date"
                  value={dateStr}
                  onChange={(e) => {
                    setDateStr(e.target.value);
                    setHold(null);
                    setHeldSlot(null);
                    setConfirmed(false);
                    setConfirmError(null);
                  }}
                  className="rounded-xl border px-3 py-2 text-sm"
                />
                <button
                  onClick={onAskAvailability}
                  disabled={!selectedService || slotsLoading}
                  className="rounded-xl bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
                >
                  Check availability
                </button>
                <span className="text-xs text-neutral-500">Local time</span>
              </div>
              {slotsError && <div className="text-xs text-red-600">{slotsError}</div>}
            </div>

            {/* Slots */}
            <div>
              <h2 className="text-sm font-medium">3) Choose a slot</h2>
              {selectedService ? (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {slots.slice(0, 20).map((slot, index) => {
                    const isHeld =
                      heldSlot?.stylist_id === slot.stylist_id &&
                      heldSlot?.start_time === slot.start_time;
                    return (
                      <button
                        key={`${slot.stylist_id}_${slot.start_time}`}
                        onClick={() => onHoldSlot(slot)}
                        disabled={holdLoading || confirmLoading}
                        className={[
                          "rounded-2xl border px-3 py-3 text-left transition hover:border-neutral-500 disabled:opacity-50",
                          isHeld ? "border-black bg-neutral-50" : "border-neutral-200 bg-white",
                        ].join(" ")}
                        style={{
                          animation: "fadeUp 260ms ease both",
                          animationDelay: `${Math.min(index, 6) * 35}ms`,
                        }}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-medium text-neutral-900">
                            {formatTimeRange(slot.start_time, slot.end_time)}
                          </div>
                          {isHeld && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-700">
                              Held
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-xs text-neutral-600">{slot.stylist_name}</div>
                      </button>
                    );
                  })}
                  {!slotsLoading && slots.length === 0 && (
                    <div className="text-sm text-neutral-500">
                      No slots yet — pick a date and check availability.
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-2 text-sm text-neutral-500">Select a service first.</div>
              )}
              {holdError && <div className="mt-2 text-xs text-red-600">{holdError}</div>}
            </div>

            {/* Confirm */}
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">4) Confirm</h2>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={onConfirm}
                  disabled={!hold || confirmLoading || confirmed}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-50"
                >
                  Confirm booking
                </button>
                {hold && (
                  <div className="text-xs text-neutral-600">
                    Hold expires at: <span className="font-mono">{new Date(hold.hold_expires_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
              {confirmError && <div className="text-xs text-red-600">{confirmError}</div>}
              {confirmed && hold && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                  ✅ Confirmed. Booking ID: <span className="font-mono">{hold.booking_id}</span>
                </div>
              )}
            </div>

            <div className="text-xs text-neutral-500">
              Frontend only — backend endpoints handled by the API at <span className="font-mono">{API_BASE}</span>.
            </div>
          </div>
        </div>
      </div>
      <style jsx global>{`
        @keyframes fadeUp {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
