import AppText from '@components/AppText';
import theme from '@utils/theme';
import React, { FC } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleProp,
  StyleSheet,
  View,
  ViewStyle,
} from 'react-native';

type BlockButtonProps = {
  text: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  buttonColor?: string;
  textColor?: string;
  font?: string;
  fontSize?: number;
  containerStyle?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * Full-width primary button. Mirrors the BlockButton from docs/ai/.
 * Loading state shows a spinner instead of text.
 */
const BlockButton: FC<BlockButtonProps> = ({
  text,
  onPress,
  disabled = false,
  loading = false,
  buttonColor = theme.colors.blackDark,
  textColor = theme.colors.textInverse,
  font = theme.fonts.poppinsMedium,
  fontSize = 16,
  containerStyle,
  testID,
}) => {
  const effectivelyDisabled = disabled || loading;

  return (
    <Pressable
      testID={testID}
      onPress={effectivelyDisabled ? undefined : onPress}
      accessibilityRole='button'
      accessibilityState={{ disabled: effectivelyDisabled, busy: loading }}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: buttonColor, opacity: effectivelyDisabled ? 0.5 : pressed ? 0.85 : 1 },
        containerStyle,
      ]}>
      <View style={styles.inner}>
        {loading ? (
          <ActivityIndicator size='small' color={textColor} />
        ) : (
          <AppText size={fontSize} font={font} color={textColor}>
            {text}
          </AppText>
        )}
      </View>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    borderRadius: theme.radii.lg,
    height: 52,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
  },
  inner: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
});

export default BlockButton;
