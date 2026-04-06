import React from 'react';
import {render} from 'ink';
import fs from 'node:fs';
import tty from 'node:tty';

import {App} from './App.js';
import type {FrontendConfig} from './types.js';

const config = JSON.parse(process.env.OPENHARNESS_FRONTEND_CONFIG ?? '{}') as FrontendConfig;

// Restore terminal cursor visibility on exit (Ink hides it by default)
const restoreCursor = (): void => {
	process.stdout.write('\x1B[?25h');
};
process.on('exit', restoreCursor);
process.on('SIGINT', () => {
	restoreCursor();
	process.exit(130);
});
process.on('SIGTERM', () => {
	restoreCursor();
	process.exit(143);
});

// On WSL / Windows the process-spawning chain (npm exec → tsx → node) can
// lose the TTY on stdin, which prevents Ink's useInput from enabling raw mode.
// When that happens, open /dev/tty directly to get a real TTY stream.
let stdinStream: NodeJS.ReadStream & {fd: 0} = process.stdin;
let ttyFd: number | undefined;

if (!process.stdin.isTTY) {
	try {
		ttyFd = fs.openSync('/dev/tty', 'r');
		const ttyStream = new tty.ReadStream(ttyFd);
		// Cast is safe — tty.ReadStream is a full readable TTY stream
		stdinStream = ttyStream as unknown as NodeJS.ReadStream & {fd: 0};
	} catch {
		// /dev/tty unavailable (e.g. non-interactive CI) — fall back to process.stdin
	}
}

process.on('exit', () => {
	if (ttyFd !== undefined) {
		try { fs.closeSync(ttyFd); } catch { /* ignore */ }
	}
});

render(<App config={config} />, {stdin: stdinStream});
