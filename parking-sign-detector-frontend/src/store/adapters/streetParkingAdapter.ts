/**
 * Adapter: ParkingSignsResponse (raw FastAPI shape) -> ParkingOption[].
 *
 * This is the only file that depends on the parking-detector API's
 * response shape. Everything else in the app works against
 * `ParkingOption`. When v1.1 brings in Melbourne open-data bays, add a
 * sibling adapter here; the screens won't change.
 */
import { ParkingLocation, ParkingSignsResponse } from '@store/api/parkingSignsApi';
import { ParkingOption } from '@store/types/parkingOption';

const STRONG_KEYWORD_TITLES: Array<[string, string]> = [
  // Order matters — first match wins.
  ['NO STOPPING', 'No stopping zone'],
  ['NO STANDING', 'No standing zone'],
  ['NO PARKING', 'No parking zone'],
  ['CLEARWAY', 'Clearway'],
  ['LOADING ZONE', 'Loading zone'],
  ['LOADING', 'Loading zone'],
  ['BUS ZONE', 'Bus zone'],
  ['TAXI ZONE', 'Taxi zone'],
  ['PERMIT ZONE', 'Permit zone'],
  ['PERMIT', 'Permit zone'],
  ['MAIL ZONE', 'Mail zone'],
  ['WORKS ZONE', 'Works zone'],
  ['DROP OFF', 'Drop-off zone'],
  ['DISABLED', 'Disabled parking'],
  ['TICKET', 'Ticket parking'],
  ['METER', 'Metered parking'],
];

function deriveTitle(keywords: string[]): string {
  // Strong / unambiguous keyword wins
  for (const [kw, title] of STRONG_KEYWORD_TITLES) {
    if (keywords.includes(kw)) return title;
  }
  // P-code (1P, 2P, 4P, 1/4P, 1/2P, etc.)
  const pCode = keywords.find((k) => /^(\d{1,2}|1\/2|1\/4)P$/.test(k));
  if (pCode) return `${pCode} parking`;
  return 'Parking sign';
}

function deriveSubtitle(loc: ParkingLocation): string {
  return `On-street · ${Math.round(loc.distance_m)} m`;
}

/**
 * Build the canonical ParkingOption[] from a ParkingSignsResponse.
 * Always-included `address_pano_preview` becomes the first option;
 * each entry in `parking_locations` becomes a `street_parking` option.
 */
export function streetParkingFromSigns(resp: ParkingSignsResponse): ParkingOption[] {
  const out: ParkingOption[] = [];

  if (resp.address_pano_preview) {
    const ap = resp.address_pano_preview;
    out.push({
      kind: 'address_preview',
      id: 'address',
      coordinate: ap.coordinate,
      distance_m: ap.distance_m,
      pano_id: ap.pano_id,
      pano_date: ap.pano_date,
      images: ap.images,
    });
  }

  for (const loc of resp.parking_locations) {
    const keywords = Array.from(
      new Set(loc.images.flatMap((i) => i.keywords_found)),
    );
    out.push({
      kind: 'street_parking',
      id: `sign-${loc.pano_id}`,
      coordinate: loc.coordinate,
      distance_m: loc.distance_m,
      title: deriveTitle(keywords),
      subtitle: deriveSubtitle(loc),
      active_now: null,
      interpretation: null,
      evidence: {
        source: 'street_view_ocr',
        pano_id: loc.pano_id,
        pano_date: loc.pano_date,
        images: loc.images,
        keywords,
      },
    });
  }

  return out;
}
