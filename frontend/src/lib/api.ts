/**
 * API Helper Library for Convo Frontend
 * Provides typed fetch functions for backend communication.
 * 
 * ## Architecture
 * - Uses Next.js backend proxy by default (/api/backend/...)
 * - All authenticated requests use Clerk JWT tokens
 * - NO X-User-Id header or localStorage - Clerk is the ONLY auth method
 * 
 * ## Authentication
 * - User identity comes from Clerk JWT token
 * - Backend verifies JWT against Clerk's public keys
 * - No dev-user fallbacks - always requires real authentication
 * 
 * ## Best Practices
 * - ALWAYS use apiFetch() for API calls - it handles auth automatically
 * - For authenticated endpoints, user must be signed in via Clerk
 * - Public endpoints can be called with skipAuth: true
 */

// ──────────────────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────────────────

const DEBUG_LOGGING = typeof window !== "undefined" && process.env.NODE_ENV === "development";

/**
 * Get the API base URL.
 * 
 * Priority:
 * 1. NEXT_PUBLIC_API_BASE if explicitly set (backward compatibility)
 * 2. /api/backend (Next.js proxy - recommended)
 * 
 * The proxy approach is preferred because:
 * - Works regardless of backend port
 * - No CORS issues (same-origin)
 * - Works in both development and production
 */
export function getApiBase(): string {
  // Allow explicit override for backward compatibility
  const explicitBase = process.env.NEXT_PUBLIC_API_BASE;
  if (explicitBase) {
    return explicitBase;
  }
  
  // Default to Next.js backend proxy
  return "/api/backend";
}

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

export interface CreateShopPayload {
  owner_user_id: string;
  name: string;
  phone_number?: string;
  timezone?: string;
  address?: string;
  category?: string;
  // Phase 3: Location coordinates for RouterGPT discovery
  latitude?: number;
  longitude?: number;
}

export interface Shop {
  id: number;
  slug: string;
  name: string;
  phone: string | null;
  timezone: string;
  address: string | null;
  category: string | null;
  // Phase 3: Location coordinates
  latitude: number | null;
  longitude: number | null;
  created_at: string;
}

/**
 * Shop info response from /s/{slug}/info - includes routing hints
 */
export interface ShopInfo {
  id: number;
  slug: string;
  name: string;
  category: string | null;
  timezone: string;
  address: string | null;
  phone: string | null;
  // Routing hints (server-authoritative)
  is_cab_service: boolean;
  owner_dashboard_path: string;
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

export interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  /** 
   * Skip authentication for public endpoints.
   * When true, no Authorization header is sent.
   */
  skipAuth?: boolean;
  /** Request body - will be JSON.stringify'd if object */
  body?: BodyInit | object | null;
  /** Skip automatic JSON content-type header */
  skipContentType?: boolean;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
}

// ──────────────────────────────────────────────────────────
// API Fetch Wrapper
// ──────────────────────────────────────────────────────────

/**
 * Get Clerk JWT token if available
 * This function safely retrieves the JWT from Clerk's session
 */
async function getClerkToken(): Promise<string | null> {
  try {
    if (typeof window === "undefined") return null;
    
    // Use Clerk's public API if available
    if ((window as any).Clerk) {
      // First try default template
      const token = await (window as any).Clerk.session?.getToken().catch((err: any) => {
        if (DEBUG_LOGGING) {
          console.log('[API Auth] Clerk.session.getToken() failed:', err);
        }
        return null;
      });
      
      if (token) {
        if (DEBUG_LOGGING) {
          console.log('[API Auth] Successfully retrieved Clerk JWT token');
        }
        return token;
      }
    } else {
      if (DEBUG_LOGGING) {
        console.log('[API Auth] window.Clerk is not available yet');
      }
    }
    
    return null;
  } catch (error) {
    if (DEBUG_LOGGING) {
      console.log(`[API Auth] Failed to get Clerk token:`, error);
    }
    return null;
  }
}

