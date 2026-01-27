/**
 * Server-side API Client with Clerk JWT Support
 * 
 * This module provides the server-side API client for use in SERVER components,
 * route handlers, and server actions only.
 * 
 * USAGE:
 * ```tsx
 * // In a Server Component or Route Handler
 * import { createServerApiClient, serverFetch } from '@/lib/api.server';
 * 
 * // Option 1: Create a client for multiple requests
 * const client = await createServerApiClient();
 * const data = await client.fetch('/s/shop/owner/dashboard');
 * 
 * // Option 2: One-off authenticated fetch
 * const data2 = await serverFetch('/s/shop/owner/cab/summary');
 * ```
 * 
 * For CLIENT components, use api.client.ts instead.
 */

import { auth } from '@clerk/nextjs/server';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/backend';

// For server-side, we might need the full backend URL
const getServerApiBase = () => {
  // In server context, use direct backend URL if available
  const backendUrl = process.env.BACKEND_URL;
  if (backendUrl) {
    return backendUrl;
  }
  // Fallback to public API base (will work if running on same host)
  return API_BASE.startsWith('/') 
    ? `http://localhost:${process.env.PORT || 3000}${API_BASE}` 
    : API_BASE;
};

export interface ServerApiClientError {
  message: string;
  status: number;
  detail?: string;
}

/**
 * Create a server-side API client with Clerk JWT
 * 
 * This must be called in a server context (Server Component, Route Handler, etc.)
 */
export async function createServerApiClient() {
  const { getToken, userId } = await auth();
  
  async function fetchWithAuth<T = unknown>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    try {
      // Get Clerk JWT token
      const token = userId ? await getToken() : null;
      
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options?.headers as Record<string, string> || {}),
      };
      
      // Add JWT token if available
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const apiBase = getServerApiBase();
      const response = await fetch(`${apiBase}${endpoint}`, {
        ...options,
        headers,
        // Disable caching for authenticated requests by default
        cache: 'no-store',
      });
      
      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}`;
        let detail: string | undefined;
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.error || errorMessage;
          detail = errorData.detail;
        } catch {
          // Response wasn't JSON
        }
        
        const error: ServerApiClientError = { 
          message: errorMessage, 
          status: response.status,
          detail 
        };
        throw error;
      }
      
      // Handle empty responses
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        return response.json();
      }
      return {} as T;
    } catch (error) {
      console.error(`[Server API Client Error] ${endpoint}:`, error);
      throw error;
    }
  }
  
  return {
    fetch: fetchWithAuth,
    userId,
    isSignedIn: !!userId,
  };
}

/**
 * Server-side authenticated fetch - one-off request helper
 * 
 * Use this when you just need to make a single authenticated request
 * without creating a full client object.
 */
export async function serverFetch<T = unknown>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const client = await createServerApiClient();
  return client.fetch<T>(endpoint, options);
}

/**
 * Get the current user ID from server context
 * Returns null if not authenticated
 */
export async function getServerUserId(): Promise<string | null> {
  const { userId } = await auth();
  return userId;
}

/**
 * Get the Clerk JWT token from server context
 * Returns null if not authenticated
 */
export async function getServerToken(): Promise<string | null> {
  const { getToken, userId } = await auth();
  if (!userId) return null;
  return getToken();
}

/**
 * Check if an error is a ServerApiClientError
 */
export function isServerApiClientError(error: unknown): error is ServerApiClientError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'message' in error &&
    'status' in error
  );
}
