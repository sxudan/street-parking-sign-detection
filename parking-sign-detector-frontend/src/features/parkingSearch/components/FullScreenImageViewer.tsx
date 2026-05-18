/**
 * Full-screen image lightbox.
 *
 * Opens over the detail sheet when the user taps a thumbnail so they
 * can actually read the parking sign. iOS gets free pinch-to-zoom via
 * the ScrollView's built-in zoom support; Android falls back to a
 * statically-fit image (good enough for v1 — adding cross-platform
 * pinch-zoom would mean wiring up gesture-handler/reanimated which we
 * keep out of v1's scope).
 *
 * Toggle button in the top bar swaps between the OCR-annotated and the
 * raw image: handy when the green keyword boxes obscure something on
 * the sign and the user wants the original frame.
 */
import AppText from '@components/AppText';
import { useStatusBar } from '@hooks/useStatusBar';
import theme from '@utils/theme';
import { Eye, EyeOff, X } from 'lucide-react-native';
import React, { FC, useEffect, useState } from 'react';
import {
  Dimensions,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

type Props = {
  visible: boolean;
  imageUrl: string | null;
  rawImageUrl?: string | null;
  caption?: string;
  onClose: () => void;
};

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

const FullScreenImageViewer: FC<Props> = ({
  visible,
  imageUrl,
  rawImageUrl,
  caption,
  onClose,
}) => {
  useStatusBar('light-content');
  // Reset to annotated view every time we open a fresh image.
  const [showRaw, setShowRaw] = useState(false);
  useEffect(() => {
    if (visible) setShowRaw(false);
  }, [visible, imageUrl]);

  if (!imageUrl) return null;

  const canToggle = Boolean(rawImageUrl) && rawImageUrl !== imageUrl;
  const displayUrl = showRaw && rawImageUrl ? rawImageUrl : imageUrl;

  return (
    <Modal
      visible={visible}
      animationType='fade'
      onRequestClose={onClose}
      statusBarTranslucent
      presentationStyle='overFullScreen'
      transparent>
      <StatusBar barStyle='light-content' backgroundColor={theme.colors.blackDark} />
      {/* iOS RN Modals present in their own UIWindow and don't inherit
          the app-root SafeAreaProvider, so the SafeAreaView inside would
          resolve to zero insets — that's why the X/toggle buttons were
          drawing under the notch. Wrap the contents in their own
          provider so the SafeAreaView reads real insets. */}
      <SafeAreaProvider style={styles.backdrop}>
        <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
          <View style={styles.topBar}>
            <Pressable
              onPress={onClose}
              hitSlop={12}
              accessibilityRole='button'
              accessibilityLabel='Close image'
              style={({ pressed }) => [styles.iconBtn, pressed && styles.iconBtnPressed]}>
              <X size={22} color={theme.colors.white} strokeWidth={2.5} />
            </Pressable>

            {canToggle ? (
              <Pressable
                onPress={() => setShowRaw((s) => !s)}
                hitSlop={12}
                accessibilityRole='button'
                accessibilityLabel={showRaw ? 'Show OCR boxes' : 'Hide OCR boxes'}
                style={({ pressed }) => [
                  styles.iconBtn,
                  styles.iconBtnLabel,
                  pressed && styles.iconBtnPressed,
                ]}>
                {showRaw ? (
                  <Eye size={18} color={theme.colors.white} strokeWidth={2.5} />
                ) : (
                  <EyeOff size={18} color={theme.colors.white} strokeWidth={2.5} />
                )}
                <AppText size={11} color={theme.colors.white} style={styles.iconBtnText}>
                  {showRaw ? 'show boxes' : 'hide boxes'}
                </AppText>
              </Pressable>
            ) : null}
          </View>

          <ScrollView
            // iOS: pinch-to-zoom is built into ScrollView. minimumZoomScale=1
            // means the image fills the viewport and the user can only zoom
            // in, not shrink past fit. centerContent keeps it centred while
            // zoomed.
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            maximumZoomScale={Platform.OS === 'ios' ? 4 : 1}
            minimumZoomScale={1}
            centerContent
            bouncesZoom
            showsHorizontalScrollIndicator={false}
            showsVerticalScrollIndicator={false}>
            <Image
              source={{ uri: displayUrl }}
              style={styles.image}
              resizeMode='contain'
              accessibilityLabel={caption ?? 'Street view image'}
            />
          </ScrollView>

          {caption ? (
            <View style={styles.captionWrap}>
              <AppText size={12} color={theme.colors.white} style={styles.caption}>
                {caption}
              </AppText>
              {Platform.OS === 'ios' ? (
                <AppText size={10} color={theme.colors.borderGrey} style={styles.hint}>
                  Pinch to zoom
                </AppText>
              ) : null}
            </View>
          ) : null}
        </SafeAreaView>
      </SafeAreaProvider>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    backgroundColor: theme.colors.blackDark,
    flex: 1,
  },
  caption: { textAlign: 'center' },
  captionWrap: {
    paddingBottom: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.sm,
  },
  hint: { marginTop: 2, textAlign: 'center' },
  iconBtn: {
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: theme.radii.pill,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  iconBtnLabel: {
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.md,
    width: 'auto',
  },
  iconBtnPressed: { opacity: 0.6 },
  iconBtnText: { marginLeft: theme.spacing.xs },
  image: {
    height: SCREEN_H * 0.75,
    width: SCREEN_W,
  },
  safe: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: {
    alignItems: 'center',
    flexGrow: 1,
    justifyContent: 'center',
  },
  topBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
});

export default FullScreenImageViewer;
