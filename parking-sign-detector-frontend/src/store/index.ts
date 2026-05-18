/**
 * Redux store wiring. Combines RTK Query APIs with local slices.
 *
 * Persistence (search history, preferences) is left as a TODO — wire
 * `redux-persist` or a small AsyncStorage-backed listener when the app
 * has stable shape.
 */
import { configureStore } from '@reduxjs/toolkit';
import { setupListeners } from '@reduxjs/toolkit/query';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

import { melbourneOpenDataApi } from './api/melbourneOpenDataApi';
import { parkingSignsApi } from './api/parkingSignsApi';
import preferencesReducer from './slices/preferencesSlice';
import searchHistoryReducer from './slices/searchHistorySlice';

export const store = configureStore({
  reducer: {
    [parkingSignsApi.reducerPath]: parkingSignsApi.reducer,
    [melbourneOpenDataApi.reducerPath]: melbourneOpenDataApi.reducer,
    searchHistory: searchHistoryReducer,
    preferences: preferencesReducer,
  },
  middleware: (getDefault) =>
    getDefault().concat(parkingSignsApi.middleware, melbourneOpenDataApi.middleware),
});

setupListeners(store.dispatch);

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
