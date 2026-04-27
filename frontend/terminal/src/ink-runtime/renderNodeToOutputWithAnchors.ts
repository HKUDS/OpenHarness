import widestLine from 'widest-line';
import indentString from 'indent-string';
import Yoga from 'yoga-layout';

import type {AnchorRect} from './cursorTypes.js';
import {
  inkGetMaxWidth,
  inkRenderBorder,
  inkSquashTextNodes,
  inkWrapText,
} from './inkInternalsAdapter.js';

type OutputLike = {
  write: (x: number, y: number, text: string, options: {transformers: Array<(text: string) => string>}) => void;
  clip: (clip: {x1?: number; x2?: number; y1?: number; y2?: number}) => void;
  unclip: () => void;
};

type InkNode = {
  nodeName: string;
  yogaNode?: {
    getDisplay: () => number;
    getComputedLeft: () => number;
    getComputedTop: () => number;
    getComputedWidth: () => number;
    getComputedHeight: () => number;
    getComputedBorder: (edge: number) => number;
  };
  style?: {
    overflowX?: string;
    overflowY?: string;
    overflow?: string;
    textWrap?: InkTextWrapMode;
    anchorId?: string;
  };
  childNodes: InkNode[];
  internal_transform?: (text: string) => string;
  attributes?: Record<string, unknown>;
};

type InkTextWrapMode = 'wrap' | 'truncate' | 'truncate-start' | 'truncate-middle' | 'truncate-end';

type RenderOptions = {
  offsetX?: number;
  offsetY?: number;
  transformers?: Array<(text: string) => string>;
  skipStaticElements: boolean;
  anchorRects: Map<string, AnchorRect>;
};

const applyPaddingToText = (node: InkNode, text: string): string => {
  const yogaNode = node.childNodes[0]?.yogaNode;
  if (yogaNode) {
    const offsetX = yogaNode.getComputedLeft();
    const offsetY = yogaNode.getComputedTop();
    text = '\n'.repeat(offsetY) + indentString(text, offsetX);
  }

  return text;
};

const renderNodeToOutputWithAnchors = (
  node: InkNode,
  output: OutputLike,
  options: RenderOptions,
): void => {
  const {
    offsetX = 0,
    offsetY = 0,
    transformers = [],
    skipStaticElements,
    anchorRects,
  } = options;

  if (skipStaticElements && (node as {internal_static?: boolean}).internal_static) {
    return;
  }

  const {yogaNode} = node;
  if (!yogaNode) {
    return;
  }

  if (yogaNode.getDisplay() === Yoga.DISPLAY_NONE) {
    return;
  }

  const x = offsetX + yogaNode.getComputedLeft();
  const y = offsetY + yogaNode.getComputedTop();

  const styleAnchorId = node.style?.anchorId;
  const anchorId = typeof node.attributes?.anchorId === 'string'
    ? node.attributes.anchorId
    : styleAnchorId;
  if (typeof anchorId === 'string' && anchorId.length > 0) {
    anchorRects.set(anchorId, {
      x,
      y,
      width: yogaNode.getComputedWidth(),
      height: yogaNode.getComputedHeight(),
    });
  }

  let newTransformers = transformers;
  if (typeof node.internal_transform === 'function') {
    newTransformers = [node.internal_transform, ...transformers];
  }

  if (node.nodeName === 'ink-text') {
    let text = inkSquashTextNodes(node);

    if (text.length > 0) {
      const currentWidth = widestLine(text);
      const maxWidth = inkGetMaxWidth(yogaNode);
      if (currentWidth > maxWidth) {
        const textWrap = node.style?.textWrap ?? 'wrap';
        text = inkWrapText(text, maxWidth, textWrap);
      }

      text = applyPaddingToText(node, text);
      output.write(x, y, text, {transformers: newTransformers});
    }

    return;
  }

  let clipped = false;

  if (node.nodeName === 'ink-box') {
    inkRenderBorder(x, y, node, output);

    const clipHorizontally = node.style?.overflowX === 'hidden' || node.style?.overflow === 'hidden';
    const clipVertically = node.style?.overflowY === 'hidden' || node.style?.overflow === 'hidden';

    if (clipHorizontally || clipVertically) {
      const x1 = clipHorizontally ? x + yogaNode.getComputedBorder(Yoga.EDGE_LEFT) : undefined;
      const x2 = clipHorizontally
        ? x + yogaNode.getComputedWidth() - yogaNode.getComputedBorder(Yoga.EDGE_RIGHT)
        : undefined;
      const y1 = clipVertically ? y + yogaNode.getComputedBorder(Yoga.EDGE_TOP) : undefined;
      const y2 = clipVertically
        ? y + yogaNode.getComputedHeight() - yogaNode.getComputedBorder(Yoga.EDGE_BOTTOM)
        : undefined;

      output.clip({x1, x2, y1, y2});
      clipped = true;
    }
  }

  if (node.nodeName === 'ink-root' || node.nodeName === 'ink-box') {
    for (const childNode of node.childNodes) {
      renderNodeToOutputWithAnchors(childNode, output, {
        offsetX: x,
        offsetY: y,
        transformers: newTransformers,
        skipStaticElements,
        anchorRects,
      });
    }

    if (clipped) {
      output.unclip();
    }
  }
};

export default renderNodeToOutputWithAnchors;
