/**
 * Results screen — map up top, two stacked horizontal rows beneath:
 *   1. Address Street View preview (8 angle thumbnails)
 *   2. Parking-sign cards carousel
 *
 * Tapping any thumbnail / card / map marker opens the OptionDetailSheet
 * for that ParkingOption. Bidirectional linking (marker ↔ carousel) is
 * driven by `selectedSignIndex`, indexing into the parking-only subset
 * so the address card and parking cards have separate selection state.
 */
import AppLoader from '@components/AppLoader';
import AppText from '@components/AppText';
import ScreenContainer from '@components/ScreenContainer';
import AddressPreviewRow from '@features/parkingSearch/components/AddressPreviewRow';
import MapResults from '@features/parkingSearch/components/MapResults';
import OptionDetailSheet from '@features/parkingSearch/components/OptionDetailSheet';
import ResultsCarousel from '@features/parkingSearch/components/ResultsCarousel';
import { HomeStackParamList } from '@navigators/paramLists';
import { RouteProp, useRoute } from '@react-navigation/native';
import { useAppSelector } from '@store/index';
import { streetParkingFromSigns } from '@store/adapters/streetParkingAdapter';
import {
  ParkingSignsRequest,
  useFindParkingSignsQuery,
} from '@store/api/parkingSignsApi';
import {
  AddressPreviewOption,
  Coord,
  ParkingOption,
} from '@store/types/parkingOption';
import theme from '@utils/theme';
import { AlertTriangle, MapPinOff, RefreshCw } from 'lucide-react-native';
import React, { FC, useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StatusBar, StyleSheet, View } from 'react-native';
import { useStatusBar } from '@hooks/useStatusBar';

type ResultsRoute = RouteProp<HomeStackParamList, 'ParkingResults'>;

