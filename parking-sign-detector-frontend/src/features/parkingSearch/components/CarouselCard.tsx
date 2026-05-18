/**
 * One card in the bottom-of-screen carousel. Dispatches to a per-kind
 * renderer so adding a new ParkingOption variant (e.g. council_bay) is
 * a localised change — append a `case` here, add a new private
 * renderer below.
 */
import AppText from '@components/AppText';
import { firstImageOf, ParkingOption } from '@store/types/parkingOption';
import theme from '@utils/theme';
import React, { FC, memo } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';

type Props = {
  option: ParkingOption;
  width: number;
  isSelected: boolean;
  onPress: () => void;
};

const CarouselCard: FC<Props> = ({ option, width, isSelected, onPress }) => {
  const accessibilityLabel = `${option.kind === 'address_preview'
    ? 'Searched address'
    : (option as { title?: string }).title ?? 'Parking option'}, ${
    option.distance_m === 0 ? 'at this location' : `${Math.round(option.distance_m)} metres away`
  }`;

  return (
    <Pressable
      onPress={onPress}
      style={[styles.card, { width }, isSelected && styles.cardSelected]}
      accessibilityRole='button'
      accessibilityLabel={accessibilityLabel}>
      <CardThumbnail option={option} />
      <View style={styles.body}>
        <CardBody option={option} />
      </View>
    </Pressable>
  );
};

// ---------------------------------------------------------------------------
// Per-kind renderers (private — only used here)
// ---------------------------------------------------------------------------

const CardThumbnail: FC<{ option: ParkingOption }> = ({ option }) => {
  const img = firstImageOf(option);
  return (
    <View style={styles.imageWrap}>
      {img ? (
        <Image source={{ uri: img.url }} style={styles.image} resizeMode='cover' />
      ) : (
        <View style={styles.imagePlaceholder} />
      )}
      <Badge option={option} />
    </View>
  );
};

const Badge: FC<{ option: ParkingOption }> = ({ option }) => {
  switch (option.kind) {
    case 'address_preview':
      return (
        <View style={[styles.badge, styles.badgeAddress]}>
          <AppText size={10} font={theme.fonts.poppinsMedium} color={theme.colors.white}>
            ADDRESS
          </AppText>
        </View>
      );
    case 'council_bay':
      return (
        <View style={[styles.badge, styles.badgeBay]}>
          <AppText size={10} font={theme.fonts.poppinsMedium} color={theme.colors.white}>
            BAY
          </AppText>
        </View>
      );
    case 'off_street_carpark':
      return (
        <View style={[styles.badge, styles.badgeCarpark]}>
          <AppText size={10} font={theme.fonts.poppinsMedium} color={theme.colors.white}>
            CARPARK
          </AppText>
        </View>
      );
    case 'street_parking':
      return null; // no badge — the title is enough
    default: {
      const _exhaustive: never = option;
      return _exhaustive;
    }
  }
};

const CardBody: FC<{ option: ParkingOption }> = ({ option }) => {
  switch (option.kind) {
    case 'address_preview':
      return (
        <>
          <AppText
            size={13}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.textDark}
            numberOfLines={1}>
            Searched address
          </AppText>
          <AppText size={11} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
            {option.images.length} Street View angles
          </AppText>
          {option.pano_date ? (
            <AppText size={10} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
              photo {option.pano_date}
            </AppText>
          ) : null}
        </>
      );

    case 'street_parking':
      return (
        <>
          <AppText
            size={13}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.textDark}
            numberOfLines={1}>
            {option.title}
          </AppText>
          <AppText size={11} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
            {option.subtitle}
          </AppText>
          {option.evidence.pano_date ? (
            <AppText size={10} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
              photo {option.evidence.pano_date}
            </AppText>
          ) : null}
        </>
      );

    case 'council_bay':
      return (
        <>
          <AppText
            size={13}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.textDark}
            numberOfLines={1}>
            {option.title}
          </AppText>
          <AppText size={11} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
            {option.subtitle}
          </AppText>
          <AppText
            size={10}
            color={
              option.live_status === 'free'
                ? theme.colors.success
                : option.live_status === 'occupied'
                  ? theme.colors.danger
                  : theme.colors.textGrey
            }
            numberOfLines={1}
            style={styles.sub}>
            {option.live_status === 'free'
              ? 'Currently free'
              : option.live_status === 'occupied'
                ? 'Occupied right now'
                : 'Live status unknown'}
          </AppText>
        </>
      );

    case 'off_street_carpark':
      return (
        <>
          <AppText
            size={13}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.textDark}
            numberOfLines={1}>
            {option.title}
          </AppText>
          <AppText size={11} color={theme.colors.textGrey} numberOfLines={1} style={styles.sub}>
            {option.subtitle}
          </AppText>
        </>
      );

    default: {
      const _exhaustive: never = option;
      return _exhaustive;
    }
  }
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  badge: {
    borderRadius: theme.radii.sm,
    left: theme.spacing.sm,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    position: 'absolute',
    top: theme.spacing.sm,
  },
  badgeAddress: { backgroundColor: theme.colors.brandGreen },
  badgeBay: { backgroundColor: theme.colors.success },
  badgeCarpark: { backgroundColor: theme.colors.brandAmber },
  body: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  card: {
    backgroundColor: theme.colors.white,
    borderColor: 'transparent',
    borderRadius: theme.radii.lg,
    borderWidth: 2,
    marginRight: theme.spacing.sm,
    overflow: 'hidden',
    shadowColor: theme.colors.blackDark,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
  },
  cardSelected: {
    borderColor: theme.colors.brandGreen,
  },
  image: { height: '100%', width: '100%' },
  imagePlaceholder: {
    backgroundColor: theme.colors.greyBgAlt,
    height: '100%',
    width: '100%',
  },
  imageWrap: {
    backgroundColor: theme.colors.greyBgAlt,
    height: 110,
    width: '100%',
  },
  sub: { marginTop: 2 },
});

export default memo(CarouselCard);
