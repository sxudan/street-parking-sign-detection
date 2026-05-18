/**
 * Map view for the results screen. Drops a green marker for the
 * searched address and a kind-specific marker for each ParkingOption,
 * fits the camera to all of them on first render, and animates to the
 * selected option whenever the user changes the selection.
 *
 * Markers are custom <View> children of <Marker> so we can render
 * Lucide icons inside themed circles instead of the default red pin.
 */
import AppText from '@components/AppText';
import { ParkingOption, ParkingOptionKind } from '@store/types/parkingOption';
import theme from '@utils/theme';
import { Car, MapPin } from 'lucide-react-native';
import React, { FC, memo, useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { LatLng, Marker, Region } from 'react-native-maps';

type Coord = { lat: number; lng: number };

type Props = {
  addressCoord: Coord;
  options: ParkingOption[];
  selectedIndex: number;
  onMarkerPress: (index: number) => void;
};

const INITIAL_DELTA = 0.005;
const SELECTED_DELTA = 0.0015;

const MARKER_COLOURS: Record<ParkingOptionKind, string> = {
  address_preview: theme.colors.brandGreen,
  street_parking: theme.colors.danger,
  council_bay: theme.colors.success,
  off_street_carpark: theme.colors.brandAmber,
};

function toLatLng(c: Coord): LatLng {
  return { latitude: c.lat, longitude: c.lng };
}

function titleFor(option: ParkingOption): string {
  switch (option.kind) {
    case 'address_preview':
      return 'Searched address';
    case 'street_parking':
      return option.title;
    case 'council_bay':
      return option.title;
    case 'off_street_carpark':
      return option.title;
  }
}

function descriptionFor(option: ParkingOption): string {
  if (option.kind === 'address_preview') return 'Your destination';
  return `${Math.round(option.distance_m)} m from address`;
}

// ---------------------------------------------------------------------------
// Custom marker — circular badge with a Lucide icon or the letter "P".
// ---------------------------------------------------------------------------

type MarkerBadgeProps = {
  option: ParkingOption;
  isSelected: boolean;
};

const MarkerBadge: FC<MarkerBadgeProps> = ({ option, isSelected }) => {
  const colour = MARKER_COLOURS[option.kind];
  const size = isSelected ? 44 : 36;
  const iconSize = isSelected ? 22 : 18;

  return (
    <View style={styles.markerWrap}>
      <View
        style={[
          styles.markerCircle,
          {
            backgroundColor: colour,
            height: size,
            width: size,
            borderRadius: size / 2,
          },
          isSelected && styles.markerCircleSelected,
        ]}>
        {option.kind === 'address_preview' ? (
          <MapPin size={iconSize} color={theme.colors.white} strokeWidth={2.5} />
        ) : option.kind === 'off_street_carpark' ? (
          <Car size={iconSize} color={theme.colors.white} strokeWidth={2.5} />
        ) : (
          <AppText
            size={isSelected ? 18 : 15}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.white}>
            P
          </AppText>
        )}
      </View>
      <View style={[styles.markerStem, { borderTopColor: colour }]} />
    </View>
  );
};

// ---------------------------------------------------------------------------

const MapResults: FC<Props> = ({ addressCoord, options, selectedIndex, onMarkerPress }) => {
  const mapRef = useRef<MapView>(null);

  const initialRegion: Region = useMemo(
    () => ({
      latitude: addressCoord.lat,
      longitude: addressCoord.lng,
      latitudeDelta: INITIAL_DELTA,
      longitudeDelta: INITIAL_DELTA,
    }),
    [addressCoord.lat, addressCoord.lng],
  );

  const fitKey = options.map((o) => o.id).join('|');
  useEffect(() => {
    if (!mapRef.current || options.length === 0) return;
    const coords = [
      toLatLng(addressCoord),
      ...options.map((o) => toLatLng(o.coordinate)),
    ];
    const id = setTimeout(() => {
      mapRef.current?.fitToCoordinates(coords, {
        edgePadding: { top: 80, right: 60, bottom: 60, left: 60 },
        animated: false,
      });
    }, 60);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  useEffect(() => {
    if (!mapRef.current || options.length === 0) return;
    const target = options[selectedIndex]?.coordinate ?? addressCoord;
    mapRef.current.animateToRegion(
      {
        latitude: target.lat,
        longitude: target.lng,
        latitudeDelta: SELECTED_DELTA,
        longitudeDelta: SELECTED_DELTA,
      },
      400,
    );
  }, [selectedIndex, addressCoord, options]);

  return (
    <View style={styles.container}>
      <MapView
        ref={mapRef}
        style={styles.map}
        initialRegion={initialRegion}
        showsUserLocation={false}
        showsCompass={false}
        toolbarEnabled={false}>
        {options.map((option, index) => (
          <Marker
            key={option.id}
            coordinate={toLatLng(option.coordinate)}
            anchor={{ x: 0.5, y: 1 }}
            title={titleFor(option)}
            description={descriptionFor(option)}
            onPress={() => onMarkerPress(index)}
            tracksViewChanges={false}>
            <MarkerBadge option={option} isSelected={index === selectedIndex} />
          </Marker>
        ))}
      </MapView>
    </View>
  );
};

// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1 },
  map: { flex: 1 },
  markerCircle: {
    alignItems: 'center',
    borderColor: theme.colors.white,
    borderWidth: 2,
    elevation: 3,
    justifyContent: 'center',
    shadowColor: theme.colors.blackDark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3,
  },
  markerCircleSelected: {
    borderWidth: 3,
  },
  markerStem: {
    borderLeftColor: 'transparent',
    borderLeftWidth: 5,
    borderRightColor: 'transparent',
    borderRightWidth: 5,
    borderTopWidth: 8,
    height: 0,
    marginTop: -1,
    width: 0,
  },
  markerWrap: {
    alignItems: 'center',
    paddingBottom: 0,
  },
});

export default memo(MapResults);
