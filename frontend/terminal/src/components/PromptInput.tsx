import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Box, Text, useInput, useStdin} from 'ink';

import {computeCaretCellPosition, CursorAnchorBox, useDeclaredCursor} from '../ink-runtime/index.js';
import {useHorizontalRule, useTerminalColumns} from '../hooks/useHorizontalRule.js';
import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';
import {
  insertAtOffset,
  moveOffsetByGrapheme,
  offsetToDisplayIndex,
  removeBackwardGraphemes,
  removeForwardGraphemes,
} from './textOffset.js';

const noop = (): void => {};
const BACKSPACE_CONTROL_PATTERN = /^[\b\u007f]+$/;
const INPUT_ANCHOR_ID = 'prompt-input-anchor';
const RESERVED_COLUMNS = 2;

type RenderSegment = {
  text: string;
};

type RenderedInputLine = {
  key: string;
  prefix: string;
  segments: RenderSegment[];
};

type InputRenderState = {
  lines: RenderedInputLine[];
  cursorLine: number;
  cursorColumn: number;
};

export function getBackspaceDeleteCount(sequence: string): number {
  if (!sequence || !BACKSPACE_CONTROL_PATTERN.test(sequence)) {
    return 1;
  }

  return [...sequence].length;
}

function isBackspaceDeleteSequence(sequence: string): boolean {
  return sequence === '\x7f'
    || sequence === '\x1b\x7f'
    || BACKSPACE_CONTROL_PATTERN.test(sequence);
}

function buildInputRenderState(
  value: string,
  cursorOffset: number,
  promptPrefix: string,
  terminalColumns: number,
): InputRenderState {
  const indent = ' '.repeat(promptPrefix.length);
  const safeCursorOffset = Math.max(0, Math.min(value.length, cursorOffset));
  const beforeCaret = value.slice(0, safeCursorOffset);
  const beforeCaretLines = beforeCaret.split('\n');
  const renderedLines = value.split('\n').map((line, index): RenderedInputLine => ({
    key: `${index}:${line}`,
    prefix: index === 0 ? promptPrefix : indent,
    segments: line ? [{text: line}] : [],
  }));

  const renderedBeforeCaret = beforeCaretLines
    .map((line, index) => `${index === 0 ? promptPrefix : indent}${line}`)
    .join('\n');
  const promptAreaColumns = Math.max(1, terminalColumns - RESERVED_COLUMNS);
  const caretCell = computeCaretCellPosition(
    renderedBeforeCaret,
    renderedBeforeCaret.length,
    promptAreaColumns,
  );

  return {
    lines: renderedLines,
    cursorLine: caretCell.line,
    cursorColumn: caretCell.column,
  };
}

