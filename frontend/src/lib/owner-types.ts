/**
 * Shared TypeScript types for Owner Dashboard
 * Extracted from legacy /owner/page.tsx for reuse in multi-tenant /s/[slug]/owner
 */

export type Role = "user" | "assistant" | "system";

export type OwnerMessage = {
  id: string;
  role: Role;
  text: string;
};

export type OwnerService = {
  id: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
  availability_rule?: string;
};

export type OwnerPromo = {
  id: number;
  shop_id: number;
  type: string;
  trigger_point: string;
  service_id?: number | null;
  discount_type: string;
  discount_value?: number | null;
  constraints_json?: Record<string, unknown> | null;
  custom_copy?: string | null;
  start_at_utc?: string | null;
  end_at_utc?: string | null;
  active: boolean;
  priority: number;
};

export type OwnerStylist = {
  id: number;
  name: string;
  work_start: string;
  work_end: string;
  active: boolean;
  specialties: string[];
  time_off_count: number;
};

export type ScheduleBooking = {
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

export type ScheduleTimeOff = {
  id: number;
  stylist_id: number;
  stylist_name: string;
  start_time: string;
  end_time: string;
  reason?: string | null;
};

export type OwnerSchedule = {
  date: string;
  stylists: OwnerStylist[];
  bookings: ScheduleBooking[];
  time_off: ScheduleTimeOff[];
};

export type OwnerChatResponse = {
  reply: string;
  action?: { type: string; params?: Record<string, unknown> } | null;
  suggested_chips?: string[];
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

export type CustomerProfile = {
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

export type CallSummary = {
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

export type OwnerTimeOffEntry = {
  start_time: string;
  end_time: string;
  date: string;
  reason?: string | null;
};

export type TimeOffRequestItem = {
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

export type PromoDraft = {
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

export type PinStatus = {
  has_pin: boolean;
  pin_set_at: string | null;
};

// Analytics Types
export type ServiceAnalytics = {
  service_id: number;
  service_name: string;
  bookings: number;
  completed: number;
  no_shows: number;
  no_show_rate: number;
  estimated_revenue_cents: number;
};

export type StylistAnalytics = {
  stylist_id: number;
  stylist_name: string;
  bookings: number;
  completed: number;
  no_shows: number;
  acknowledgement_rate: number;
};

export type TimeOfDayDistribution = {
  morning: number;
  afternoon: number;
  evening: number;
};

export type AnalyticsSummary = {
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

export type Anomaly = {
  metric: string;
  direction: "increase" | "decrease";
  value: string;
  likely_causes: string[];
  confidence: "low" | "medium" | "high";
};

export type Insight = {
  title: string;
  explanation: string;
  supporting_data: string[];
  confidence: "low" | "medium" | "high";
};

export type Recommendation = {
  action: string;
  expected_impact: string;
  risk: "low" | "medium" | "high";
  requires_owner_confirmation: boolean;
};

export type AIInsights = {
  executive_summary: string[];
  anomalies: Anomaly[];
  insights: Insight[];
  recommendations: Recommendation[];
  questions_for_owner: string[];
};

// Constants
export const PROMO_TYPES = [
  { value: "FIRST_USER_PROMO", label: "First-time customer" },
  { value: "DAILY_PROMO", label: "Daily offer" },
  { value: "SEASONAL_PROMO", label: "Seasonal campaign" },
  { value: "SERVICE_COMBO_PROMO", label: "Service combo" },
] as const;

export const PROMO_TRIGGERS = [
  { value: "AT_CHAT_START", label: "At chat start" },
  { value: "AFTER_EMAIL_CAPTURE", label: "After email capture" },
  { value: "AFTER_SERVICE_SELECTED", label: "After service selected" },
  { value: "AFTER_SLOT_SHOWN", label: "After slots shown" },
  { value: "AFTER_HOLD_CREATED", label: "After hold created" },
] as const;

export const PROMO_DISCOUNTS = [
  { value: "PERCENT", label: "Percent off" },
  { value: "FIXED", label: "Fixed amount off" },
] as const;

export const DAY_OPTIONS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
] as const;

export const SLOT_MINUTES = 30;
export const ROW_HEIGHT = 60;
