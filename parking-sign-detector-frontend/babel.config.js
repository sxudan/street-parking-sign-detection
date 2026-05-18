module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      [
        'module-resolver',
        {
          root: ['./'],
          alias: {
            '@components': './src/components',
            '@containers': './src/containers',
            '@features': './src/features',
            '@hooks': './src/hooks',
            '@navigators': './src/navigators',
            '@store': './src/store',
            '@utils': './src/utils',
            '@assets': './assets',
          },
          extensions: ['.ts', '.tsx', '.js', '.jsx', '.json'],
        },
      ],
      // react-native-reanimated/plugin must be listed last.
      'react-native-reanimated/plugin',
    ],
  };
};