function MultilineTextInput({
  value,
  onChange,
  onSubmit,
  focus = true,
  promptPrefix,
  promptColor,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: (value: string) => void;
  focus?: boolean;
  promptPrefix: string;
  promptColor: string;
}): React.JSX.Element {
  const [cursorOffset, setCursorOffset] = useState(value.length);
  const {internal_eventEmitter} = useStdin();
  const lastSequenceRef = useRef('');
  const valueRef = useRef(value);
  const cursorOffsetRef = useRef(value.length);
  const terminalColumns = useTerminalColumns();

  // Keep track of self-authored value updates so external updates (completion,
  // history, clear) can still reset the cursor to the end.
  const lastInternalValueRef = useRef<string>(value);

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    cursorOffsetRef.current = cursorOffset;
  }, [cursorOffset]);

  useEffect(() => {
    if (value === lastInternalValueRef.current) {
      return;
    }

    lastInternalValueRef.current = value;
    cursorOffsetRef.current = value.length;
    setCursorOffset(() => value.length);
  }, [value]);

  useEffect(() => {
    if (!focus) {
      return;
    }

    const handleRawInput = (chunk: string | Buffer): void => {
      const sequence = Buffer.isBuffer(chunk) ? chunk.toString('utf8') : String(chunk);
      lastSequenceRef.current = sequence;
    };

    internal_eventEmitter.on('input', handleRawInput);
    return () => {
      internal_eventEmitter.removeListener('input', handleRawInput);
    };
  }, [focus, internal_eventEmitter]);

  const commitValue = (nextValue: string): void => {
    valueRef.current = nextValue;
    lastInternalValueRef.current = nextValue;
    onChange(nextValue);
  };

  const applyCursorMutation = (
    mutate: (state: {currentValue: string; currentOffset: number}) => {nextValue?: string; nextOffset: number},
  ): void => {
    const currentValue = valueRef.current;
    const currentOffset = cursorOffsetRef.current;
    const result = mutate({currentValue, currentOffset});
    const nextValueLength = (result.nextValue ?? currentValue).length;
    const nextOffset = Math.max(0, Math.min(nextValueLength, result.nextOffset));

    cursorOffsetRef.current = nextOffset;
    setCursorOffset(() => nextOffset);

    if (typeof result.nextValue === 'string' && result.nextValue !== currentValue) {
      commitValue(result.nextValue);
    }
  };

  useInput(
    (input, key) => {
      if (!focus) {
        return;
      }
      const rawSequence = lastSequenceRef.current;
      lastSequenceRef.current = '';

      const isStandaloneEscape = key.escape
        && !key.leftArrow
        && !key.rightArrow
        && !key.upArrow
        && !key.downArrow
        && !key.delete
        && !key.backspace
        && !key.return
        && !key.tab;

      if (
        key.upArrow
        || key.downArrow
        || key.tab
        || (key.shift && key.tab)
        || isStandaloneEscape
        || (key.ctrl && input === 'c')
      ) {
        return;
      }

      if (key.return) {
        if (key.shift) {
          applyCursorMutation(({currentValue, currentOffset}) => {
            const insertion = insertAtOffset(currentValue, currentOffset, '\n');
            return {
              nextValue: insertion.nextValue,
              nextOffset: insertion.nextOffset,
            };
          });
          return;
        }

        onSubmit?.(valueRef.current);
        return;
      }

      if (key.leftArrow) {
        applyCursorMutation(({currentValue, currentOffset}) => ({
          nextOffset: moveOffsetByGrapheme(currentValue, currentOffset, -1),
        }));
        return;
      }

      if (key.rightArrow) {
        applyCursorMutation(({currentValue, currentOffset}) => ({
          nextOffset: moveOffsetByGrapheme(currentValue, currentOffset, 1),
        }));
        return;
      }

      const isBareBackspaceSequence = !key.backspace
        && !key.delete
        && BACKSPACE_CONTROL_PATTERN.test(rawSequence || input);

      if (key.backspace || isBareBackspaceSequence) {
        if (cursorOffsetRef.current === 0) {
          return;
        }

        applyCursorMutation(({currentValue, currentOffset}) => {
          const currentDisplayIndex = offsetToDisplayIndex(currentValue, currentOffset);
          const deleteCount = Math.min(currentDisplayIndex, getBackspaceDeleteCount(rawSequence || input));
          const deletion = removeBackwardGraphemes(currentValue, currentOffset, deleteCount);
          return deletion.changed
            ? {nextValue: deletion.nextValue, nextOffset: deletion.nextOffset}
            : {nextOffset: deletion.nextOffset};
        });
        return;
      }

      if (key.delete) {
        const treatAsBackspace = isBackspaceDeleteSequence(rawSequence);

        if (treatAsBackspace) {
          if (cursorOffsetRef.current === 0) {
            if (valueRef.current.length > 0) {
              applyCursorMutation(({currentValue, currentOffset}) => {
                const deletion = removeForwardGraphemes(currentValue, currentOffset, 1);
                return deletion.changed
                  ? {nextValue: deletion.nextValue, nextOffset: deletion.nextOffset}
                  : {nextOffset: deletion.nextOffset};
              });
            }
            return;
          }

          applyCursorMutation(({currentValue, currentOffset}) => {
            const currentDisplayIndex = offsetToDisplayIndex(currentValue, currentOffset);
            const deleteCount = Math.min(currentDisplayIndex, getBackspaceDeleteCount(rawSequence));
            const deletion = removeBackwardGraphemes(currentValue, currentOffset, deleteCount);
            return deletion.changed
              ? {nextValue: deletion.nextValue, nextOffset: deletion.nextOffset}
              : {nextOffset: deletion.nextOffset};
          });
          return;
        }

        if (cursorOffsetRef.current >= valueRef.current.length) {
          return;
        }

        applyCursorMutation(({currentValue, currentOffset}) => {
          const deletion = removeForwardGraphemes(currentValue, currentOffset, 1);
          return deletion.changed
            ? {nextValue: deletion.nextValue, nextOffset: deletion.nextOffset}
            : {nextOffset: deletion.nextOffset};
        });
        return;
      }

      if (!input) {
        return;
      }

      applyCursorMutation(({currentValue, currentOffset}) => {
        const insertion = insertAtOffset(currentValue, currentOffset, input);
        return {
          nextValue: insertion.nextValue,
          nextOffset: insertion.nextOffset,
        };
      });
    },
    {isActive: focus},
  );

  const renderCursorOffset = Math.max(0, Math.min(value.length, cursorOffsetRef.current));
  const renderState = useMemo(
    () => buildInputRenderState(value, renderCursorOffset, promptPrefix, terminalColumns),
    [value, renderCursorOffset, promptPrefix, terminalColumns],
  );

  useDeclaredCursor(
    focus
      ? {
        anchorId: INPUT_ANCHOR_ID,
        relativeX: renderState.cursorColumn,
        relativeY: renderState.cursorLine,
        active: true,
      }
      : null,
  );

  return (
    <CursorAnchorBox flexDirection="column" anchorId={INPUT_ANCHOR_ID}>
      {renderState.lines.map((line) => (
        <Box key={line.key}>
          <Text color={promptColor} bold>
            {line.prefix}
          </Text>
          {line.segments.length === 0 ? (
            <Text> </Text>
          ) : (
            line.segments.map((segment, index) => (
              <Text key={`${index}:${segment.text}`}>
                {segment.text}
              </Text>
            ))
          )}
        </Box>
      ))}
    </CursorAnchorBox>
  );
}

export function PromptInput({
  busy,
  input,
  setInput,
  onSubmit,
  toolName,
  suppressSubmit,
  statusLabel,
}: {
  busy: boolean;
  input: string;
  setInput: (value: string) => void;
  onSubmit: (value: string) => void;
  toolName?: string;
  suppressSubmit?: boolean;
  statusLabel?: string;
}): React.JSX.Element {
  const {theme} = useTheme();
  const horizontalRule = useHorizontalRule();
  const promptPrefix = busy ? '… ' : '❯ ';

  return (
    <Box flexDirection="column">
      <Text color={theme.colors.muted}>{horizontalRule}</Text>
      {busy ? (
        <Box flexDirection="column" marginBottom={0}>
          <Box>
            <Spinner label={statusLabel ?? (toolName ? `Running ${toolName}...` : 'Running...')} />
          </Box>
        </Box>
      ) : null}
      <MultilineTextInput
        value={input}
        onChange={setInput}
        onSubmit={suppressSubmit || busy ? noop : onSubmit}
        focus={!busy}
        promptPrefix={promptPrefix}
        promptColor={theme.colors.secondary}
      />
      <Text color={theme.colors.muted}>{horizontalRule}</Text>
    </Box>
  );
}
