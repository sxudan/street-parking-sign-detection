/**
 * ParkingOption — the canonical, source-agnostic shape every screen in
 * the app works against. A "parking option" is something the user can
 * act on (or be told to avoid) at the searched location.
 *
 * The discriminated union below covers every kind we expect to support:
 *   - 'address_preview'      always-included Street View context
 *   - 'street_parking'       on-street signs detected via Street View OCR (v1)
 *   - 'council_bay'          marked parking bays from City of Melbourne /
 *                            City of Sydney open data, with live occupancy
 *                            (v1.1)
 *   - 'off_street_carpark'   paid carparks/garages from Google Places etc.
 *                            (v1.2+)
 *
 * Backend responses get translated into ParkingOption[] by adapters in
 * src/store/adapters/. The screen layer never sees raw API shapes.
 */
import { LatLng, SignImage } from '@store/api/parkingSignsApi';

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type Coord = LatLng;

/**
 * Structured restriction info, populated when a sign parser exists
 * (e.g. a vision LLM). Until then it stays null and the UI falls back
 * to the title/subtitle strings on the option.
 */
export type ParkingInterpretation = {
  code: string;                      // "2P", "NO STOPPING", "LOADING ZONE"
  time_limit_hours: number | null;   // null for non-time-limited (No Stopping etc.)
  operating_hours: Array<{
    days: string;                    // "MON-FRI", "SAT", "PUBLIC HOLIDAYS"
    start: string;                   // "08:30"
    end: string;                     // "18:30"
  }>;
  plain_english: string;             // "2-hour parking weekdays 8:30 AM - 6:30 PM"
};

// ---------------------------------------------------------------------------
// Address preview
// ---------------------------------------------------------------------------

export type AddressPreviewOption = {
  kind: 'address_preview';
  id: 'address';
  coordinate: Coord;
  distance_m: number;
  pano_id: string;
  pano_date: string | null;
  images: SignImage[];               // 8 sweep angles
};

// ---------------------------------------------------------------------------
// Street parking sign (Street View OCR — v1)
// ---------------------------------------------------------------------------

export type StreetParkingOption = {
  kind: 'street_parking';
  id: string;                        // stable id, e.g. `sign-${pano_id}`
  coordinate: Coord;
  distance_m: number;
  title: string;                     // "2P parking", "No stopping zone"
  subtitle: string;                  // "On-street · 16 m east"
  /** Whether the restriction is currently active. Null until rule
   *  parsing exists. */
  active_now: boolean | null;
  /** Structured restriction. Null in v1; populated in v1.5 with vision LLM. */
  interpretation: ParkingInterpretation | null;
  evidence: {
    source: 'street_view_ocr';
    pano_id: string;
    pano_date: string | null;
    images: SignImage[];             // 1+ flagged angles of the same sign
    keywords: string[];               // de-duped union of keywords across images
  };
};

// ---------------------------------------------------------------------------
// Council parking bay (Melbourne / Sydney open data — v1.1)
// ---------------------------------------------------------------------------

export type CouncilBayOption = {
  kind: 'council_bay';
  id: string;
  coordinate: Coord;
  distance_m: number;
  title: string;
  subtitle: string;
  active_now: boolean | null;
  live_status: 'free' | 'occupied' | 'unknown';
  interpretation: ParkingInterpretation | null;
  evidence: {
    source: 'city_of_melbourne' | 'city_of_sydney';
    bay_id: string;
    sensor_updated_at: string | null;
  };
};

// ---------------------------------------------------------------------------
// Off-street paid carpark (Google Places / Parkopedia — v1.2+)
// ---------------------------------------------------------------------------

export type OffStreetCarparkOption = {
  kind: 'off_street_carpark';
  id: string;
  coordinate: Coord;
  distance_m: number;
  title: string;                     // "Wilson Parking", "Secure Parking"
  subtitle: string;                  // "$5/hr · 12 spaces"
  active_now: true;                  // carparks are always "available" as a category
  hourly_rate: { currency: string; cents_per_hour: number } | null;
  spaces_available: number | null;
  evidence: {
    source: 'google_places' | 'parkopedia';
    place_id: string;
  };
};

// ---------------------------------------------------------------------------
// Discriminated union
// ---------------------------------------------------------------------------

export type ParkingOption =
  | AddressPreviewOption
  | StreetParkingOption
  | CouncilBayOption
  | OffStreetCarparkOption;

/**
 * Type-narrowing helpers — these are where the discriminator is paying
 * off. Use them in switch statements:
 *
 *   switch (option.kind) {
 *     case 'street_parking': return <StreetParkingCard option={option} />;
 *     ...
 *   }
 */
export type ParkingOptionKind = ParkingOption['kind'];

export function isAddressPreview(o: ParkingOption): o is AddressPreviewOption {
  return o.kind === 'address_preview';
}

export function isStreetParking(o: ParkingOption): o is StreetParkingOption {
  return o.kind === 'street_parking';
}

export function isCouncilBay(o: ParkingOption): o is CouncilBayOption {
  return o.kind === 'council_bay';
}

export function isOffStreetCarpark(o: ParkingOption): o is OffStreetCarparkOption {
  return o.kind === 'off_street_carpark';
}

/** Convenience: extract the first image from any option that carries
 * imagery. Returns null for kinds that don't (carparks etc.). */
export function firstImageOf(option: ParkingOption): SignImage | null {
  if (option.kind === 'address_preview') return option.images[0] ?? null;
  if (option.kind === 'street_parking') return option.evidence.images[0] ?? null;
  return null;
}

/** Convenience: ALL imagery for an option, in the order to display. */
export function imagesOf(option: ParkingOption): SignImage[] {
  if (option.kind === 'address_preview') return option.images;
  if (option.kind === 'street_parking') return option.evidence.images;
  return [];
}
