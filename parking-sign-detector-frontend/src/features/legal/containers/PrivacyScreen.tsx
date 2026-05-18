/**
 * Privacy Policy modal — short, clear v1 copy. Replace with the legal
 * team's wording before launch.
 */
import AppText from '@components/AppText';
import ScreenContainer from '@components/ScreenContainer';
import theme from '@utils/theme';
import React, { FC } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

const PrivacyScreen: FC = () => (
  <ScreenContainer edges={['bottom']} backgroundColor={theme.colors.white}>
    <ScrollView contentContainerStyle={styles.content}>
      <AppText size={22} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
        Privacy Policy
      </AppText>
      <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
        Effective: May 2026 · v1
      </AppText>

      <Section title='What we collect'>
        Addresses you search for. Approximate device location, only when you tap "Use my
        location". Recent searches saved on this device. We do not collect names, emails, or
        phone numbers in v1.
      </Section>

      <Section title='What we send to others'>
        Addresses and coordinates are sent to Google (Maps Places + Street View) to fetch
        suggestions and imagery. Recent searches stay on your device.
      </Section>

      <Section title='What we keep'>
        Search history is stored locally on your device only. You can clear it from
        Settings. We do not run analytics in v1.
      </Section>

      <Section title='Children'>
        The app is not directed at children under 13 and we do not knowingly collect data
        from them.
      </Section>

      <Section title='Your rights'>
        Because we do not store personal data on our servers, there is nothing to delete on
        request. To clear your local data, uninstall the app or use the "Clear search
        history" option in Settings.
      </Section>

      <Section title='Contact'>
        For privacy questions, email the address listed on the app store listing.
      </Section>
    </ScrollView>
  </ScreenContainer>
);

const Section: FC<{ title: string; children: string }> = ({ title, children }) => (
  <View style={styles.section}>
    <AppText size={14} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
      {title}
    </AppText>
    <AppText size={13} color={theme.colors.textGrey} lineHeight={20} style={styles.sectionBody}>
      {children}
    </AppText>
  </View>
);

const styles = StyleSheet.create({
  content: {
    paddingBottom: theme.spacing.xxl,
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
  },
  metaLine: { marginTop: theme.spacing.xs },
  section: { marginTop: theme.spacing.xl },
  sectionBody: { marginTop: theme.spacing.sm },
});

export default PrivacyScreen;
