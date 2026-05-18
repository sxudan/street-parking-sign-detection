import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import theme from '@utils/theme';
import { MapPin, Settings as SettingsIcon } from 'lucide-react-native';
import React, { FC } from 'react';

import HomeStackNavigator from './HomeStackNavigator';
import SettingsStackNavigator from './SettingsStackNavigator';
import { MainTabParamList } from './paramLists';
import { ROUTE_HOME_TAB, ROUTE_SETTINGS_TAB } from './routeNames';

const Tab = createBottomTabNavigator<MainTabParamList>();

const ICON_SIZE = 22;

/**
 * Two tabs only for v1 — Find + Settings. The Explain (camera) tab is
 * deferred until the backend `/parse-sign` endpoint exists. The route
 * constant + screen file are kept in the codebase so re-enabling later
 * is a one-line addition here.
 */
const MainTabNavigator: FC = () => (
  <Tab.Navigator
    screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: theme.colors.brandGreen,
      tabBarInactiveTintColor: theme.colors.textGrey,
      tabBarStyle: {
        backgroundColor: theme.colors.white,
        borderTopColor: theme.colors.divider,
      },
      tabBarLabelStyle: { fontFamily: theme.fonts.poppinsMedium, fontSize: 11 },
    }}>
    <Tab.Screen
      name={ROUTE_HOME_TAB}
      component={HomeStackNavigator}
      options={{
        title: 'Find',
        tabBarIcon: ({ color }) => <MapPin color={color} size={ICON_SIZE} />,
      }}
    />
    <Tab.Screen
      name={ROUTE_SETTINGS_TAB}
      component={SettingsStackNavigator}
      options={{
        title: 'Settings',
        tabBarIcon: ({ color }) => <SettingsIcon color={color} size={ICON_SIZE} />,
      }}
    />
  </Tab.Navigator>
);

export default MainTabNavigator;
