/**
 * Snap-paged horizontal carousel of parking-sign cards.
 *
 * Renders ONLY non-address ParkingOption entries (council bay, off-
 * street carpark, street parking). The address-preview lives in the
 * sibling AddressPreviewRow above this carousel.
 *
 * Bidirectional linking with the map: tapping a card or letting the
 * user swipe will animate the map to that location, and tapping a
 * marker scrolls the carousel to the matching card.
 */
import { ParkingOption } from '@store/types/parkingOption';
import theme from '@utils/theme';
import React, { FC, memo, useCallback, useEffect, useRef } from 'react';
import {
  Dimensions,
  FlatList,
  NativeScrollEvent,
  NativeSyntheticEvent,
  StyleSheet,
} from 'react-native';

import CarouselCard from './CarouselCard';

const SCREEN_WIDTH = Dimensions.get('window').width;
const CARD_GUTTER = theme.spacing.sm;
const CARD_WIDTH = SCREEN_WIDTH - theme.spacing.horizontalDefault * 2 - CARD_GUTTER * 2;
const SNAP_INTERVAL = CARD_WIDTH + CARD_GUTTER;

type Props = {
  options: ParkingOption[];
  selectedIndex: number;
  onChangeIndex: (index: number) => void;
  onCardPress: (index: number) => void;
};

const ResultsCarousel: FC<Props> = ({ options, selectedIndex, onChangeIndex, onCardPress }) => {
  const flatListRef = useRef<FlatList<ParkingOption>>(null);

  // External (marker tap) selection → scroll the carousel to match.
  useEffect(() => {
    if (options.length === 0) return;
    flatListRef.current?.scrollToIndex({
      index: Math.max(0, Math.min(selectedIndex, options.length - 1)),
      animated: true,
      viewPosition: 0,
    });
  }, [selectedIndex, options.length]);

  const handleMomentumEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const offset = e.nativeEvent.contentOffset.x;
      const next = Math.round(offset / SNAP_INTERVAL);
      const clamped = Math.max(0, Math.min(next, options.length - 1));
      if (clamped !== selectedIndex) {
        onChangeIndex(clamped);
      }
    },
    [options.length, selectedIndex, onChangeIndex],
  );

  const renderItem = useCallback(
    ({ item, index }: { item: ParkingOption; index: number }) => (
      <CarouselCard
        option={item}
        width={CARD_WIDTH}
        isSelected={index === selectedIndex}
        onPress={() => onCardPress(index)}
      />
    ),
    [selectedIndex, onCardPress],
  );

  const handleScrollFail = useCallback(
    ({ index, averageItemLength }: { index: number; averageItemLength: number }) => {
      flatListRef.current?.scrollToOffset({ offset: index * averageItemLength, animated: true });
    },
    [],
  );

  return (
    <FlatList
      ref={flatListRef}
      data={options}
      keyExtractor={(item) => item.id}
      renderItem={renderItem}
      horizontal
      showsHorizontalScrollIndicator={false}
      snapToInterval={SNAP_INTERVAL}
      snapToAlignment='start'
      decelerationRate='fast'
      onMomentumScrollEnd={handleMomentumEnd}
      onScrollToIndexFailed={handleScrollFail}
      contentContainerStyle={styles.content}
      style={styles.list}
      getItemLayout={(_, index) => ({
        length: SNAP_INTERVAL,
        offset: SNAP_INTERVAL * index,
        index,
      })}
    />
  );
};

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: theme.spacing.horizontalDefault,
  },
  list: { flexGrow: 0 },
});

export default memo(ResultsCarousel);
