import type {AnchorRect, DeclaredCursor} from './cursorTypes.js';

const DISABLE_NATIVE_CURSOR_PARK = process.env.OPENHARNESS_DISABLE_NATIVE_CURSOR_PARK === '1';
const DEBUG_NATIVE_CURSOR_PARK = process.env.OPENHARNESS_DEBUG_NATIVE_CURSOR_PARK === '1';
const SHOW_CURSOR = '\u001b[?25h';
const STEADY_BAR_CURSOR = '\u001b[6 q';

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function parkNativeCursor(options: {
  stdout: NodeJS.WriteStream;
  anchorRects: Map<string, AnchorRect>;
  declaredCursor: DeclaredCursor | null;
}): void {
  const {stdout, anchorRects, declaredCursor} = options;

  if (DISABLE_NATIVE_CURSOR_PARK) {
    if (DEBUG_NATIVE_CURSOR_PARK) {
      process.stderr.write('[native-cursor] skip: disabled by OPENHARNESS_DISABLE_NATIVE_CURSOR_PARK=1\n');
    }
    return;
  }

  if (!stdout.isTTY) {
    if (DEBUG_NATIVE_CURSOR_PARK) {
      process.stderr.write('[native-cursor] skip: stdout is not a TTY\n');
    }
    return;
  }

  if (!declaredCursor || !declaredCursor.active) {
    if (DEBUG_NATIVE_CURSOR_PARK) {
      process.stderr.write('[native-cursor] skip: no active declared cursor\n');
    }
    return;
  }

  const rect = anchorRects.get(declaredCursor.anchorId);
  if (!rect) {
    if (DEBUG_NATIVE_CURSOR_PARK) {
      process.stderr.write(
        `[native-cursor] skip: missing anchor rect for ${declaredCursor.anchorId}\n`,
      );
    }
    return;
  }

  const rawX = rect.x + declaredCursor.relativeX;
  const rawY = rect.y + declaredCursor.relativeY;

  const maxColumns = Number.isFinite(stdout.columns) && stdout.columns > 0
    ? Math.floor(stdout.columns) - 1
    : Number.MAX_SAFE_INTEGER;
  const maxRows = Number.isFinite(stdout.rows) && stdout.rows > 0
    ? Math.floor(stdout.rows) - 1
    : Number.MAX_SAFE_INTEGER;

  const absoluteX = clamp(Math.floor(rawX), 0, maxColumns);
  const absoluteY = clamp(Math.floor(rawY), 0, maxRows);

  if (DEBUG_NATIVE_CURSOR_PARK) {
    process.stderr.write(
      `[native-cursor] declared=${JSON.stringify(declaredCursor)} anchor=${JSON.stringify(rect)} absolute={"x":${absoluteX},"y":${absoluteY}}\n`,
    );
  }

  // Keep the native terminal cursor visible and park it at the input caret.
  stdout.write(`${SHOW_CURSOR}${STEADY_BAR_CURSOR}\u001b[${absoluteY + 1};${absoluteX + 1}H`);
}
