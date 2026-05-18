import theme from '@utils/theme';
import React, { FC, ReactNode } from 'react';
import { StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { Edges, SafeAreaView } from 'react-native-safe-area-context';

type ScreenContainerProps = {
  children: ReactNode;
  edges?: Edges;
  backgroundColor?: string;
  style?: StyleProp<ViewStyle>;
};

/**
 * Standard screen shell — `SafeAreaView` with theme background.
 * Pass `edges={[]}` for screens nested inside a tab navigator (the
 * tab bar handles its own safe area).
 */
const ScreenContainer: FC<ScreenContainerProps> = ({
  children,
  edges,
  backgroundColor = theme.colors.greyBg,
  style,
}) => {
  return (
    <SafeAreaView edges={edges} style={[styles.root, { backgroundColor }, style]}>
      <View style={styles.fill}>{children}</View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  fill: { flex: 1 },
  root: { flex: 1 },
});

export default ScreenContainer;
