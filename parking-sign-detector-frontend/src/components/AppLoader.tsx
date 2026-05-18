import theme from '@utils/theme';
import React, { FC } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

type AppLoaderProps = {
  size?: 'small' | 'large';
  color?: string;
  testID?: string;
};

/**
 * Centered spinner. Used as a loading gate before main content renders
 * (see docs/ai/examples/screen-patterns.tsx — pattern 6).
 */
const AppLoader: FC<AppLoaderProps> = ({ size = 'large', color = theme.colors.brandGreen, testID }) => (
  <View testID={testID} style={styles.container}>
    <ActivityIndicator size={size} color={color} />
  </View>
);

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
});

export default AppLoader;
