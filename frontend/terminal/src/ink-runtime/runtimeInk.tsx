import process from 'node:process';

import React from 'react';
import ansiEscapes from 'ansi-escapes';
import isInCi from 'is-in-ci';
import autoBind from 'auto-bind';
import patchConsole from 'patch-console';
import Yoga from 'yoga-layout';

import {getDeclaredCursor} from './cursorStore.js';
import {
  InkApp,
  createInkContainer,
  createInkLogRenderer,
  createInkRootNode,
  type InkLogRenderer,
  type InkRootNode,
  updateInkContainer,
} from './inkInternalsAdapter.js';
import {parkNativeCursor} from './parkNativeCursor.js';
import {renderWithAnchors} from './rendererWithAnchors.js';
import type {AnchorRect} from './cursorTypes.js';

type RuntimeInkOptions = {
  stdout: NodeJS.WriteStream;
  stdin: NodeJS.ReadStream;
  stderr: NodeJS.WriteStream;
  debug: boolean;
  exitOnCtrlC: boolean;
  patchConsole: boolean;
};

type RuntimeFrame = {
  output: string;
  outputHeight: number;
  staticOutput: string;
};

type RuntimeState = {
  fullStaticOutput: string;
  lastOutput: string;
};

const CURSOR_HOME = '\u001b[H';
const CLEAR_TO_SCREEN_END = '\u001b[J';
const CLEAR_LINE = '\u001b[2K';
const CURSOR_BAR = '\u001b[6 q';
const CURSOR_DEFAULT = '\u001b[0 q';

function renderAbsoluteFrame(frame: string): string {
  const normalized = frame.endsWith('\n') ? frame.slice(0, -1) : frame;
  const lines = normalized.length > 0 ? normalized.split('\n') : [''];

  let output = CURSOR_BAR;

  for (let index = 0; index < lines.length; index += 1) {
    output += `\u001b[${index + 1};1H${CLEAR_LINE}${lines[index]}`;
  }

  output += `\u001b[${lines.length + 1};1H${CLEAR_TO_SCREEN_END}`;

  return output;
}

export function flushAndParkFrame(options: {
  stdout: NodeJS.WriteStream;
  frame: RuntimeFrame;
  state: RuntimeState;
  log: InkLogRenderer;
  debug: boolean;
  inCi: boolean;
  absoluteScreen?: boolean;
  parkCursor: () => void;
}): RuntimeState {
  const {
    stdout,
    frame,
    state,
    log,
    debug,
    inCi,
    absoluteScreen = false,
    parkCursor,
  } = options;

  const {output, outputHeight, staticOutput} = frame;
  let {fullStaticOutput, lastOutput} = state;
  const hasStaticOutput = Boolean(staticOutput && staticOutput !== '\n');

  if (debug) {
    if (hasStaticOutput) {
      fullStaticOutput += staticOutput;
    }

    stdout.write(fullStaticOutput + output);
    lastOutput = output;
    parkCursor();

    return {fullStaticOutput, lastOutput};
  }

  if (inCi) {
    if (hasStaticOutput) {
      stdout.write(staticOutput);
    }

    lastOutput = output;
    return {fullStaticOutput, lastOutput};
  }

  if (hasStaticOutput) {
    fullStaticOutput += staticOutput;
  }

  if (absoluteScreen) {
    stdout.write(renderAbsoluteFrame(fullStaticOutput + output));
    lastOutput = output;
    parkCursor();

    return {fullStaticOutput, lastOutput};
  }

  if (outputHeight >= (stdout.rows || Number.MAX_SAFE_INTEGER)) {
    stdout.write(ansiEscapes.clearTerminal + fullStaticOutput + output);
    lastOutput = output;
    parkCursor();

    return {fullStaticOutput, lastOutput};
  }

  if (hasStaticOutput) {
    log.clear();
    stdout.write(staticOutput);
    log(output);
  } else if (output !== lastOutput) {
    log(output);
  }

  lastOutput = output;
  parkCursor();

  return {fullStaticOutput, lastOutput};
}

export default class RuntimeInk {
  options: RuntimeInkOptions;
  log: InkLogRenderer;
  isUnmounted: boolean;
  lastOutput: string;
  fullStaticOutput: string;
  container: unknown;
  rootNode: InkRootNode;
  restoreConsole: undefined | (() => void);
  unsubscribeResize: undefined | (() => void);
  unsubscribeExit: () => void;
  exitPromise?: Promise<void>;
  resolveExitPromise: () => void;
  rejectExitPromise: (error: Error) => void;
  lastAnchorRects: Map<string, AnchorRect>;

  constructor(options: RuntimeInkOptions) {
    autoBind(this);

    this.options = options;
    this.rootNode = createInkRootNode();
    this.rootNode.onComputeLayout = this.calculateLayout;
    this.rootNode.onRender = this.onRender;
    this.rootNode.onImmediateRender = this.onRender;

    // Keep native cursor visible; IME pre-edit uses the real terminal cursor.
    this.log = createInkLogRenderer(options.stdout);

    this.isUnmounted = false;
    this.lastOutput = '';
    this.fullStaticOutput = '';
    this.lastAnchorRects = new Map<string, AnchorRect>();

    this.container = createInkContainer(this.rootNode);

    const handleProcessExit = (): void => {
      this.unmount();
    };
    process.once('exit', handleProcessExit);
    this.unsubscribeExit = () => {
      process.off('exit', handleProcessExit);
    };

    if (options.patchConsole) {
      this.patchConsole();
    }

    if (!isInCi) {
      options.stdout.on('resize', this.resized);
      this.unsubscribeResize = () => {
        options.stdout.off('resize', this.resized);
      };
    }

    this.resolveExitPromise = () => {};
    this.rejectExitPromise = () => {};
  }

