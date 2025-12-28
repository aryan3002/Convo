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
  start_time: string;
  end_time: string;
};

type HoldResponse = {
  booking_id: string;
  status: "HOLD";
  hold_expires_at: string;
};

type BookingMode = "chat" | "track";

type AIAction = {
  type: string;
  params?: Record<string, unknown>;
};

type ChatAPIResponse = {
  reply: string;
  action: AIAction | null;
};

type BookingTrack = {
  booking_id: string;
  service_name: string;
  stylist_name: string;
  customer_name: string | null;
  customer_email: string | null;
  start_time: string;
  end_time: string;
  status: string;
  created_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function uid(prefix = "m") {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function formatMoney(priceCents: number) {
  return (priceCents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function toLocalDateInputValue(d = new Date()) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDateLabel(dateStr: string) {
  if (!dateStr) return "";
  const [yyyy, mm, dd] = dateStr.split("-").map(Number);
  const dt = new Date(yyyy, mm - 1, dd);
  return dt.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export default function ChatPage() {
  const [mode, setMode] = useState<BookingMode>("chat");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: uid(),
      role: "assistant",
      text: "Hi there! 👋 I'm your booking assistant. Tell me what you're looking for and I'll help you find the perfect appointment.",
    },
  ]);

  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [services, setServices] = useState<Service[]>([]);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [dateStr, setDateStr] = useState<string>(toLocalDateInputValue());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);

  const [hold, setHold] = useState<HoldResponse | null>(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");

  const [trackEmail, setTrackEmail] = useState("");
  const [lastTrackedEmail, setLastTrackedEmail] = useState("");
  const [trackResults, setTrackResults] = useState<BookingTrack[]>([]);
  const [trackLoading, setTrackLoading] = useState(false);
  const [trackError, setTrackError] = useState("");

  const bottomRef = useRef<HTMLDivElement | null>(null);

  const tzOffset = useMemo(() => -new Date().getTimezoneOffset(), []);

  const appendAssistantMessage = (text: string) => {
    setMessages((prev) => [...prev, { id: uid(), role: "assistant", text }]);
  };

  const handleEmailFromChat = (text: string) => {
    const extracted = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    if (extracted) {
      const normalized = extracted[0].trim().toLowerCase();
      setCustomerEmail(normalized);
      setTrackEmail(normalized);
    }
  };

  const handleNameFromChat = (text: string) => {
    // Try to extract name when user provides it along with email or standalone
    // Look for patterns like "Name is X", "I'm X", "my name is X", or just a capitalized word before email
    const namePatterns = [
      /(?:my name is|name is|i'm|i am)\s+([A-Z][a-z]+)/i,
      /^([A-Z][a-z]+)\s+(?:and|,)/i,  // "Ash and ash@gmail.com"
      /^([A-Z][a-z]+)$/i,  // Just a name by itself
    ];
    for (const pattern of namePatterns) {
      const match = text.match(pattern);
      if (match && match[1]) {
        setCustomerName(match[1]);
        return;
      }
    }
  };

  function buildConversationContext() {
    return {
      selected_service: selectedService?.name,
      selected_service_id: selectedService?.id,
      selected_date: dateStr,
      customer_name: customerName || undefined,
      customer_email: customerEmail || undefined,
      held_slot: hold
        ? {
            booking_id: hold.booking_id,
            start_time: selectedSlot?.start_time,
            stylist_id: selectedSlot?.stylist_id,
          }
        : undefined,
      available_slots: slots.slice(0, 5).map((slot) => ({
        stylist_id: slot.stylist_id,
        start_time: slot.start_time,
        stylist_name: slot.stylist_name,
      })),
    };
  }

  function describeSlots(slotsToDescribe: Slot[], date: string) {
    if (!slotsToDescribe.length) return "No openings on " + formatDateLabel(date) + ". Try another date?";
    
    // Group slots by time to show all stylists available at each time
    const timeMap = new Map<string, string[]>();
    slotsToDescribe.forEach((s) => {
      const timeKey = formatTime(s.start_time);
      if (!timeMap.has(timeKey)) {
        timeMap.set(timeKey, []);
      }
      timeMap.get(timeKey)!.push(s.stylist_name);
    });
    
    // Format: "10:00 AM (Alex, Jamie), 10:30 AM (Alex)..."
    const timeEntries = Array.from(timeMap.entries());
    const formatted = timeEntries
      .map(([time, stylists]) => `${time} (${stylists.join(", ")})`)
      .join(" • ");
    
    return `Available on ${formatDateLabel(date)}:\n${formatted}`;
  }

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load services on mount
  useEffect(() => {
    async function loadServices() {
      try {
        const res = await fetch(`${API_BASE}/services`);
        if (res.ok) {
          const data = await res.json();
          setServices(data);
        }
      } catch (e) {
        console.error("Failed to load services:", e);
      }
    }
    loadServices();
  }, []);

  // Load slots when a service/date is selected
  useEffect(() => {
    if (selectedService && dateStr) {
      loadSlots(selectedService, dateStr);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedService, dateStr]);

  async function loadSlots(service: Service, date: string, options?: { announce?: boolean }) {
    setDateStr(date);
    setSlotsLoading(true);
    setSlots([]);
    setSelectedSlot(null);
    try {
      const url = new URL(`${API_BASE}/availability`);
      url.searchParams.set("service_id", String(service.id));
      url.searchParams.set("date", date);
      url.searchParams.set("tz_offset_minutes", String(tzOffset));
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        setSlots(data);
        if (options?.announce) {
          appendAssistantMessage(describeSlots(data, date));
        }
      }
    } catch (e) {
      console.error("Failed to load slots:", e);
    } finally {
      setSlotsLoading(false);
    }
  }

  async function loadSlotsByIds(serviceId: number | string, date: string, options?: { announce?: boolean }) {
    const numericId = typeof serviceId === 'string' ? parseInt(serviceId, 10) : serviceId;
    const svc = services.find((s) => s.id === numericId);
    if (svc) {
      setSelectedService(svc);
      await loadSlots(svc, date, options);
    } else {
      // If service not found in loaded services, try to load slots anyway
      // by creating a temporary service object
      try {
        const url = new URL(`${API_BASE}/availability`);
        url.searchParams.set("service_id", String(numericId));
        url.searchParams.set("date", date);
        url.searchParams.set("tz_offset_minutes", String(tzOffset));
        const res = await fetch(url.toString());
        if (res.ok) {
          const data = await res.json();
          setSlots(data);
          setDateStr(date);
          if (options?.announce) {
            appendAssistantMessage(describeSlots(data, date));
          }
        } else {
          appendAssistantMessage("I couldn't find available slots for that service. Please try again.");
        }
      } catch (e) {
        console.error("Failed to load slots:", e);
        appendAssistantMessage("I had trouble checking availability. Please try again.");
      }
    }
  }

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    handleEmailFromChat(text);
    handleNameFromChat(text);

    setInputValue("");
    const userMsg: Message = { id: uid(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const conversationHistory = [...messages, userMsg].map((m) => ({
        role: m.role,
        content: m.text,
      }));

      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: conversationHistory, context: buildConversationContext() }),
      });

      if (res.ok) {
        const data: ChatAPIResponse = await res.json();
        appendAssistantMessage(data.reply);

        // Capture email if the bot repeats it back in its reply.
        handleEmailFromChat(data.reply);

        if (data.action) {
          await handleAIAction(data.action);
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
          text: "I apologize, but I'm having trouble connecting. Please try again or use Quick Book for instant scheduling.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAIAction(action: AIAction) {
    const params = action.params || {};

    switch (action.type) {
      case "select_service": {
        const serviceId = params.service_id;
        if (serviceId) {
          const numericId = typeof serviceId === 'string' ? parseInt(serviceId, 10) : serviceId;
          const svc = services.find((s) => s.id === numericId);
          if (svc) {
            setSelectedService(svc);
          }
        }
        break;
      }
      case "select_date": {
        if (params.date) {
          setDateStr(params.date as string);
          if (selectedService) {
            await loadSlots(selectedService, params.date as string);
          }
        }
        break;
      }
      case "fetch_availability": {
        const serviceId = params.service_id ?? selectedService?.id;
        const date = (params.date as string) ?? dateStr;
        if (serviceId && date) {
          await loadSlotsByIds(serviceId as number, date, { announce: true });
        } else {
          appendAssistantMessage("Tell me which service and date you'd like, and I'll pull up times.");
        }
        break;
      }
      case "show_slots": {
        if (params.slots) {
          setSlots(params.slots as Slot[]);
          appendAssistantMessage(describeSlots(params.slots as Slot[], dateStr));
        }
        break;
      }
      case "ask_email": {
        setMode("chat");
        appendAssistantMessage("Share your email here and I'll save it for your booking.");
        break;
      }
      case "hold_slot": {
        if (params.service_id && params.stylist_id && params.date && params.start_time) {
          await createHoldRequest({
            serviceId: params.service_id as number,
            stylistId: params.stylist_id as number,
            date: params.date as string,
            startTime: params.start_time as string,
            customerName: params.customer_name as string | undefined,
            customerEmail: params.customer_email as string | undefined,
          });
        } else {
          appendAssistantMessage("I need the service, stylist, date, and time before I can reserve that.");
        }
        break;
      }
      case "confirm_booking": {
        const bookingId = (params.booking_id as string) ?? hold?.booking_id;
        if (bookingId) {
          await confirmBooking(bookingId);
        } else {
          appendAssistantMessage("I don't have a booking on hold yet. Let's pick a time first.");
        }
        break;
      }
      default:
        break;
    }
  }

  async function createHoldRequest(args: {
    serviceId: number;
    stylistId: number;
    date: string;
    startTime: string;
    customerName?: string;
    customerEmail?: string;
  }) {
    const svc = services.find((s) => s.id === args.serviceId) || selectedService;
    if (!svc) {
      appendAssistantMessage("Please pick a service to continue.");
      return;
    }

    // Use params from AI action, fallback to state
    const email = args.customerEmail?.trim() || customerEmail.trim();
    const name = args.customerName?.trim() || customerName.trim() || "Guest";
    
    if (!email) {
      appendAssistantMessage("I need your email address to hold the slot. What's your email?");
      return;
    }

    // Update state with collected info
    if (args.customerEmail) setCustomerEmail(args.customerEmail);
    if (args.customerName) setCustomerName(args.customerName);
    
    setSelectedService(svc);
    setMode("chat");
    setMode("chat");

    setHoldLoading(true);
    try {
      const [holdHour, holdMinute] = args.startTime.split(":").map(Number);
      const urlSlot = slots.find(
        (slot) =>
          slot.stylist_id === args.stylistId &&
          new Date(slot.start_time).getHours() === holdHour &&
          new Date(slot.start_time).getMinutes() === holdMinute
      );

      const payload = {
        service_id: svc.id,
        date: args.date,
        start_time: args.startTime,
        stylist_id: args.stylistId,
        customer_name: name,
        customer_email: email,
        tz_offset_minutes: tzOffset,
      };

      const res = await fetch(`${API_BASE}/bookings/hold`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        setHold(data);
        // Remove the held slot from current view so it can't be selected again.
        setSlots((prev) =>
          prev.filter(
            (slot) =>
              !(
                slot.stylist_id === args.stylistId &&
                new Date(slot.start_time).getHours() === holdHour &&
                new Date(slot.start_time).getMinutes() === holdMinute
              )
          )
        );
        if (urlSlot) {
          setSelectedSlot(urlSlot);
        } else {
          const dateObj = new Date(`${args.date}T${args.startTime}`);
          setSelectedSlot({
            stylist_id: args.stylistId,
            stylist_name: "Selected stylist",
            start_time: dateObj.toISOString(),
            end_time: new Date(dateObj.getTime() + (svc.duration_minutes || 30) * 60000).toISOString(),
          });
        }
        appendAssistantMessage("Got it! I reserved that time. Want me to confirm it?");
        // Immediately refresh booking list for this email
        if (email) {
          await trackBookings(email);
        }
      } else {
        alert("This slot is no longer available. Please select another.");
      }
    } catch {
      alert("Failed to hold slot. Please try again.");
    } finally {
      setHoldLoading(false);
    }
  }

  async function holdSlot() {
    if (!selectedService || !selectedSlot) return;

    const start = new Date(selectedSlot.start_time);
    const hh = String(start.getHours()).padStart(2, "0");
    const mm = String(start.getMinutes()).padStart(2, "0");

    await createHoldRequest({
      serviceId: selectedService.id,
      stylistId: selectedSlot.stylist_id,
      date: dateStr,
      startTime: `${hh}:${mm}`,
    });
  }

  async function confirmBooking(bookingId?: string) {
    const targetBookingId = bookingId ?? hold?.booking_id;
    if (!targetBookingId) return;

    setConfirmLoading(true);
    try {
      const res = await fetch(`${API_BASE}/bookings/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ booking_id: targetBookingId }),
      });

      if (res.ok) {
        setConfirmed(true);
        appendAssistantMessage("You're all set! Your booking is confirmed.");
        if (customerEmail.trim()) {
          await trackBookings(customerEmail.trim());
        }
      } else {
        alert("Failed to confirm booking. The hold may have expired.");
      }
    } catch {
      alert("Failed to confirm booking. Please try again.");
    } finally {
      setConfirmLoading(false);
    }
  }

  async function trackBookings(overrideEmail?: string) {
    const email = (overrideEmail || trackEmail || customerEmail).trim();
    if (!email) {
      setTrackError("Enter the email you used for booking.");
      return;
    }

    setTrackLoading(true);
    setTrackError("");
    setTrackResults([]);
    try {
      const url = new URL(`${API_BASE}/bookings/track`);
      url.searchParams.set("email", email);
      const res = await fetch(url.toString());
      if (res.ok) {
        const data: BookingTrack[] = await res.json();
        setTrackResults(data);
        setLastTrackedEmail(email.toLowerCase());
        if (data.length === 0) {
          setTrackError("No bookings found for this email yet.");
        }
      } else {
        setTrackError("Unable to fetch bookings right now.");
      }
    } catch {
      setTrackError("Unable to fetch bookings right now.");
    } finally {
      setTrackLoading(false);
    }
  }

  function resetBooking() {
    setSelectedService(null);
    setSelectedSlot(null);
    setSlots([]);
    setHold(null);
    setConfirmed(false);
    setCustomerName("");
    setCustomerEmail("");
  }

  // Generate next 7 days for date selection
  const dateOptions = useMemo(() => {
    const dates = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      dates.push({
        value: toLocalDateInputValue(d),
        label:
          i === 0
            ? "Today"
            : i === 1
            ? "Tomorrow"
            : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
      });
    }
    return dates;
  }, []);

  // Confirmation success screen
  if (confirmed) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50 flex items-center justify-center p-4">
        <div className="max-w-md w-full text-center animate-fadeIn">
          <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-3xl font-semibold text-gray-900 mb-2">Booking Confirmed!</h1>
          <p className="text-gray-600 mb-8">
            We have sent a confirmation to your email. See you soon!
          </p>
          <div className="bg-white rounded-2xl shadow-lg p-6 text-left mb-8">
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-gray-500">Service</span>
                <span className="font-medium">{selectedService?.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Date</span>
                <span className="font-medium">{formatDateLabel(dateStr)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Time</span>
                <span className="font-medium">
                  {selectedSlot && formatTime(selectedSlot.start_time)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Stylist</span>
                <span className="font-medium">{selectedSlot?.stylist_name}</span>
              </div>
              <div className="border-t pt-4 flex justify-between">
                <span className="text-gray-500">Total</span>
                <span className="font-semibold text-lg">
                  {selectedService && formatMoney(selectedService.price_cents)}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={resetBooking}
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            Book another appointment
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">Bishops Tempe</h1>
              <p className="text-sm text-gray-500">Premium Hair Studio</p>
            </div>
            <div className="flex items-center gap-2 bg-gray-100 rounded-full p-1">
              <button
                onClick={() => setMode("chat")}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  mode === "chat"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                AI Assistant
              </button>
              <button
                onClick={() => setMode("track")}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  mode === "track"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                Bookings
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {mode === "chat" && (
          /* ==================== CHAT MODE ==================== */
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Chat Container */}
            <div className="bg-white rounded-3xl shadow-xl overflow-hidden">
              {/* Chat Messages */}
              <div className="h-[60vh] overflow-y-auto p-6">
                <div className="space-y-4">
                  {messages.map((m, i) => (
                    <div
                      key={m.id}
                      className={`flex ${m.role === "user" ? "justify-end" : "justify-start"} animate-slideUp`}
                      style={{ animationDelay: `${Math.min(i, 5) * 50}ms` }}
                    >
                      <div
                        className={`max-w-[80%] px-5 py-3 rounded-2xl ${
                          m.role === "user"
                            ? "bg-gray-800 text-white rounded-br-md"
                            : "bg-gray-100 text-gray-800 rounded-bl-md"
                        }`}
                      >
                        <p className="text-[15px] leading-relaxed">{m.text}</p>
                      </div>
                    </div>
                  ))}
                  {isLoading && (
                    <div className="flex justify-start animate-slideUp">
                      <div className="bg-gray-100 px-5 py-3 rounded-2xl rounded-bl-md">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Quick Service Chips */}
              {messages.length <= 2 && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">Popular services:</p>
                  <div className="flex flex-wrap gap-2">
                    {services.slice(0, 4).map((svc) => (
                      <button
                        key={svc.id}
                        onClick={() => sendMessage(`I'd like to book a ${svc.name}`)}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                      >
                        {svc.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Chat Input */}
              <div className="border-t border-gray-100 p-4">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendMessage(inputValue);
                  }}
                  className="flex gap-3"
                >
                  <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="Type your message..."
                    className="flex-1 px-5 py-3 bg-gray-100 rounded-full text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-gray-400 focus:bg-white transition-all"
                    disabled={isLoading}
                  />
                  <button
                    type="submit"
                    disabled={!inputValue.trim() || isLoading}
                    className="px-6 py-3 bg-gray-700 hover:bg-gray-800 disabled:bg-gray-300 text-white rounded-full font-medium transition-all disabled:cursor-not-allowed"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                  </button>
                </form>
              </div>
            </div>

            {/* Booking Status - only show when we have collected info */}
            {(customerName || customerEmail || hold) && (
              <div className="mt-4 bg-white/70 backdrop-blur rounded-2xl shadow p-4 border border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">Booking Status</p>
                    <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-600">
                      {customerName && <span>👤 {customerName}</span>}
                      {customerEmail && <span>✉️ {customerEmail}</span>}
                      {hold && <span className="text-green-600 font-medium">✓ Slot held</span>}
                      {confirmed && <span className="text-green-600 font-medium">✓ Confirmed!</span>}
                    </div>
                  </div>
                  {hold && !confirmed && (
                    <button
                      onClick={() => confirmBooking()}
                      disabled={confirmLoading}
                      className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white text-sm rounded-lg font-medium transition-all"
                    >
                      {confirmLoading ? "..." : "Confirm"}
                    </button>
                  )}
                </div>
              </div>
            )}



            {(selectedSlot || hold) && (
              <div className="bg-white rounded-3xl shadow-xl p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Booking summary</h3>
                <div className="space-y-3 text-sm text-gray-700">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Service</span>
                    <span className="font-medium text-gray-900">
                      {selectedService?.name || "Select a service"}
                    </span>
                  </div>
                  {selectedService && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Total</span>
                      <span className="font-semibold text-gray-800">
                        {formatMoney(selectedService.price_cents)}
                      </span>
                    </div>
                  )}
                  {selectedSlot && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Date</span>
                        <span className="font-medium text-gray-900">{formatDateLabel(dateStr)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Time</span>
                        <span className="font-medium text-gray-900">{formatTime(selectedSlot.start_time)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Stylist</span>
                        <span className="font-medium text-gray-900">{selectedSlot.stylist_name}</span>
                      </div>
                    </>
                  )}
                  {hold && (
                    <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-xl px-3 py-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Slot reserved for 5 minutes. Confirm to lock it in.</span>
                    </div>
                  )}
                </div>

                {hold && !confirmed && (
                  <button
                    onClick={() => confirmBooking()}
                    disabled={confirmLoading}
                    className="mt-4 w-full py-4 bg-gray-700 hover:bg-gray-800 disabled:bg-gray-300 text-white rounded-xl font-semibold transition-all"
                  >
                    {confirmLoading ? "Confirming..." : "Confirm booking"}
                  </button>
                )}
              </div>
            )}

            <p className="text-center text-gray-400 text-sm">
              Powered by AI • Available 24/7
            </p>
          </div>
        )}

        {mode === "track" && (
          <div className="max-w-3xl mx-auto">
            <div className="bg-white rounded-3xl shadow-xl p-8">
              <div className="flex items-center justify-between gap-4 mb-6">
                <div>
                  <p className="text-sm uppercase tracking-wide text-gray-600 font-semibold">Track</p>
                  <h2 className="text-2xl font-semibold text-gray-900">Find your bookings</h2>
                  <p className="text-sm text-gray-500">Enter the email you used when booking to see status and details.</p>
                </div>
                <div className="hidden sm:block w-12 h-12 rounded-2xl bg-gray-100 text-gray-600 flex items-center justify-center">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10m-9 4h4" />
                  </svg>
                </div>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  trackBookings();
                }}
                className="flex flex-col sm:flex-row gap-3"
              >
                <input
                  type="email"
                  value={trackEmail}
                  onChange={(e) => setTrackEmail(e.target.value)}
                  placeholder="Enter your email"
                  className="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-400"
                />
                <button
                  type="submit"
                  className="px-5 py-3 bg-gray-700 hover:bg-gray-800 text-white rounded-xl font-semibold transition disabled:bg-gray-300 disabled:cursor-not-allowed"
                  disabled={trackLoading || !trackEmail.trim()}
                >
                  {trackLoading ? "Checking..." : "View bookings"}
                </button>
              </form>

              {trackError && (
                <div className="mt-4 p-3 rounded-xl bg-red-50 text-red-700 text-sm border border-red-100">
                  {trackError}
                </div>
              )}

              <div className="mt-6 space-y-4">
                {trackResults.map((b) => (
                  <div key={b.booking_id} className="border border-gray-100 rounded-2xl p-5 bg-gray-50/60">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm text-gray-500">{new Date(b.start_time).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</p>
                        <h3 className="text-lg font-semibold text-gray-900">{b.service_name}</h3>
                        <p className="text-sm text-gray-600">With {b.stylist_name}</p>
                      </div>
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          b.status === "CONFIRMED"
                            ? "bg-green-100 text-green-700"
                            : b.status === "HOLD"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-gray-200 text-gray-700"
                        }`}
                      >
                        {b.status}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-gray-600">
                      <div className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10m-9 4h4" />
                        </svg>
                        {formatTime(b.start_time)} - {formatTime(b.end_time)}
                      </div>
                      <div className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                        {b.customer_name || "Guest"}
                      </div>
                      <div className="flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 12h.01M12 12h.01M8 12h.01M21 12c0 4.418-4.03 8-9 8a9.77 9.77 0 01-4-.838L3 21l1.445-4.815C3.524 14.993 3 13.552 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        {b.customer_email}
                      </div>
                    </div>
                  </div>
                ))}

                {!trackLoading && !trackResults.length && lastTrackedEmail && !trackError && (
                  <p className="text-sm text-gray-500">No bookings found for {lastTrackedEmail} yet.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 mt-16">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-gray-500 text-sm">
              © 2025 Bishops Tempe. All rights reserved.
            </p>
            <div className="flex items-center gap-6 text-sm text-gray-500">
              <a href="#" className="hover:text-gray-900 transition-colors">Privacy</a>
              <a href="#" className="hover:text-gray-900 transition-colors">Terms</a>
              <a href="#" className="hover:text-gray-900 transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>

      {/* Global Styles */}
      <style jsx global>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.4s ease-out;
        }
        .animate-slideUp {
          animation: slideUp 0.3s ease-out both;
        }
      `}</style>
    </div>
  );
}
