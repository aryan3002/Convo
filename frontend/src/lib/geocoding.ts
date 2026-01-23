/**
 * Geocoding Service for Shop Location Management
 * 
 * This module provides geocoding functionality for the shop onboarding process.
 * It supports multiple geocoding providers with automatic fallback.
 * 
 * Primary Provider: Google Maps Geocoding API (if NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is set)
 * Fallback Provider: OpenStreetMap Nominatim (free, rate-limited)
 * 
 * @module geocoding
 */

// ────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────

export interface GeocodingResult {
  lat: number;
  lon: number;
  formattedAddress?: string;
  confidence?: number;
}

export interface GeocodingError {
  type: 'INVALID_ADDRESS' | 'NO_RESULTS' | 'API_ERROR' | 'RATE_LIMITED' | 'NETWORK_ERROR';
  message: string;
}

// ────────────────────────────────────────────────────────────────
// Configuration
// ────────────────────────────────────────────────────────────────

const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
const NOMINATIM_USER_AGENT = 'ConvoAI-Booking/1.0';
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1000;

// ────────────────────────────────────────────────────────────────
// Helper: Delay for retry logic
// ────────────────────────────────────────────────────────────────

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// ────────────────────────────────────────────────────────────────
// Google Maps Geocoding
// ────────────────────────────────────────────────────────────────

interface GoogleGeocodeResponse {
  status: string;
  results: Array<{
    formatted_address: string;
    geometry: {
      location: {
        lat: number;
        lng: number;
      };
      location_type: string;
    };
  }>;
  error_message?: string;
}

async function geocodeWithGoogle(address: string): Promise<GeocodingResult | null> {
  if (!GOOGLE_MAPS_API_KEY) {
    return null;
  }

  const url = new URL('https://maps.googleapis.com/maps/api/geocode/json');
  url.searchParams.set('address', address);
  url.searchParams.set('key', GOOGLE_MAPS_API_KEY);

  try {
    const response = await fetch(url.toString());
    
    if (!response.ok) {
      console.error('[Geocoding] Google API HTTP error:', response.status);
      return null;
    }

    const data: GoogleGeocodeResponse = await response.json();

    if (data.status === 'OK' && data.results.length > 0) {
      const result = data.results[0];
      
      // Calculate confidence based on location type
      let confidence = 0.8;
      if (result.geometry.location_type === 'ROOFTOP') confidence = 1.0;
      else if (result.geometry.location_type === 'RANGE_INTERPOLATED') confidence = 0.9;
      else if (result.geometry.location_type === 'GEOMETRIC_CENTER') confidence = 0.7;
      else if (result.geometry.location_type === 'APPROXIMATE') confidence = 0.5;

      return {
        lat: result.geometry.location.lat,
        lon: result.geometry.location.lng,
        formattedAddress: result.formatted_address,
        confidence,
      };
    }

    if (data.status === 'ZERO_RESULTS') {
      console.warn('[Geocoding] Google API: No results for address');
      return null;
    }

    console.error('[Geocoding] Google API error:', data.status, data.error_message);
    return null;
  } catch (error) {
    console.error('[Geocoding] Google API exception:', error);
    return null;
  }
}

// ────────────────────────────────────────────────────────────────
// OpenStreetMap Nominatim Geocoding (Fallback)
// ────────────────────────────────────────────────────────────────

interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
  importance: number;
}

