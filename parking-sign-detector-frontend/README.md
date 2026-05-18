# Parking Sign Detector — Mobile (Expo)

Expo / React Native client for the parking-sign-detector backend.
Companion to the FastAPI service in `../parking-detector/`.

> Read **`docs/requirements.md`** before changing anything substantive,
> and **`docs/ai/rules/rules.md`** before writing any feature code.

## Stack at a glance

- **Expo SDK 51**, React Native 0.74, TypeScript (strict)
- **React Navigation 6** (native stack + bottom tabs + modal stack)
- **Redux Toolkit** + **RTK Query** for state and server cache
- **react-hook-form** + **Zod** for forms
- **react-native-maps**, **expo-camera**, **expo-location**, **expo-image-picker**

## Prerequisites

1. **Node 20+** and **Yarn**.
2. **Expo CLI** (`npx expo …` works without a global install).
3. **iOS Simulator** (Xcode) and/or **Android Emulator** (Android Studio) for local dev.
4. The **parking-detector** backend running somewhere reachable from your device. See `../parking-detector/README.md`.

## Setup

```bash
yarn install
cp .env.example .env   # then edit .env to point at your backend
```

### Pointing the app at the backend

Set `EXPO_PUBLIC_API_BASE_URL` in `.env`:

| Where the app runs    | URL                                |
| --------------------- | ---------------------------------- |
| iOS Simulator         | `http://localhost:8000`            |
| Android Emulator      | `http://10.0.2.2:8000`             |
| Physical device       | `http://<your-laptop-LAN-IP>:8000` |
| Production            | `https://api.your-domain.com`      |

If you set `PUBLIC_BASE_URL` on the backend, image URLs returned in
the API will already be absolute and reachable from the device — no
extra config needed.

## Run

```bash
yarn start          # Metro bundler, then choose i / a / w
yarn ios            # boot iOS simulator + open
yarn android        # boot Android emulator + open
yarn web            # browser (limited — maps + camera don't work)
```

## What works in the v0 skeleton

- App boots into a 3-tab layout: **Find / Explain / Settings**.
- **Find tab** has "Use my location" and a "Try a demo address" button that hits the backend at the South Yarra coordinate and renders results.
- **Explain tab** lets you take or pick a photo. The "Explain this sign" call requires the backend `POST /parse-sign` endpoint, which is **not yet implemented** server-side (see backend tasks in `docs/requirements.md` §12).
- **Settings tab** shows current backend URL + preferences from the Redux store.
- **First-launch disclaimer modal** is wired but not yet auto-presented; that hook lives in the side-effects layer to be added.

## Where to look next

| Area                 | Path                                                              |
| -------------------- | ----------------------------------------------------------------- |
| Project rules & conventions | [`docs/ai/rules/rules.md`](docs/ai/rules/rules.md)         |
| Component patterns   | [`docs/ai/examples/component-patterns.tsx`](docs/ai/examples/component-patterns.tsx) |
| Screen patterns      | [`docs/ai/examples/screen-patterns.tsx`](docs/ai/examples/screen-patterns.tsx) |
| Product requirements | [`docs/requirements.md`](docs/requirements.md)                    |
| Route names          | [`src/navigators/routeNames.ts`](src/navigators/routeNames.ts)    |
| Param lists          | [`src/navigators/paramLists.ts`](src/navigators/paramLists.ts)    |
| Store + RTK Query    | [`src/store/`](src/store/)                                        |
| Backend types        | [`src/store/api/parkingSignsApi.ts`](src/store/api/parkingSignsApi.ts) |
| Theme                | [`src/utils/theme.ts`](src/utils/theme.ts)                        |
| App* primitives      | [`src/components/`](src/components/)                              |
| Feature folders      | [`src/features/`](src/features/)                                  |

## Adding a new screen

Mirror an existing screen in `src/features/<area>/containers/`. Then:

1. Add `ROUTE_*` in `src/navigators/routeNames.ts`.
2. Add the screen to the matching `*ParamList` in `src/navigators/paramLists.ts`.
3. Register `<Stack.Screen … />` in the right navigator (Home / Explain / Settings / Root).
4. Use typed `RouteProp<ParamList, 'Name'>` and `NativeStackNavigationProp<ParamList, 'Name'>`.
5. `yarn ts-check && yarn lint` before committing.

## File layout

```
parking-sign-detector-frontend/
├── App.tsx                       Redux Provider + NavigationContainer
├── app.json                      Expo config + plugins
├── babel.config.js               module-resolver + reanimated
├── tsconfig.json                 path aliases
├── package.json
├── eslint.config.js
├── prettier.config.js
├── docs/
│   ├── requirements.md           product spec — read first
│   └── ai/                       conventions inherited from existing codebase
└── src/
    ├── components/               App* primitives (AppText, AppLoader, BlockButton, ScreenContainer)
    ├── features/
    │   ├── parkingSearch/        F2 — sign detection at any address
    │   ├── signExplainer/        F3 — explain a sign from a photo
    │   ├── settings/             prefs + debug
    │   └── onboarding/           first-launch disclaimer modal
    ├── hooks/                    shared hooks
    ├── navigators/
    │   ├── RootNavigator.tsx
    │   ├── MainTabNavigator.tsx
    │   ├── HomeStackNavigator.tsx
    │   ├── ExplainStackNavigator.tsx
    │   ├── SettingsStackNavigator.tsx
    │   ├── routeNames.ts
    │   ├── paramLists.ts
    │   └── navigationOptions/defaultStackOptions.tsx
    ├── store/
    │   ├── index.ts              configureStore + typed hooks
    │   ├── api/parkingSignsApi.ts        RTK Query against ../parking-detector
    │   ├── api/melbourneOpenDataApi.ts   RTK Query against City of Melbourne open data
    │   └── slices/
    │       ├── searchHistorySlice.ts
    │       └── preferencesSlice.ts
    └── utils/
        ├── theme.ts              colours, fonts, spacing tokens
        └── config.ts             runtime config (API_BASE_URL etc.)
```

## Roadmap (next up)

- [ ] Map view on Find tab — overlay Melbourne bays + sign pins.
- [ ] Address autocomplete via backend `/places/autocomplete` proxy.
- [ ] Backend `POST /parse-sign` (then enable F3 happy path).
- [ ] Time-of-day rule parser (interpret `2P MON-FRI 8:30-18:30` for the current moment).
- [ ] Show first-launch disclaimer modal automatically when `disclaimerAcknowledged` is `false`.
- [ ] Persistence layer for `searchHistory` + `preferences` via AsyncStorage.
- [ ] Empty / error states polished per `docs/ai/examples/`.

## Contributing rules

- One main component per file (`docs/ai/rules/rules.md` enforces this).
- No raw colour literals in JSX — use `theme.colors.*`.
- No inline styles — use `StyleSheet.create` (sorted ascending, ESLint enforces).
- Use `AppText`, not raw `Text`, for product UI.
- Path aliases over relative imports for anything under `src/`.
- `yarn validate` clean before committing.
