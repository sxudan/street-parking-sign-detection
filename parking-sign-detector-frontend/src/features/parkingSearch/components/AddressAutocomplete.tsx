/**
 * Address autocomplete input. Calls the backend Places proxy with a
 * 300ms debounce, shows a list of suggestions inline below the input,
 * and on tap returns { lat, lng, address } via onSelect.
 *
 * Backend uses Photon (OSM) for v1 — no API key. Same response shape
 * lets us swap providers later without touching this component.
 */
import AppText from '@components/AppText';
import {
  PlacePrediction,
  useAutocompletePlacesQuery,
  useLazyGetPlaceDetailsQuery,
} from '@store/api/parkingSignsApi';
import theme from '@utils/theme';
import { MapPin, Search, X } from 'lucide-react-native';
import React, { FC, useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

type Props = {
  onSelect: (selection: { lat: number; lng: number; address: string }) => void;
  placeholder?: string;
  initialValue?: string;
};

const AddressAutocomplete: FC<Props> = ({
  onSelect,
  placeholder = 'e.g. 12 Smith St, Fitzroy VIC 3065',
  initialValue = '',
}) => {
  const [query, setQuery] = useState(initialValue);
  const [debouncedQuery, setDebouncedQuery] = useState(initialValue);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQuery(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [query]);

  const skipQuery = debouncedQuery.length < MIN_QUERY_LENGTH || !showSuggestions;
  const { data, isFetching } = useAutocompletePlacesQuery(
    { q: debouncedQuery, country: 'au', limit: 8 },
    { skip: skipQuery },
  );

  const [fetchPlaceDetails] = useLazyGetPlaceDetailsQuery();

  const handleClear = useCallback(() => {
    setQuery('');
    setDebouncedQuery('');
    setShowSuggestions(false);
  }, []);

  const handleChangeText = useCallback((text: string) => {
    if (!text) {
      handleClear();
      return;
    }
    setQuery(text);
    setShowSuggestions(true);
  }, [handleClear]);

  const handlePick = useCallback(
    async (prediction: PlacePrediction) => {
      setQuery(prediction.description);
      setShowSuggestions(false);

      // Fast path: provider already gave us coords (e.g. Photon).
      if (typeof prediction.lat === 'number' && typeof prediction.lng === 'number') {
        onSelect({
          lat: prediction.lat,
          lng: prediction.lng,
          address: prediction.description,
        });
        return;
      }

      // Slow path (Google): resolve place_id → lat/lng via /places/details.
      setResolving(true);
      try {
        const details = await fetchPlaceDetails({ place_id: prediction.place_id }).unwrap();
        onSelect({
          lat: details.lat,
          lng: details.lng,
          address: details.formatted_address || prediction.description,
        });
      } catch (err) {
        Alert.alert(
          'Could not resolve address',
          'The selected place could not be looked up. Please try another suggestion.',
        );
      } finally {
        setResolving(false);
      }
    },
    [fetchPlaceDetails, onSelect],
  );

  const predictions = data?.predictions ?? [];
  const hasSuggestions = showSuggestions && predictions.length > 0;
  const isEmpty =
    showSuggestions &&
    !isFetching &&
    debouncedQuery.length >= MIN_QUERY_LENGTH &&
    predictions.length === 0;

  return (
    <View>
      <View style={styles.inputRow}>
        <Search size={18} color={theme.colors.textGrey} style={styles.leadingIcon} />
        <TextInput
          value={query}
          onChangeText={handleChangeText}
          onFocus={() => setShowSuggestions(true)}
          placeholder={placeholder}
          placeholderTextColor={theme.colors.textGrey}
          autoCapitalize='words'
          autoCorrect={false}
          returnKeyType='search'
          style={styles.input}
          accessibilityLabel='Address'
        />
        {isFetching || resolving ? (
          <ActivityIndicator
            size='small'
            color={theme.colors.brandGreen}
            style={styles.trailingIcon}
          />
        ) : query.length > 0 ? (
          <Pressable
            onPress={handleClear}
            hitSlop={12}
            accessibilityRole='button'
            accessibilityLabel='Clear address'
            style={styles.trailingIcon}>
            <X size={18} color={theme.colors.textGrey} />
          </Pressable>
        ) : null}
      </View>

      {hasSuggestions ? (
        <View style={styles.suggestions}>
          {predictions.map((p, i) => (
            <Pressable
              key={p.place_id}
              onPress={() => handlePick(p)}
              accessibilityRole='button'
              style={({ pressed }) => [
                styles.suggestionRow,
                i < predictions.length - 1 && styles.suggestionDivider,
                pressed && styles.suggestionRowPressed,
              ]}>
              <MapPin
                size={16}
                color={theme.colors.textGrey}
                style={styles.suggestionIcon}
              />
              <View style={styles.suggestionText}>
                <AppText
                  size={14}
                  font={theme.fonts.poppinsMedium}
                  color={theme.colors.textDark}
                  numberOfLines={1}>
                  {p.main_text}
                </AppText>
                {p.secondary_text ? (
                  <AppText
                    size={12}
                    color={theme.colors.textGrey}
                    numberOfLines={1}
                    style={styles.suggestionSecondary}>
                    {p.secondary_text}
                  </AppText>
                ) : null}
              </View>
            </Pressable>
          ))}
        </View>
      ) : null}

      {isEmpty ? (
        <View style={styles.emptyHint}>
          <AppText size={12} color={theme.colors.textGrey}>
            No matches. Try a fuller address (e.g. include the suburb).
          </AppText>
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  emptyHint: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.sm,
  },
  input: {
    color: theme.colors.textDark,
    flex: 1,
    fontFamily: theme.fonts.poppinsRegular,
    fontSize: 15,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.md,
  },
  inputRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.white,
    borderColor: theme.colors.borderGrey,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 52,
    paddingHorizontal: theme.spacing.md,
  },
  leadingIcon: { marginRight: theme.spacing.xs },
  suggestionDivider: {
    borderBottomColor: theme.colors.divider,
    borderBottomWidth: 1,
  },
  suggestionIcon: { marginRight: theme.spacing.md },
  suggestionRow: {
    alignItems: 'center',
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  suggestionRowPressed: { backgroundColor: theme.colors.greyBgAlt },
  suggestionSecondary: { marginTop: 2 },
  suggestionText: { flex: 1 },
  suggestions: {
    backgroundColor: theme.colors.white,
    borderColor: theme.colors.divider,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    marginTop: theme.spacing.sm,
    overflow: 'hidden',
    shadowColor: theme.colors.blackDark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
  },
  trailingIcon: { marginLeft: theme.spacing.xs },
});

export default AddressAutocomplete;
