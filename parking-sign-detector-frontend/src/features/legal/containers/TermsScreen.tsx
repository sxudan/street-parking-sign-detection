/**
 * Terms & Conditions modal — short, clear v1 copy. Replace with the
 * legal team's wording before launch.
 */
import AppText from '@components/AppText';
import ScreenContainer from '@components/ScreenContainer';
import theme from '@utils/theme';
import React, { FC } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

const TermsScreen: FC = () => (
  <ScreenContainer edges={['bottom']} backgroundColor={theme.colors.white}>
    <ScrollView contentContainerStyle={styles.content}>
      <AppText size={22} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
        Terms & Conditions
      </AppText>
      <AppText size={11} color={theme.colors.textGrey} style={styles.metaLine}>
        Effective: May 2026 · v1
      </AppText>

      <Section title='1. The service'>
        This app shows parking sign photos pulled from Google Street View and runs OCR over
        them to suggest parking restrictions near a given address. Detection is best-effort.
      </Section>

      <Section title='2. No legal or driving advice'>
        Information returned by the app is informational only and does not constitute legal,
        financial, or driving advice. Parking restrictions, signage, and council policies
        change. Always verify the actual sign in person before parking.
      </Section>

      <Section title='3. No liability for parking infringements'>
        We accept no liability for any parking fines, vehicle clamping, towing, or other
        consequences arising from your use of the app. You are solely responsible for
        complying with the actual signs at the location.
      </Section>

      <Section title='4. Imagery freshness'>
        Google Street View imagery may be 1–4 years old. Pano dates are surfaced in the app
        where available. Recent changes to signs may not yet be reflected.
      </Section>

      <Section title='5. Use at your own risk'>
        The app is provided "as is", without warranties of any kind, express or implied.
        Continued use of the app constitutes acceptance of these terms.
      </Section>

      <Section title='6. Changes'>
        We may update these terms from time to time. Material changes will be surfaced in
        the app on next launch.
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

export default TermsScreen;
