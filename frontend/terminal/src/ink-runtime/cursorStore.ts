import type {DeclaredCursor} from './cursorTypes.js';

let currentDeclaredCursor: DeclaredCursor | null = null;
let currentDeclaredCursorOwner: symbol | null = null;

export type DeclaredCursorSnapshot = {
  owner: symbol;
  cursor: DeclaredCursor | null;
};

function normalizeCursor(cursor: DeclaredCursor | null): DeclaredCursor | null {
  if (!cursor || !cursor.active) {
    return null;
  }

  return cursor;
}

function isSameCursor(a: DeclaredCursor, b: DeclaredCursor): boolean {
  return a.anchorId === b.anchorId
    && a.relativeX === b.relativeX
    && a.relativeY === b.relativeY
    && a.active === b.active;
}

export function commitDeclaredCursor(owner: symbol, cursor: DeclaredCursor | null): DeclaredCursorSnapshot {
  const normalizedCursor = normalizeCursor(cursor);

  if (!normalizedCursor) {
    if (currentDeclaredCursorOwner === owner) {
      currentDeclaredCursor = null;
      currentDeclaredCursorOwner = null;
    }

    return {owner, cursor: null};
  }

  currentDeclaredCursor = normalizedCursor;
  currentDeclaredCursorOwner = owner;

  return {owner, cursor: normalizedCursor};
}

export function clearDeclaredCursorFromSnapshot(snapshot: DeclaredCursorSnapshot | null): void {
  if (!snapshot?.cursor) {
    return;
  }

  if (currentDeclaredCursorOwner !== snapshot.owner || !currentDeclaredCursor) {
    return;
  }

  if (!isSameCursor(currentDeclaredCursor, snapshot.cursor)) {
    return;
  }

  currentDeclaredCursor = null;
  currentDeclaredCursorOwner = null;
}

export function setDeclaredCursor(cursor: DeclaredCursor | null): void {
  const normalizedCursor = normalizeCursor(cursor);
  if (!normalizedCursor) {
    currentDeclaredCursor = null;
    currentDeclaredCursorOwner = null;
    return;
  }

  currentDeclaredCursor = normalizedCursor;
}

export function clearDeclaredCursor(): void {
  currentDeclaredCursor = null;
  currentDeclaredCursorOwner = null;
}

export function getDeclaredCursor(): DeclaredCursor | null {
  return currentDeclaredCursor;
}
