/**
 * First-launch disclaimer the user must dismiss once. Shown again any
 * time the user re-installs (preferences are local).
 */
import AppText from '@components/AppText';
import BlockButton from '@components/BlockButton';
import ScreenContainer from '@components/ScreenContainer';
import { useNavigation } from '@react-navigation/native';
import { acknowledgeDisclaimer } from '@store/slices/preferencesSlice';
import { useAppDispatch } from '@store/index';
import theme from '@utils/theme';
import React, { FC, useCallback } from 'react';
import { ScrollView, StyleSheet } from 'react-native';

const DisclaimerModalScreen: FC = () => {
  const dispatch = useAppDispatch();
  const navigation = useNavigation();

  const accept = useCallback(() => {
    dispatch(acknowledgeDisclaimer());
    if (navigation.canGoBack()) {
      navigation.goBack();
    }
  }, [dispatch, navigation]);

  return (
    <ScreenContainer edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText size={22} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
          Before you park
        </AppText>
        <AppText size={13} color={theme.colors.textGrey} style={styles.body}>
          This app shows parking-sign photos from Google Street View and (in Melbourne CBD) live
          bay availability from open data. Imagery can be 1–4 years old, OCR can misread signs,
          and rules change.{'\n\n'}
          Always verify the actual sign in person before parking. We accept no liability for
          parking infringements.
        </AppText>
        <BlockButton
          text='I understand'
          onPress={accept}
          buttonColor={theme.colors.brandGreen}
          containerStyle={styles.cta}
        />
      </ScrollView>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  body: { lineHeight: 20, marginTop: theme.spacing.md },
  content: {
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingTop: theme.spacing.lg,
  },
  cta: { marginTop: theme.spacing.xl },
});

export default DisclaimerModalScreen;
