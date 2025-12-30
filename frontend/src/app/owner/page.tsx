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
    schedule?: OwnerSchedule;
    updated_service?: {
      id: number;
      name: string;
      price_cents: number;
    };
  } | null;
};

type OwnerTimeOffEntry = {
  start_time: string;
  end_time: string;
  date: string;
  reason?: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TZ_OFFSET =
  Number(process.env.NEXT_PUBLIC_TZ_OFFSET_MINUTES) || -new Date().getTimezoneOffset();
const SLOT_MINUTES = 30;
const ROW_HEIGHT = 60;

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
  const [rightView, setRightView] = useState<'services' | 'stylists'>('services');
  const [schedule, setSchedule] = useState<OwnerSchedule | null>(null);
  const [scheduleDate, setScheduleDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [timeOffOpenStylistId, setTimeOffOpenStylistId] = useState<number | null>(null);
  const [timeOffLoading, setTimeOffLoading] = useState(false);
  const [timeOffEntries, setTimeOffEntries] = useState<Record<number, OwnerTimeOffEntry[]>>({});

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const quickActions = useMemo(
    () => [
      "Add a service",
      "Change price of a service",
      "Remove a service",
      "Add a stylist",
      "Set stylist off time",
      "Add a specialization",
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
      if (schedule) {
        setSchedule({...schedule, stylists: data.stylists});
      }
    }
    if (data.schedule) {
      setSchedule(data.schedule);
      setScheduleDate(data.schedule.date);
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
        // Auto-refresh services or stylists if the message likely modified them
        if (text.toLowerCase().includes('service') || text.toLowerCase().includes('add') || text.toLowerCase().includes('remove') || text.toLowerCase().includes('change') || text.toLowerCase().includes('price')) {
          sendSilentMessage("List services");
        }
        if (text.toLowerCase().includes('stylist') || text.toLowerCase().includes('add') || text.toLowerCase().includes('set') || text.toLowerCase().includes('specialization')) {
          sendSilentMessage("List stylists");
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
    entries.forEach((entry) => {
      const start = parseTimeToMinutes(entry.start_time);
      const end = parseTimeToMinutes(entry.end_time);
      if (!byDate[entry.date]) byDate[entry.date] = [];
      byDate[entry.date].push({ start, end });
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
    const hour = Math.floor(minutes / 60);
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
          </div>

          {rightView === 'services' && (
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
                      {stylist.time_off_count} hours off
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
                            const service = services.find(s => s.name === booking.service_name);
                            if (!service) return;
                            const duration = service.duration_minutes;
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
                    className="bg-[#0b1c36] text-white text-xs rounded-2xl px-3 py-2 shadow-lg border border-blue-900/50 z-20 cursor-grab active:cursor-grabbing"
                    style={{
                      gridColumn: stylistIndex + 2,
                      gridRow: `${rowStart} / span ${rowSpan}`,
                      minWidth: 0,
                    }}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-semibold text-xs">{booking.service_name}</div>
                        <div className="text-[10px] text-gray-100">
                          {booking.start_time}–{booking.end_time}
                        </div>
                        <div className="text-[10px] text-gray-100">
                          {booking.customer_name || "Guest"}
                        </div>
                      </div>
                      <button
                        onClick={() => cancelBooking(booking.id)}
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