async function geocodeWithNominatim(address: string): Promise<GeocodingResult | null> {
  const url = new URL('https://nominatim.openstreetmap.org/search');
  url.searchParams.set('q', address);
  url.searchParams.set('format', 'json');
  url.searchParams.set('limit', '1');
  url.searchParams.set('countrycodes', 'us');

  try {
    const response = await fetch(url.toString(), {
      headers: {
        'User-Agent': NOMINATIM_USER_AGENT,
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      console.error('[Geocoding] Nominatim HTTP error:', response.status);
      return null;
    }

    const data: NominatimResult[] = await response.json();

    if (data.length > 0) {
      const result = data[0];
      return {
        lat: parseFloat(result.lat),
        lon: parseFloat(result.lon),
        formattedAddress: result.display_name,
        confidence: Math.min(result.importance, 1.0),
      };
    }

    console.warn('[Geocoding] Nominatim: No results for address');
    return null;
  } catch (error) {
    console.error('[Geocoding] Nominatim exception:', error);
    return null;
  }
}

// ────────────────────────────────────────────────────────────────
// Main Geocoding Function
// ────────────────────────────────────────────────────────────────

/**
 * Geocode an address string to latitude/longitude coordinates.
 * 
 * This function attempts to use Google Maps Geocoding API first (if configured),
 * then falls back to OpenStreetMap Nominatim.
 * 
 * @param address - The address string to geocode
 * @returns Promise resolving to coordinates or null if geocoding fails
 * 
 * @example
 * ```typescript
 * const result = await geocodeAddress("123 Main St, Tempe, AZ");
 * if (result) {
 *   console.log(`Location: ${result.lat}, ${result.lon}`);
 * }
 * ```
 */
export async function geocodeAddress(
  address: string
): Promise<GeocodingResult | null> {
  // Validate input
  const trimmedAddress = address.trim();
  if (!trimmedAddress || trimmedAddress.length < 5) {
    console.warn('[Geocoding] Address too short or empty');
    return null;
  }

  // Try with retries
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      console.log(`[Geocoding] Retry attempt ${attempt}`);
      await delay(RETRY_DELAY_MS * attempt);
    }

    // Try Google first if API key is available
    if (GOOGLE_MAPS_API_KEY) {
      const googleResult = await geocodeWithGoogle(trimmedAddress);
      if (googleResult) {
        console.log('[Geocoding] Success via Google Maps');
        return googleResult;
      }
    }

    // Fallback to Nominatim
    const nominatimResult = await geocodeWithNominatim(trimmedAddress);
    if (nominatimResult) {
      console.log('[Geocoding] Success via Nominatim');
      return nominatimResult;
    }
  }

  console.error('[Geocoding] All providers failed after retries');
  return null;
}

// ────────────────────────────────────────────────────────────────
// Reverse Geocoding
// ────────────────────────────────────────────────────────────────

/**
 * Convert coordinates back to an address string.
 * Useful for location sharing features.
 * 
 * @param lat - Latitude
 * @param lon - Longitude
 * @returns Promise resolving to address string or null
 */
export async function reverseGeocode(
  lat: number,
  lon: number
): Promise<string | null> {
  // Validate coordinates
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    console.warn('[Geocoding] Invalid coordinates for reverse geocoding');
    return null;
  }

  // Try Google first
  if (GOOGLE_MAPS_API_KEY) {
    const url = new URL('https://maps.googleapis.com/maps/api/geocode/json');
    url.searchParams.set('latlng', `${lat},${lon}`);
    url.searchParams.set('key', GOOGLE_MAPS_API_KEY);

    try {
      const response = await fetch(url.toString());
      const data: GoogleGeocodeResponse = await response.json();

      if (data.status === 'OK' && data.results.length > 0) {
        return data.results[0].formatted_address;
      }
    } catch (error) {
      console.error('[Geocoding] Google reverse geocode error:', error);
    }
  }

  // Fallback to Nominatim
  try {
    const url = new URL('https://nominatim.openstreetmap.org/reverse');
    url.searchParams.set('lat', lat.toString());
    url.searchParams.set('lon', lon.toString());
    url.searchParams.set('format', 'json');

    const response = await fetch(url.toString(), {
      headers: {
        'User-Agent': NOMINATIM_USER_AGENT,
        'Accept': 'application/json',
      },
    });

    if (response.ok) {
      const data = await response.json();
      return data.display_name || null;
    }
  } catch (error) {
    console.error('[Geocoding] Nominatim reverse geocode error:', error);
  }

  return null;
}

// ────────────────────────────────────────────────────────────────
// Coordinate Validation
// ────────────────────────────────────────────────────────────────

/**
 * Validate latitude/longitude coordinates.
 * 
 * @param lat - Latitude to validate
 * @param lon - Longitude to validate
 * @returns True if coordinates are valid
 */
export function isValidCoordinates(lat: number, lon: number): boolean {
  return (
    typeof lat === 'number' &&
    typeof lon === 'number' &&
    !isNaN(lat) &&
    !isNaN(lon) &&
    lat >= -90 &&
    lat <= 90 &&
    lon >= -180 &&
    lon <= 180
  );
}

// ────────────────────────────────────────────────────────────────
// Distance Calculation (Haversine)
// ────────────────────────────────────────────────────────────────

const EARTH_RADIUS_MILES = 3959.0;

/**
 * Calculate the distance between two coordinates using the Haversine formula.
 * 
 * @param lat1 - Latitude of first point
 * @param lon1 - Longitude of first point
 * @param lat2 - Latitude of second point
 * @param lon2 - Longitude of second point
 * @returns Distance in miles
 */
export function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;

  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);

  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return EARTH_RADIUS_MILES * c;
}
