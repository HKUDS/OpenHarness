import {useLayoutEffect, useRef} from 'react';

import {clearDeclaredCursorFromSnapshot, commitDeclaredCursor} from './cursorStore.js';
import type {DeclaredCursor} from './cursorTypes.js';
import type {DeclaredCursorSnapshot} from './cursorStore.js';

export function useDeclaredCursor(cursor: DeclaredCursor | null): void {
  const ownerRef = useRef<symbol>(Symbol('declared-cursor-owner'));
  const committedSnapshotRef = useRef<DeclaredCursorSnapshot | null>(null);

  // Publish during render so the runtime can park the native cursor with
  // current-frame coordinates. Effect-only publication can lag by one frame.
  committedSnapshotRef.current = commitDeclaredCursor(ownerRef.current, cursor);

  // Cleanup only on unmount. Clearing on every dependency update can create a
  // transient "no cursor declared" gap between cleanup and the next commit,
  // and that single frame is enough for IME caret anchoring to drift.
  useLayoutEffect(() => {
    return () => {
      clearDeclaredCursorFromSnapshot(committedSnapshotRef.current);
    };
  }, []);
}
