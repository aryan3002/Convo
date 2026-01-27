/**
 * Clerk Middleware - Route Protection for Convo
 * 
 * This middleware:
 * - Allows PUBLIC routes for customers/employees/landing pages
 * - Protects authenticated owner ACTION routes (setup, dashboard, settings)
 * - Does NOT redirect away from /s/:slug/owner - that's a public landing page
 * 
 * PUBLIC routes (no auth required):
 * - / (home)
 * - /sign-in, /sign-up
 * - /s/:slug/cab/book (customer booking)
 * - /employee/* (employee portal)
 * - /s/:slug/owner (public owner landing page with Login button)
 * - /s/:slug/owner/landing (if exists)
 * - /api/webhook/*
 * 
 * PROTECTED routes (require authenticated owner):
 * - /s/:slug/owner/cab/setup
 * - /s/:slug/owner/cab/dashboard
 * - /s/:slug/owner/settings
 * - /s/:slug/owner/team
 */

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Define public routes that DON'T require authentication
const isPublicRoute = createRouteMatcher([
  // Home & auth pages
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  
  // API webhooks (Clerk, Stripe, etc.)
  "/api/webhook(.*)",
  
  // Customer booking flow (PUBLIC - no login needed)
  "/s/:slug/cab/book(.*)",
  "/s/(.*)/cab/book(.*)",
  
  // Employee portal (PUBLIC - employees have their own auth)
  "/employee(.*)",
  "/employee/:slug(.*)",
  
  // Owner LANDING page (PUBLIC - shows Login button for unauthenticated users)
  // This is the entry point where owners see info and can choose to log in
  "/s/:slug/owner",
  "/s/(.*)/owner",
  "/s/:slug/owner/landing",
  "/s/(.*)/owner/landing",
  
  // API backend proxy routes (auth handled by backend)
  "/api/backend(.*)",
]);

// Routes that REQUIRE authentication (owner action routes)
const isProtectedOwnerRoute = createRouteMatcher([
  // Cab service setup & management
  "/s/:slug/owner/cab/setup(.*)",
  "/s/(.*)/owner/cab/setup(.*)",
  "/s/:slug/owner/cab/dashboard(.*)",
  "/s/(.*)/owner/cab/dashboard(.*)",
  "/s/:slug/owner/cab",
  "/s/(.*)/owner/cab",
  
  // Owner settings & team management
  "/s/:slug/owner/settings(.*)",
  "/s/(.*)/owner/settings(.*)",
  "/s/:slug/owner/team(.*)",
  "/s/(.*)/owner/team(.*)",
  
  // Onboarding (requires auth to create shop)
  "/onboarding(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  const url = req.nextUrl;
  
  // If it's a protected owner route, require auth
  if (isProtectedOwnerRoute(req)) {
    await auth.protect();
    return;
  }
  
  // If it's a public route, allow through
  if (isPublicRoute(req)) {
    return;
  }
  
  // For any other routes, require auth (default protected)
  await auth.protect();
});

export const config = {
  matcher: [
    // Run middleware on all routes except static files and Next.js internals
    "/((?!.+\\.[\\w]+$|_next).*)",
    "/",
    "/(api|trpc)(.*)",
  ],
};
