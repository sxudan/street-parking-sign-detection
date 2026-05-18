/**
 * Param lists for every navigator. Extend these when registering new
 * screens so `route.params` and `navigate()` are typed end-to-end.
 */
import {
  ROUTE_DISCLAIMER_MODAL,
  ROUTE_EXPLAIN_TAB,
  ROUTE_HOME_TAB,
  ROUTE_MAIN_TABS,
  ROUTE_PARKING_RESULTS,
  ROUTE_PARKING_SEARCH,
  ROUTE_PRIVACY_MODAL,
  ROUTE_SETTINGS,
  ROUTE_SETTINGS_TAB,
  ROUTE_SIGN_DETAIL_MODAL,
  ROUTE_SIGN_EXPLAINER,
  ROUTE_TERMS_MODAL,
} from './routeNames';

export type RootStackParamList = {
  [ROUTE_MAIN_TABS]: undefined;
  [ROUTE_DISCLAIMER_MODAL]: undefined;
  [ROUTE_SIGN_DETAIL_MODAL]: { panoId: string; heading: number };
  [ROUTE_TERMS_MODAL]: undefined;
  [ROUTE_PRIVACY_MODAL]: undefined;
};

export type MainTabParamList = {
  [ROUTE_HOME_TAB]: undefined;
  [ROUTE_EXPLAIN_TAB]: undefined;          // unused in v1; kept for future re-enable
  [ROUTE_SETTINGS_TAB]: undefined;
};

export type HomeStackParamList = {
  [ROUTE_PARKING_SEARCH]: undefined;
  [ROUTE_PARKING_RESULTS]: {
    /** Pass either `address` (preferred — backend will geocode) OR
     * both `lat` and `lng`. Both can be provided; `address` wins. */
    address?: string;
    lat?: number;
    lng?: number;
  };
};

export type ExplainStackParamList = {
  [ROUTE_SIGN_EXPLAINER]: undefined;
};

export type SettingsStackParamList = {
  [ROUTE_SETTINGS]: undefined;
};