/**
 * Centralized API fetch wrapper with automatic Clerk JWT auth.
 * 
 * Features:
 * - Automatic Clerk JWT token injection in Authorization header
 * - Request timeout handling
 * - Consistent error handling with ApiError type
 * - Debug logging in development
 * - Safe JSON body handling
 * 
 * @example
 * // Simple GET (auto-authenticates with Clerk JWT)
 * const shops = await apiFetch<Shop[]>('/shops');
 * 
 * // POST with body
 * const shop = await apiFetch<Shop>('/shops', {
 *   method: 'POST',
 *   body: { name: 'My Shop' },
 * });
 * 
 * // Skip auth for public endpoints
 * const publicData = await apiFetch('/public/info', { skipAuth: true });
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { 
    skipAuth = false, 
    body, 
    skipContentType,
    timeout = 30000,
    ...fetchOptions 
  } = options;
  
  // Build headers
  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string> || {}),
  };
  
  // Add Content-Type for JSON unless explicitly skipped
  if (!skipContentType && body && typeof body === "object" && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  
  // Get Clerk JWT token for authentication (unless skipped)
  if (!skipAuth) {
    const clerkToken = await getClerkToken();
    if (clerkToken) {
      headers["Authorization"] = `Bearer ${clerkToken}`;
      if (DEBUG_LOGGING) {
        console.log(`[API Auth] Using Clerk JWT token`);
      }
    } else {
      if (DEBUG_LOGGING) {
        console.warn(`[API Auth] No Clerk token available - user may not be signed in`);
      }
    }
  }

  const url = `${getApiBase()}${endpoint}`;
  
  // Serialize body
  let serializedBody: BodyInit | null | undefined;
  if (body === null || body === undefined) {
    serializedBody = undefined;
  } else if (typeof body === "object" && !(body instanceof FormData) && !(body instanceof ArrayBuffer)) {
    serializedBody = JSON.stringify(body);
  } else {
    serializedBody = body as BodyInit;
  }
  
  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  if (DEBUG_LOGGING) {
    console.log(`[API] ${fetchOptions.method || 'GET'} ${endpoint}`, { 
      hasAuth: !!headers["X-User-Id"],
      hasBody: !!body 
    });
  }
  
  try {
    const res = await fetch(url, {
      ...fetchOptions,
      headers,
      body: serializedBody,
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);

    if (!res.ok) {
      let detail = "Request failed";
      try {
        const errBody = await res.json();
        detail = errBody.detail || errBody.error || detail;
      } catch {
        // Response wasn't JSON, try text
        try {
          detail = await res.text() || detail;
        } catch {
          // ignore
        }
      }
      
      if (DEBUG_LOGGING) {
        // Don't log expected 404s (like checking if cab owner exists)
        const isExpected404 = res.status === 404 && (
          endpoint.includes('/owner/cab/owner') ||
          endpoint.includes('not configured')
        );
        
        if (!isExpected404) {
          console.error(`[API] Error ${res.status}: ${detail}`, { endpoint });
        }
      }
      
      const error: ApiError = { detail, status: res.status };
      throw error;
    }
    
    // Handle empty responses
    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      return {} as T;
    }
    
    const text = await res.text();
    if (!text) {
      return {} as T;
    }

    return JSON.parse(text) as T;
  } catch (err) {
    clearTimeout(timeoutId);
    
    // Handle abort (timeout)
    if (err instanceof Error && err.name === "AbortError") {
      if (DEBUG_LOGGING) {
        console.error(`[API] Timeout after ${timeout}ms`, { endpoint });
      }
      const error: ApiError = { 
        detail: `Request timed out after ${timeout / 1000} seconds`, 
        status: 504 
      };
      throw error;
    }
    
    // Re-throw ApiError as-is
    if (isApiError(err)) {
      throw err;
    }
    
    // Wrap other errors
    if (DEBUG_LOGGING) {
      console.error(`[API] Network error:`, err);
    }
    const error: ApiError = { 
      detail: err instanceof Error ? err.message : "Network error", 
      status: 0 
    };
    throw error;
  }
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
    body: payload,
  });
}

/**
 * Get public shop info by slug.
 */
export async function getShopBySlug(slug: string): Promise<Shop> {
  return apiFetch<Shop>(`/shops/${slug}`, { skipAuth: true }); // Public endpoint
}

/**
 * Get shop info including routing hints.
 * This is the SERVER-AUTHORITATIVE endpoint for determining which dashboard to show.
 * 
 * @param slug - Shop URL slug
 * @returns ShopInfo including is_cab_service and owner_dashboard_path
 */
export async function getShopInfo(slug: string): Promise<ShopInfo> {
  return apiFetch<ShopInfo>(`/s/${slug}/info`, { skipAuth: true }); // Public endpoint
}

// ──────────────────────────────────────────────────────────
// Shop-Scoped Endpoints
// ──────────────────────────────────────────────────────────

/**
 * Get services for a shop.
 */
export async function getServices(slug: string): Promise<Service[]> {
  return apiFetch<Service[]>(`/s/${slug}/services`, { skipAuth: true }); // Public endpoint
}

/**
 * Get stylists for a shop.
 */
export async function getStylists(slug: string): Promise<Stylist[]> {
  return apiFetch<Stylist[]>(`/s/${slug}/stylists`, { skipAuth: true }); // Public endpoint
}

/**
 * Send a message to the owner chat endpoint.
 * Requires user authentication (auto-injected from localStorage).
 */
export async function ownerChat(
  slug: string,
  messages: OwnerMessage[],
  userId?: string
): Promise<OwnerChatResponse> {
  return apiFetch<OwnerChatResponse>(`/s/${slug}/owner/chat`, {
    method: "POST",
    body: { messages },
    ...(userId && { userId }), // Only override if explicitly provided
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
    if (err.status === 503) {
      return "Backend service is unavailable. Please try again later.";
    }
    if (err.status === 504) {
      return "Request timed out. Please try again.";
    }
    return err.detail;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return "An unexpected error occurred.";
}

// ──────────────────────────────────────────────────────────
// DEPRECATED: Legacy localStorage Auth Stubs
// ──────────────────────────────────────────────────────────
// These functions are deprecated and will be removed.
// Authentication is now handled exclusively via Clerk JWT.
// These stubs exist only to provide clear migration errors.

/**
 * @deprecated Authentication is now via Clerk JWT only. Use useAuth() from @clerk/nextjs
 */
export function getStoredUserId(): null {
  if (DEBUG_LOGGING) {
    console.warn(
      "[DEPRECATED] getStoredUserId() is deprecated. " +
      "Use Clerk's useAuth().userId instead. " +
      "localStorage auth has been removed."
    );
  }
  return null;
}

/**
 * @deprecated Authentication is now via Clerk JWT only. Use Clerk for user identity.
 */
export function setStoredUserId(_userId: string): void {
  console.warn(
    "[DEPRECATED] setStoredUserId() is deprecated and has no effect. " +
    "User identity is now managed by Clerk."
  );
}

/**
 * @deprecated Authentication is now via Clerk JWT only.
 */
export function clearStoredUserId(): void {
  if (DEBUG_LOGGING) {
    console.warn(
      "[DEPRECATED] clearStoredUserId() is deprecated and has no effect. " +
      "localStorage auth has been removed."
    );
  }
}
