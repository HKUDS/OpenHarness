import assert from 'node:assert/strict';
import test from 'node:test';

import {getBackspaceDeleteCount} from './PromptInput.js';

test('counts repeated backspace control characters from a single input chunk', () => {
	assert.equal(getBackspaceDeleteCount('\b\b\b'), 3);
	assert.equal(getBackspaceDeleteCount('\u007f\u007f'), 2);
	assert.equal(getBackspaceDeleteCount('\x7f\x7f\x7f'), 3);
});

test('falls back to a single delete for empty or unexpected input', () => {
	assert.equal(getBackspaceDeleteCount(''), 1);
	assert.equal(getBackspaceDeleteCount('abc'), 1);
	assert.equal(getBackspaceDeleteCount('\bA'), 1);
});
