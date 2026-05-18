/**
 * RTK Query slice for the City of Melbourne open-data portal
 * (Opendatasoft Explore v2.1). Keyless. Used for live bay availability
 * inside the Melbourne LGA only.
 *
 * Datasets:
 *   on-street-parking-bays             - bay polygons (joins via marker_id)
 *   on-street-parking-bay-sensors      - live occupancy
 *   on-street-car-park-bay-information - restriction text (joins via bay_id)
 */
import config from '@utils/config';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export type ParkingBayRecord = {
  bay_id?: string;
  marker_id?: string;
  meter_id?: string;
  rd_seg_id?: string;
  geo_shape?: unknown;
  geo_point_2d?: { lat: number; lon: number };
  // Datasets evolve; keep the rest loose.
  [key: string]: unknown;
};

export type ParkingBaySensorRecord = {
  bay_id?: string;
  marker_id?: string;
  status_description?: 'Present' | 'Unoccupied' | string;
  status_timestamp?: string;
  location?: { lat: number; lon: number };
  [key: string]: unknown;
};

export type RecordsResponse<T> = {
  total_count: number;
  results: T[];
};

type NearbyBaysArgs = {
  lat: number;
  lng: number;
  /** metres */
  radius?: number;
  /** max records to fetch */
  limit?: number;
};

export const melbourneOpenDataApi = createApi({
  reducerPath: 'melbourneOpenDataApi',
  baseQuery: fetchBaseQuery({ baseUrl: config.melbourneApiBase }),
  endpoints: (builder) => ({
    nearbyParkingBays: builder.query<RecordsResponse<ParkingBayRecord>, NearbyBaysArgs>({
      query: ({ lat, lng, radius = 200, limit = 100 }) => ({
        url: '/on-street-parking-bays/records',
        params: {
          where: `distance(geo_point_2d, geom'POINT(${lng} ${lat})', ${radius}m)`,
          limit,
        },
      }),
    }),
    nearbyBaySensors: builder.query<RecordsResponse<ParkingBaySensorRecord>, NearbyBaysArgs>({
      query: ({ lat, lng, radius = 200, limit = 100 }) => ({
        url: '/on-street-parking-bay-sensors/records',
        params: {
          where: `distance(location, geom'POINT(${lng} ${lat})', ${radius}m)`,
          limit,
        },
      }),
    }),
  }),
});

export const { useNearbyParkingBaysQuery, useNearbyBaySensorsQuery } = melbourneOpenDataApi;
