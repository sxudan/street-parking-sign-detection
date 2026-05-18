/**
 * Settings tab — radius editor + legal links. v1 keeps it minimal.
 *
 * Radius is held in the Redux preferences slice. AsyncStorage
 * persistence is wired in a separate task; for now the value resets
 * on app reload.
 */
import AppText from '@components/AppText';
import ScreenContainer from '@components/ScreenContainer';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { RootStackParamList } from '@navigators/paramLists';
import { ROUTE_PRIVACY_MODAL, ROUTE_TERMS_MODAL } from '@navigators/routeNames';
import { useAppDispatch, useAppSelector } from '@store/index';
import { setDefaultRadius } from '@store/slices/preferencesSlice';
import theme from '@utils/theme';
import { ChevronRight, FileText, Shield } from 'lucide-react-native';
import React, { FC, useCallback, useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

const RADIUS_OPTIONS = [10, 20, 30, 50, 80, 100, 200];

type SettingsNavProp = NativeStackNavigationProp<RootStackParamList>;

const SettingsScreen: FC = () => {
  const dispatch = useAppDispatch();
  const navigation = useNavigation<SettingsNavProp>();
  const radius = useAppSelector((s) => s.preferences.defaultRadiusMetres);

  const handlePickRadius = useCallback(
    (value: number) => {
      dispatch(setDefaultRadius(value));
    },
    [dispatch],
  );

  const handleOpenTerms = useCallback(() => {
    navigation.navigate(ROUTE_TERMS_MODAL);
  }, [navigation]);

  const handleOpenPrivacy = useCallback(() => {
    navigation.navigate(ROUTE_PRIVACY_MODAL);
  }, [navigation]);

  const radiusButtons = useMemo(
    () =>
      RADIUS_OPTIONS.map((value) => ({
        value,
        label: `${value} m`,
        active: value === radius,
      })),
    [radius],
  );

  return (
    <ScreenContainer edges={['bottom']} backgroundColor={theme.colors.greyBg}>
      <ScrollView contentContainerStyle={styles.content}>
        <SectionHeader>Search radius</SectionHeader>
        <View style={styles.card}>
          <AppText size={13} color={theme.colors.textGrey} style={styles.cardSub}>
            How far from the address to look for parking signs.
          </AppText>
          <View style={styles.radiusRow}>
            {radiusButtons.map((opt) => (
              <Pressable
                key={opt.value}
                onPress={() => handlePickRadius(opt.value)}
                style={[styles.radiusPill, opt.active && styles.radiusPillActive]}
                accessibilityRole='button'
                accessibilityState={{ selected: opt.active }}>
                <AppText
                  size={13}
                  font={
                    opt.active ? theme.fonts.poppinsSemiBold : theme.fonts.poppinsRegular
                  }
                  color={opt.active ? theme.colors.white : theme.colors.textDark}>
                  {opt.label}
                </AppText>
              </Pressable>
            ))}
          </View>
        </View>

        <SectionHeader>About</SectionHeader>
        <View style={styles.card}>
          <SettingsRow
            icon={<FileText size={18} color={theme.colors.textGrey} />}
            label='Terms & Conditions'
            onPress={handleOpenTerms}
            isFirst
          />
          <View style={styles.divider} />
          <SettingsRow
            icon={<Shield size={18} color={theme.colors.textGrey} />}
            label='Privacy Policy'
            onPress={handleOpenPrivacy}
            isLast
          />
        </View>

        <AppText size={11} color={theme.colors.textGrey} style={styles.versionLine}>
          v0.1.0
        </AppText>
      </ScrollView>
    </ScreenContainer>
  );
};

// ---------------------------------------------------------------------------

const SectionHeader: FC<{ children: string }> = ({ children }) => (
  <AppText
    size={11}
    font={theme.fonts.poppinsMedium}
    color={theme.colors.textGrey}
    style={styles.sectionHeader}>
    {children.toUpperCase()}
  </AppText>
);

type SettingsRowProps = {
  icon: React.ReactNode;
  label: string;
  onPress: () => void;
  isFirst?: boolean;
  isLast?: boolean;
};

const SettingsRow: FC<SettingsRowProps> = ({ icon, label, onPress, isFirst, isLast }) => (
  <Pressable
    onPress={onPress}
    accessibilityRole='button'
    accessibilityLabel={label}
    style={({ pressed }) => [
      styles.row,
      isFirst && styles.rowFirst,
      isLast && styles.rowLast,
      pressed && styles.rowPressed,
    ]}>
    <View style={styles.rowIcon}>{icon}</View>
    <AppText size={15} color={theme.colors.textDark} style={styles.rowLabel}>
      {label}
    </AppText>
    <ChevronRight size={18} color={theme.colors.borderGrey} />
  </Pressable>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.white,
    borderRadius: theme.radii.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  cardSub: { marginBottom: theme.spacing.md },
  content: {
    paddingBottom: theme.spacing.xxl,
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingTop: theme.spacing.sm,
  },
  divider: {
    backgroundColor: theme.colors.divider,
    height: 1,
    marginLeft: theme.spacing.xl + theme.spacing.md,
  },
  radiusPill: {
    backgroundColor: theme.colors.greyBg,
    borderRadius: theme.radii.pill,
    minWidth: 60,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  radiusPillActive: { backgroundColor: theme.colors.brandGreen },
  radiusRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.md,
  },
  rowFirst: {},
  rowIcon: {
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: theme.spacing.md,
    width: theme.spacing.xl,
  },
  rowLabel: { flex: 1 },
  rowLast: {},
  rowPressed: { backgroundColor: theme.colors.greyBgAlt },
  sectionHeader: {
    letterSpacing: 0.6,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.xl,
  },
  versionLine: {
    marginTop: theme.spacing.xl,
    textAlign: 'center',
  },
});

export default SettingsScreen;
