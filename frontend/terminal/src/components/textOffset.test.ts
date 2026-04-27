import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clampOffsetToGraphemeBoundary,
  displayIndexToOffset,
  insertAtOffset,
  moveOffsetByGrapheme,
  offsetToDisplayIndex,
  removeBackwardGraphemes,
  removeForwardGraphemes,
} from './textOffset.js';

test('moves cursor by grapheme boundaries for emoji and cjk text', () => {
  const value = `A👩‍💻中B`;

  assert.equal(moveOffsetByGrapheme(value, value.length, -1), 7);
  assert.equal(moveOffsetByGrapheme(value, value.length, -2), 6);
  assert.equal(moveOffsetByGrapheme(value, value.length, -3), 1);
  assert.equal(moveOffsetByGrapheme(value, 1, 1), 6);
});

test('inserts text at a grapheme boundary even when offset is inside an emoji', () => {
  const value = '👩‍💻';
  const insertion = insertAtOffset(value, 2, 'a');

  assert.equal(insertion.nextValue, 'a👩‍💻');
  assert.equal(insertion.nextOffset, 1);
  assert.equal(insertion.changed, true);
});

test('removes whole graphemes for backward and forward deletion', () => {
  const value = '👩‍💻中a';

  const backward = removeBackwardGraphemes(value, value.length, 2);
  assert.equal(backward.nextValue, '👩‍💻');
  assert.equal(backward.nextOffset, 5);

  const forward = removeForwardGraphemes(value, 0, 2);
  assert.equal(forward.nextValue, 'a');
  assert.equal(forward.nextOffset, 0);
});

test('converts display index and string offset consistently', () => {
  const value = 'x👩‍💻y';

  assert.equal(displayIndexToOffset(value, 0), 0);
  assert.equal(displayIndexToOffset(value, 1), 1);
  assert.equal(displayIndexToOffset(value, 2), 6);
  assert.equal(displayIndexToOffset(value, 3), 7);

  assert.equal(offsetToDisplayIndex(value, 0), 0);
  assert.equal(offsetToDisplayIndex(value, 1), 1);
  assert.equal(offsetToDisplayIndex(value, 6), 2);
  assert.equal(offsetToDisplayIndex(value, 7), 3);
});

test('clamps offsets to nearest grapheme boundary', () => {
  const value = '👩‍💻z';

  assert.equal(clampOffsetToGraphemeBoundary(value, 2, 'backward'), 0);
  assert.equal(clampOffsetToGraphemeBoundary(value, 2, 'forward'), 5);
});
