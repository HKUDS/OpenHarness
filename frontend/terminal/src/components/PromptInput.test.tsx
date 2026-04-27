import assert from 'node:assert/strict';
import test from 'node:test';
import {PassThrough} from 'node:stream';
import React, {useState} from 'react';
import {render} from 'ink';

import {clearDeclaredCursor, getDeclaredCursor} from '../ink-runtime/cursorStore.js';
import {ThemeProvider} from '../theme/ThemeContext.js';
import {PromptInput} from './PromptInput.js';

const nextLoopTurn = (): Promise<void> => new Promise((resolve) => setImmediate(resolve));

type InkTestStdout = PassThrough & {
	isTTY: boolean;
	columns: number;
	rows: number;
	cursorTo: () => boolean;
	clearLine: () => boolean;
	moveCursor: () => boolean;
};

type InkTestStdin = PassThrough & {
	isTTY: boolean;
	setRawMode: (_mode: boolean) => void;
	resume: () => InkTestStdin;
	pause: () => InkTestStdin;
	ref: () => InkTestStdin;
	unref: () => InkTestStdin;
};

function createTestStdout(): InkTestStdout {
	return Object.assign(new PassThrough(), {
		isTTY: true,
		columns: 120,
		rows: 40,
		cursorTo: () => true,
		clearLine: () => true,
		moveCursor: () => true,
	});
}

function createTestStdin(): InkTestStdin {
	return Object.assign(new PassThrough(), {
		isTTY: true,
		setRawMode: () => undefined,
		resume() {
			return this;
		},
		pause() {
			return this;
		},
		ref() {
			return this;
		},
		unref() {
			return this;
		},
	});
}

async function sendKey(stdin: InkTestStdin, chunk: string | Buffer): Promise<void> {
	stdin.write(chunk);
	await nextLoopTurn();
	await nextLoopTurn();
}

async function waitForValue(getValue: () => string, expected: string): Promise<void> {
	for (let i = 0; i < 50; i += 1) {
		await nextLoopTurn();
		if (getValue() === expected) {
			return;
		}
	}

	assert.equal(getValue(), expected);
}

async function waitForCursorColumn(expectedColumn: number): Promise<void> {
	for (let i = 0; i < 50; i += 1) {
		await nextLoopTurn();
		if (getDeclaredCursor()?.relativeX === expectedColumn) {
			return;
		}
	}

	assert.equal(getDeclaredCursor()?.relativeX, expectedColumn);
}

function PromptHarness({onInputChange}: {onInputChange: (value: string) => void}): React.JSX.Element {
	const [input, setInput] = useState('');

	return (
		<ThemeProvider initialTheme="default">
			<PromptInput
				busy={false}
				input={input}
				setInput={(value) => {
					onInputChange(value);
					setInput(value);
				}}
				onSubmit={() => undefined}
			/>
		</ThemeProvider>
	);
}

