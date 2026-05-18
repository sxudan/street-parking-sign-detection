/**
 * RTK Query slice for our own FastAPI backend (parking-detector).
 * Mirrors the response shape returned by `POST /parking-signs`.
 */
import config from '@utils/config';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export type LatLng = {
  lat: number;
  lng: number;
};

export type SignImage = {
  heading: number;
  pitch: number;
  url: string;
  annotated_url: string | null;
  ocr_text: string;
  keywords_found: string[];
  keyword_score: number;
  flagged: boolean;
};

export type ParkingLocation = {
  coordinate: LatLng;
  pano_id: string;
  pano_date: string | null;
  distance_m: number;
  images: SignImage[];
};

export type ParkingSignsRequest = {
  address?: string;
  lat?: number;
  lng?: number;
  radius?: number;
  /** Override the backend's radius-derived pano cap. When omitted, the
   *  backend scales the cap with radius (ceil(radius/5), floor 10), so
   *  larger radii actually scan more panos instead of collapsing to the
   *  closest-10 set. */
  max_panos?: number;
  thumbnail_size?: string;
  same_street?: boolean;
  focus?: boolean;
  headings?: number;
  pitches?: string;
  fetch_workers?: number;
  ocr_workers?: number;
};

export type ParkingSignsResponse = {
  address_query: string | null;
  resolved_address: string;
  coordinate: LatLng;
  address_pano_preview: ParkingLocation | null;
  parking_locations: ParkingLocation[];
  stats: {
    panos_with_signs: number;
    images_captured: number;
    images_kept: number;
    images_deleted: number;
    address_preview_images: number;
    flagged_images: number;
  };
};

export type ParseSignResponse = {
  ocr_text: string;
  keywords_found: string[];
  keyword_score: number;
  flagged: boolean;
  word_boxes: Array<{ text: string; conf: number; x: number; y: number; w: number; h: number }>;
  interpretation?: {
    code: string;
    time_limit_hours?: number;
    operating_hours?: Array<{ days: string; start: string; end: string }>;
    plain_english: string;
  };
};

// ---------------------------------------------------------------------------
// Address autocomplete (Photon-backed proxy)
// ---------------------------------------------------------------------------

/** One typeahead suggestion.
 *
 * `lat`/`lng` are optional because Google's Places Autocomplete API
 * doesn't include coordinates — the client must call /places/details
 * after the user picks a suggestion to resolve them. Other providers
 * (e.g. Photon) DO bake them in; in that case the client can skip the
 * details round-trip. Treat the fields as a hint: when null, fall
 * back to /places/details. */
export type PlacePrediction = {
  place_id: string;
  description: string;
  main_text: string;
  secondary_text: string;
  lat?: number | null;
  lng?: number | null;
};

export type PlacesAutocompleteResponse = {
  predictions: PlacePrediction[];
};

export type PlaceDetailsResponse = {
  place_id: string;
  formatted_address: string;
  lat: number;
  lng: number;
};

// ---------------------------------------------------------------------------

export const parkingSignsApi = createApi({
  reducerPath: 'parkingSignsApi',
  baseQuery: fetchBaseQuery({ baseUrl: config.apiBaseUrl }),
  endpoints: (builder) => ({
    findParkingSigns: builder.query<ParkingSignsResponse, ParkingSignsRequest>({
      query: (body) => ({
        url: '/parking-signs',
        method: 'POST',
        body: {
          radius: 30,
          same_street: true,
          thumbnail_size: '1600x900',
          ...body,
        },
      }),
    }),
    parseSign: builder.mutation<ParseSignResponse, { uri: string; mimeType?: string; name?: string }>({
      query: ({ uri, mimeType = 'image/jpeg', name = 'sign.jpg' }) => {
        const form = new FormData();
        form.append('image', { uri, type: mimeType, name } as unknown as Blob);
        return {
          url: '/parse-sign',
          method: 'POST',
          body: form,
        };
      },
    }),
    autocompletePlaces: builder.query<
      PlacesAutocompleteResponse,
      { q: string; country?: string; limit?: number }
    >({
      query: ({ q, country = 'au', limit = 8 }) => ({
        url: '/places/autocomplete',
        params: { q, country, limit },
      }),
    }),
    getPlaceDetails: builder.query<PlaceDetailsResponse, { place_id: string }>({
      query: ({ place_id }) => ({
        url: '/places/details',
        params: { place_id },
      }),
    }),
  }),
});

export const {
  useFindParkingSignsQuery,
  useLazyFindParkingSignsQuery,
  useParseSignMutation,
  useAutocompletePlacesQuery,
  useLazyAutocompletePlacesQuery,
  useLazyGetPlaceDetailsQuery,
} = parkingSignsApi;
