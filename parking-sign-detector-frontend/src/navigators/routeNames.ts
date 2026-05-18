/**
 * All route names live here as `ROUTE_*` constants. Adding a screen?
 * Add the constant here, extend the right ParamList in this folder,
 * register the `<Stack.Screen />` in the matching navigator.
 */

// Root stack
export const ROUTE_MAIN_TABS = 'MainTabs' as const;
export const ROUTE_DISCLAIMER_MODAL = 'DisclaimerModal' as const;
export const ROUTE_SIGN_DETAIL_MODAL = 'SignDetailModal' as const;
export const ROUTE_TERMS_MODAL = 'TermsModal' as const;
export const ROUTE_PRIVACY_MODAL = 'PrivacyModal' as const;

// Tab routes
export const ROUTE_HOME_TAB = 'HomeTab' as const;
export const ROUTE_EXPLAIN_TAB = 'ExplainTab' as const;
export const ROUTE_SETTINGS_TAB = 'SettingsTab' as const;

// Home tab stack
export const ROUTE_PARKING_SEARCH = 'ParkingSearch' as const;
export const ROUTE_PARKING_RESULTS = 'ParkingResults' as const;

// Explain tab
export const ROUTE_SIGN_EXPLAINER = 'SignExplainer' as const;

// Settings tab
export const ROUTE_SETTINGS = 'Settings' as const;
