const segmenterFactory = (Intl as unknown as {
  Segmenter?: new (
    locales?: string | string[],
    options?: {granularity: 'grapheme'},
  ) => {
    segment: (input: string) => Iterable<{index: number; segment: string}>;
  };
}).Segmenter;

const graphemeSegmenter = segmenterFactory
  ? new segmenterFactory(undefined, {granularity: 'grapheme'})
  : null;

export type TextOffsetMutation = {
  nextValue: string;
  nextOffset: number;
  changed: boolean;
};

function clampOffset(value: string, offset: number): number {
  if (!Number.isFinite(offset)) {
    return value.length;
  }

  return Math.max(0, Math.min(value.length, Math.floor(offset)));
}

function getCursorStops(value: string): number[] {
  const stops = [0];

  if (!value) {
    return stops;
  }

  if (graphemeSegmenter) {
    for (const token of graphemeSegmenter.segment(value)) {
      stops.push(token.index + token.segment.length);
    }
    return stops;
  }

  let index = 0;
  for (const char of value) {
    index += char.length;
    stops.push(index);
  }

  return stops;
}

function findStopIndex(stops: number[], offset: number, direction: 'backward' | 'forward'): number {
  if (direction === 'backward') {
    for (let index = stops.length - 1; index >= 0; index -= 1) {
      if (stops[index] <= offset) {
        return index;
      }
    }

    return 0;
  }

  for (let index = 0; index < stops.length; index += 1) {
    if (stops[index] >= offset) {
      return index;
    }
  }

  return stops.length - 1;
}

export function clampOffsetToGraphemeBoundary(
  value: string,
  offset: number,
  direction: 'backward' | 'forward' = 'backward',
): number {
  const safeOffset = clampOffset(value, offset);
  const stops = getCursorStops(value);
  return stops[findStopIndex(stops, safeOffset, direction)];
}

export function moveOffsetByGrapheme(value: string, offset: number, delta: number): number {
  if (delta === 0) {
    return clampOffsetToGraphemeBoundary(value, offset, 'backward');
  }

  const safeOffset = clampOffset(value, offset);
  const stops = getCursorStops(value);
  const direction = delta > 0 ? 'forward' : 'backward';
  const currentIndex = findStopIndex(stops, safeOffset, direction);
  const nextIndex = Math.max(0, Math.min(stops.length - 1, currentIndex + delta));
  return stops[nextIndex];
}

export function insertAtOffset(value: string, offset: number, text: string): TextOffsetMutation {
  if (!text) {
    const nextOffset = clampOffsetToGraphemeBoundary(value, offset, 'backward');
    return {nextValue: value, nextOffset, changed: false};
  }

  const insertionOffset = clampOffsetToGraphemeBoundary(value, offset, 'backward');
  const nextValue = value.slice(0, insertionOffset) + text + value.slice(insertionOffset);
  return {
    nextValue,
    nextOffset: insertionOffset + text.length,
    changed: true,
  };
}

export function removeBackwardGraphemes(value: string, offset: number, count: number): TextOffsetMutation {
  if (count <= 0) {
    const nextOffset = clampOffsetToGraphemeBoundary(value, offset, 'backward');
    return {nextValue: value, nextOffset, changed: false};
  }

  const end = clampOffsetToGraphemeBoundary(value, offset, 'backward');
  if (end === 0) {
    return {nextValue: value, nextOffset: 0, changed: false};
  }

  const start = moveOffsetByGrapheme(value, end, -count);
  if (start === end) {
    return {nextValue: value, nextOffset: end, changed: false};
  }

  return {
    nextValue: value.slice(0, start) + value.slice(end),
    nextOffset: start,
    changed: true,
  };
}

export function removeForwardGraphemes(value: string, offset: number, count: number): TextOffsetMutation {
  if (count <= 0) {
    const nextOffset = clampOffsetToGraphemeBoundary(value, offset, 'backward');
    return {nextValue: value, nextOffset, changed: false};
  }

  const start = clampOffsetToGraphemeBoundary(value, offset, 'backward');
  if (start >= value.length) {
    return {nextValue: value, nextOffset: start, changed: false};
  }

  const end = moveOffsetByGrapheme(value, start, count);
  if (end === start) {
    return {nextValue: value, nextOffset: start, changed: false};
  }

  return {
    nextValue: value.slice(0, start) + value.slice(end),
    nextOffset: start,
    changed: true,
  };
}

export function offsetToDisplayIndex(value: string, offset: number): number {
  const safeOffset = clampOffset(value, offset);
  const stops = getCursorStops(value);
  return findStopIndex(stops, safeOffset, 'backward');
}

export function displayIndexToOffset(value: string, index: number): number {
  const stops = getCursorStops(value);
  if (!Number.isFinite(index)) {
    return stops[stops.length - 1];
  }

  const safeIndex = Math.max(0, Math.min(stops.length - 1, Math.floor(index)));
  return stops[safeIndex];
}
