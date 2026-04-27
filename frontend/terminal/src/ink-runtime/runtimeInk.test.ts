import assert from 'node:assert/strict';
import test from 'node:test';

import {flushAndParkFrame} from './runtimeInk.js';

type FakeStdout = NodeJS.WriteStream & {
  writes: string[];
};

type FakeLog = ((output: string) => void) & {
  clear: () => void;
  done: () => void;
};

function createStdout(): FakeStdout {
  const writes: string[] = [];
  return {
    isTTY: true,
    columns: 120,
    rows: 40,
    write(data: string): boolean {
      writes.push(`STDOUT:${String(data)}`);
      return true;
    },
    writes,
  } as FakeStdout;
}

function createLog(writes: string[]): FakeLog {
  const log = ((output: string) => {
    writes.push(`LOG:${output}`);
  }) as FakeLog;

  log.clear = () => {
    writes.push('CLEAR');
  };

  log.done = () => {
    writes.push('DONE');
  };

  return log;
}

test('flushAndParkFrame parks cursor after normal frame writes', () => {
  const stdout = createStdout();
  const log = createLog(stdout.writes);

  const next = flushAndParkFrame({
    stdout,
    frame: {output: 'hello', outputHeight: 1, staticOutput: ''},
    state: {fullStaticOutput: '', lastOutput: ''},
    log,
    debug: false,
    inCi: false,
    parkCursor: () => {
      stdout.writes.push('PARK');
    },
  });

  assert.deepEqual(stdout.writes, ['LOG:hello', 'PARK']);
  assert.deepEqual(next, {fullStaticOutput: '', lastOutput: 'hello'});
});

test('flushAndParkFrame still parks when output is unchanged', () => {
  const stdout = createStdout();
  const log = createLog(stdout.writes);

  const next = flushAndParkFrame({
    stdout,
    frame: {output: 'same', outputHeight: 1, staticOutput: ''},
    state: {fullStaticOutput: '', lastOutput: 'same'},
    log,
    debug: false,
    inCi: false,
    parkCursor: () => {
      stdout.writes.push('PARK');
    },
  });

  assert.deepEqual(stdout.writes, ['PARK']);
  assert.deepEqual(next, {fullStaticOutput: '', lastOutput: 'same'});
});

test('flushAndParkFrame handles staticOutput branch and parks last', () => {
  const stdout = createStdout();
  const log = createLog(stdout.writes);

  const next = flushAndParkFrame({
    stdout,
    frame: {output: 'interactive', outputHeight: 1, staticOutput: 'STATIC\n'},
    state: {fullStaticOutput: '', lastOutput: 'old'},
    log,
    debug: false,
    inCi: false,
    parkCursor: () => {
      stdout.writes.push('PARK');
    },
  });

  assert.deepEqual(stdout.writes, [
    'CLEAR',
    'STDOUT:STATIC\n',
    'LOG:interactive',
    'PARK',
  ]);
  assert.deepEqual(next, {fullStaticOutput: 'STATIC\n', lastOutput: 'interactive'});
});

test('flushAndParkFrame repaints absolute screen and clears stale shorter frames', () => {
  const stdout = createStdout();
  const log = createLog(stdout.writes);

  const next = flushAndParkFrame({
    stdout,
    frame: {output: 'input only', outputHeight: 1, staticOutput: ''},
    state: {fullStaticOutput: '', lastOutput: 'input only\n/help\n/exit'},
    log,
    debug: false,
    inCi: false,
    absoluteScreen: true,
    parkCursor: () => {
      stdout.writes.push('PARK');
    },
  });

  assert.deepEqual(stdout.writes, ['STDOUT:\u001b[Hinput only\u001b[J', 'PARK']);
  assert.deepEqual(next, {fullStaticOutput: '', lastOutput: 'input only'});
});

test('flushAndParkFrame skips parking in CI mode', () => {
  const stdout = createStdout();
  const log = createLog(stdout.writes);

  const next = flushAndParkFrame({
    stdout,
    frame: {output: 'ci', outputHeight: 1, staticOutput: 'STATIC\n'},
    state: {fullStaticOutput: '', lastOutput: ''},
    log,
    debug: false,
    inCi: true,
    parkCursor: () => {
      stdout.writes.push('PARK');
    },
  });

  assert.deepEqual(stdout.writes, ['STDOUT:STATIC\n']);
  assert.deepEqual(next, {fullStaticOutput: '', lastOutput: 'ci'});
});
