/**
 * Next.js Backend Proxy Route Handler
 * 
 * This catch-all route forwards all requests to the FastAPI backend,
 * eliminating port configuration issues between frontend and backend.
 * 
 * Usage: Frontend calls /api/backend/s/{slug}/... which proxies to BACKEND_URL/s/{slug}/...
 * 
 * Environment Variables:
 *   BACKEND_URL - The backend server URL (default: http://127.0.0.1:8000)
 * 
 * Features:
 *   - Timeout handling (30s default)
 *   - Connection error detection with helpful messages
 *   - Safe error propagation with meaningful HTTP status codes
 *   - Request/response logging for debugging
 */

import { NextRequest, NextResponse } from "next/server";

// Configuration
const REQUEST_TIMEOUT_MS = 30000; // 30 seconds
const DEBUG_LOGGING = process.env.NODE_ENV === "development";

// Get backend URL from environment (server-side only)
function getBackendUrl(): string {
  const url = process.env.BACKEND_URL;
  
  if (!url) {
    // In development, provide a helpful error
    if (DEBUG_LOGGING) {
      console.warn(
        "⚠️  BACKEND_URL not set. Using default http://127.0.0.1:8000\n" +
        "   Set BACKEND_URL in .env.local to configure the backend server."
      );
    }
    // Use 127.0.0.1 to avoid IPv6 resolution issues with localhost
    return "http://127.0.0.1:8000";
  }
  
  // Remove trailing slash if present
  return url.replace(/\/$/, "");
}

// Headers to skip when forwarding (hop-by-hop headers)
const SKIP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length", // Let fetch recalculate this
]);

// Logging helper
function logProxy(level: "info" | "warn" | "error", message: string, meta?: Record<string, unknown>) {
  if (!DEBUG_LOGGING && level === "info") return;
  
  const timestamp = new Date().toISOString();
  const prefix = `[Proxy ${timestamp}]`;
  
  switch (level) {
    case "info":
      console.log(prefix, message, meta ? JSON.stringify(meta) : "");
      break;
    case "warn":
      console.warn(prefix, message, meta ? JSON.stringify(meta) : "");
      break;
    case "error":
      console.error(prefix, message, meta ? JSON.stringify(meta) : "");
      break;
  }
}

// Create AbortController with timeout
function createTimeoutController(ms: number): { controller: AbortController; timeoutId: NodeJS.Timeout } {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ms);
  return { controller, timeoutId };
}

async function proxyRequest(
  request: NextRequest,
  params: { path: string[] }
): Promise<NextResponse> {
  const backendUrl = getBackendUrl();
  const path = params.path.join("/");
  
  // Build the target URL with query params
  const url = new URL(request.url);
  const targetUrl = `${backendUrl}/${path}${url.search}`;
  
  logProxy("info", `${request.method} ${targetUrl}`, { 
    hasUserId: !!request.headers.get("x-user-id") 
  });
  
  // Forward headers, excluding hop-by-hop headers
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    // Skip hop-by-hop headers and defer X-User-Id so we only set it once
    if (!SKIP_HEADERS.has(lowerKey) && lowerKey !== "x-user-id") {
      headers[key] = value;
    }
  });
  
  // Ensure X-User-Id is forwarded for owner auth
  const userId = request.headers.get("x-user-id");
  if (userId) {
    // Use a single canonical header to avoid duplicate values being joined with commas
    headers["x-user-id"] = userId;
  }
  
  // Create timeout controller
  const { controller, timeoutId } = createTimeoutController(REQUEST_TIMEOUT_MS);
  
  try {
    // Get request body for non-GET requests using arrayBuffer for raw bytes
    let body: BodyInit | null = null;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const contentType = request.headers.get("content-type") || "";
      
      if (contentType.includes("multipart/form-data")) {
        // Form data - let fetch handle it with proper boundary
        body = await request.formData();
        // Remove content-type so fetch can set it with boundary
        delete headers["Content-Type"];
      } else {
        // For all other content types (JSON, form-urlencoded, raw),
        // forward raw bytes to avoid any encoding/parsing issues
        const rawBody = await request.arrayBuffer();
        if (rawBody.byteLength > 0) {
          body = rawBody;
        }
      }
    }
    
    // Make the proxied request with timeout
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: controller.signal,
    });
    
    // Clear the timeout since request completed
    clearTimeout(timeoutId);
    
    logProxy("info", `Response: ${response.status} ${response.statusText}`, { 
      path, 
      status: response.status 
    });
    
    // Build response headers
    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      if (!SKIP_HEADERS.has(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });
    
    // Handle redirects
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location");
      if (location) {
        // Rewrite backend URLs to proxy URLs in redirects
        const rewrittenLocation = location.replace(backendUrl, "/api/backend");
        responseHeaders.set("location", rewrittenLocation);
      }
    }
    
    // Return the proxied response
    const responseBody = await response.arrayBuffer();
    
    return new NextResponse(responseBody, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    // Clear timeout on error
    clearTimeout(timeoutId);
    
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    
    // Check for timeout (AbortError)
    if (error instanceof Error && error.name === "AbortError") {
      logProxy("error", `Request timeout after ${REQUEST_TIMEOUT_MS}ms`, { 
        path, 
        targetUrl 
      });
      return NextResponse.json(
        {
          error: "Request Timeout",
          detail: `Backend request timed out after ${REQUEST_TIMEOUT_MS / 1000} seconds.`,
          hint: "The server may be overloaded or the request took too long to process.",
        },
        { status: 504 }
      );
    }
    
    // Check if it's a connection error
    const isConnectionError = 
      errorMessage.includes("ECONNREFUSED") ||
      errorMessage.includes("fetch failed") ||
      errorMessage.includes("ENOTFOUND") ||
      errorMessage.includes("ECONNRESET") ||
      errorMessage.includes("ETIMEDOUT");
    
    if (isConnectionError) {
      logProxy("error", `Backend connection failed: ${errorMessage}`, { 
        backendUrl,
        path 
      });
      return NextResponse.json(
        {
          error: "Backend Unavailable",
          detail: `Cannot connect to backend at ${backendUrl}. Is the server running?`,
          hint: "Start the backend with: cd Backend && uvicorn app.main:app --reload --port 8000",
        },
        { status: 503 }
      );
    }
    
    // Log unexpected errors
    logProxy("error", `Proxy error: ${errorMessage}`, { 
      path, 
      errorType: error instanceof Error ? error.constructor.name : typeof error 
    });
    
    return NextResponse.json(
      {
        error: "Proxy Error",
        detail: errorMessage,
      },
      { status: 502 }
    );
  }
}

// Export handlers for all HTTP methods
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}

export async function OPTIONS(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(request, await params);
}
