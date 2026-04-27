import process from 'node:process';
import {Stream} from 'node:stream';

import type {ReactNode} from 'react';

import RuntimeInk from './runtimeInk.js';

export type RenderOptions = {
  stdout?: NodeJS.WriteStream;
  stdin?: NodeJS.ReadStream;
  stderr?: NodeJS.WriteStream;
  debug?: boolean;
  exitOnCtrlC?: boolean;
  patchConsole?: boolean;
};

export type Instance = {
  rerender: (node: ReactNode) => void;
  unmount: () => void;
  waitUntilExit: () => Promise<void>;
  cleanup: () => void;
  clear: () => void;
};

const instances = new Map<NodeJS.WriteStream, RuntimeInk>();

function getOptions(options?: NodeJS.WriteStream | RenderOptions): RenderOptions {
  if (options instanceof Stream) {
    return {
      stdout: options,
      stdin: process.stdin,
    };
  }

  return options ?? {};
}

function getInstance(stdout: NodeJS.WriteStream, createInstance: () => RuntimeInk): RuntimeInk {
  let instance = instances.get(stdout);
  if (!instance) {
    instance = createInstance();
    instances.set(stdout, instance);
  }

  return instance;
}

export function render(node: ReactNode, options?: NodeJS.WriteStream | RenderOptions): Instance {
  const inkOptions = {
    stdout: process.stdout,
    stdin: process.stdin,
    stderr: process.stderr,
    debug: false,
    exitOnCtrlC: true,
    patchConsole: true,
    ...getOptions(options),
  };

  const instance = getInstance(inkOptions.stdout, () => new RuntimeInk(inkOptions));
  instance.render(node);

  return {
    rerender: (nextNode) => instance.render(nextNode),
    unmount: () => {
      instance.unmount();
    },
    waitUntilExit: () => instance.waitUntilExit(),
    cleanup: () => {
      instances.delete(inkOptions.stdout);
    },
    clear: () => instance.clear(),
  };
}
