/**
 * API Helper Library for Convo Frontend
 * Provides typed fetch functions for backend communication.
 */

// ──────────────────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────────────────

export function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
}

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

export interface CreateShopPayload {
  owner_user_id: string;
  name: string;
  phone?: string;
  timezone?: string;
  address?: string;
  category?: string;
}

export interface Shop {
  id: number;
  slug: string;
  name: string;
  phone: string | null;
  timezone: string;
  address: string | null;
  category: string | null;
  created_at: string;
}

export interface Service {
  id: number;
  name: string;
  duration_minutes: number;
  price_cents: number;
  description?: string;
}

export interface Stylist {
  id: number;
  name: string;
  work_start: string;
  work_end: string;
  specialties: string[];
  time_off_count: number;
}

export interface OwnerMessage {
  role: "user" | "assistant";
  content: string;
}

export interface OwnerChatResponse {
  reply: string;
  suggested_chips?: string[];
}

export interface ApiError {
  detail: string;
  status: number;
}

// ──────────────────────────────────────────────────────────
// API Fetch Wrapper
// ──────────────────────────────────────────────────────────

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit & { userId?: string } = {}
): Promise<T> {
  const { userId, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string> || {}),
  };
  
  // Add user ID header if provided
  if (userId) {
    headers["X-User-Id"] = userId;
  }

  const url = `${getApiBase()}${endpoint}`;
  const res = await fetch(url, {
    ...fetchOptions,
    headers,
  });

  if (!res.ok) {
    let detail = "Request failed";
    try {
      const errBody = await res.json();
      detail = errBody.detail || detail;
    } catch {
      // ignore parse errors
    }
    const error: ApiError = { detail, status: res.status };
    throw error;
  }

  return res.json();
}

// ──────────────────────────────────────────────────────────
// Shop Endpoints
// ──────────────────────────────────────────────────────────

/**
 * Create a new shop and owner membership.
 * Returns the created shop object with slug for redirect.
 */
export async function createShop(payload: CreateShopPayload): Promise<Shop> {
  return apiFetch<Shop>("/shops", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Get public shop info by slug.
 */
export async function getShopBySlug(slug: string): Promise<Shop> {
  return apiFetch<Shop>(`/shops/${slug}`);
}

// ──────────────────────────────────────────────────────────
// Shop-Scoped Endpoints
// ──────────────────────────────────────────────────────────

/**
 * Get services for a shop.
 */
export async function getServices(slug: string): Promise<Service[]> {
  return apiFetch<Service[]>(`/s/${slug}/services`);
}

/**
 * Get stylists for a shop.
 */
export async function getStylists(slug: string): Promise<Stylist[]> {
  return apiFetch<Stylist[]>(`/s/${slug}/stylists`);
}

/**
 * Send a message to the owner chat endpoint.
 * Requires user authentication.
 */
export async function ownerChat(
  slug: string,
  messages: OwnerMessage[],
  userId: string
): Promise<OwnerChatResponse> {
  return apiFetch<OwnerChatResponse>(`/s/${slug}/owner/chat`, {
    method: "POST",
    body: JSON.stringify({ messages }),
    userId,
  });
}

// ──────────────────────────────────────────────────────────
// Error Helpers
// ──────────────────────────────────────────────────────────

export function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === "object" &&
    err !== null &&
    "detail" in err &&
    "status" in err
  );
}

export function getErrorMessage(err: unknown): string {
  if (isApiError(err)) {
    if (err.status === 401) {
      return "You must be logged in to access this resource.";
    }
    if (err.status === 403) {
      return "You don't have permission to access this shop. Make sure you're the owner.";
    }
    if (err.status === 409) {
      return "A shop with this name already exists. Please choose a different name.";
    }
    if (err.status === 422) {
      return err.detail || "Invalid request. Please check your input.";
    }
    return err.detail;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "An unexpected error occurred.";
}

// ──────────────────────────────────────────────────────────
// Storage Helpers
// ──────────────────────────────────────────────────────────

const OWNER_USER_ID_KEY = "owner_user_id";

export function getStoredUserId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(OWNER_USER_ID_KEY);
}

export function setStoredUserId(userId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(OWNER_USER_ID_KEY, userId);
}

export function clearStoredUserId(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(OWNER_USER_ID_KEY);
}
