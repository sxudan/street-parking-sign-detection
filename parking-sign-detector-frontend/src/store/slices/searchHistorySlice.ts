/**
 * Local-only slice of the user's recent searches. Persists via redux
 * middleware (see store/index.ts) when AsyncStorage hydration is wired
 * up. For v1 we cap to the last 20 entries.
 */
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type SearchHistoryEntry = {
  id: string;
  label: string;
  lat: number;
  lng: number;
  timestamp: number;
};

type SearchHistoryState = {
  entries: SearchHistoryEntry[];
};

const initialState: SearchHistoryState = {
  entries: [],
};

const MAX_ENTRIES = 20;

const searchHistorySlice = createSlice({
  name: 'searchHistory',
  initialState,
  reducers: {
    addSearch(state, action: PayloadAction<Omit<SearchHistoryEntry, 'id' | 'timestamp'>>) {
      const entry: SearchHistoryEntry = {
        ...action.payload,
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Date.now(),
      };
      // Prepend, dedupe by label, cap to MAX_ENTRIES
      const deduped = state.entries.filter((e) => e.label !== entry.label);
      state.entries = [entry, ...deduped].slice(0, MAX_ENTRIES);
    },
    clearHistory(state) {
      state.entries = [];
    },
    removeEntry(state, action: PayloadAction<string>) {
      state.entries = state.entries.filter((e) => e.id !== action.payload);
    },
  },
});

export const { addSearch, clearHistory, removeEntry } = searchHistorySlice.actions;
export default searchHistorySlice.reducer;
