import SignExplainerScreen from '@features/signExplainer/containers/SignExplainerScreen';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { FC } from 'react';

import defaultStackOptions from './navigationOptions/defaultStackOptions';
import { ExplainStackParamList } from './paramLists';
import { ROUTE_SIGN_EXPLAINER } from './routeNames';

const Stack = createNativeStackNavigator<ExplainStackParamList>();

const ExplainStackNavigator: FC = () => (
  <Stack.Navigator screenOptions={defaultStackOptions}>
    <Stack.Screen
      name={ROUTE_SIGN_EXPLAINER}
      component={SignExplainerScreen}
      options={{ title: 'Explain a sign' }}
    />
  </Stack.Navigator>
);

export default ExplainStackNavigator;
