import assert from 'node:assert/strict';
import test from 'node:test';

import {parkNativeCursor} from './parkNativeCursor.js';
import type {DeclaredCursor} from './cursorTypes.js';

type FakeStdout = NodeJS.WriteStream & {
  chunks: string[];
};

function createStdout(isTTY: boolean): FakeStdout {
  const chunks: string[] = [];
  return {
    isTTY,
    columns: 120,
    rows: 40,
    write(data: string): boolean {
      chunks.push(String(data));
      return true;
    },
    chunks,
  } as FakeStdout;
}

test('parks native cursor at anchor-relative coordinates', () => {
  const stdout = createStdout(true);
  const declaredCursor: DeclaredCursor = {
    anchorId: 'prompt-input-anchor',
    relativeX: 4,
    relativeY: 2,
    active: true,
  };

  parkNativeCursor({
    stdout,
    anchorRects: new Map([
      ['prompt-input-anchor', {x: 10, y: 3, width: 40, height: 1}],
    ]),
    declaredCursor,
  });

  assert.deepEqual(stdout.chunks, ['\u001b[?25h\u001b[6;15H']);
});

test('skips cursor parking when stdout is not a TTY', () => {
  const stdout = createStdout(false);
  const declaredCursor: DeclaredCursor = {
    anchorId: 'prompt-input-anchor',
    relativeX: 1,
    relativeY: 0,
    active: true,
  };

  parkNativeCursor({
    stdout,
    anchorRects: new Map([
      ['prompt-input-anchor', {x: 1, y: 1, width: 10, height: 1}],
    ]),
    declaredCursor,
  });

  assert.deepEqual(stdout.chunks, []);
});

test('clamps cursor coordinates inside terminal viewport', () => {
  const stdout = createStdout(true);
  stdout.columns = 5;
  stdout.rows = 3;

  const declaredCursor: DeclaredCursor = {
    anchorId: 'prompt-input-anchor',
    relativeX: 100,
    relativeY: 100,
    active: true,
  };

  parkNativeCursor({
    stdout,
    anchorRects: new Map([
      ['prompt-input-anchor', {x: 0, y: 0, width: 5, height: 1}],
    ]),
    declaredCursor,
  });

  assert.deepEqual(stdout.chunks, ['\u001b[?25h\u001b[3;5H']);
});
