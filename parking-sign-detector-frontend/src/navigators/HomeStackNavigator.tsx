import ParkingResultsScreen from '@features/parkingSearch/containers/ParkingResultsScreen';
import ParkingSearchScreen from '@features/parkingSearch/containers/ParkingSearchScreen';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { FC } from 'react';

import defaultStackOptions from './navigationOptions/defaultStackOptions';
import { HomeStackParamList } from './paramLists';
import { ROUTE_PARKING_RESULTS, ROUTE_PARKING_SEARCH } from './routeNames';

const Stack = createNativeStackNavigator<HomeStackParamList>();

const HomeStackNavigator: FC = () => (
  <Stack.Navigator screenOptions={defaultStackOptions}>
    <Stack.Screen
      name={ROUTE_PARKING_SEARCH}
      component={ParkingSearchScreen}
      // The screen renders its own large title — let it own the chrome.
      // `title: ' '` (intentional space) ensures that when ParkingResults
      // pushes on top, iOS doesn't fall back to using the route name
      // "ParkingSearch" as the back-button label.
      options={{ headerShown: false, title: '' }}
    />
    <Stack.Screen
      name={ROUTE_PARKING_RESULTS}
      component={ParkingResultsScreen}
      options={{ title: 'Parking signs', headerBackTitle: '' }}
    />
  </Stack.Navigator>
);

export default HomeStackNavigator;
