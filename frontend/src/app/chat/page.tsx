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
  discount_cents: number;
};

type BookingMode = "chat" | "track";

type Stage =
  | "WELCOME"
  | "CAPTURE_EMAIL"
  | "SELECT_SERVICE"
  | "PREFERRED_STYLE"
  | "SELECT_DATE"
  | "SELECT_SLOT"
  | "SELECT_STYLIST"
  | "HOLDING"
  | "CONFIRMING"
  | "DONE";

type AIAction = {
  type: string;
  params?: Record<string, any>;
};

type ChatAPIResponse = {
  reply: string;
  action: AIAction | null;
  next_state?: string;
  chips?: string[] | null;
};

type BookingTrack = {
  booking_id: string;
  service_name: string;
  secondary_service_name?: string | null;
  stylist_name: string;
  customer_name: string | null;
  customer_email: string | null;
  customer_phone?: string | null;
  preferred_style_text?: string | null;
  preferred_style_image_url?: string | null;
  start_time: string;
  end_time: string;
  status: string;
  created_at: string;
  service_price_cents?: number;
  secondary_service_price_cents?: number | null;
  discount_cents?: number;
  total_price_cents?: number;
};

type Promo = {
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

type PromoEligibilityResponse = {
  promo: Promo | null;
  combo_promo: Promo | null;  // Combo promo returned separately (combinable with main promo)
  reason_codes: string[];
};

type PreferredStyle = {
  text?: string | null;
  image_url?: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const SHOP_ID = 1;

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

function formatPromoDiscount(promo: Promo) {
  if (promo.discount_type === "PERCENT") {
    return `${promo.discount_value ?? 0}% off`;
  }
  if (promo.discount_type === "FIXED") {
    const cents = promo.discount_value ?? 0;
    return (cents / 100).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
    }) + " off";
  }
  if (promo.discount_type === "FREE_ADDON") {
    return "Complimentary add-on";
  }
  if (promo.discount_type === "BUNDLE") {
    return "Bundle perk";
  }
  return "Special offer";
}

function getPromoDiscountCents(promo: Promo, baseCents: number) {
  if (promo.discount_type === "PERCENT") {
    const percent = promo.discount_value ?? 0;
    return Math.round((baseCents * percent) / 100);
  }
  if (promo.discount_type === "FIXED") {
    return promo.discount_value ?? 0;
  }
  return 0;
}

function applyPromoTotal(
  baseCents: number,
  promo: Promo | null,
  options?: { comboAccepted?: boolean }
) {
  if (!promo) {
    return { totalCents: baseCents, discountCents: 0 };
  }
  if (promo.type === "SERVICE_COMBO_PROMO" && !options?.comboAccepted) {
    return { totalCents: baseCents, discountCents: 0 };
  }
  const discount = getPromoDiscountCents(promo, baseCents);
  const total = Math.max(baseCents - discount, 0);
  return { totalCents: total, discountCents: discount };
}

function promoValueForCompare(promo: Promo | null, baseCents: number) {
  if (!promo) return 0;
  if (promo.discount_type === "PERCENT") {
    const percent = promo.discount_value ?? 0;
    return Math.round((baseCents * percent) / 100);
  }
  if (promo.discount_type === "FIXED") {
    return promo.discount_value ?? 0;
  }
  return 0;
}

function hasPreferredStyleData(style: PreferredStyle | null) {
  if (!style) return false;
  if (style.text && style.text.trim()) return true;
  return Boolean(style.image_url);
}