const ParkingResultsScreen: FC = () => {
  useStatusBar('dark-content');
  const route = useRoute<ResultsRoute>();
  const { address, lat, lng } = route.params;

  // Pulled from the Settings tab's radius pills — the user picks a
  // value there and it drives every subsequent search.
  const radius = useAppSelector((s) => s.preferences.defaultRadiusMetres);

  const queryArgs: ParkingSignsRequest | null = useMemo(() => {
    if (lat !== undefined && lng !== undefined) {
      // Prefer lat/lng even when address is also passed — coords are
      // exact, the address would just be re-geocoded server-side.
      return { lat, lng, radius, thumbnail_size: '1600x900', same_street: false };
    }
    if (address) {
      return { address, radius, thumbnail_size: '1600x900', same_street: false };
    }
    return null;
  }, [address, lat, lng, radius]);

  const { data, isLoading, isFetching, error, refetch } = useFindParkingSignsQuery(
    (queryArgs ?? {}) as ParkingSignsRequest,
    { skip: !queryArgs },
  );

  // selectedSignIndex indexes into `parkingOptions` (NOT the full
  // options list). The address card has its own separate selection
  // path through `addressOption`.
  const [selectedSignIndex, setSelectedSignIndex] = useState(0);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sheetOption, setSheetOption] = useState<ParkingOption | null>(null);

  const allOptions: ParkingOption[] = useMemo(
    () => (data ? streetParkingFromSigns(data) : []),
    [data],
  );

  // Best-known coordinate for the map: backend-resolved coord wins (it's
  // the geocoded answer); otherwise fall back to whatever the route was
  // given. Lets the map keep rendering on the error / no-imagery paths
  // instead of swapping the whole screen for a blank empty state.
  const fallbackCoord: Coord | null = useMemo(() => {
    if (data?.coordinate) return data.coordinate;
    if (lat !== undefined && lng !== undefined) return { lat, lng };
    return null;
  }, [data?.coordinate, lat, lng]);

  const addressOption = allOptions.find(
    (o): o is AddressPreviewOption => o.kind === 'address_preview',
  );
  const parkingOptions = useMemo(
    () => allOptions.filter((o) => o.kind !== 'address_preview'),
    [allOptions],
  );

  // If we have no real options but we DO have a coordinate, synthesise a
  // minimal address pin so the map still has something to point at.
  // Empty `images` means tapping it opens the detail sheet to a graceful
  // "no preview available" state (see AddressPreviewContent in
  // OptionDetailSheet — the image strip just renders null on empty).
  const markerOptions: ParkingOption[] = useMemo(() => {
    if (allOptions.length > 0) return allOptions;
    if (!fallbackCoord) return [];
    const synth: AddressPreviewOption = {
      kind: 'address_preview',
      id: 'address',
      coordinate: fallbackCoord,
      distance_m: 0,
      pano_id: '',
      pano_date: null,
      images: [],
    };
    return [synth];
  }, [allOptions, fallbackCoord]);

  const handleMarkerPress = useCallback(
    (index: number) => {
      const option = allOptions[index];
      if (!option) return;
      if (option.kind === 'address_preview') {
        setSheetOption(option);
      } else {
        const signIndex = parkingOptions.findIndex((o) => o.id === option.id);
        if (signIndex >= 0) {
          setSelectedSignIndex(signIndex);
          setSheetOption(parkingOptions[signIndex]);
        }
      }
      setSheetOpen(true);
    },
    [allOptions, parkingOptions],
  );

  const handleSignCardPress = useCallback(
    (index: number) => {
      const option = parkingOptions[index];
      if (!option) return;
      setSelectedSignIndex(index);
      setSheetOption(option);
      setSheetOpen(true);
    },
    [parkingOptions],
  );

  const handleAddressTap = useCallback(() => {
    if (!addressOption) return;
    setSheetOption(addressOption);
    setSheetOpen(true);
  }, [addressOption]);

  // ---------- Render branches ----------

  // Hard block — we don't even know where to point the map.
  if (!queryArgs) {
    return <Empty title='Missing address' body='Open this screen from the search bar.' />;
  }

  // First-load spinner: no data yet AND no fallback coord to draw a map.
  // Once we have a coord (data.coordinate or route lat/lng) the map can
  // render even while a refetch is pending.
  if (isLoading && !fallbackCoord) {
    return (
      <ScreenContainer>
        <AppLoader />
      </ScreenContainer>
    );
  }

  // Last-resort error: no coord, no data — can't render the map at all.
  if (!fallbackCoord) {
    return (
      <Empty
        tone='danger'
        title="Couldn't load parking info"
        body='Something went wrong fetching results. Check your internet and give it another try.'
      />
    );
  }

  // Three-state machine for the bottom panel. Order matters: a fetch
  // can be in progress AND the previous response can be the empty
  // result, so we have to check `isFirstLoad` BEFORE `hasNoImagery`.
  //   - isFirstLoad: still waiting on the very first response. No data,
  //     no error, query in flight. `allOptions === []` here but that's
  //     because we don't have data yet — NOT because the backend said
  //     there's no imagery.
  //   - hasError: most recent fetch errored. Persists across retries
  //     until a successful response replaces it.
  //   - hasNoImagery: data successfully arrived AND the backend told us
  //     there's no Street View imagery near the address.
  const isFirstLoad = !data && !error;
  const hasError = Boolean(error);
  const hasNoImagery = Boolean(data) && allOptions.length === 0;

  const headerLabel =
    parkingOptions.length === 0
      ? 'No parking signs detected nearby.'
      : `${parkingOptions.length} parking option${parkingOptions.length === 1 ? '' : 's'} detected`;

  // selectedSignIndex maps back into markerOptions for the map's
  // selection pin highlight.
  const selectedAllIndex =
    parkingOptions.length > 0
      ? markerOptions.findIndex((o) => o.id === parkingOptions[selectedSignIndex]?.id)
      : markerOptions.findIndex((o) => o.kind === 'address_preview');

  return (
    <ScreenContainer edges={['bottom']} backgroundColor={theme.colors.greyBg}>
      <View style={styles.mapWrap}>
        <MapResults
          addressCoord={fallbackCoord}
          options={markerOptions}
          selectedIndex={Math.max(0, selectedAllIndex)}
          onMarkerPress={handleMarkerPress}
        />
      </View>

      <View style={styles.bottomWrap}>
        {isFirstLoad ? (
          <StateBanner
            tone='info'
            icon={<ActivityIndicator size='small' color={theme.colors.textGrey} />}
            title='Looking for parking signs…'
            body='Scanning Street View around this address. This usually takes a few seconds.'
          />
        ) : hasError ? (
          <StateBanner
            tone='danger'
            icon={<AlertTriangle size={18} color={theme.colors.danger} />}
            title="Couldn't load parking info"
            body='Something went wrong fetching results. Check your internet and give it another try.'
            actionLabel={isFetching ? 'Retrying…' : 'Retry'}
            actionIcon={<RefreshCw size={14} color={theme.colors.white} />}
            actionDisabled={isFetching}
            onAction={refetch}
          />
        ) : hasNoImagery ? (
          <StateBanner
            tone='info'
            icon={<MapPinOff size={18} color={theme.colors.textGrey} />}
            title='No Street View imagery here'
            body="We couldn't find any panoramas near this address. Try a different street, or move closer to a main road."
          />
        ) : (
          <>
            {addressOption ? (
              <AddressPreviewRow option={addressOption} onPress={handleAddressTap} />
            ) : null}

            <View style={styles.carouselSection}>
              <View style={styles.carouselHeaderRow}>
                <AppText
                  size={11}
                  font={theme.fonts.poppinsSemiBold}
                  color={theme.colors.textGrey}>
                  PARKING SIGNS
                </AppText>
                <AppText size={11} color={theme.colors.textGrey}>
                  {headerLabel}
                </AppText>
              </View>

              {parkingOptions.length === 0 ? (
                <View style={styles.noSigns}>
                  <AppText size={12} color={theme.colors.textGrey}>
                    No parking signs were detected within the search radius. The Street View
                    preview above is still available.
                  </AppText>
                </View>
              ) : (
                <ResultsCarousel
                  options={parkingOptions}
                  selectedIndex={selectedSignIndex}
                  onChangeIndex={setSelectedSignIndex}
                  onCardPress={handleSignCardPress}
                />
              )}
            </View>
          </>
        )}

        <View style={styles.footer}>
          <AppText size={10} color={theme.colors.textGrey} numberOfLines={1}>
            ⚠️ Verify on site — Street View can be 1–4 years old.
          </AppText>
        </View>
      </View>

      <OptionDetailSheet
        visible={sheetOpen}
        option={sheetOption}
        onClose={() => {
          setSheetOpen(false);
          StatusBar.setBarStyle('dark-content');
        }}
      />
    </ScreenContainer>
  );
};