  resized = (): void => {
    this.calculateLayout();
    this.onRender();
  };

  calculateLayout = (): void => {
    const terminalWidth = this.options.stdout.columns || 80;
    this.rootNode.yogaNode?.setWidth(terminalWidth);
    this.rootNode.yogaNode?.calculateLayout(undefined, undefined, Yoga.DIRECTION_LTR);
  };

  private parkCursor = (): void => {
    parkNativeCursor({
      stdout: this.options.stdout,
      anchorRects: this.lastAnchorRects,
      declaredCursor: getDeclaredCursor(),
    });
  };

  private shouldUseAbsoluteScreen = (): boolean => {
    return Boolean(
      this.options.stdout.isTTY
      && process.env.OPENHARNESS_DISABLE_ALTERNATE_SCREEN !== '1',
    );
  };

  onRender = (): void => {
    if (this.isUnmounted) {
      return;
    }

    const frame = renderWithAnchors(this.rootNode as never);
    this.lastAnchorRects = frame.anchorRects;

    const nextState = flushAndParkFrame({
      stdout: this.options.stdout,
      frame,
      state: {
        fullStaticOutput: this.fullStaticOutput,
        lastOutput: this.lastOutput,
      },
      log: this.log,
      debug: this.options.debug,
      inCi: isInCi,
      absoluteScreen: this.shouldUseAbsoluteScreen(),
      parkCursor: this.parkCursor,
    });

    this.fullStaticOutput = nextState.fullStaticOutput;
    this.lastOutput = nextState.lastOutput;
  };

  render(node: React.ReactNode): void {
    const tree = (
      <InkApp
        stdin={this.options.stdin}
        stdout={this.options.stdout}
        stderr={this.options.stderr}
        writeToStdout={this.writeToStdout}
        writeToStderr={this.writeToStderr}
        exitOnCtrlC={this.options.exitOnCtrlC}
        onExit={this.unmount}
      >
        {node}
      </InkApp>
    );

    updateInkContainer(this.container, tree);
  }

  writeToStdout(data: string): void {
    if (this.isUnmounted) {
      return;
    }

    if (this.options.debug) {
      this.options.stdout.write(data + this.fullStaticOutput + this.lastOutput);
      this.parkCursor();
      return;
    }

    if (isInCi) {
      this.options.stdout.write(data);
      return;
    }

    if (this.shouldUseAbsoluteScreen()) {
      this.options.stdout.write(
        renderAbsoluteFrame(data + this.fullStaticOutput + this.lastOutput),
      );
      this.parkCursor();
      return;
    }

    this.log.clear();
    this.options.stdout.write(data);
    this.log(this.lastOutput);
    this.parkCursor();
  }

  writeToStderr(data: string): void {
    if (this.isUnmounted) {
      return;
    }

    if (this.options.debug) {
      this.options.stderr.write(data);
      this.options.stdout.write(this.fullStaticOutput + this.lastOutput);
      this.parkCursor();
      return;
    }

    if (isInCi) {
      this.options.stderr.write(data);
      return;
    }

    if (this.shouldUseAbsoluteScreen()) {
      this.options.stderr.write(data);
      this.options.stdout.write(
        renderAbsoluteFrame(this.fullStaticOutput + this.lastOutput),
      );
      this.parkCursor();
      return;
    }

    this.log.clear();
    this.options.stderr.write(data);
    this.log(this.lastOutput);
    this.parkCursor();
  }

  unmount(error?: unknown): void {
    if (this.isUnmounted) {
      return;
    }

    this.calculateLayout();
    this.onRender();

    this.unsubscribeExit();

    if (typeof this.restoreConsole === 'function') {
      this.restoreConsole();
    }

    if (typeof this.unsubscribeResize === 'function') {
      this.unsubscribeResize();
    }

    if (this.options.stdout.isTTY) {
      this.options.stdout.write(CURSOR_DEFAULT);
    }

    if (isInCi) {
      this.options.stdout.write(this.lastOutput + '\n');
    } else if (!this.options.debug) {
      this.log.done();
    }

    this.isUnmounted = true;
    updateInkContainer(this.container, null);

    if (error instanceof Error) {
      this.rejectExitPromise(error);
      return;
    }

    this.resolveExitPromise();
  }

  async waitUntilExit(): Promise<void> {
    this.exitPromise ??= new Promise((resolve, reject) => {
      this.resolveExitPromise = resolve;
      this.rejectExitPromise = reject;
    });

    return this.exitPromise;
  }

  clear(): void {
    if (this.shouldUseAbsoluteScreen()) {
      this.options.stdout.write(CURSOR_HOME + CLEAR_TO_SCREEN_END);
      return;
    }

    if (!isInCi && !this.options.debug) {
      this.log.clear();
    }
  }

  patchConsole(): void {
    if (this.options.debug) {
      return;
    }

    this.restoreConsole = patchConsole((stream, data) => {
      if (stream === 'stdout') {
        this.writeToStdout(data);
      }

      if (stream === 'stderr') {
        const isReactMessage = data.startsWith('The above error occurred');
        if (!isReactMessage) {
          this.writeToStderr(data);
        }
      }
    });
  }
}
