import assert from 'node:assert/strict';
import test from 'node:test';

import {
  INK_VERSION,
  InkApp,
  InkOutputConstructor,
  createInkContainer,
  createInkLogRenderer,
  createInkRootNode,
  inkGetMaxWidth,
  inkRenderBorder,
  inkSquashTextNodes,
  inkWrapText,
  updateInkContainer,
} from './inkInternalsAdapter.js';

test('ink internals adapter validates and exposes required internals', () => {
  assert.ok(INK_VERSION.length > 0);
  assert.equal(typeof InkApp, 'function');
  assert.equal(typeof InkOutputConstructor, 'function');
  assert.equal(typeof createInkRootNode, 'function');
  assert.equal(typeof createInkContainer, 'function');
  assert.equal(typeof updateInkContainer, 'function');
  assert.equal(typeof createInkLogRenderer, 'function');
  assert.equal(typeof inkWrapText, 'function');
  assert.equal(typeof inkGetMaxWidth, 'function');
  assert.equal(typeof inkSquashTextNodes, 'function');
  assert.equal(typeof inkRenderBorder, 'function');
});
