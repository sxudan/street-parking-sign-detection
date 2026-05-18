/**
 * Compact horizontal strip of the 8 Street View angles around the
 * searched address. Sits above the parking-signs carousel on the
 * results screen so the user always has a "what does this place look
 * like" reference.
 *
 * Tapping any thumbnail opens the full address-preview detail sheet
 * (same modal the carousel cards open into).
 */
import AppText from '@components/AppText';
import { AddressPreviewOption } from '@store/types/parkingOption';
import theme from '@utils/theme';
import React, { FC, memo } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, View } from 'react-native';

const THUMB_SIZE = 64;

type Props = {
  option: AddressPreviewOption;
  onPress: () => void;
};

const AddressPreviewRow: FC<Props> = ({ option, onPress }) => {
  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <AppText size={11} font={theme.fonts.poppinsSemiBold} color={theme.colors.textGrey}>
          STREET VIEW PREVIEW
        </AppText>
        <AppText size={11} color={theme.colors.textGrey}>
          {option.images.length} angles{option.pano_date ? ` · ${option.pano_date}` : ''}
        </AppText>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}>
        {option.images.map((img, idx) => (
          <Pressable
            key={`${img.heading}-${img.pitch}-${idx}`}
            onPress={onPress}
            style={({ pressed }) => [styles.thumbWrap, pressed && styles.thumbWrapPressed]}
            accessibilityRole='button'
            accessibilityLabel={`Street View angle ${Math.round(img.heading)} degrees`}>
            <Image
              source={{ uri: img.url }}
              style={styles.thumb}
              resizeMode='cover'
            />
            <AppText size={9} color={theme.colors.textGrey} style={styles.thumbLabel}>
              {Math.round(img.heading)}°
            </AppText>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingTop: theme.spacing.sm,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  scrollContent: {
    paddingRight: theme.spacing.horizontalDefault,
  },
  thumb: {
    backgroundColor: theme.colors.greyBgAlt,
    borderRadius: theme.radii.md,
    height: THUMB_SIZE,
    width: THUMB_SIZE,
  },
  thumbLabel: {
    marginTop: 2,
    textAlign: 'center',
  },
  thumbWrap: {
    marginRight: theme.spacing.sm,
  },
  thumbWrapPressed: { opacity: 0.7 },
});

export default memo(AddressPreviewRow);
