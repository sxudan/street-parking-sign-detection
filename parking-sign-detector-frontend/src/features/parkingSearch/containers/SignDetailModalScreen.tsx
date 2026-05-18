/**
 * Modal that shows a single sign in detail (full image + interpretation).
 * Stub for v1 — wire up params + interpretation rendering.
 */
import AppText from '@components/AppText';
import ScreenContainer from '@components/ScreenContainer';
import { RouteProp, useRoute } from '@react-navigation/native';
import { RootStackParamList } from '@navigators/paramLists';
import theme from '@utils/theme';
import React, { FC } from 'react';
import { StyleSheet, View } from 'react-native';

type DetailRoute = RouteProp<RootStackParamList, 'SignDetailModal'>;

const SignDetailModalScreen: FC = () => {
  const route = useRoute<DetailRoute>();
  return (
    <ScreenContainer>
      <View style={styles.body}>
        <AppText size={16} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
          Sign detail
        </AppText>
        <AppText size={12} color={theme.colors.textGrey} style={styles.note}>
          pano: {route.params.panoId}
          {'\n'}heading: {route.params.heading}
        </AppText>
      </View>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  body: { paddingHorizontal: theme.spacing.horizontalDefault, paddingTop: theme.spacing.lg },
  note: { marginTop: theme.spacing.sm },
});

export default SignDetailModalScreen;
