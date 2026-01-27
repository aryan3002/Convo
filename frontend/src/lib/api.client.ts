/**
 * Client-side API Client with Clerk JWT Support
 * 
 * This module provides the client-side API client for use in CLIENT components only.
 * It automatically includes JWT token in Authorization header.
 * 
 * USAGE:
 * ```tsx
 * 'use client';
 * import { useApiClient, useAuthenticatedFetch } from '@/lib/api.client';
 * 
 * function MyComponent() {
 *   const client = useApiClient();
 *   const authFetch = useAuthenticatedFetch();
 *   
 *   // Option 1: Using the client object
 *   const data = await client.fetch('/s/shop/owner/dashboard');
 *   
 *   // Option 2: Using the fetch function directly
 *   const data2 = await authFetch('/s/shop/owner/cab/summary');
 * }
 * ```
 * 
 * For SERVER components or route handlers, use api.server.ts instead.
 */

'use client';

import { useAuth } from '@clerk/nextjs';
import { useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/backend';

export interface ApiClientError {
  message: string;
  status: number;
  detail?: string;
}

/**
 * Client-side API client hook using Clerk JWT
 * 
 * Returns an object with a `fetch` method that automatically includes
 * the Clerk JWT token in the Authorization header.
 */
export function useApiClient() {
  const { getToken, isSignedIn } = useAuth();
  
  const fetchWithAuth = useCallback(async <T = unknown>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> => {
    try {
      // Get Clerk JWT token if signed in
      const token = isSignedIn ? await getToken() : null;
      
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options?.headers as Record<string, string> || {}),
      };
      
      // Add JWT token if available (production auth)
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
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
        
        const error: ApiClientError = { 
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
      console.error(`[API Client Error] ${endpoint}:`, error);
      throw error;
    }
  }, [getToken, isSignedIn]);
  
  return {
    fetch: fetchWithAuth,
    isSignedIn,
  };
}

/**
 * Hook that returns just the authenticated fetch function
 * Useful when you only need the fetch capability without the full client object
 */
export function useAuthenticatedFetch() {
  const { fetch } = useApiClient();
  return fetch;
}

/**
 * Hook that returns a function to get the current auth token
 * Useful for making requests outside of the useApiClient pattern
 */
export function useGetAuthToken() {
  const { getToken, isSignedIn } = useAuth();
  
  return useCallback(async (): Promise<string | null> => {
    if (!isSignedIn) return null;
    return getToken();
  }, [getToken, isSignedIn]);
}

/**
 * Check if an error is an ApiClientError
 */
export function isApiClientError(error: unknown): error is ApiClientError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'message' in error &&
    'status' in error
  );
}
