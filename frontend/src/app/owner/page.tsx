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
  customer_name: string | null;
  status: "HOLD" | "CONFIRMED" | "EXPIRED";
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
    updated_service?: {
      id: number;
      name: string;
      price_cents: number;
    };
  } | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TZ_OFFSET =
  Number(process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES) || -new Date().getTimezoneOffset();
const SLOT_MINUTES = 30;
const ROW_HEIGHT = 48;

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
  const [schedule, setSchedule] = useState<OwnerSchedule | null>(null);
  const [scheduleDate, setScheduleDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [scheduleLoading, setScheduleLoading] = useState(false);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const quickActions = useMemo(
    () => [
      "List services",
      "List stylists",
      "Add Keratin Treatment: 90 minutes, $200",
      "Add stylist Taylor 10am-6pm",
      "Increase Men's Haircut price to $40",
      "Remove Beard Trim",
      "Alex is off next Tuesday 2–6pm",
      "Jamie specializes in color + balayage",
    ],
    []
  );

  const scheduleStylists = schedule?.stylists ?? stylists;
  const scheduleBookings = schedule?.bookings ?? [];
  const scheduleTimeOff = schedule?.time_off ?? [];

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
    fetchSchedule();
  }, [scheduleDate]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
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

  function parseTimeToMinutes(value: string) {
    const [hour, minute] = value.split(":").map(Number);
    return hour * 60 + minute;
  }

  function minutesToTimeLabel(minutes: number) {
    const hour = Math.floor(minutes / 60);
    const min = minutes % 60;
    const suffix = hour >= 12 ? "PM" : "AM";
    const displayHour = ((hour + 11) % 12) + 1;
    return `${displayHour}:${min.toString().padStart(2, "0")} ${suffix}`;
  }

  function minutesToTimeValue(minutes: number) {
    const hour = Math.floor(minutes / 60);
    const min = minutes % 60;
    return `${hour.toString().padStart(2, "0")}:${min.toString().padStart(2, "0")}`;
  }

  const timeRange = useMemo(() => {
    if (scheduleStylists.length === 0) {
      return { start: 9 * 60, end: 19 * 60 };
    }
    const start = Math.min(
      ...scheduleStylists.map((stylist) => parseTimeToMinutes(stylist.work_start))
    );
    const end = Math.max(
      ...scheduleStylists.map((stylist) => parseTimeToMinutes(stylist.work_end))
    );
    return { start, end };
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
    await fetch(`${API_BASE}/owner/bookings/reschedule`, {
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
    fetchSchedule(scheduleDate);
  }

  async function cancelBooking(bookingId: string) {
    await fetch(`${API_BASE}/owner/bookings/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_id: bookingId }),
    });
    fetchSchedule(scheduleDate);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50">
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
          <div className="space-y-4">
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
                  onClick={() => sendMessage(action)}
                  className="px-3 py-2 rounded-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs transition-colors"
                >
                  {action}
                </button>
              ))}
            </div>
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
          <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">Current services</h2>
            <p className="text-xs text-gray-500 mb-4">Live view from the database.</p>
            <div className="space-y-3">
              {services.length === 0 && (
                <div className="text-xs text-gray-400">No services loaded yet.</div>
              )}
              {services.map((svc) => (
                <div key={svc.id} className="border border-gray-100 rounded-2xl p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-900">{svc.name}</p>
                      <p className="text-xs text-gray-500">
                        {svc.duration_minutes} min · {formatMoney(svc.price_cents)}
                      </p>
                    </div>
                    <span className="text-[11px] px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                      {svc.availability_rule || "none"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

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
                    <span className="text-[11px] px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                      {stylist.time_off_count} off
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </main>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-10">
        <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Schedule</h2>
              <p className="text-xs text-gray-500">
                Drag a booking to reschedule or move across stylists.
              </p>
            </div>
            <div className="flex items-center gap-2">
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
            <div
              className="grid border border-gray-100 rounded-2xl overflow-hidden"
              style={{
                minWidth: 720,
                gridTemplateColumns: `96px repeat(${scheduleStylists.length || 1}, minmax(160px, 1fr))`,
                gridTemplateRows: `48px repeat(${slots.length}, ${ROW_HEIGHT}px)`,
              }}
            >
              <div className="bg-gray-50 border-b border-gray-100" />
              {scheduleStylists.length === 0 && (
                <div className="col-span-1 bg-gray-50 border-b border-gray-100 text-xs text-gray-400 flex items-center justify-center">
                  No stylists
                </div>
              )}
              {scheduleStylists.map((stylist) => (
                <div
                  key={stylist.id}
                  className="bg-gray-50 border-b border-gray-100 text-xs font-medium text-gray-700 flex items-center justify-center"
                >
                  {stylist.name}
                </div>
              ))}

              {slots.map((slot) => (
                <React.Fragment key={slot}>
                  <div className="border-t border-gray-100 text-[11px] text-gray-400 pr-2 flex items-start justify-end pt-2">
                    {minutesToTimeLabel(slot)}
                  </div>
                  {scheduleStylists.map((stylist) => (
                    <div
                      key={`${stylist.id}-${slot}`}
                      className="border-t border-gray-100 bg-white"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={(event) => {
                        event.preventDefault();
                        const bookingId = event.dataTransfer.getData("text/plain");
                        if (bookingId) {
                          rescheduleBooking(bookingId, stylist.id, slot);
                        }
                      }}
                    />
                  ))}
                </React.Fragment>
              ))}

              {scheduleTimeOff.map((block) => {
                const startMinutes = parseTimeToMinutes(block.start_time);
                const endMinutes = parseTimeToMinutes(block.end_time);
                const rowStart = Math.floor((startMinutes - timeRange.start) / SLOT_MINUTES) + 2;
                const rowSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / SLOT_MINUTES));
                const stylistIndex = scheduleStylists.findIndex(
                  (stylist) => stylist.id === block.stylist_id
                );
                if (stylistIndex === -1) return null;
                return (
                  <div
                    key={`timeoff-${block.id}`}
                    className="bg-gray-200/80 text-gray-600 text-[11px] px-2 py-1 rounded-xl z-10"
                    style={{
                      gridColumn: stylistIndex + 2,
                      gridRow: `${rowStart} / span ${rowSpan}`,
                      margin: 4,
                    }}
                  >
                    Time off
                  </div>
                );
              })}

              {scheduleBookings.map((booking) => {
                const startMinutes = parseTimeToMinutes(booking.start_time);
                const endMinutes = parseTimeToMinutes(booking.end_time);
                const rowStart = Math.floor((startMinutes - timeRange.start) / SLOT_MINUTES) + 2;
                const rowSpan = Math.max(1, Math.ceil((endMinutes - startMinutes) / SLOT_MINUTES));
                const stylistIndex = scheduleStylists.findIndex(
                  (stylist) => stylist.id === booking.stylist_id
                );
                if (stylistIndex === -1) return null;
                return (
                  <div
                    key={booking.id}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", booking.id);
                    }}
                    className="bg-gray-900 text-white text-xs rounded-2xl px-3 py-2 shadow-sm z-20 cursor-grab active:cursor-grabbing"
                    style={{
                      gridColumn: stylistIndex + 2,
                      gridRow: `${rowStart} / span ${rowSpan}`,
                      margin: 4,
                    }}
                  >
                    <div className="font-medium">{booking.service_name}</div>
                    <div className="text-[11px] text-gray-200">
                      {booking.start_time}–{booking.end_time}
                    </div>
                    <div className="text-[11px] text-gray-300">
                      {booking.customer_name || "Guest"} · {booking.status}
                    </div>
                    <button
                      onClick={() => cancelBooking(booking.id)}
                      className="mt-2 text-[11px] text-gray-200 underline"
                    >
                      Cancel
                    </button>
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