export default function ChatPage() {
  const [mode, setMode] = useState<BookingMode>("chat");
  const [stage, setStage] = useState<Stage>("CAPTURE_EMAIL");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: uid(),
      role: "assistant",
      text: "Hi! What's your name and best email to get started?",
    },
  ]);

  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [services, setServices] = useState<Service[]>([]);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [comboServiceId, setComboServiceId] = useState<number | null>(null);
  const [comboChoice, setComboChoice] = useState<"pending" | "accepted" | "declined" | null>(null);
  const [dateStr, setDateStr] = useState<string>(toLocalDateInputValue());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null); // Time string like "10:00 AM"

  const [hold, setHold] = useState<HoldResponse | null>(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [preferredStyle, setPreferredStyle] = useState<PreferredStyle | null>(null);
  const [lastPreferredStyle, setLastPreferredStyle] = useState<PreferredStyle | null>(null);
  const [preferredStyleComplete, setPreferredStyleComplete] = useState(false);
  const [styleDraftText, setStyleDraftText] = useState("");
  const [styleDraftImageUrl, setStyleDraftImageUrl] = useState<string | null>(null);
  const [styleMode, setStyleMode] = useState<"idle" | "text" | "image">("idle");
  const [styleError, setStyleError] = useState("");
  const [styleSaving, setStyleSaving] = useState(false);
  const [styleUploading, setStyleUploading] = useState(false);
  const [pendingStyle, setPendingStyle] = useState<PreferredStyle | null>(null);
  const [awaitingStyleEmail, setAwaitingStyleEmail] = useState<"none" | "save" | "same">("none");
  const [deferredStyleSave, setDeferredStyleSave] = useState<{
    style: PreferredStyle;
    serviceId: number;
  } | null>(null);

  const [trackEmail, setTrackEmail] = useState("");
  const [trackIdentity, setTrackIdentity] = useState(""); // Can be email or phone
  const [lastTrackedIdentity, setLastTrackedIdentity] = useState("");
  const [trackResults, setTrackResults] = useState<BookingTrack[]>([]);
  const [trackLoading, setTrackLoading] = useState(false);
  const [trackError, setTrackError] = useState("");
  const [selectedTrackBooking, setSelectedTrackBooking] = useState<BookingTrack | null>(null);
  const [appliedPromo, setAppliedPromo] = useState<Promo | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const pendingSlotRef = useRef<Slot | null>(null); // Store slot while waiting for email
  const pendingDateRef = useRef<string | null>(null);
  const shownPromosRef = useRef<Set<number>>(new Set());
  const promoMessageShownRef = useRef<boolean>(false);
  const styleFileInputRef = useRef<HTMLInputElement | null>(null);
  const chatStartPromoCheckedRef = useRef<boolean>(false); // Guard AT_CHAT_START to run once

  const promoSessionId = useMemo(() => {
    if (typeof window === "undefined") return "";
    const key = "promo_session_id";
    const existing = window.sessionStorage.getItem(key);
    if (existing) return existing;
    const newId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : uid("promo");
    window.sessionStorage.setItem(key, newId);
    return newId;
  }, []);

  const tzOffset = useMemo(() => -new Date().getTimezoneOffset(), []);

  const comboServiceIds =
    appliedPromo?.type === "SERVICE_COMBO_PROMO" &&
    Array.isArray(appliedPromo.constraints_json?.combo_service_ids)
      ? (appliedPromo.constraints_json?.combo_service_ids as number[])
      : [];
  const comboOtherServiceId =
    selectedService && comboServiceIds.length === 2
      ? comboServiceIds.find((id) => id !== selectedService.id) ?? null
      : null;
  const comboOtherService = comboOtherServiceId
    ? services.find((svc) => svc.id === comboOtherServiceId)
    : null;
  const comboAccepted = comboChoice === "accepted" && comboServiceId === comboOtherServiceId;
  const combinedServiceLabel =
    selectedService && comboAccepted && comboOtherService
      ? `${selectedService.name} + ${comboOtherService.name}`
      : selectedService?.name || "";

  const stagePrompts: Record<Stage, string> = {
    WELCOME: "Welcome! What service would you like to book?",
    CAPTURE_EMAIL: "What's your name and best email to get started?",
    SELECT_SERVICE: "Please choose a service below.",
    PREFERRED_STYLE: "Do you have a preferred style for this service?",
    SELECT_DATE: "Pick a date below to see times.",
    SELECT_SLOT: "Here are a few good options. Tap one to continue.",
    SELECT_STYLIST: "Which stylist would you prefer?",
    HOLDING: "One moment while I reserve that.",
    CONFIRMING: "Tap Confirm booking to finalize.",
    DONE: "You are all set. Anything else I can help with?",
  };

  const appendAssistantMessage = (text: string) => {
    setMessages((prev) => [...prev, { id: uid(), role: "assistant", text }]);
  };

  const appendUserMessage = (text: string) => {
    setMessages((prev) => [...prev, { id: uid(), role: "user", text }]);
  };

  const resetPreferredStyleState = () => {
    setPreferredStyle(null);
    setLastPreferredStyle(null);
    setPreferredStyleComplete(false);
    setStyleDraftText("");
    setStyleDraftImageUrl(null);
    setStyleMode("idle");
    setStyleError("");
    setPendingStyle(null);
    setAwaitingStyleEmail("none");
    pendingDateRef.current = null;
  };

  const fetchLastPreferredStyle = async (email: string, serviceId: number) => {
    try {
      const url = new URL(`${API_BASE}/customers/${encodeURIComponent(email)}/preferences`);
      url.searchParams.set("service_id", String(serviceId));
      const res = await fetch(url.toString());
      if (!res.ok) {
        setLastPreferredStyle(null);
        return null;
      }
      const data = await res.json();
      if (!data) {
        setLastPreferredStyle(null);
        return null;
      }
      const style = {
        text: data.preferred_style_text ?? "",
        image_url: data.preferred_style_image_url ?? null,
      };
      if (!hasPreferredStyleData(style)) {
        setLastPreferredStyle(null);
        return null;
      }
      setLastPreferredStyle(style);
      return style;
    } catch (error) {
      console.error("Failed to load preferred style:", error);
      setLastPreferredStyle(null);
      return null;
    }
  };

  const handleEmailFromChat = (text: string) => {
    const extracted = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    if (extracted) {
      const normalized = extracted[0].trim().toLowerCase();
      setCustomerEmail(normalized);
      setTrackEmail(normalized);
    }
  };

  const extractEmail = (text: string) => {
    const extracted = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    return extracted ? extracted[0].trim().toLowerCase() : "";
  };

  const completePreferredStyle = async (message?: string) => {
    setPreferredStyleComplete(true);
    setStyleMode("idle");
    setStyleDraftText("");
    setStyleDraftImageUrl(null);
    setStyleError("");
    if (message) {
      appendAssistantMessage(message);
    }
    if (pendingDateRef.current && selectedService) {
      const pendingDate = pendingDateRef.current;
      pendingDateRef.current = null;
      try {
        await loadSlots(selectedService, pendingDate, {
          announce: true,
          secondaryServiceId: comboAccepted ? comboOtherServiceId : null,
        });
      } catch (error) {
        console.error("Failed to load slots after preferred style:", error);
        appendAssistantMessage("I had trouble loading available times. Please pick a date below.");
        setStage("SELECT_DATE");
      }
    } else {
      setStage("SELECT_DATE");
    }
  };

  const savePreferredStyle = async (
    style: PreferredStyle,
    options?: { emailOverride?: string; serviceIdOverride?: number; announce?: boolean }
  ) => {
    const serviceId = options?.serviceIdOverride ?? selectedService?.id;
    if (!serviceId) {
      appendAssistantMessage("Please pick a service first.");
      return;
    }
    if (!hasPreferredStyleData(style)) {
      appendAssistantMessage("Share a short style note or add an image.");
      return;
    }
    const email = (options?.emailOverride || customerEmail).trim();
    const announce = options?.announce ?? true;
    if (!email) {
      setPreferredStyle(style);
      setDeferredStyleSave({ style, serviceId });
      if (stage === "PREFERRED_STYLE") {
        await completePreferredStyle(
          "Got it. I'll save this after you share your email. Pick a date below."
        );
      } else if (announce) {
        appendAssistantMessage("Got it. I'll save this after you share your email.");
      }
      return;
    }
    setStyleSaving(true);
    setStyleError("");
    try {
      const res = await fetch(`${API_BASE}/customers/${encodeURIComponent(email)}/preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_id: serviceId,
          preferred_style_text: style.text || null,
          preferred_style_image_url: style.image_url || null,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail || "Unable to save preference");
      }
      const savedStyle = {
        text: data.preferred_style_text ?? style.text ?? "",
        image_url: data.preferred_style_image_url ?? style.image_url ?? null,
      };
      setPreferredStyle(savedStyle);
      setLastPreferredStyle(savedStyle);
      setDeferredStyleSave(null);
      if (stage === "PREFERRED_STYLE" && announce) {
        await completePreferredStyle("Got it. Pick a date below.");
      } else if (announce) {
        appendAssistantMessage("Saved your preferred style.");
      }
    } catch (error) {
      console.error("Failed to save preferred style:", error);
      const message =
        error instanceof Error ? error.message : "Couldn't save the style preference.";
      setStyleError(message);
    } finally {
      setStyleSaving(false);
      setPendingStyle(null);
      setAwaitingStyleEmail("none");
    }
  };

  const applySameAsLastTime = async (emailOverride?: string, serviceIdOverride?: number) => {
    const serviceId = serviceIdOverride ?? selectedService?.id;
    if (!serviceId) {
      appendAssistantMessage("Please pick a service first.");
      return;
    }
    const email = (emailOverride || customerEmail).trim();
    if (!email) {
      setAwaitingStyleEmail("same");
      appendAssistantMessage(
        "Tell me the email you used before so I can retrieve your preferred style."
      );
      return;
    }
    setStyleSaving(true);
    setStyleError("");
    try {
      const url = new URL(`${API_BASE}/customers/${encodeURIComponent(email)}/preferences`);
      url.searchParams.set("service_id", String(serviceId));
      const res = await fetch(url.toString());
      if (!res.ok) {
        throw new Error("Unable to fetch preference");
      }
      const data = await res.json();
      if (!data) {
        appendAssistantMessage("I don't have a saved style for this service yet.");
        setLastPreferredStyle(null);
        return;
      }
      const savedStyle = {
        text: data.preferred_style_text ?? "",
        image_url: data.preferred_style_image_url ?? null,
      };
      if (!hasPreferredStyleData(savedStyle)) {
        appendAssistantMessage("I don't have a saved style for this service yet.");
        setLastPreferredStyle(null);
        return;
      }
      setPreferredStyle(savedStyle);
      setLastPreferredStyle(savedStyle);
      if (stage === "PREFERRED_STYLE") {
        await completePreferredStyle("Perfect. Pick a date below.");
      } else {
        appendAssistantMessage("Applied your last saved style.");
      }
    } catch (error) {
      console.error("Failed to fetch preferred style:", error);
      setStyleError("Couldn't load that style preference.");
    } finally {
      setStyleSaving(false);
      setAwaitingStyleEmail("none");
      setPendingStyle(null);
    }
  };

  const skipPreferredStyle = async () => {
    setPreferredStyle(null);
    if (stage === "PREFERRED_STYLE") {
      setPreferredStyleComplete(true);
    }
    setPendingStyle(null);
    setAwaitingStyleEmail("none");
    if (stage === "PREFERRED_STYLE") {
      await completePreferredStyle("No problem. Pick a date below.");
    } else {
      appendAssistantMessage("No preferred style saved.");
    }
  };

  const handleStyleImageUpload = async (file: File) => {
    setStyleUploading(true);
    setStyleError("");
    try {
      const form = new FormData();
      form.append("file", file);
      console.log('[UPLOAD] Uploading style image to:', `${API_BASE}/uploads/style-image`);
      const res = await fetch(`${API_BASE}/uploads/style-image`, {
        method: "POST",
        body: form,
      });
      console.log('[UPLOAD] Response status:', res.status, res.statusText);
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const errorMsg = data?.detail || "Upload failed";
        console.error('[UPLOAD] Upload failed:', errorMsg, data);
        throw new Error(errorMsg);
      }
      if (!data?.image_url) {
        console.error('[UPLOAD] No image URL in response:', data);
        throw new Error("Upload failed - no image URL returned");
      }
      console.log('[UPLOAD] Image uploaded successfully:', data.image_url);
      setStyleDraftImageUrl(data.image_url);
      setStyleMode("image");
    } catch (error) {
      console.error('[UPLOAD] Failed to upload style image:', error);
      const message = error instanceof Error ? error.message : "Couldn't upload that image.";
      setStyleError(message);
      appendAssistantMessage(`I had trouble uploading that image: ${message}`);
    } finally {
      setStyleUploading(false);
    }
  };

  const handleNameFromChat = (text: string) => {
    // Try to extract name when user provides it along with email or standalone
    // Look for patterns like "Name is X", "I'm X", "my name is X", or just a capitalized word before email
    const namePatterns = [
      /(?:my name is|name is|i'm|i am)\s+([A-Za-z][a-z]+)/i,
      /^([A-Za-z][a-z]+)\s+(?:and|,)/i,  // "Ash and ash@gmail.com"
      /^([A-Za-z][a-z]+)$/i,  // Just a name by itself
    ];
    for (const pattern of namePatterns) {
      const match = text.match(pattern);
      if (match && match[1]) {
        const normalizedName = match[1].trim();
        setCustomerName(normalizedName.charAt(0).toUpperCase() + normalizedName.slice(1));
        return;
      }
    }
  };

  const renderPromoCopy = (promo: Promo) => {
    const comboIds = Array.isArray(promo.constraints_json?.combo_service_ids)
      ? (promo.constraints_json?.combo_service_ids as number[])
      : [];
    const comboNames =
      promo.type === "SERVICE_COMBO_PROMO" && comboIds.length === 2
        ? comboIds
            .map((id) => services.find((svc) => svc.id === id)?.name)
            .filter(Boolean)
        : [];
    const serviceName =
      comboNames.length === 2
        ? `${comboNames[0]} + ${comboNames[1]}`
        : selectedService?.name ||
          (promo.service_id ? services.find((svc) => svc.id === promo.service_id)?.name : "") ||
          "";
    const discountLabel = formatPromoDiscount(promo);
    const perkDescription =
      promo.constraints_json && typeof promo.constraints_json.perk_description === "string"
        ? promo.constraints_json.perk_description
        : "";
    const endDate = promo.end_at_utc
      ? new Date(promo.end_at_utc).toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : "";

    if (promo.custom_copy) {
      const fallbackService = serviceName || "your service";
      return promo.custom_copy
        .replace(/\{service_name\}/gi, fallbackService)
        .replace(/\{discount\}/gi, discountLabel)
        .replace(/\{end_date\}/gi, endDate)
        .replace(/\{start_date\}/gi, promo.start_at_utc
          ? new Date(promo.start_at_utc).toLocaleDateString("en-US", { month: "short", day: "numeric" })
          : ""
        )
        .trim();
    }

    const serviceSuffix = serviceName ? ` on ${serviceName}` : "";
    const seasonalSuffix = promo.type === "SEASONAL_PROMO" && endDate ? ` Ends ${endDate}.` : "";
    const minSpend = promo.constraints_json?.min_spend_cents
      ? ` (min ${formatMoney(promo.constraints_json.min_spend_cents)})`
      : "";
    const perkSuffix = perkDescription ? ` (${perkDescription})` : "";
    return `${discountLabel}${perkSuffix}${serviceSuffix}${minSpend}.${seasonalSuffix}`
      .replace("..", ".")
      .trim();
  };

  const maybeShowPromo = async (
    triggerPoint: string,
    overrides?: { email?: string; serviceId?: number | null; bookingDate?: string; servicePriceCents?: number | null }
  ) => {
    console.log('[PROMO] maybeShowPromo called', { triggerPoint, overrides });
    try {
      const resolvedEmail = overrides?.email ?? customerEmail.trim();
      const resolvedServiceId =
        overrides?.serviceId ?? selectedService?.id ?? null;
      const resolvedBookingDate = overrides?.bookingDate ?? dateStr;
      // Resolve service price for min_spend constraint evaluation
      const resolvedServicePriceCents =
        overrides?.servicePriceCents ??
        (resolvedServiceId ? services.find((s) => s.id === resolvedServiceId)?.price_cents : null) ??
        selectedService?.price_cents ??
        null;
      const url = new URL(`${API_BASE}/promos/eligible`);
      url.searchParams.set("trigger_point", triggerPoint);
      url.searchParams.set("shop_id", String(SHOP_ID));
      url.searchParams.set("session_id", promoSessionId);
      if (resolvedEmail) {
        url.searchParams.set("email", resolvedEmail);
      }
      if (resolvedServiceId) {
        url.searchParams.set("service_id", String(resolvedServiceId));
      }
      if (resolvedServicePriceCents != null) {
        url.searchParams.set("selected_service_price_cents", String(resolvedServicePriceCents));
      }
      if (resolvedBookingDate) {
        url.searchParams.set("booking_date", resolvedBookingDate);
      }

      console.log('[PROMO] Fetching from URL:', url.toString());
      const res = await fetch(url.toString());
      console.log('[PROMO] Response status:', res.status, res.statusText);
      if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        console.error('[PROMO] Failed to fetch promo:', res.status, errorText);
        return;
      }
      const data: PromoEligibilityResponse = await res.json();
      console.log('[PROMO] Fetched promo data:', data);
      
      // Handle regular (non-combo) promo
      if (data.promo && !shownPromosRef.current.has(data.promo.id)) {
        shownPromosRef.current.add(data.promo.id);
        const baseCents =
          (selectedService?.price_cents ?? 0) +
          (comboAccepted && comboOtherService ? comboOtherService.price_cents : 0);
        const currentValue = promoValueForCompare(appliedPromo, baseCents);
        const nextValue = promoValueForCompare(data.promo, baseCents);
        const shouldReplace =
          !appliedPromo || nextValue > currentValue || data.promo.priority > (appliedPromo.priority ?? 0);
        if (shouldReplace) {
          setAppliedPromo(data.promo);
        }
        console.log('[PROMO] Appending promo message:', renderPromoCopy(data.promo));
        appendAssistantMessage(renderPromoCopy(data.promo));
      }
      
      // Handle combo promo separately (combinable with regular promo)
      if (data.combo_promo && !shownPromosRef.current.has(data.combo_promo.id)) {
        shownPromosRef.current.add(data.combo_promo.id);
        if (
          selectedService &&
          Array.isArray(data.combo_promo.constraints_json?.combo_service_ids)
        ) {
          const comboIds = data.combo_promo.constraints_json?.combo_service_ids as number[];
          const otherId = comboIds.includes(selectedService.id)
            ? comboIds.find((id) => id !== selectedService.id) ?? null
            : null;
          if (otherId) {
            // Store the combo promo for later application if user accepts
            setComboServiceId(otherId);
            setComboChoice("pending");
            // Show the combo offer message
            const otherService = services.find(s => s.id === otherId);
            const comboDiscount = data.combo_promo.discount_type === "PERCENT" 
              ? `${data.combo_promo.discount_value}% off`
              : data.combo_promo.discount_type === "FIXED"
              ? `$${(data.combo_promo.discount_value || 0) / 100} off`
              : "special discount";
            const comboMessage = otherService 
              ? `🎁 Combo offer: Add ${otherService.name} for ${comboDiscount}! Would you like to add it?`
              : renderPromoCopy(data.combo_promo);
            console.log('[PROMO] Appending combo promo message:', comboMessage);
            appendAssistantMessage(comboMessage);
          }
        }
      }
      
      if (!data.promo && !data.combo_promo) {
        if (data.reason_codes && data.reason_codes.length > 0) {
          console.log('[PROMO] No promo eligible. Reason codes:', data.reason_codes);
        }
      }
    } catch (error) {
      console.error('[PROMO] Failed to load promo:', error);
      if (error instanceof Error) {
        console.error('[PROMO] Error details:', error.message, error.stack);
      }
    }
  };

  const extractName = (text: string) => {
    const namePatterns = [
      /(?:my name is|name is|i'm|i am)\s+([A-Za-z][a-z]+)/i,
      /^([A-Za-z][a-z]+)\s+(?:and|,)/i,
      /^([A-Za-z][a-z]+)$/i,
    ];
    for (const pattern of namePatterns) {
      const match = text.match(pattern);
      if (match && match[1]) {
        const normalizedName = match[1].trim();
        return normalizedName.charAt(0).toUpperCase() + normalizedName.slice(1);
      }
    }
    return "";
  };

  function buildConversationContext() {
    return {
      stage,
      selected_service: selectedService?.name,
      selected_service_id: selectedService?.id,
      selected_date: dateStr,
      customer_name: customerName || undefined,
      customer_email: customerEmail || undefined,
      customer_phone: customerPhone || undefined,
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
      preferred_style_text: preferredStyle?.text || undefined,
      preferred_style_image_url: preferredStyle?.image_url || undefined,
      preferred_style_complete: preferredStyleComplete,
      has_last_preferred_style: hasPreferredStyleData(lastPreferredStyle),
    };
  }

  function describeSlots(slotsToDescribe: Slot[], date: string) {
    if (!slotsToDescribe.length) {
      return `No openings on ${formatDateLabel(date)}. Try another date?`;
    }
    return `Here are a few good options for ${formatDateLabel(date)}. Tap one to continue.`;
  }

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Note: AT_CHAT_START trigger removed - promos are now shown at AFTER_EMAIL_CAPTURE 
  // (when we know if user is first-time or returning) or AFTER_SERVICE_SELECTED (for combos)
  // AFTER_HOLD_CREATED trigger also removed - promos are applied earlier now

  useEffect(() => {
    if (!selectedService || !dateStr) return;
    if (comboChoice !== "accepted" && comboChoice !== "declined") return;
    if (stage !== "SELECT_DATE" && stage !== "SELECT_SLOT") return;
    loadSlots(selectedService, dateStr, {
      announce: false,
      setStageToSlot: stage === "SELECT_SLOT",
      secondaryServiceId: comboChoice === "accepted" ? comboOtherServiceId : null,
    });
  }, [comboChoice, comboOtherServiceId, selectedService?.id, dateStr, stage]);

  useEffect(() => {
    if (!selectedService || !customerEmail.trim()) {
      setLastPreferredStyle(null);
      return;
    }
    fetchLastPreferredStyle(customerEmail.trim(), selectedService.id);
  }, [selectedService?.id, customerEmail]);

  // Load services on mount
  useEffect(() => {
    async function loadServices() {
      try {
        const res = await fetch(`${API_BASE}/services`);
        if (res.ok) {
          const data = await res.json();
          setServices(data);
          setStage(customerEmail.trim() ? "SELECT_SERVICE" : "CAPTURE_EMAIL");
        }
      } catch (e) {
        console.error("Failed to load services:", e);
      }
    }
    loadServices();
  }, []);

  // Slots are loaded only when the user picks a date (guardrailed flow).

  async function loadSlots(
    service: Service,
    date: string,
    options?: { announce?: boolean; setStageToSlot?: boolean; secondaryServiceId?: number | null }
  ): Promise<Slot[]> {
    setDateStr(date);
    setSlotsLoading(true);
    setSlots([]);
    setSelectedSlot(null);
    // Only set stage to SELECT_SLOT if not explicitly disabled
    if (options?.setStageToSlot !== false) {
      setStage("SELECT_SLOT");
    }
    let fetchedSlots: Slot[] = [];
    try {
    const url = new URL(`${API_BASE}/availability`);
    url.searchParams.set("service_id", String(service.id));
    url.searchParams.set("date", date);
    url.searchParams.set("tz_offset_minutes", String(tzOffset));
    if (options?.secondaryServiceId) {
      url.searchParams.set("secondary_service_id", String(options.secondaryServiceId));
    }
      const res = await fetch(url.toString());
      if (res.ok) {
        const data = await res.json();
        fetchedSlots = data;
        setSlots(data);
        // Note: AFTER_SLOT_SHOWN trigger removed - promos handled at AFTER_EMAIL_CAPTURE and AFTER_SERVICE_SELECTED
        if (!data.length && options?.setStageToSlot !== false) {
          setStage("SELECT_DATE");
        }
        if (options?.announce) {
          appendAssistantMessage(describeSlots(data, date));
        }
      }
    } catch (e) {
      console.error("Failed to load slots:", e);
      if (options?.setStageToSlot !== false) {
        setStage("SELECT_DATE");
      }
    } finally {
      setSlotsLoading(false);
    }
    return fetchedSlots;
  }

  async function loadSlotsByIds(
    serviceId: number | string,
    date: string,
    options?: { announce?: boolean }
  ): Promise<Slot[]> {
    const numericId = typeof serviceId === 'string' ? parseInt(serviceId, 10) : serviceId;
    const svc = services.find((s) => s.id === numericId);
    if (svc) {
      setSelectedService(svc);
      return await loadSlots(svc, date, {
        ...options,
        secondaryServiceId: comboAccepted ? comboOtherServiceId : null,
      });
    } else {
      // If service not found in loaded services, try to load slots anyway
      // by creating a temporary service object
      try {
        const url = new URL(`${API_BASE}/availability`);
        url.searchParams.set("service_id", String(numericId));
        url.searchParams.set("date", date);
        url.searchParams.set("tz_offset_minutes", String(tzOffset));
        if (comboAccepted && comboOtherServiceId) {
          url.searchParams.set("secondary_service_id", String(comboOtherServiceId));
        }
        const res = await fetch(url.toString());
        if (res.ok) {
          const data = await res.json();
          setSlots(data);
          setDateStr(date);
          setStage(data.length ? "SELECT_SLOT" : "SELECT_DATE");
          // Note: AFTER_SLOT_SHOWN trigger removed
          if (options?.announce) {
            appendAssistantMessage(describeSlots(data, date));
          }
          return data;
        } else {
          appendAssistantMessage("I couldn't find available slots for that service. Please try again.");
        }
      } catch (e) {
        console.error("Failed to load slots:", e);
        appendAssistantMessage("I had trouble checking availability. Please try again.");
      }
    }
    return [];
  }

  async function onSelectService(svc: Service) {
    appendUserMessage(svc.name);
    setSelectedService(svc);
    setComboServiceId(null);
    setComboChoice(null);
    resetPreferredStyleState();
    await maybeShowPromo("AFTER_SERVICE_SELECTED", { serviceId: svc.id, servicePriceCents: svc.price_cents });
    setStage("PREFERRED_STYLE");
    appendAssistantMessage(`Great choice. ${stagePrompts.PREFERRED_STYLE}`);
  }

  async function onSelectDate(date: string) {
    // Show user's selection in chat
    const dateLabel = formatDateLabel(date);
    appendUserMessage(dateLabel);
    
    if (!selectedService) {
      appendAssistantMessage(stagePrompts.SELECT_SERVICE);
      return;
    }
    await loadSlots(selectedService, date, {
      announce: true,
      secondaryServiceId: comboAccepted ? comboOtherServiceId : null,
    });
  }

  // When user clicks a time slot button (time only, no stylist yet)
  function onSelectTime(timeStr: string) {
    appendUserMessage(timeStr);
    setSelectedTime(timeStr);
    // Find stylists available at this time
    const stylistsAtTime = slots.filter((s) => formatTime(s.start_time) === timeStr);
    if (stylistsAtTime.length === 1) {
      // Only one stylist available, proceed directly
      onSelectSlotWithStylist(stylistsAtTime[0]);
    } else {
      // Multiple stylists, ask user to choose
      setStage("SELECT_STYLIST");
      appendAssistantMessage(`Great! ${timeStr} works. Who would you like as your stylist?`);
    }
  }

  // When user clicks a stylist button after selecting time
  function onSelectStylist(stylistId: number, stylistName: string) {
    appendUserMessage(stylistName);
    if (!selectedTime) return;
    const slot = slots.find(
      (s) => formatTime(s.start_time) === selectedTime && s.stylist_id === stylistId
    );
    if (slot) {
      onSelectSlotWithStylist(slot);
    }
  }

  // Renamed from onSelectSlot to be clearer
  async function onSelectSlotWithStylist(slot: Slot) {
    if (!selectedService) {
      appendAssistantMessage(stagePrompts.SELECT_SERVICE);
      return;
    }
    
    // Check if we have email - if not, ask for it
    if (!customerEmail.trim()) {
      setSelectedSlot(slot);
      pendingSlotRef.current = slot; // Store in ref for immediate access
      setStage("HOLDING");
      appendAssistantMessage("I need your email address to hold the slot. What's your email?");
      return;
    }
    
    setSelectedSlot(slot);
    setStage("HOLDING");
    const start = new Date(slot.start_time);
    const hh = String(start.getHours()).padStart(2, "0");
    const mm = String(start.getMinutes()).padStart(2, "0");
    await createHoldRequest({
      serviceId: selectedService.id,
      stylistId: slot.stylist_id,
      date: dateStr,
      startTime: `${hh}:${mm}`,
      slot,
    });
  }

  function findServiceMatch(text: string): Service | null {
    const normalized = text.toLowerCase();
    for (const svc of services) {
      const name = svc.name.toLowerCase();
      if (normalized.includes(name)) {
        return svc;
      }
      if (name.includes("men") && normalized.includes("mens haircut")) {
        return svc;
      }
      if (name.includes("women") && normalized.includes("womens haircut")) {
        return svc;
      }
      if (name.includes("beard") && normalized.includes("beard")) {
        return svc;
      }
      if (name.includes("color") && normalized.includes("color")) {
        return svc;
      }
    }
    return null;
  }

  function parseDateFromText(text: string): string | null {
    const normalized = text.toLowerCase();
    if (normalized.includes("today")) {
      return toLocalDateInputValue(new Date());
    }
    if (normalized.includes("tomorrow")) {
      return toLocalDateInputValue(new Date(Date.now() + 24 * 60 * 60 * 1000));
    }
    const isoMatch = normalized.match(/\b20\d{2}-\d{2}-\d{2}\b/);
    if (isoMatch) {
      return isoMatch[0];
    }
    // Handle "Saturday, January 3" format
    const dayMonthMatch = normalized.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(\d{1,2})\b/);
    if (dayMonthMatch) {
      const monthKey = dayMonthMatch[1];
      const day = parseInt(dayMonthMatch[2], 10);
      const monthMap: Record<string, number> = {
        jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
        jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
      };
      const month = monthMap[monthKey];
      if (month !== undefined) {
        const now = new Date();
        let year = now.getFullYear();
        const candidate = new Date(year, month, day);
        if (candidate < now) {
          year += 1;
        }
        return toLocalDateInputValue(new Date(year, month, day));
      }
    }
    const ordinalMatch = normalized.match(/\b(\d{1,2})(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b/);
    if (ordinalMatch) {
      const day = parseInt(ordinalMatch[1], 10);
      const monthKey = ordinalMatch[3];
      const monthMap: Record<string, number> = {
        jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
        jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
      };
      const month = monthMap[monthKey];
      if (month !== undefined) {
        const now = new Date();
        let year = now.getFullYear();
        const candidate = new Date(year, month, day);
        if (candidate < now) {
          year += 1;
        }
        return toLocalDateInputValue(new Date(year, month, day));
      }
    }
    const monthFirstMatch = normalized.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*(\d{1,2})(st|nd|rd|th)?\b/);
    if (monthFirstMatch) {
      const monthKey = monthFirstMatch[1];
      const day = parseInt(monthFirstMatch[2], 10);
      const monthMap: Record<string, number> = {
        jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
        jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
      };
      const month = monthMap[monthKey];
      if (month !== undefined) {
        const now = new Date();
        let year = now.getFullYear();
        const candidate = new Date(year, month, day);
        if (candidate < now) {
          year += 1;
        }
        return toLocalDateInputValue(new Date(year, month, day));
      }
    }
    return null;
  }

  function parseTimeFromText(text: string): { hours: number; minutes: number } | null {
    const normalized = text.toLowerCase().replace(/\./g, "");
    if (normalized.includes("noon")) {
      return { hours: 12, minutes: 0 };
    }
    if (normalized.includes("midnight")) {
      return { hours: 0, minutes: 0 };
    }

    const ampmMatch = normalized.match(/\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/);
    if (ampmMatch) {
      let hours = parseInt(ampmMatch[1], 10);
      const minutes = ampmMatch[2] ? parseInt(ampmMatch[2], 10) : 0;
      const meridiem = ampmMatch[3];
      if (meridiem === "pm" && hours < 12) hours += 12;
      if (meridiem === "am" && hours === 12) hours = 0;
      return { hours, minutes };
    }

    const militaryMatch = normalized.match(/\b(\d{1,2}):(\d{2})\b/);
    if (militaryMatch) {
      const hours = parseInt(militaryMatch[1], 10);
      const minutes = parseInt(militaryMatch[2], 10);
      if (hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59) {
        return { hours, minutes };
      }
    }

    return null;
  }

  function parseStylistFromText(text: string): string | null {
    const normalized = text.toLowerCase();
    // Check against actual stylist names from current slots
    for (const slot of slots) {
      if (normalized.includes(slot.stylist_name.toLowerCase())) {
        return slot.stylist_name;
      }
    }
    // Fallback common names
    if (normalized.includes("alex")) return "Alex";
    if (normalized.includes("jamie")) return "Jamie";
    return null;
  }

  function matchSlotByTime(
    slotsToMatch: Slot[],
    targetTime: { hours: number; minutes: number },
    stylistName?: string | null
  ): Slot | null {
    const timeMatches = slotsToMatch.filter((slot) => {
      const dt = new Date(slot.start_time);
      return dt.getHours() === targetTime.hours && dt.getMinutes() === targetTime.minutes;
    });
    if (!timeMatches.length) return null;
    if (stylistName) {
      const normalized = stylistName.toLowerCase();
      const stylistMatch = timeMatches.find((slot) =>
        slot.stylist_name.toLowerCase().includes(normalized)
      );
      return stylistMatch || null; // Return null if stylist not found, don't default
    }
    return timeMatches[0];
  }

  // Get all slots matching a time (for stylist selection)
  function getSlotsAtTime(
    slotsToMatch: Slot[],
    targetTime: { hours: number; minutes: number }
  ): Slot[] {
    return slotsToMatch.filter((slot) => {
      const dt = new Date(slot.start_time);
      return dt.getHours() === targetTime.hours && dt.getMinutes() === targetTime.minutes;
    });
  }

  // Handle time selection from chat (not button click) - follows step-by-step flow
  async function handleTimeFromChat(
    slotsToCheck: Slot[],
    parsedTime: { hours: number; minutes: number },
    parsedStylist: string | null,
    extractedEmail: string | null,
    extractedName: string | null
  ): Promise<boolean> {
    const timeStr = formatTime(
      new Date(2000, 0, 1, parsedTime.hours, parsedTime.minutes).toISOString()
    );
    setSelectedTime(timeStr);
    
    const slotsAtTime = getSlotsAtTime(slotsToCheck, parsedTime);
    if (!slotsAtTime.length) {
      appendAssistantMessage(`No availability at ${timeStr}. Please pick another time.`);
      setStage("SELECT_SLOT");
      return true;
    }

    // If user specified a stylist, try to match
    if (parsedStylist) {
      const matchedSlot = matchSlotByTime(slotsToCheck, parsedTime, parsedStylist);
      if (matchedSlot) {
        // Stylist matched, proceed to email
        return await handleStylistSelected(matchedSlot, extractedEmail, extractedName);
      } else {
        // Stylist not available at this time
        appendAssistantMessage(`${parsedStylist} isn't available at ${timeStr}. Who would you like instead?`);
        setStage("SELECT_STYLIST");
        return true;
      }
    }

    // Multiple stylists at this time? Ask user to choose
    if (slotsAtTime.length > 1) {
      const stylistNames = slotsAtTime.map(s => s.stylist_name).join(" or ");
      appendAssistantMessage(`${timeStr} works! Would you prefer ${stylistNames}?`);
      setStage("SELECT_STYLIST");
      return true;
    }

    // Only one stylist, proceed to email check
    return await handleStylistSelected(slotsAtTime[0], extractedEmail, extractedName);
  }

  // Handle when stylist is determined (either by user or auto-selected)
  async function handleStylistSelected(
    slot: Slot,
    extractedEmail: string | null,
    extractedName: string | null
  ): Promise<boolean> {
    setSelectedSlot(slot);
    pendingSlotRef.current = slot;

    const email = extractedEmail || customerEmail.trim();
    const name = extractedName || customerName.trim();

    if (!email) {
      setStage("HOLDING");
      appendAssistantMessage(`Great, ${slot.stylist_name} at ${formatTime(slot.start_time)}. What's your email to hold this slot?`);
      return true;
    }

    // Have email, proceed to hold
    if (!selectedService) {
      appendAssistantMessage("Please select a service first.");
      return true;
    }

    const start = new Date(slot.start_time);
    const hh = String(start.getHours()).padStart(2, "0");
    const mm = String(start.getMinutes()).padStart(2, "0");
    
    setStage("HOLDING");
    await createHoldRequest({
      serviceId: selectedService.id,
      stylistId: slot.stylist_id,
      date: dateStr,
      startTime: `${hh}:${mm}`,
      slot,
      customerEmail: email,
      customerName: name || "Guest",
    });
    return true;
  }

  function isSimpleQuestion(text: string) {
    const normalized = text.toLowerCase();
    return (
      normalized.includes("?") ||
      normalized.includes("price") ||
      normalized.includes("cost") ||
      normalized.includes("hours") ||
      normalized.includes("open") ||
      normalized.includes("close")
    );
  }

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    const extractedEmail = extractEmail(text);
    const extractedName = extractName(text);
    if (extractedEmail) {
      setCustomerEmail(extractedEmail);
      setTrackEmail(extractedEmail);
      if (deferredStyleSave && awaitingStyleEmail === "none") {
        void savePreferredStyle(deferredStyleSave.style, {
          emailOverride: extractedEmail,
          serviceIdOverride: deferredStyleSave.serviceId,
          announce: false,
        });
      }
    }
    if (extractedName) {
      setCustomerName(extractedName);
    }

    setInputValue("");
    const userMsg: Message = { id: uid(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const normalized = text.toLowerCase();
      const matchedService = findServiceMatch(text);
      const parsedDate = parseDateFromText(text);
      const parsedTime = parseTimeFromText(text);
      const parsedStylist = parseStylistFromText(text);

      if (awaitingStyleEmail !== "none" && extractedEmail) {
        if (awaitingStyleEmail === "save" && pendingStyle) {
          await savePreferredStyle(pendingStyle, { emailOverride: extractedEmail });
        } else if (awaitingStyleEmail === "same") {
          await applySameAsLastTime(extractedEmail);
        }
        setIsLoading(false);
        return;
      }

      if (stage === "CAPTURE_EMAIL") {
        if (!extractedEmail) {
          appendAssistantMessage("Please share your email to get started.");
          setIsLoading(false);
          return;
        }
        appendAssistantMessage("Thanks! What service would you like to book?");
        await maybeShowPromo("AFTER_EMAIL_CAPTURE", { 
          email: extractedEmail,
          serviceId: selectedService?.id ?? null,
          servicePriceCents: selectedService?.price_cents ?? null,
        });
        setStage("SELECT_SERVICE");
        setIsLoading(false);
        return;
      }

      if (stage === "PREFERRED_STYLE") {
        if (/^(skip|no|none|not now)\b/i.test(normalized)) {
          await skipPreferredStyle();
          setIsLoading(false);
          return;
        }

        if (/\bsame\b|same as last time|same as last|same as before|same again/i.test(normalized)) {
          await applySameAsLastTime();
          setIsLoading(false);
          return;
        }

        if (parsedDate) {
          pendingDateRef.current = parsedDate;
          appendAssistantMessage(stagePrompts.PREFERRED_STYLE);
          setIsLoading(false);
          return;
        }

        if (!isSimpleQuestion(text)) {
          await savePreferredStyle({
            text: text.trim(),
            image_url: styleDraftImageUrl ?? undefined,
          });
          setIsLoading(false);
          return;
        }
      }

      // If we're waiting for email to hold a slot and user just provided email
      const slotToHold = pendingSlotRef.current || selectedSlot;
      if (stage === "HOLDING" && extractedEmail && slotToHold && selectedService) {
        const start = new Date(slotToHold.start_time);
        const hh = String(start.getHours()).padStart(2, "0");
        const mm = String(start.getMinutes()).padStart(2, "0");
        pendingSlotRef.current = null; // Clear the ref
        await createHoldRequest({
          serviceId: selectedService.id,
          stylistId: slotToHold.stylist_id,
          date: dateStr,
          startTime: `${hh}:${mm}`,
          slot: slotToHold,
          customerEmail: extractedEmail,
          customerName: extractedName || customerName,
        });
        setIsLoading(false);
        return;
      }

      if (matchedService && selectedService?.id !== matchedService.id) {
        setSelectedService(matchedService);
        resetPreferredStyleState();
        setStage("PREFERRED_STYLE");
        if (parsedDate) {
          setDateStr(parsedDate);
          pendingDateRef.current = parsedDate;
        }
        appendAssistantMessage(stagePrompts.PREFERRED_STYLE);
        setIsLoading(false);
        return;
      }
      if (parsedDate) {
        setDateStr(parsedDate);
      }

      const serviceForFlow = matchedService ?? selectedService;
      if (serviceForFlow && !preferredStyleComplete && stage !== "PREFERRED_STYLE") {
        if (parsedDate) {
          pendingDateRef.current = parsedDate;
        }
        setStage("PREFERRED_STYLE");
        appendAssistantMessage(stagePrompts.PREFERRED_STYLE);
        setIsLoading(false);
        return;
      }

      // Fast-path: if the user typed a clear service/date/time, advance without waiting for LLM
      if (!isSimpleQuestion(text)) {
        const dateForFlow = parsedDate ?? dateStr;

        // User provided service + date + time (e.g., "haircut 2pm Jan 1")
        if (serviceForFlow && parsedDate && parsedTime) {
          setSelectedService(serviceForFlow);
          // Don't set stage to SELECT_SLOT since we're handling time directly
          const fetchedSlots = await loadSlots(serviceForFlow, dateForFlow, { announce: false, setStageToSlot: false });
          if (!fetchedSlots.length) {
            appendAssistantMessage(describeSlots(fetchedSlots, dateForFlow));
            setStage("SELECT_DATE");
            setIsLoading(false);
            return;
          }

          // Use step-by-step flow: Time → Stylist → Email
          const handled = await handleTimeFromChat(fetchedSlots, parsedTime, parsedStylist, extractedEmail, extractedName);
          if (handled) {
            setIsLoading(false);
            return;
          }
        }

        // User in SELECT_SLOT stage and typed a time (e.g., "2 PM")
        if (stage === "SELECT_SLOT" && selectedService && parsedTime) {
          const handled = await handleTimeFromChat(slots, parsedTime, parsedStylist, extractedEmail, extractedName);
          if (handled) {
            setIsLoading(false);
            return;
          }
        }

        // User in SELECT_STYLIST stage and typed a stylist name
        if (stage === "SELECT_STYLIST" && selectedTime && parsedStylist) {
          const parsedTimeObj = parseTimeFromText(selectedTime);
          if (parsedTimeObj) {
            const matchedSlot = matchSlotByTime(slots, parsedTimeObj, parsedStylist);
            if (matchedSlot) {
              const handled = await handleStylistSelected(matchedSlot, extractedEmail, extractedName);
              if (handled) {
                setIsLoading(false);
                return;
              }
            }
          }
        }

        if (stage === "CONFIRMING" && hold?.booking_id && /confirm|yes|yep|book|finalize/.test(normalized)) {
          await confirmBooking(hold.booking_id);
          setIsLoading(false);
          return;
        }

        if ((stage === "WELCOME" || stage === "SELECT_SERVICE") && matchedService) {
          if (parsedDate) {
            await loadSlots(matchedService, parsedDate, { announce: true });
          } else {
            await onSelectService(matchedService);
          }
          setIsLoading(false);
          return;
        }

        if ((stage === "SELECT_DATE" || stage === "WELCOME" || stage === "SELECT_SERVICE") && serviceForFlow && parsedDate) {
          await loadSlots(serviceForFlow, parsedDate, { announce: true });
          setIsLoading(false);
          return;
        }
      }

      // Allow free-text parsing: service/date/time can still be parsed downstream by the AI.
      // Minimal guardrails to keep DONE loop clean.
      if (!isSimpleQuestion(text) && stage === "DONE") {
        setStage("SELECT_SERVICE");
      }

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
      case "show_services": {
        resetPreferredStyleState();
        setStage("SELECT_SERVICE");
        appendAssistantMessage(stagePrompts.SELECT_SERVICE);
        break;
      }
      case "select_service": {
        const serviceId = params.service_id;
        if (serviceId) {
          const numericId = typeof serviceId === 'string' ? parseInt(serviceId, 10) : serviceId;
          const svc = services.find((s) => s.id === numericId);
          if (svc) {
            setSelectedService(svc);
            resetPreferredStyleState();
            setStage("PREFERRED_STYLE");
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
          const nextSlots = await loadSlotsByIds(serviceId as number, date, { announce: false });
          if (!nextSlots.length) {
            appendAssistantMessage(`No openings on ${formatDateLabel(date)}. Try another date?`);
            setStage("SELECT_DATE");
          }
        } else {
          appendAssistantMessage("Tell me which service and date you'd like, and I'll pull up times.");
        }
        break;
      }
      case "show_slots": {
        if (Array.isArray(params.slots)) {
          const nextSlots = params.slots as Slot[];
          setSlots(nextSlots);
          setStage(nextSlots.length ? "SELECT_SLOT" : "SELECT_DATE");
          appendAssistantMessage(describeSlots(nextSlots, dateStr));
        }
        break;
      }
      case "ask_email": {
        setMode("chat");
        appendAssistantMessage("Share your email here and I'll save it for your booking.");
        break;
      }
      case "hold_slot": {
        const serviceId = Number(params.service_id);
        const stylistId = Number(params.stylist_id);
        const date = typeof params.date === "string" ? params.date : "";
        const startTime = typeof params.start_time === "string" ? params.start_time : "";
        if (serviceId && stylistId && date && startTime) {
          await createHoldRequest({
            serviceId,
            stylistId,
            date,
            startTime,
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
      case "get_last_preferred_style": {
        const serviceId = Number(params.service_id || selectedService?.id);
        const email = String(params.customer_email || customerEmail || "").trim();
        if (!serviceId) {
          appendAssistantMessage("Which service should I check for?");
          break;
        }
        if (!email) {
          appendAssistantMessage("What's your email so I can look that up?");
          break;
        }
        const style = await fetchLastPreferredStyle(email, serviceId);
        if (style && hasPreferredStyleData(style)) {
          appendAssistantMessage("I found your last saved style preference.");
        } else {
          appendAssistantMessage("I don't see a saved style for that service yet.");
        }
        break;
      }
      case "set_preferred_style": {
        const serviceId = Number(params.service_id || selectedService?.id);
        const email = String(params.customer_email || customerEmail || "").trim();
        if (!serviceId) {
          appendAssistantMessage("Which service should I save this style for?");
          break;
        }
        const svc = services.find((s) => s.id === serviceId);
        if (svc) {
          setSelectedService(svc);
        }
        await savePreferredStyle(
          {
            text: params.preferred_style_text as string | undefined,
            image_url: params.preferred_style_image_url as string | undefined,
          },
          { emailOverride: email, serviceIdOverride: serviceId }
        );
        break;
      }
      case "apply_same_as_last_time": {
        const email = String(params.customer_email || customerEmail || "").trim();
        const serviceId = Number(params.service_id || selectedService?.id);
        await applySameAsLastTime(email || undefined, serviceId || undefined);
        break;
      }
      case "skip_preferred_style": {
        await skipPreferredStyle();
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
    slot?: Slot;
    announce?: boolean;
    autoConfirm?: boolean;
  }) {
    const svc = services.find((s) => s.id === args.serviceId) || selectedService;
    const secondaryService =
      comboAccepted && comboOtherService ? comboOtherService : null;
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
    const announceHold = args.announce !== false;
    const autoConfirm = Boolean(args.autoConfirm);

    setHoldLoading(true);
    try {
      setStage("HOLDING");
      const [holdHour, holdMinute] = args.startTime.split(":").map(Number);
      const urlSlot: Slot | undefined =
        args.slot ||
        slots.find(
          (slot) =>
            slot.stylist_id === args.stylistId &&
            new Date(slot.start_time).getHours() === holdHour &&
            new Date(slot.start_time).getMinutes() === holdMinute
        );

    // Send promo_id if we have an applied promo from an earlier trigger point
    const promoIdToSend = appliedPromo?.id ?? null;

    const payload = {
      service_id: svc.id,
      secondary_service_id: secondaryService?.id ?? null,
      date: args.date,
      start_time: args.startTime,
      stylist_id: args.stylistId,
      customer_name: name,
      customer_email: email,
      customer_phone: customerPhone || undefined,
      tz_offset_minutes: tzOffset,
      promo_id: promoIdToSend,
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
          const totalDurationMinutes =
            svc.duration_minutes + (secondaryService?.duration_minutes ?? 0);
          setSelectedSlot({
            stylist_id: args.stylistId,
            stylist_name: "Selected stylist",
            start_time: dateObj.toISOString(),
            end_time: new Date(dateObj.getTime() + (totalDurationMinutes || 30) * 60000).toISOString(),
          });
        }
        setStage("CONFIRMING");
        if (announceHold) {
          appendAssistantMessage("Slot reserved. Tap Confirm booking to finalize.");
        }
        // Note: AFTER_HOLD_CREATED trigger removed - promos applied earlier at AFTER_EMAIL_CAPTURE/AFTER_SERVICE_SELECTED
        // Immediately refresh booking list for this email
        if (email) {
          await trackBookings(email);
        }
        if (autoConfirm) {
          await confirmBooking(data.booking_id);
        }
      } else {
        appendAssistantMessage("This slot is no longer available. Please pick another time.");
        setStage("SELECT_SLOT");
      }
    } catch {
      appendAssistantMessage("I had trouble reserving that slot. Please try again or pick another time.");
      setStage("SELECT_SLOT");
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
      slot: selectedSlot,
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
        setStage("DONE");
        appendAssistantMessage("You're all set. Your booking is confirmed.");
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

  async function trackBookings(overrideIdentity?: string) {
    const identity = (overrideIdentity || trackIdentity || trackEmail || customerEmail).trim();
    if (!identity) {
      setTrackError("Enter your email or phone number.");
      return;
    }

    setTrackLoading(true);
    setTrackError("");
    setTrackResults([]);
    try {
      // Determine if input is phone or email
      const isPhone = /^[\d\s\-\+\(\)]+$/.test(identity);
      const url = new URL(`${API_BASE}/bookings/${isPhone ? 'lookup' : 'track'}`);
      url.searchParams.set(isPhone ? "phone" : "email", identity);
      const res = await fetch(url.toString());
      if (res.ok) {
        const data: BookingTrack[] = await res.json();
        setTrackResults(data);
        setSelectedTrackBooking(null);
        setLastTrackedIdentity(identity.toLowerCase());
        if (data.length === 0) {
          setTrackError(`No bookings found for this ${isPhone ? 'phone number' : 'email'} yet.`);
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
    resetPreferredStyleState();
    setStage("CAPTURE_EMAIL");
    setAppliedPromo(null);
    setComboServiceId(null);
    setComboChoice(null);
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

  // Confirmation success popup (dismissible)
  const [showConfirmationPopup, setShowConfirmationPopup] = useState(false);

  // Show popup when confirmed
  React.useEffect(() => {
    if (confirmed) {
      setShowConfirmationPopup(true);
    }
  }, [confirmed]);

  const dismissConfirmation = () => {
    setShowConfirmationPopup(false);
  };

  const bookAnotherAndDismiss = () => {
    setShowConfirmationPopup(false);
    resetBooking();
  };

  const basePriceCents =
    (selectedService?.price_cents ?? 0) +
    (comboAccepted && comboOtherService ? comboOtherService.price_cents : 0);
  
  // Use the backend's discount if available (from hold), otherwise calculate from appliedPromo
  const actualDiscountCents = hold?.discount_cents ?? 0;
  const calculatedDiscountCents = appliedPromo 
    ? getPromoDiscountCents(appliedPromo, basePriceCents)
    : 0;
  const discountCents = hold ? actualDiscountCents : calculatedDiscountCents;
  const totalCents = Math.max(basePriceCents - discountCents, 0);
  
  const promoTotals = useMemo(
    () => ({ totalCents, discountCents }),
    [totalCents, discountCents]
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-blue-50">
      {/* Confirmation Popup */}
      {showConfirmationPopup && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-sm w-full animate-fadeIn relative">
            {/* Close button */}
            <button
              onClick={dismissConfirmation}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            
            {/* Success icon */}
            <div className="w-14 h-14 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            
            <h2 className="text-xl font-semibold text-gray-900 text-center mb-1">Booking Confirmed!</h2>
            <p className="text-sm text-gray-500 text-center mb-4">Confirmation sent to your email.</p>
            
            {/* Booking details */}
            <div className="bg-gray-50 rounded-xl p-4 text-sm space-y-2 mb-4">
              <div className="flex justify-between">
                <span className="text-gray-500">Service</span>
                <span className="font-medium text-gray-900">{combinedServiceLabel}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Date</span>
                <span className="font-medium text-gray-900">{formatDateLabel(dateStr)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Time</span>
                <span className="font-medium text-gray-900">
                  {selectedSlot && formatTime(selectedSlot.start_time)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Stylist</span>
                <span className="font-medium text-gray-900">{selectedSlot?.stylist_name}</span>
              </div>
              <div className="border-t border-gray-200 pt-2 flex justify-between">
                <span className="text-gray-500">Subtotal</span>
                <span className="font-medium text-gray-900">
                  {formatMoney(basePriceCents)}
                </span>
              </div>
              {(promoTotals.discountCents > 0 || (appliedPromo && (appliedPromo.type !== "SERVICE_COMBO_PROMO" || comboAccepted))) && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Promotion</span>
                  <span className="font-medium text-green-700">
                    {promoTotals.discountCents > 0
                      ? `- ${formatMoney(promoTotals.discountCents)}`
                      : "Applied"}
                  </span>
                </div>
              )}
              <div className="border-t border-gray-200 pt-2 flex justify-between">
                <span className="text-gray-500">Total</span>
                <span className="font-semibold text-gray-900">
                  {selectedService && formatMoney(promoTotals.totalCents)}
                </span>
              </div>
            </div>
            
            <button
              onClick={bookAnotherAndDismiss}
              className="w-full py-2.5 text-blue-600 hover:text-blue-700 font-medium text-sm hover:bg-blue-50 rounded-lg transition-colors"
            >
              Book another appointment
            </button>
          </div>
        </div>
      )}

      {selectedTrackBooking && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-md w-full animate-fadeIn relative">
            <button
              onClick={() => setSelectedTrackBooking(null)}
              className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Preferred style</h3>
              <p className="text-xs text-gray-500">
                {selectedTrackBooking.secondary_service_name
                  ? `${selectedTrackBooking.service_name} + ${selectedTrackBooking.secondary_service_name}`
                  : selectedTrackBooking.service_name}{" "}
                · {formatTime(selectedTrackBooking.start_time)}
              </p>
            </div>
            {selectedTrackBooking.preferred_style_text && (
              <p className="text-sm text-gray-700 whitespace-pre-wrap mb-4">
                {selectedTrackBooking.preferred_style_text}
              </p>
            )}
            {selectedTrackBooking.preferred_style_image_url && (
              <div className="rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
                <img
                  src={selectedTrackBooking.preferred_style_image_url}
                  alt="Preferred style"
                  className="w-full max-h-64 object-cover"
                />
              </div>
            )}
            {!selectedTrackBooking.preferred_style_text &&
              !selectedTrackBooking.preferred_style_image_url && (
                <p className="text-sm text-gray-500">No preferred style saved for this booking.</p>
              )}
          </div>
        </div>
      )}

      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-gray-900">Bishops Tempe</h1>
              <p className="text-sm text-gray-500">Premium Hair Studio</p>
            </div>
            <div className="flex items-center gap-3">
              <a
                href="/owner"
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Owner
              </a>
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

              {/* Guardrailed controls */}
              {stage === "SELECT_SERVICE" && services.length > 0 && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">Choose a service:</p>
                  <div className="flex flex-wrap gap-2">
                    {services.map((svc) => (
                      <button
                        key={svc.id}
                        onClick={() => onSelectService(svc)}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                      >
                        {svc.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {stage === "PREFERRED_STYLE" && selectedService && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">
                    Preferred style for {selectedService.name}?
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {hasPreferredStyleData(lastPreferredStyle) && (
                      <button
                        onClick={() => applySameAsLastTime()}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                      >
                        Same as last time
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setStyleMode("text");
                        setStyleDraftText("");
                        setStyleDraftImageUrl(null);
                      }}
                      className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                    >
                      Type it
                    </button>
                    <button
                      onClick={() => styleFileInputRef.current?.click()}
                      disabled={styleUploading}
                      className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors disabled:opacity-60"
                    >
                      {styleUploading ? "Uploading..." : "Add image"}
                    </button>
                    <button
                      onClick={() => skipPreferredStyle()}
                      className="px-4 py-2 bg-gray-800 text-white text-sm rounded-full transition-colors"
                    >
                      Skip
                    </button>
                  </div>

                  {styleMode !== "idle" && (
                    <div className="mt-4 rounded-2xl border border-gray-100 bg-gray-50/70 p-4 space-y-3">
                      {styleDraftImageUrl && (
                        <div className="rounded-xl overflow-hidden border border-gray-200 bg-white">
                          <img
                            src={styleDraftImageUrl}
                            alt="Preferred style"
                            className="w-full max-h-48 object-cover"
                          />
                        </div>
                      )}
                      <textarea
                        value={styleDraftText}
                        onChange={(event) => setStyleDraftText(event.target.value)}
                        placeholder="Describe your preferred style (optional if you uploaded an image)."
                        className="w-full min-h-[90px] rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-200"
                      />
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() =>
                            savePreferredStyle({
                              text: styleDraftText,
                              image_url: styleDraftImageUrl ?? undefined,
                            })
                          }
                          disabled={styleSaving}
                          className="px-4 py-2 bg-gray-800 text-white text-sm rounded-full disabled:opacity-60"
                        >
                          {styleSaving ? "Saving..." : "Save preference"}
                        </button>
                        <button
                          onClick={() => {
                            setStyleMode("idle");
                            setStyleDraftText("");
                            setStyleDraftImageUrl(null);
                          }}
                          className="px-4 py-2 bg-white text-gray-600 text-sm rounded-full border border-gray-200"
                        >
                          Cancel
                        </button>
                      </div>
                      {styleError && (
                        <p className="text-xs text-red-600">{styleError}</p>
                      )}
                    </div>
                  )}
                  {styleMode === "idle" && styleError && (
                    <p className="mt-3 text-xs text-red-600">{styleError}</p>
                  )}

                  {appliedPromo?.type === "SERVICE_COMBO_PROMO" &&
                    comboOtherService &&
                    comboChoice === "pending" && (
                      <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                        <p className="text-sm text-blue-900 font-medium">
                          Bundle this with {comboOtherService.name} for the combo offer?
                        </p>
                        <p className="text-xs text-blue-700 mt-1">
                          You can add it now or skip the combo.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => {
                              if (comboOtherServiceId) {
                                setComboServiceId(comboOtherServiceId);
                                setComboChoice("accepted");
                                appendAssistantMessage(
                                  `Added ${comboOtherService.name} to your booking.`
                                );
                              }
                            }}
                            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-full"
                          >
                            Add {comboOtherService.name}
                          </button>
                          <button
                            onClick={() => {
                              setComboChoice("declined");
                              setComboServiceId(null);
                              appendAssistantMessage("No problem, we'll keep just the main service.");
                            }}
                            className="px-4 py-2 bg-white text-blue-700 text-sm rounded-full border border-blue-200"
                          >
                            No thanks
                          </button>
                        </div>
                      </div>
                    )}
                  {comboChoice === "accepted" && comboOtherService && (
                    <p className="mt-3 text-xs text-green-700">
                      Combo added: {comboOtherService.name}.
                    </p>
                  )}

                  <input
                    ref={styleFileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) {
                        handleStyleImageUpload(file);
                      }
                      event.currentTarget.value = "";
                    }}
                  />
                </div>
              )}

              {stage === "SELECT_DATE" && selectedService && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">Pick a date:</p>
                  {appliedPromo?.type === "SERVICE_COMBO_PROMO" &&
                    comboOtherService &&
                    comboChoice === "pending" && (
                      <div className="mb-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                        <p className="text-sm text-blue-900 font-medium">
                          Bundle this with {comboOtherService.name} for the combo offer?
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => {
                              if (comboOtherServiceId) {
                                setComboServiceId(comboOtherServiceId);
                                setComboChoice("accepted");
                                appendAssistantMessage(
                                  `Added ${comboOtherService.name} to your booking.`
                                );
                              }
                            }}
                            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-full"
                          >
                            Add {comboOtherService.name}
                          </button>
                          <button
                            onClick={() => {
                              setComboChoice("declined");
                              setComboServiceId(null);
                              appendAssistantMessage("No problem, we'll keep just the main service.");
                            }}
                            className="px-4 py-2 bg-white text-blue-700 text-sm rounded-full border border-blue-200"
                          >
                            No thanks
                          </button>
                        </div>
                      </div>
                    )}
                  <div className="flex flex-wrap gap-2">
                    {dateOptions.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => onSelectDate(opt.value)}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {stage === "SELECT_SLOT" && slots.length > 0 && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">Pick a time:</p>
                  <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
                    {/* Show unique times only */}
                    {Array.from(new Set(slots.map((s) => formatTime(s.start_time)))).map((timeStr) => (
                      <button
                        key={timeStr}
                        onClick={() => onSelectTime(timeStr)}
                        className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                      >
                        {timeStr}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {stage === "SELECT_STYLIST" && selectedTime && (
                <div className="px-6 pb-4">
                  <p className="text-xs text-gray-500 mb-3">Choose a stylist for {selectedTime}:</p>
                  <div className="flex flex-wrap gap-2">
                    {slots
                      .filter((s) => formatTime(s.start_time) === selectedTime)
                      .map((slot) => (
                        <button
                          key={slot.stylist_id}
                          onClick={() => onSelectStylist(slot.stylist_id, slot.stylist_name)}
                          className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-full transition-colors"
                        >
                          {slot.stylist_name}
                        </button>
                      ))}
                  </div>
                </div>
              )}

              {stage === "CONFIRMING" && hold && !confirmed && (
                <div className="px-6 pb-4">
                  <button
                    onClick={() => confirmBooking()}
                    disabled={confirmLoading}
                    className="w-full py-3 bg-gray-700 hover:bg-gray-800 disabled:bg-gray-300 text-white rounded-xl font-semibold transition-all"
                  >
                    {confirmLoading ? "Confirming..." : "Confirm booking"}
                  </button>
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
                      {combinedServiceLabel || "Select a service"}
                    </span>
                  </div>
                  {selectedService && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Subtotal</span>
                      <span className="font-medium text-gray-800">
                        {formatMoney(basePriceCents)}
                      </span>
                    </div>
                  )}
                  {selectedService &&
                    appliedPromo &&
                    (appliedPromo.type !== "SERVICE_COMBO_PROMO" || comboAccepted) && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Promotion</span>
                      <span className="font-medium text-green-700">
                        {promoTotals.discountCents > 0
                          ? `- ${formatMoney(promoTotals.discountCents)}`
                          : "Applied"}
                      </span>
                    </div>
                  )}
                  {selectedService && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Total</span>
                      <span className="font-semibold text-gray-800">
                        {formatMoney(promoTotals.totalCents)}
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
                  <p className="text-sm text-gray-500">Enter your email or phone number to see status and details.</p>
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
                  type="text"
                  value={trackIdentity}
                  onChange={(e) => setTrackIdentity(e.target.value)}
                  placeholder="Email or phone number"
                  className="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-gray-400"
                />
                <button
                  type="submit"
                  className="px-5 py-3 bg-gray-700 hover:bg-gray-800 text-white rounded-xl font-semibold transition disabled:bg-gray-300 disabled:cursor-not-allowed"
                  disabled={trackLoading || !trackIdentity.trim()}
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
                {trackResults.map((b) => {
                  const hasStyle = Boolean(
                    (b.preferred_style_text && b.preferred_style_text.trim()) ||
                      b.preferred_style_image_url
                  );
                  return (
                    <div
                      key={b.booking_id}
                      onClick={() => {
                        if (hasStyle) setSelectedTrackBooking(b);
                      }}
                      className={`border border-gray-100 rounded-2xl p-5 bg-gray-50/60 ${
                        hasStyle ? "cursor-pointer hover:border-blue-200" : ""
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm text-gray-500">{new Date(b.start_time).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</p>
                          <h3 className="text-lg font-semibold text-gray-900">
                            {b.secondary_service_name
                              ? `${b.service_name} + ${b.secondary_service_name}`
                              : b.service_name}
                          </h3>
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
                        {b.total_price_cents != null && (
                          <div className="flex items-center gap-2">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {b.discount_cents && b.discount_cents > 0 ? (
                              <span>
                                <span className="line-through text-gray-400 mr-1">
                                  {formatMoney((b.service_price_cents || 0) + (b.secondary_service_price_cents || 0))}
                                </span>
                                <span className="text-green-700 font-medium">
                                  {formatMoney(b.total_price_cents)}
                                </span>
                              </span>
                            ) : (
                              <span>{formatMoney(b.total_price_cents)}</span>
                            )}
                          </div>
                        )}
                      </div>
                      {hasStyle && (
                        <button
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedTrackBooking(b);
                          }}
                          className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-100 px-3 py-2 rounded-full"
                        >
                          View preferred style
                        </button>
                      )}
                    </div>
                  );
                })}

                {!trackLoading && !trackResults.length && lastTrackedIdentity && !trackError && (
                  <p className="text-sm text-gray-500">No bookings found for {lastTrackedIdentity} yet.</p>
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
