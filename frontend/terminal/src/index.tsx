import React from 'react';
import {render} from 'ink';

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

render(<App config={config} />);
