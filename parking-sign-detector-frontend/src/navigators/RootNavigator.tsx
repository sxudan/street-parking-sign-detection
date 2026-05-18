import DisclaimerModalScreen from '@features/onboarding/containers/DisclaimerModalScreen';
import PrivacyScreen from '@features/legal/containers/PrivacyScreen';
import TermsScreen from '@features/legal/containers/TermsScreen';
import SignDetailModalScreen from '@features/parkingSearch/containers/SignDetailModalScreen';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { FC } from 'react';

import MainTabNavigator from './MainTabNavigator';
import defaultStackOptions, { defaultModalOptions } from './navigationOptions/defaultStackOptions';
import { RootStackParamList } from './paramLists';
import {
  ROUTE_DISCLAIMER_MODAL,
  ROUTE_MAIN_TABS,
  ROUTE_PRIVACY_MODAL,
  ROUTE_SIGN_DETAIL_MODAL,
  ROUTE_TERMS_MODAL,
} from './routeNames';

const Stack = createNativeStackNavigator<RootStackParamList>();

const RootNavigator: FC = () => (
  <Stack.Navigator screenOptions={defaultStackOptions}>
    <Stack.Screen name={ROUTE_MAIN_TABS} component={MainTabNavigator} options={{ headerShown: false }} />
    <Stack.Group screenOptions={defaultModalOptions}>
      <Stack.Screen
        name={ROUTE_DISCLAIMER_MODAL}
        component={DisclaimerModalScreen}
        options={{ title: 'Before you park' }}
      />
      <Stack.Screen
        name={ROUTE_SIGN_DETAIL_MODAL}
        component={SignDetailModalScreen}
        options={{ title: 'Sign detail' }}
      />
      <Stack.Screen
        name={ROUTE_TERMS_MODAL}
        component={TermsScreen}
        options={{ title: 'Terms & Conditions' }}
      />
      <Stack.Screen
        name={ROUTE_PRIVACY_MODAL}
        component={PrivacyScreen}
        options={{ title: 'Privacy Policy' }}
      />
    </Stack.Group>
  </Stack.Navigator>
);

export default RootNavigator;
