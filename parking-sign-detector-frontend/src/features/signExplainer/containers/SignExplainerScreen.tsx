/**
 * F3 — "Explain this sign". Take a photo or pick from library, send to
 * the backend `/parse-sign` endpoint, render the OCR result + a
 * plain-English interpretation.
 *
 * Backend `/parse-sign` doesn't exist yet — this screen will fail
 * gracefully when called against the current API. See requirements §12.
 */
import AppLoader from '@components/AppLoader';
import AppText from '@components/AppText';
import BlockButton from '@components/BlockButton';
import ScreenContainer from '@components/ScreenContainer';
import { useParseSignMutation } from '@store/api/parkingSignsApi';
import theme from '@utils/theme';
import * as ImagePicker from 'expo-image-picker';
import React, { FC, useCallback, useState } from 'react';
import { Alert, Image, ScrollView, StyleSheet, View } from 'react-native';

const SignExplainerScreen: FC = () => {
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [parseSign, parseState] = useParseSignMutation();

  const pickFromCamera = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Camera permission denied', 'Grant camera access to use this feature.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri);
    }
  }, []);

  const pickFromLibrary = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri);
    }
  }, []);

  const explain = useCallback(async () => {
    if (!imageUri) return;
    try {
      await parseSign({ uri: imageUri }).unwrap();
    } catch (err) {
      // Soft-fail until the backend endpoint exists.
      Alert.alert('Could not parse sign', String(err));
    }
  }, [imageUri, parseSign]);

  return (
    <ScreenContainer edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText size={20} font={theme.fonts.poppinsSemiBold} color={theme.colors.textDark}>
          Explain a sign
        </AppText>
        <AppText size={13} color={theme.colors.textGrey} style={styles.subhead}>
          Take a photo of a parking sign and we'll explain what it means in plain English.
        </AppText>

        {imageUri ? (
          <Image source={{ uri: imageUri }} style={styles.preview} resizeMode='cover' />
        ) : (
          <View style={styles.placeholder}>
            <AppText size={12} color={theme.colors.textGrey}>
              No photo yet
            </AppText>
          </View>
        )}

        <View style={styles.actions}>
          <BlockButton text='Take a photo' onPress={pickFromCamera} buttonColor={theme.colors.brandGreen} />
          <View style={styles.gap} />
          <BlockButton
            text='Pick from library'
            onPress={pickFromLibrary}
            buttonColor={theme.colors.blackDark}
          />
          {imageUri ? (
            <>
              <View style={styles.gap} />
              <BlockButton
                text='Explain this sign'
                onPress={explain}
                disabled={parseState.isLoading}
                loading={parseState.isLoading}
                buttonColor={theme.colors.brandAmber}
              />
            </>
          ) : null}
        </View>

        {parseState.isLoading ? <AppLoader /> : null}

        {parseState.data ? (
          <View style={styles.resultBlock}>
            <AppText size={14} font={theme.fonts.poppinsMedium} color={theme.colors.textDark}>
              Detected text
            </AppText>
            <AppText size={12} color={theme.colors.textGrey} style={styles.resultBody}>
              {parseState.data.ocr_text || '(empty)'}
            </AppText>
            <AppText size={12} color={theme.colors.textGrey}>
              Keywords: {parseState.data.keywords_found.join(', ') || 'none'}
            </AppText>
            {parseState.data.interpretation ? (
              <AppText size={13} color={theme.colors.textDark} style={styles.resultBody}>
                {parseState.data.interpretation.plain_english}
              </AppText>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </ScreenContainer>
  );
};

const styles = StyleSheet.create({
  actions: { marginTop: theme.spacing.lg },
  content: {
    paddingBottom: theme.spacing.xl,
    paddingHorizontal: theme.spacing.horizontalDefault,
    paddingTop: theme.spacing.lg,
  },
  gap: { height: theme.spacing.md },
  placeholder: {
    alignItems: 'center',
    backgroundColor: theme.colors.greyBgAlt,
    borderRadius: theme.radii.lg,
    height: 220,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
  },
  preview: {
    backgroundColor: theme.colors.greyBgAlt,
    borderRadius: theme.radii.lg,
    height: 220,
    marginTop: theme.spacing.lg,
    width: '100%',
  },
  resultBlock: {
    backgroundColor: theme.colors.white,
    borderRadius: theme.radii.lg,
    marginTop: theme.spacing.lg,
    padding: theme.spacing.lg,
  },
  resultBody: { marginVertical: theme.spacing.sm },
  subhead: { marginTop: theme.spacing.sm },
});

export default SignExplainerScreen;
