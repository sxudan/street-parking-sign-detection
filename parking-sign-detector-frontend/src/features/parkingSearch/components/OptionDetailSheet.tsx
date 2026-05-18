/**
 * Bottom-sheet modal for one ParkingOption. Dispatches to a per-kind
 * detail renderer so adding a new variant (council bay, off-street
 * carpark) means appending a `case` here.
 *
 * Built on RN's plain Modal. v1.1 can swap in @gorhom/bottom-sheet for
 * a draggable peek-up sheet if the UX warrants it.
 */
import AppText from '@components/AppText';
import FullScreenImageViewer from '@features/parkingSearch/components/FullScreenImageViewer';
import {
  AddressPreviewOption,
  CouncilBayOption,
  OffStreetCarparkOption,
  ParkingOption,
  StreetParkingOption,
} from '@store/types/parkingOption';
import { SignImage } from '@store/api/parkingSignsApi';
import theme from '@utils/theme';
import React, { FC, useCallback, useMemo, useState } from 'react';
import { Image, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';

type Props = {
  visible: boolean;
  option: ParkingOption | null;
  onClose: () => void;
};

type ZoomTarget = {
  url: string;
  rawUrl?: string;
  caption: string;
};

const OptionDetailSheet: FC<Props> = ({ visible, option, onClose }) => {
  const [zoomImage, setZoomImage] = useState<ZoomTarget | null>(null);

  const handleImagePress = useCallback((target: ZoomTarget) => {
    setZoomImage(target);
  }, []);

  const handleZoomClose = useCallback(() => setZoomImage(null), []);

  return (
    <Modal
      visible={visible}
      transparent
      animationType='slide'
      onRequestClose={onClose}
      statusBarTranslucent>
      <View style={styles.scrim}>
        {/* Tap-outside-to-close lives ONLY in the empty area above the
            sheet. Wrapping the sheet itself in a Pressable causes the
            inner horizontal ScrollView to lose its pan gesture. */}
        <Pressable style={styles.scrimTop} onPress={onClose} />

        <View style={styles.sheet}>
          <View style={styles.handle} />
          {option ? (
            <ScrollView
              contentContainerStyle={styles.body}
              showsVerticalScrollIndicator={false}>
              <DetailContent option={option} onImagePress={handleImagePress} />
              <Disclaimer />
            </ScrollView>
          ) : null}
        </View>
      </View>

      <FullScreenImageViewer
        visible={zoomImage !== null}
        imageUrl={zoomImage?.url ?? null}
        rawImageUrl={zoomImage?.rawUrl}
        caption={zoomImage?.caption}
        onClose={handleZoomClose}
      />
    </Modal>
  );
};

// ---------------------------------------------------------------------------
// Per-kind content
// ---------------------------------------------------------------------------

type ContentProps<T extends ParkingOption> = {
  option: T;
  onImagePress: (target: ZoomTarget) => void;
};

const DetailContent: FC<{
  option: ParkingOption;
  onImagePress: (target: ZoomTarget) => void;
}> = ({ option, onImagePress }) => {
  switch (option.kind) {
    case 'address_preview':
      return <AddressPreviewContent option={option} onImagePress={onImagePress} />;
    case 'street_parking':
      return <StreetParkingContent option={option} onImagePress={onImagePress} />;
    case 'council_bay':
      return <CouncilBayContent option={option} />;
    case 'off_street_carpark':
      return <CarparkContent option={option} />;
    default: {
      const _exhaustive: never = option;
      return _exhaustive;
    }
  }
};

const AddressPreviewContent: FC<ContentProps<AddressPreviewOption>> = ({
  option,
  onImagePress,
}) => (
  <>
    <AppText size={18} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
      Searched address — Street View preview
    </AppText>
    <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
      {option.pano_date ? `Imagery from ${option.pano_date}` : 'Imagery date unknown'}
      {' · '}
      pano {option.pano_id.slice(0, 14)}…
    </AppText>
    <ImageStrip images={option.images} onImagePress={onImagePress} />
  </>
);

const StreetParkingContent: FC<ContentProps<StreetParkingOption>> = ({
  option,
  onImagePress,
}) => (
  <>
    <AppText size={18} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
      {option.title}
    </AppText>
    <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
      {option.subtitle}
      {option.evidence.pano_date ? ` · imagery from ${option.evidence.pano_date}` : ''}
    </AppText>

    <ImageStrip images={option.evidence.images} onImagePress={onImagePress} />

    <View style={styles.metaBlock}>
      <AppText size={13} font={theme.fonts.poppinsMedium} color={theme.colors.textDark}>
        Detected keywords
      </AppText>
      <AppText size={12} color={theme.colors.textGrey} style={styles.metaLine}>
        {option.evidence.keywords.length ? option.evidence.keywords.join(' · ') : '(none)'}
      </AppText>
    </View>

    {option.interpretation ? (
      <View style={styles.metaBlock}>
        <AppText size={13} font={theme.fonts.poppinsMedium} color={theme.colors.textDark}>
          What this means
        </AppText>
        <AppText size={12} color={theme.colors.textDark} style={styles.metaLine}>
          {option.interpretation.plain_english}
        </AppText>
      </View>
    ) : null}
  </>
);

const CouncilBayContent: FC<{ option: CouncilBayOption }> = ({ option }) => (
  <>
    <AppText size={18} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
      {option.title}
    </AppText>
    <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
      {option.subtitle}
    </AppText>
    <View style={styles.metaBlock}>
      <AppText size={13} font={theme.fonts.poppinsMedium} color={theme.colors.textDark}>
        Live status
      </AppText>
      <AppText size={12} color={theme.colors.textGrey} style={styles.metaLine}>
        {option.live_status === 'free'
          ? 'Currently free'
          : option.live_status === 'occupied'
            ? 'Occupied right now'
            : 'Live status unknown'}
        {option.evidence.sensor_updated_at
          ? ` · updated ${option.evidence.sensor_updated_at}`
          : ''}
      </AppText>
    </View>
  </>
);

const CarparkContent: FC<{ option: OffStreetCarparkOption }> = ({ option }) => (
  <>
    <AppText size={18} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
      {option.title}
    </AppText>
    <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
      {option.subtitle}
    </AppText>
    {option.spaces_available !== null ? (
      <AppText size={12} color={theme.colors.textGrey} style={styles.metaLine}>
        {option.spaces_available} spaces available
      </AppText>
    ) : null}
  </>
);

// ---------------------------------------------------------------------------
// Sub-pieces
// ---------------------------------------------------------------------------

type ImageStripProps = {
  images: SignImage[];
  onImagePress: (target: ZoomTarget) => void;
};

const ImageStrip: FC<ImageStripProps> = ({ images, onImagePress }) => {
  const ordered = useMemo(
    () => [...images].sort((a, b) => Number(b.flagged) - Number(a.flagged) || a.heading - b.heading),
    [images],
  );
  if (ordered.length === 0) return null;
  return (
    <ScrollView
      horizontal
      nestedScrollEnabled
      showsHorizontalScrollIndicator={false}
      style={styles.gallery}
      contentContainerStyle={styles.galleryContent}>
      {ordered.map((img, idx) => {
        const displayUrl = img.annotated_url ?? img.url;
        const caption = `Heading ${Math.round(img.heading)}°${
          img.flagged && img.keywords_found.length > 0
            ? ' · ' + img.keywords_found.join(' · ')
            : ''
        }`;
        return (
          <View key={`${img.heading}-${img.pitch}-${idx}`} style={styles.imageBlock}>
            <Pressable
              onPress={() =>
                onImagePress({ url: displayUrl, rawUrl: img.url, caption })
              }
              accessibilityRole='button'
              accessibilityLabel={`Open image at heading ${Math.round(img.heading)} degrees`}
              style={({ pressed }) => [styles.imagePressable, pressed && styles.imagePressed]}>
              <Image
                source={{ uri: displayUrl }}
                style={styles.image}
                resizeMode='cover'
              />
              <View style={styles.zoomHint}>
                <AppText size={9} color={theme.colors.white} font={theme.fonts.poppinsSemiBold}>
                  TAP TO ENLARGE
                </AppText>
              </View>
            </Pressable>
            <AppText
              size={10}
              color={img.flagged ? theme.colors.brandGreen : theme.colors.textGrey}
              font={img.flagged ? theme.fonts.poppinsSemiBold : theme.fonts.poppinsRegular}
              style={styles.imageLabel}>
              heading {Math.round(img.heading)}°{img.flagged ? ' · SIGN' : ''}
            </AppText>
            {img.flagged && img.keywords_found.length > 0 ? (
              <AppText size={10} color={theme.colors.textGrey} numberOfLines={1}>
                {img.keywords_found.join(' · ')}
              </AppText>
            ) : null}
          </View>
        );
      })}
    </ScrollView>
  );
};

const Disclaimer: FC = () => (
  <View style={styles.disclaimerBlock}>
    <AppText size={11} color={theme.colors.textGrey}>
      Always verify the actual sign in person before parking. Imagery can be 1–4 years old;
      restrictions may have changed.
    </AppText>
  </View>
);

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  body: {
    paddingBottom: theme.spacing.xxl,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.sm,
  },
  disclaimerBlock: {
    marginTop: theme.spacing.lg,
    paddingTop: theme.spacing.md,
  },
  gallery: { marginTop: theme.spacing.md },
  galleryContent: { paddingRight: theme.spacing.lg },
  handle: {
    alignSelf: 'center',
    backgroundColor: theme.colors.borderGrey,
    borderRadius: theme.radii.pill,
    height: 4,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.sm,
    width: 40,
  },
  image: {
    backgroundColor: theme.colors.greyBgAlt,
    borderRadius: theme.radii.md,
    height: 180,
    width: 260,
  },
  imageBlock: { marginRight: theme.spacing.sm, width: 260 },
  imageLabel: { marginTop: theme.spacing.xs },
  imagePressable: { position: 'relative' },
  imagePressed: { opacity: 0.85 },
  zoomHint: {
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: theme.radii.sm,
    bottom: theme.spacing.sm,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    position: 'absolute',
    right: theme.spacing.sm,
  },
  metaBlock: { marginTop: theme.spacing.lg },
  metaLine: { marginTop: theme.spacing.xs },
  scrim: {
    backgroundColor: theme.colors.scrimDark,
    flex: 1,
    justifyContent: 'flex-end',
  },
  scrimTop: {
    flex: 1,
  },
  sheet: {
    backgroundColor: theme.colors.white,
    borderTopLeftRadius: theme.radii.xl,
    borderTopRightRadius: theme.radii.xl,
    maxHeight: '80%',
  },
});

export default OptionDetailSheet;
