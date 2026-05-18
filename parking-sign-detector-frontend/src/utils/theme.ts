/**
 * Theme tokens. Always reference these — `theme.colors.*`, `theme.fonts.*`,
 * `theme.spacing.*` — instead of raw hex / numeric values in JSX. Enforced
 * by ESLint (`react-native/no-color-literals`, `no-inline-styles`).
 *
 * Mirrors the docs/ai/ rules (single source of truth for visual tokens).
 */

const colors = {
  // brand
  brandGreen: '#1F8C45',
  brandGreenSoft: '#E8F5EE',
  brandRed: '#D14343',
  brandAmber: '#E08A1E',

  // text
  textDark: '#1A1A1A',
  textGrey: '#6E6E72',
  textInverse: '#FFFFFF',
  blackDark: '#0E0E0E',

  // surfaces
  white: '#FFFFFF',
  greyBg: '#F5F5F7',
  greyBgAlt: '#EDEDF0',
  borderGrey: '#D4D4D8',
  divider: '#E5E5EA',

  // status colours
  success: '#1F8C45',
  warning: '#E08A1E',
  danger: '#D14343',

  // overlays
  scrimDark: 'rgba(0,0,0,0.55)',
} as const;

const fonts = {
  // Replace with bundled Poppins families when assets land.
  poppinsRegular: 'System',
  poppinsMedium: 'System',
  poppinsSemiBold: 'System',
  poppinsBold: 'System',
} as const;

const spacing = {
  // 4px grid
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,

  horizontalDefault: 16,
  verticalDefault: 16,
} as const;

const radii = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  pill: 999,
} as const;

const theme = {
  colors,
  fonts,
  spacing,
  radii,
} as const;

export type Theme = typeof theme;
export default theme;
