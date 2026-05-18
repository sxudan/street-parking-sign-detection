import SettingsScreen from '@features/settings/containers/SettingsScreen';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { FC } from 'react';

import defaultStackOptions from './navigationOptions/defaultStackOptions';
import { SettingsStackParamList } from './paramLists';
import { ROUTE_SETTINGS } from './routeNames';

const Stack = createNativeStackNavigator<SettingsStackParamList>();

const SettingsStackNavigator: FC = () => (
  <Stack.Navigator screenOptions={defaultStackOptions}>
    <Stack.Screen
      name={ROUTE_SETTINGS}
      component={SettingsScreen}
      options={{ title: 'Settings' }}
    />
  </Stack.Navigator>
);

export default SettingsStackNavigator;
