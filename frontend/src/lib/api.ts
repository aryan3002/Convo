/**
 * API Helper Library for Convo Frontend
 * Provides typed fetch functions for backend communication.
 * 
 * ## Architecture
 * - Uses Next.js backend proxy by default (/api/backend/...)
 * - This eliminates port configuration issues between frontend and backend
 * - Falls back to NEXT_PUBLIC_API_BASE if explicitly set (for backward compatibility)
 * 
 * ## Identity Management (TRANSITIONAL)
 * 
 * CURRENT STATE (Temporary):
 * - User ID is stored in localStorage under 'owner_user_id'
 * - All authenticated requests automatically include X-User-Id header
 * - This is INSECURE but works for development/pilot
 * 
 * FUTURE STATE (When Clerk is integrated):
 * - User ID will come from Clerk session/JWT
 * - X-User-Id header will be removed
 * - Server will verify JWT signature
 * 
 * ## Best Practices
 * - ALWAYS use apiFetch() for API calls - it handles auth automatically
 * - NEVER pass userId in URL query params (security risk)
 * - Use getStoredUserId() to read the current user ID
 * - Use setStoredUserId() only during onboarding
 * 
 * ## Debugging Auth Issues
 * - If you get 403 errors, check that localStorage has the correct owner_user_id
 * - The backend endpoint /s/{slug}/owner/auth-status can help diagnose issues
 * - The user_id must match what was used when creating the shop
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
   * User ID for authenticated requests. 
   * If not provided, will automatically use getStoredUserId().
   * Pass false to explicitly skip auth header.
   */
  userId?: string | false;
  /** Request body - will be JSON.stringify'd if object */
  body?: BodyInit | object | null;
  /** Skip automatic JSON content-type header */
  skipContentType?: boolean;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
}

// ──────────────────────────────────────────────────────────
// Storage Helpers (defined early for use in apiFetch)
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
  if (DEBUG_LOGGING) {
    console.log("[API] Cleared old owner_user_id from localStorage");
  }
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
 * Centralized API fetch wrapper with automatic auth injection.
 * 
 * Features:
 * - Automatic Clerk JWT token injection in Authorization header
 * - Falls back to X-User-Id from localStorage for dev/legacy compatibility
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
 * const publicData = await apiFetch('/public/info', { userId: false });
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { 
    userId: explicitUserId, 
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
  
  // Try to get Clerk JWT token first (for production auth)
  let hasAuth = false;
  if (explicitUserId !== false) {
    const clerkToken = await getClerkToken();
    if (clerkToken) {
      headers["Authorization"] = `Bearer ${clerkToken}`;
      hasAuth = true;
      if (DEBUG_LOGGING) {
        console.log(`[API Auth] Using Clerk JWT token`);
      }
    }
  }
  
  // Fallback to X-User-Id from localStorage if no JWT available (for dev mode)
  if (!hasAuth && explicitUserId !== false) {
    const userId = explicitUserId || getStoredUserId();
    if (userId) {
      headers["X-User-Id"] = userId;
      if (DEBUG_LOGGING) {
        console.log(`[API Auth] Using X-User-Id header: ${userId}`);
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
  return apiFetch<Shop>(`/shops/${slug}`, { userId: false }); // Public endpoint
}

/**
 * Get shop info including routing hints.
 * This is the SERVER-AUTHORITATIVE endpoint for determining which dashboard to show.
 * 
 * @param slug - Shop URL slug
 * @returns ShopInfo including is_cab_service and owner_dashboard_path
 */
export async function getShopInfo(slug: string): Promise<ShopInfo> {
  return apiFetch<ShopInfo>(`/s/${slug}/info`, { userId: false }); // Public endpoint
}

// ──────────────────────────────────────────────────────────
// Shop-Scoped Endpoints
// ──────────────────────────────────────────────────────────

/**
 * Get services for a shop.
 */
export async function getServices(slug: string): Promise<Service[]> {
  return apiFetch<Service[]>(`/s/${slug}/services`, { userId: false }); // Public endpoint
}

/**
 * Get stylists for a shop.
 */
export async function getStylists(slug: string): Promise<Stylist[]> {
  return apiFetch<Stylist[]>(`/s/${slug}/stylists`, { userId: false }); // Public endpoint
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
