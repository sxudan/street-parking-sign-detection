/**
 * Runtime config. Pulls values from Expo's `extra` config + EXPO_PUBLIC_*
 * env vars. Fail loudly in dev if a required value is missing.
 */
import Constants from 'expo-constants';

type AppConfig = {
  apiBaseUrl: string;
  melbourneApiBase: string;
};

function readApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_BASE_URL;
  const fromExtra = (Constants.expoConfig?.extra as Record<string, unknown> | undefined)?.API_BASE_URL;
  const value = fromEnv ?? (typeof fromExtra === 'string' ? fromExtra : undefined);
  if (!value) {
    // eslint-disable-next-line no-console
    console.warn('[config] EXPO_PUBLIC_API_BASE_URL not set; falling back to http://localhost:8000');
    return 'http://localhost:8000';
  }
  return value.replace(/\/+$/, '');
}

const config: AppConfig = {
  apiBaseUrl: readApiBaseUrl(),
  melbourneApiBase: 'https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets',
};

export default config;
