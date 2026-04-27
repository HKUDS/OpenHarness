import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

import type React from 'react';

import reconcilerInternal from '../../node_modules/ink/build/reconciler.js';
import * as domInternal from '../../node_modules/ink/build/dom.js';
import logUpdateInternal from '../../node_modules/ink/build/log-update.js';
import AppInternal from '../../node_modules/ink/build/components/App.js';
import OutputInternal from '../../node_modules/ink/build/output.js';
import wrapTextInternal from '../../node_modules/ink/build/wrap-text.js';
import getMaxWidthInternal from '../../node_modules/ink/build/get-max-width.js';
import squashTextNodesInternal from '../../node_modules/ink/build/squash-text-nodes.js';
import renderBorderInternal from '../../node_modules/ink/build/render-border.js';

const require = createRequire(import.meta.url);
const inkEntryPath = require.resolve('ink');
const inkPackagePath = path.resolve(path.dirname(inkEntryPath), '..', 'package.json');
const inkPackageJson = fs.existsSync(inkPackagePath)
  ? JSON.parse(fs.readFileSync(inkPackagePath, 'utf8')) as {version?: string}
  : {};

export const INK_VERSION = String(inkPackageJson.version ?? 'unknown');

function assertInternal(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(`[ink-runtime] ${message} (ink=${INK_VERSION})`);
  }
}

if (INK_VERSION !== 'unknown' && !INK_VERSION.startsWith('5.')) {
  throw new Error(
    `[ink-runtime] Unsupported Ink version "${INK_VERSION}". Expected ink 5.x internals.`,
  );
}

type ReconcilerInternals = {
  createContainer: (...args: unknown[]) => unknown;
  updateContainer: (...args: unknown[]) => void;
};

type InkDomInternals = {
  createNode: (nodeName: string) => InkRootNode;
};

type LogUpdateInternals = {
  create: (
    stdout: NodeJS.WriteStream,
    options: {showCursor: boolean},
  ) => InkLogRenderer;
};

type OutputInternals = new (options: {width: number; height: number}) => InkOutput;

export type InkRootNode = {
  nodeName: string;
  yogaNode?: {
    setWidth: (width: number) => void;
    calculateLayout: (width?: number, height?: number, direction?: number) => void;
    getComputedWidth: () => number;
    getComputedHeight: () => number;
  };
  staticNode?: InkRootNode;
  onComputeLayout?: () => void;
  onRender?: () => void;
  onImmediateRender?: () => void;
};

export type InkLogRenderer = ((output: string) => void) & {
  clear: () => void;
  done: () => void;
};

export type InkOutput = {
  get: () => {output: string; height: number};
  write: (
    x: number,
    y: number,
    text: string,
    options: {transformers: Array<(value: string) => string>},
  ) => void;
  clip: (clip: {x1?: number; x2?: number; y1?: number; y2?: number}) => void;
  unclip: () => void;
};

const reconciler = reconcilerInternal as unknown as Partial<ReconcilerInternals>;
assertInternal(typeof reconciler.createContainer === 'function', 'Missing reconciler.createContainer');
assertInternal(typeof reconciler.updateContainer === 'function', 'Missing reconciler.updateContainer');

const dom = domInternal as unknown as Partial<InkDomInternals>;
assertInternal(typeof dom.createNode === 'function', 'Missing dom.createNode');

const logUpdate = logUpdateInternal as unknown as Partial<LogUpdateInternals>;
assertInternal(typeof logUpdate.create === 'function', 'Missing logUpdate.create');

const OutputConstructor = OutputInternal as unknown as OutputInternals;
assertInternal(typeof OutputConstructor === 'function', 'Missing Output constructor');

const wrapText = wrapTextInternal as unknown as ((text: string, width: number, mode: string) => string);
const getMaxWidth = getMaxWidthInternal as unknown as ((node: unknown) => number);
const squashTextNodes = squashTextNodesInternal as unknown as ((node: unknown) => string);
const renderBorder = renderBorderInternal as unknown as (
  x: number,
  y: number,
  node: unknown,
  output: unknown,
) => void;

assertInternal(typeof wrapText === 'function', 'Missing wrap-text export');
assertInternal(typeof getMaxWidth === 'function', 'Missing get-max-width export');
assertInternal(typeof squashTextNodes === 'function', 'Missing squash-text-nodes export');
assertInternal(typeof renderBorder === 'function', 'Missing render-border export');
assertInternal(Boolean(AppInternal), 'Missing App component export');

const noop = (): void => {};

export const InkApp = AppInternal as React.ComponentType<Record<string, unknown>>;
export const InkOutputConstructor = OutputConstructor;
export const inkWrapText = wrapText;
export const inkGetMaxWidth = getMaxWidth;
export const inkSquashTextNodes = squashTextNodes;
export const inkRenderBorder = renderBorder;

export function createInkRootNode(): InkRootNode {
  return dom.createNode!('ink-root');
}

export function createInkContainer(rootNode: InkRootNode): unknown {
  return reconciler.createContainer!(
    rootNode,
    0,
    null,
    false,
    null,
    'id',
    noop,
    null,
  );
}

export function updateInkContainer(container: unknown, node: React.ReactNode | null): void {
  reconciler.updateContainer!(node, container, null, noop);
}

export function createInkLogRenderer(stdout: NodeJS.WriteStream): InkLogRenderer {
  return logUpdate.create!(stdout, {showCursor: true});
}
