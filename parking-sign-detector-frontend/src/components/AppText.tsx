import theme from '@utils/theme';
import React, { FC, ReactNode } from 'react';
import { StyleProp, Text, TextStyle } from 'react-native';

type AppTextProps = {
  children: ReactNode;
  size?: number;
  font?: string;
  color?: string;
  lineHeight?: number;
  numberOfLines?: number;
  style?: StyleProp<TextStyle>;
  testID?: string;
};

/**
 * Project-wide text primitive. Use this instead of `Text` for product UI.
 * Forces theme tokens for size/font/colour so JSX never carries literals.
 */
const AppText: FC<AppTextProps> = ({
  children,
  size = 14,
  font = theme.fonts.poppinsRegular,
  color = theme.colors.textDark,
  lineHeight,
  numberOfLines,
  style,
  testID,
}) => {
  return (
    <Text
      testID={testID}
      numberOfLines={numberOfLines}
      style={[{ fontSize: size, fontFamily: font, color, lineHeight }, style]}>
      {children}
    </Text>
  );
};

export default AppText;
