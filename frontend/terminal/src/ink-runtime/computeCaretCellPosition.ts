import stringWidth from 'string-width';

import type {CaretCellPosition} from './cursorTypes.js';

const DEFAULT_COLUMNS = 80;

function normalizeColumns(columns: number): number {
  if (!Number.isFinite(columns) || columns <= 0) {
    return DEFAULT_COLUMNS;
  }

  return Math.max(1, Math.floor(columns));
}

function clampOffset(text: string, offset: number): number {
  if (!Number.isFinite(offset)) {
    return text.length;
  }

  return Math.min(text.length, Math.max(0, Math.floor(offset)));
}

export function computeCaretCellPosition(
  text: string,
  offset: number,
  inputColumns: number,
): CaretCellPosition {
  const columns = normalizeColumns(inputColumns);
  const safeOffset = clampOffset(text, offset);
  const beforeCaret = text.slice(0, safeOffset);

  let line = 0;
  let column = 0;

  for (const char of beforeCaret) {
    if (char === '\n') {
      line += 1;
      column = 0;
      continue;
    }

    const width = Math.max(0, stringWidth(char));
    if (width === 0) {
      continue;
    }

    if (column > 0 && column + width > columns) {
      line += 1;
      column = 0;
    }

    column += width;

    if (column === columns) {
      line += 1;
      column = 0;
    } else if (column > columns) {
      line += Math.floor(column / columns);
      column = column % columns;
    }
  }

  return {line, column};
}
