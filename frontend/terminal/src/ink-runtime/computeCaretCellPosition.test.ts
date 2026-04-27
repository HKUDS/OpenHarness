import assert from 'node:assert/strict';
import test from 'node:test';

import {computeCaretCellPosition} from './computeCaretCellPosition.js';

test('computes caret column for simple ascii input', () => {
  assert.deepEqual(computeCaretCellPosition('hello', 5, 40), {line: 0, column: 5});
  assert.deepEqual(computeCaretCellPosition('hello', 2, 40), {line: 0, column: 2});
});

test('handles explicit newline boundaries', () => {
  assert.deepEqual(computeCaretCellPosition('ab\ncd', 3, 40), {line: 1, column: 0});
  assert.deepEqual(computeCaretCellPosition('ab\ncd', 5, 40), {line: 1, column: 2});
});

test('handles automatic wrapping at terminal width boundaries', () => {
  assert.deepEqual(computeCaretCellPosition('abcde', 5, 5), {line: 1, column: 0});
  assert.deepEqual(computeCaretCellPosition('abcdef', 6, 5), {line: 1, column: 1});
});

test('handles cjk and emoji cell widths', () => {
  assert.deepEqual(computeCaretCellPosition('中a', '中a'.length, 20), {line: 0, column: 3});
  assert.deepEqual(computeCaretCellPosition('🙂a', '🙂a'.length, 20), {line: 0, column: 3});
});

test('handles mixed cjk/emoji wrapping cases', () => {
  assert.deepEqual(computeCaretCellPosition('ab中', 'ab中'.length, 4), {line: 1, column: 0});
  assert.deepEqual(computeCaretCellPosition('ab中🙂x', 'ab中🙂x'.length, 4), {line: 1, column: 3});
});

test('clamps invalid offsets and columns safely', () => {
  assert.deepEqual(computeCaretCellPosition('abc', -1, 0), {line: 0, column: 0});
  assert.deepEqual(computeCaretCellPosition('abc', 100, Number.NaN), {line: 0, column: 3});
});
