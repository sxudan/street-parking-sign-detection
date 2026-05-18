/**
 * Find tab landing — address autocomplete + "Use my location".
 *
 * Address autocomplete is powered by the backend's /places/autocomplete
 * proxy (Photon / OSM under the hood — free, no key). Picking a
 * suggestion immediately navigates to ParkingResults with lat/lng so we
 * skip the backend's geocoding step on the next call too.
 */
import AppText from '@components/AppText';
import BlockButton from '@components/BlockButton';
import ScreenContainer from '@components/ScreenContainer';
import AddressAutocomplete from '@features/parkingSearch/components/AddressAutocomplete';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import { HomeStackParamList } from '@navigators/paramLists';
import { ROUTE_PARKING_RESULTS } from '@navigators/routeNames';
import theme from '@utils/theme';
import * as Location from 'expo-location';
import React, { FC, useCallback, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { useStatusBar } from '@hooks/useStatusBar';

type SearchNavProp = NativeStackNavigationProp<HomeStackParamList, 'ParkingSearch'>;

const ParkingSearchScreen: FC = () => {
  useStatusBar('dark-content');

  const navigation = useNavigation<SearchNavProp>();
  const [locating, setLocating] = useState(false);

  const handleSelectAddress = useCallback(
    (selection: { lat: number; lng: number; address: string }) => {
      navigation.navigate(ROUTE_PARKING_RESULTS, {
        lat: selection.lat,
        lng: selection.lng,
      });
    },
    [navigation],
  );

  const handleUseMyLocation = useCallback(async () => {
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert(
          'Location permission denied',
          'Grant location access to use this feature.',
        );
        return;
      }
      const pos = await Location.getCurrentPositionAsync({});
      navigation.navigate(ROUTE_PARKING_RESULTS, {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
      });
    } catch (err) {
      Alert.alert('Could not get location', String(err));
    } finally {
      setLocating(false);
    }
  }, [navigation]);

  return (
    <ScreenContainer edges={['top', 'bottom']} backgroundColor={theme.colors.greyBg}>
      <KeyboardAvoidingView
        style={styles.fill}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps='handled'>
          <AppText
            size={22}
            font={theme.fonts.poppinsSemiBold}
            color={theme.colors.textDark}>
            Find parking
          </AppText>
          <AppText
            size={13}
            color={theme.colors.textGrey}
            style={styles.subhead}>
            Type an address (or use your location) to see parking signs visible from Google
            Street View at that spot.
          </AppText>

          <View style={styles.autocompleteWrap}>
            <AddressAutocomplete onSelect={handleSelectAddress} />
          </View>

          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <AppText
              size={11}
              color={theme.colors.textGrey}
              style={styles.dividerLabel}>
              or
            </AppText>
            <View style={styles.dividerLine} />
          </View>

          <BlockButton
            text={locating ? 'Locating…' : 'Use my location'}
            onPress={handleUseMyLocation}
            disabled={locating}
            loading={locating}
            buttonColor={theme.colors.blackDark}
          />

          <AppText
            size={11}
            color={theme.colors.textGrey}
            style={styles.disclaimer}>
            Always verify the actual sign in person before parking. Imagery on Street View
            can be 1–4 years old.
          </AppText>
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  autocompleteWrap: {
    marginTop: theme.spacing.xl,
    zIndex: 10,
  },
  content: {
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingTop: theme.spacing.lg,
  },
  disclaimer: {
    marginTop: theme.spacing.xl,
    textAlign: 'center',
  },
  divider: {
    alignItems: 'center',
    flexDirection: 'row',
    marginVertical: theme.spacing.lg,
  },
  dividerLabel: { marginHorizontal: theme.spacing.md },
  dividerLine: {
    backgroundColor: theme.colors.divider,
    flex: 1,
    height: 1,
  },
  fill: { flex: 1 },
  subhead: { marginTop: theme.spacing.sm },
});

export default ParkingSearchScreen;
