import assert from 'node:assert/strict';
import test from 'node:test';
import {PassThrough} from 'node:stream';
import React, {useState} from 'react';
import {render} from 'ink';

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

		await sendKey(stdin, 'a');
		await waitForValue(() => currentValue, 'a');

		await sendKey(stdin, 'b');
		await waitForValue(() => currentValue, 'ab');

		await sendKey(stdin, Buffer.from([0x7f]));
		await waitForValue(() => currentValue, 'a');
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
	}
});

test('keeps forward delete behavior when cursor is inside the line', async () => {
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

		await sendKey(stdin, 'a');
		await waitForValue(() => currentValue, 'a');

		await sendKey(stdin, 'b');
		await waitForValue(() => currentValue, 'ab');

		await sendKey(stdin, '\u001B[D');
		await nextLoopTurn();

		await sendKey(stdin, '\u001B[3~');
		await waitForValue(() => currentValue, 'a');
	} finally {
		instance.unmount();
		await exitPromise;
		instance.cleanup();
		stdin.destroy();
		stdout.destroy();
	}
});