// ---------- State banner (banner-style empty/error inside bottom panel) ----------

type StateBannerProps = {
  tone: 'danger' | 'info';
  icon: React.ReactNode;
  title: string;
  body: string;
  actionLabel?: string;
  actionIcon?: React.ReactNode;
  actionDisabled?: boolean;
  onAction?: () => void;
};

const StateBanner: FC<StateBannerProps> = ({
  tone,
  icon,
  title,
  body,
  actionLabel,
  actionIcon,
  actionDisabled,
  onAction,
}) => (
  <View
    style={[
      styles.banner,
      tone === 'danger' ? styles.bannerDanger : styles.bannerInfo,
    ]}>
    <View style={styles.bannerHeaderRow}>
      <View style={styles.bannerIcon}>{icon}</View>
      <AppText
        size={14}
        font={theme.fonts.poppinsSemiBold}
        color={tone === 'danger' ? theme.colors.danger : theme.colors.textDark}>
        {title}
      </AppText>
    </View>
    <AppText size={12} color={theme.colors.textGrey} style={styles.bannerBody}>
      {body}
    </AppText>
    {onAction && actionLabel ? (
      <Pressable
        accessibilityRole='button'
        accessibilityLabel={actionLabel}
        onPress={actionDisabled ? undefined : onAction}
        disabled={actionDisabled}
        style={({ pressed }) => [
          styles.bannerAction,
          pressed && !actionDisabled && styles.bannerActionPressed,
          actionDisabled && styles.bannerActionDisabled,
        ]}>
        {actionIcon ? <View style={styles.bannerActionIcon}>{actionIcon}</View> : null}
        <AppText
          size={12}
          font={theme.fonts.poppinsSemiBold}
          color={theme.colors.white}>
          {actionLabel}
        </AppText>
      </Pressable>
    ) : null}
  </View>
);

// ---------- Helper: empty / error states ----------

type EmptyProps = {
  title: string;
  body: string;
  tone?: 'default' | 'danger';
};

const Empty: FC<EmptyProps> = ({ title, body, tone = 'default' }) => (
  <ScreenContainer>
    <View style={styles.emptyBlock}>
      <AppText
        size={16}
        font={theme.fonts.poppinsSemiBold}
        color={tone === 'danger' ? theme.colors.danger : theme.colors.textDark}>
        {title}
      </AppText>
      <AppText size={13} color={theme.colors.textGrey} style={styles.emptyBody}>
        {body}
      </AppText>
    </View>
  </ScreenContainer>
);

const styles = StyleSheet.create({
  banner: {
    backgroundColor: theme.colors.white,
    borderRadius: theme.radii.lg,
    marginHorizontal: theme.spacing.horizontalDefault,
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  bannerAction: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: theme.colors.blackDark,
    borderRadius: theme.radii.pill,
    flexDirection: 'row',
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  bannerActionDisabled: { opacity: 0.5 },
  bannerActionIcon: { marginRight: theme.spacing.xs },
  bannerActionPressed: { opacity: 0.75 },
  bannerBody: { marginTop: theme.spacing.xs },
  bannerDanger: {
    borderLeftColor: theme.colors.danger,
    borderLeftWidth: 3,
  },
  bannerHeaderRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
  bannerIcon: { marginRight: theme.spacing.sm },
  bannerInfo: {
    borderLeftColor: theme.colors.borderGrey,
    borderLeftWidth: 3,
  },
  bottomWrap: {
    backgroundColor: theme.colors.greyBg,
    paddingBottom: theme.spacing.sm,
  },
  carouselHeaderRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
    paddingHorizontal: theme.spacing.horizontalDefault,
  },
  carouselSection: {
    paddingTop: theme.spacing.md,
  },
  emptyBlock: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.xl,
  },
  emptyBody: { marginTop: theme.spacing.sm, textAlign: 'center' },
  footer: {
    alignItems: 'center',
    paddingTop: theme.spacing.md,
  },
  mapWrap: { flex: 1 },
  noSigns: {
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingVertical: theme.spacing.md,
  },
});

export default ParkingResultsScreen;
