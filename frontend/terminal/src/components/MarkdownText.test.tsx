import assert from 'node:assert/strict';
import test from 'node:test';
import {PassThrough} from 'node:stream';
import React from 'react';
import {render} from 'ink';

import {ThemeProvider} from '../theme/ThemeContext.js';
import {MarkdownText} from './MarkdownText.js';

const stripAnsi = (value: string): string => value.replace(/\u001B\[[0-9;?]*[ -/]*[@-~]/g, '');
const nextLoopTurn = (): Promise<void> => new Promise((resolve) => setImmediate(resolve));

type InkTestStdout = PassThrough & {
	isTTY: boolean;
	columns: number;
	rows: number;
	cursorTo: () => boolean;
	clearLine: () => boolean;
	moveCursor: () => boolean;
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

async function waitForOutputToStabilize(getOutput: () => string): Promise<string> {
	let previous = '';
	let sawOutput = false;

	for (let i = 0; i < 50; i++) {
		await nextLoopTurn();
		const current = getOutput();
		sawOutput ||= current.length > 0;
		if (sawOutput && current === previous) {
			return current;
		}

		previous = current;
	}

	throw new Error(`Ink output did not stabilize: ${JSON.stringify(previous)}`);
}

async function renderMarkdownLines(content: string): Promise<string[]> {
	const stdout = createTestStdout();

	let output = '';
	stdout.on('data', (chunk) => {
		output += chunk.toString();
	});

	const instance = render(
		<ThemeProvider initialTheme="default">
			<MarkdownText content={content} />
		</ThemeProvider>,
		{stdout: stdout as unknown as NodeJS.WriteStream, debug: true, patchConsole: false},
	);

	const exitPromise = instance.waitUntilExit();
	const stableOutput = await waitForOutputToStabilize(() => output);
	instance.unmount();
	await exitPromise;
	await waitForOutputToStabilize(() => output);
	instance.cleanup();

	return stripAnsi(stableOutput)
		.split('\n')
		.filter(Boolean);
}

async function renderTableLines(content: string): Promise<string[]> {
	return (await renderMarkdownLines(content))
		.filter((line) => /[┌├│└]/.test(line))
		.slice(0, 5);
}

test('keeps table borders aligned when cells contain inline markdown', async () => {
	const lines = await renderTableLines('| `aa` | bb |\n|------|----|\n| c | **ddd** |');

	assert.equal(lines.length, 5);

	const widths = lines.map((line) => [...line].length);
	assert.ok(
		widths.every((width) => width === widths[0]),
		`Expected table lines to share a width, got ${JSON.stringify(
			lines.map((line, index) => ({line, width: widths[index]})),
		)}`,
	);
});

test('renders unknown inline table tokens using the visible token text fallback', async () => {
	const lines = await renderTableLines('| ![alt](https://example.com/img.png) | ok |\n|---|---|\n| x | y |');

	assert.equal(lines.length, 5);
	assert.match(lines[1] ?? '', /\balt\b/);
	assert.doesNotMatch(lines[1] ?? '', /!\[alt\]/);

	const widths = lines.map((line) => [...line].length);
	assert.ok(
		widths.every((width) => width === widths[0]),
		`Expected fallback-token table lines to share a width, got ${JSON.stringify(
			lines.map((line, index) => ({line, width: widths[index]})),
		)}`,
	);
});

test('preserves nested markdown structure inside blockquotes', async () => {
	const lines = await renderMarkdownLines('> - first\n> - second');

	assert.ok(lines.some((line) => line.includes('• first')), `Expected blockquote output to include a rendered bullet: ${JSON.stringify(lines)}`);
	assert.ok(lines.some((line) => line.includes('• second')), `Expected blockquote output to include the second rendered bullet: ${JSON.stringify(lines)}`);
});
