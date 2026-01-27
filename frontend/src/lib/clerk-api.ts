/**
 * API Client with Clerk JWT Support
 * 
 * ⚠️ DEPRECATED: This file is kept for backward compatibility.
 * 
 * For new code, use:
 * - Client components: import { useApiClient } from '@/lib/api.client'
 * - Server components: import { serverFetch } from '@/lib/api.server'
 */

'use client';

// Re-export everything from the new client module for backward compatibility
export { 
  useApiClient, 
  useAuthenticatedFetch,
  useGetAuthToken,
  isApiClientError,
  type ApiClientError 
} from './api.client';