test('treats terminal DEL at end-of-line as backward delete', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, 'a');
		await waitForValue(() => currentValue, 'a');
		await waitForCursorColumn(3);

		await sendKey(stdin, 'b');
		await waitForValue(() => currentValue, 'ab');
		await waitForCursorColumn(4);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, 'a');
		await waitForCursorColumn(3);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('keeps forward delete behavior when cursor is inside the line', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, 'a');
		await waitForValue(() => currentValue, 'a');
		await waitForCursorColumn(3);

		await sendKey(stdin, 'b');
		await waitForValue(() => currentValue, 'ab');
		await waitForCursorColumn(4);

		await sendKey(stdin, '\u001B[D');
		await nextLoopTurn();
		await waitForCursorColumn(3);

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, 'a');
		await waitForCursorColumn(3);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('does not let stale backspace raw sequence override next forward delete', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, 'abc');
		await waitForValue(() => currentValue, 'abc');
		await waitForCursorColumn(5);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, 'ab');
		await waitForCursorColumn(4);

		await sendKey(stdin, '\u001B[D');
		await waitForCursorColumn(3);

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, 'a');
		await waitForCursorColumn(3);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('treats raw delete at start-of-line as forward delete', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, '你好你好');
		await waitForValue(() => currentValue, '你好你好');
		await waitForCursorColumn(10);

		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, '\u001B[D');
		await waitForCursorColumn(2);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, '好你好');
		await waitForCursorColumn(2);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, '你好');
		await waitForCursorColumn(2);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('keeps cursor alignment for chinese input and horizontal movement', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, '你好');
		await waitForValue(() => currentValue, '你好');
		await waitForCursorColumn(6);

		await sendKey(stdin, '\u001B[D');
		await waitForCursorColumn(4);

		await sendKey(stdin, '\u001B[C');
		await waitForCursorColumn(6);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('parks cursor after slash immediately when command picker input starts', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	const stdoutChunks: string[] = [];
	stdout.on('data', (chunk: Buffer) => {
		stdoutChunks.push(chunk.toString('utf8'));
	});
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		stdin.write('/');
		await nextLoopTurn();
		await waitForValue(() => currentValue, '/');
		assert.equal(getDeclaredCursor()?.relativeX, 3);
		assert.doesNotMatch(stdoutChunks.join(''), /\u001B\[7m \u001B\[27m/);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('backspaces slash plus chinese content without leaving residual characters', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, '/好');
		await waitForValue(() => currentValue, '/好');
		await waitForCursorColumn(5);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, '/');
		await waitForCursorColumn(3);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, '');
		await waitForCursorColumn(2);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('clears slash plus chinese content without leaving residual characters', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	const stdoutChunks: string[] = [];
	stdout.on('data', (chunk: Buffer) => {
		stdoutChunks.push(chunk.toString('utf8'));
	});
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, '/');
		await waitForValue(() => currentValue, '/');
		await waitForCursorColumn(3);

		await sendKey(stdin, '你好');
		await waitForValue(() => currentValue, '/你好');
		await waitForCursorColumn(7);

		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, '\u001B[D');
		await waitForCursorColumn(2);
		assert.match(stdoutChunks.at(-1) ?? '', /❯ \/你好/);
		assert.doesNotMatch(stdoutChunks.at(-1) ?? '', /❯  \/你好/);

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, '你好');
		await waitForCursorColumn(2);
		assert.match(stdoutChunks.at(-1) ?? '', /❯ 你好/);
		assert.doesNotMatch(stdoutChunks.at(-1) ?? '', /❯  你好/);

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, '好');
		await waitForCursorColumn(2);
		assert.match(stdoutChunks.at(-1) ?? '', /❯ 好/);
		assert.doesNotMatch(stdoutChunks.at(-1) ?? '', /❯  好/);

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, '');
		await waitForCursorColumn(2);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});

test('keeps grapheme-safe movement and delete behavior for emoji input', async () => {
	clearDeclaredCursor();
	const stdin = createTestStdin();
	const stdout = createTestStdout();
	let currentValue = '';

	const instance = render(<PromptHarness onInputChange={(value) => {
		currentValue = value;
	}} />, {
		stdin: stdin as unknown as NodeJS.ReadStream & {fd: 0},
		stdout: stdout as unknown as NodeJS.WriteStream,
		debug: true,
		patchConsole: false,
	});
	const exitPromise = instance.waitUntilExit();

	try {
		await nextLoopTurn();
		await waitForCursorColumn(2);

		await sendKey(stdin, '👩‍💻');
		await waitForValue(() => currentValue, '👩‍💻');
		await waitForCursorColumn(6);

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, '');
		await waitForCursorColumn(2);

		await sendKey(stdin, '👩‍💻');
		await waitForValue(() => currentValue, '👩‍💻');

		await sendKey(stdin, '\u001B[D');
		await sendKey(stdin, 'a');
		await waitForValue(() => currentValue, 'a👩‍💻');
		await waitForCursorColumn(3);
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
		clearDeclaredCursor();
	}
});
