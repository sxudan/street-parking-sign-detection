/**
 * App entry point. Wires the Redux Provider, NavigationContainer,
 * SafeAreaProvider, and StatusBar — then hands off to RootNavigator.
 */
import 'react-native-gesture-handler';

import { NavigationContainer } from '@react-navigation/native';
import RootNavigator from '@navigators/RootNavigator';
import { store } from '@store/index';
import { StatusBar } from 'expo-status-bar';
import React, { FC } from 'react';
import { Provider } from 'react-redux';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

const App: FC = () => {
  return (
    <Provider store={store}>
      <SafeAreaProvider>
        <GestureHandlerRootView style={styles.fill}>
          <NavigationContainer>
            <RootNavigator />
            <StatusBar style='auto' />
          </NavigationContainer>
        </GestureHandlerRootView>
      </SafeAreaProvider>
    </Provider>
  );
};

const styles = { fill: { flex: 1 } } as const;

export default App;
