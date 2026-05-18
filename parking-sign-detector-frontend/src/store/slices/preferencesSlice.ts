/**
 * App-level preferences (disclaimer acknowledged, default radius, etc.).
 * Persisted via AsyncStorage middleware in store/index.ts.
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

type PreferencesState = {
  disclaimerAcknowledged: boolean;
  defaultRadiusMetres: number;
  preferThumbnailHighRes: boolean;
};

const initialState: PreferencesState = {
  disclaimerAcknowledged: false,
  defaultRadiusMetres: 30,
  preferThumbnailHighRes: true,
};

const preferencesSlice = createSlice({
  name: 'preferences',
  initialState,
  reducers: {
    acknowledgeDisclaimer(state) {
      state.disclaimerAcknowledged = true;
    },
    setDefaultRadius(state, action: PayloadAction<number>) {
      state.defaultRadiusMetres = action.payload;
    },
    setPreferThumbnailHighRes(state, action: PayloadAction<boolean>) {
      state.preferThumbnailHighRes = action.payload;
    },
  },
});

export const { acknowledgeDisclaimer, setDefaultRadius, setPreferThumbnailHighRes } =
  preferencesSlice.actions;
export default preferencesSlice.reducer;
