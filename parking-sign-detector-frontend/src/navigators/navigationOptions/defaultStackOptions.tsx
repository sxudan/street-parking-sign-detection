import theme from '@utils/theme';
import { NativeStackNavigationOptions } from '@react-navigation/native-stack';

/**
 * Shared header chrome for native-stack navigators.
 *
 * - `headerBackTitle: ''` — drops the iOS "previous screen title" text
 *   next to the back chevron (e.g. "< Find parking" becomes just "<").
 * - `headerBackTitleVisible: false` — older iOS API equivalent; kept so
 *   we look chevron-only across the @react-navigation versions we ship.
 * - `headerShadowVisible: false` — flat headers, no hairline shadow.
 */
const defaultStackOptions: NativeStackNavigationOptions = {
  headerStyle: {
    backgroundColor: theme.colors.white,
  },
  headerTintColor: theme.colors.textDark,
  headerTitleStyle: {
    fontFamily: theme.fonts.poppinsSemiBold,
    fontSize: 17,
  },
  headerTitleAlign: 'center',
  headerBackTitle: '',
  headerShadowVisible: false,
  contentStyle: {
    backgroundColor: theme.colors.greyBg,
  },
};

export const defaultModalOptions: NativeStackNavigationOptions = {
  ...defaultStackOptions,
  presentation: 'modal',
};

export default defaultStackOptions;
