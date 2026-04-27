import type {AnchorRect} from './cursorTypes.js';
import {InkOutputConstructor} from './inkInternalsAdapter.js';
import renderNodeToOutputWithAnchors from './renderNodeToOutputWithAnchors.js';

type InkRootNode = {
  yogaNode?: {
    getComputedWidth: () => number;
    getComputedHeight: () => number;
  };
  staticNode?: InkRootNode;
};

export type RenderFrame = {
  output: string;
  outputHeight: number;
  staticOutput: string;
  anchorRects: Map<string, AnchorRect>;
};

export function renderWithAnchors(node: InkRootNode): RenderFrame {
  const anchorRects = new Map<string, AnchorRect>();

  if (!node.yogaNode) {
    return {
      output: '',
      outputHeight: 0,
      staticOutput: '',
      anchorRects,
    };
  }

  const output = new InkOutputConstructor({
    width: node.yogaNode.getComputedWidth(),
    height: node.yogaNode.getComputedHeight(),
  });

  renderNodeToOutputWithAnchors(node as never, output as never, {
    skipStaticElements: true,
    anchorRects,
  });

  let staticOutput: InstanceType<typeof InkOutputConstructor> | undefined;
  if (node.staticNode?.yogaNode) {
    staticOutput = new InkOutputConstructor({
      width: node.staticNode.yogaNode.getComputedWidth(),
      height: node.staticNode.yogaNode.getComputedHeight(),
    });

    renderNodeToOutputWithAnchors(node.staticNode as never, staticOutput as never, {
      skipStaticElements: false,
      anchorRects,
    });
  }

  const {output: generatedOutput, height: outputHeight} = output.get();

  return {
    output: generatedOutput,
    outputHeight,
    staticOutput: staticOutput ? `${staticOutput.get().output}\n` : '',
    anchorRects,
  };
}
