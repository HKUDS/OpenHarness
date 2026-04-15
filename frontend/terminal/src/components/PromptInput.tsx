import React, {useEffect, useRef, useState} from 'react';
import {Box, Text, useInput, useStdout} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';

function wrapLine(line: string, width: number): string[] {
	if (width <= 0) {
		return [line];
	}
	if (!line) {
		return [''];
	}

	const segments: string[] = [];
	let index = 0;
	while (index < line.length) {
		segments.push(line.slice(index, index + width));
		index += width;
	}
	return segments;
}

function wrapInput(text: string, width: number): string[] {
	if (width <= 0) {
		return [text];
	}
	return text.split('\n').flatMap((line) => wrapLine(line, width));
}

export function PromptInput({
	busy,
	input,
	setInput,
	onSubmit,
	toolName,
	suppressSubmit,
}: {
	busy: boolean;
	input: string;
	setInput: (value: string) => void;
	onSubmit: (value: string) => void;
	toolName?: string;
	suppressSubmit?: boolean;
}): React.JSX.Element {
	const {theme} = useTheme();
	const {stdout} = useStdout();
	const [cursorOffset, setCursorOffset] = useState(input.length);
	const localEditRef = useRef(false);

	useEffect(() => {
		if (localEditRef.current) {
			localEditRef.current = false;
			setCursorOffset((offset) => Math.min(Math.max(0, offset), input.length));
			return;
		}
		setCursorOffset(input.length);
	}, [input]);

	const insertText = (text: string): void => {
		if (!text) {
			return;
		}
		localEditRef.current = true;
		const nextValue = input.slice(0, cursorOffset) + text + input.slice(cursorOffset);
		setInput(nextValue);
		setCursorOffset(cursorOffset + text.length);
	};

	const removeBeforeCursor = (): void => {
		if (cursorOffset <= 0) {
			return;
		}
		localEditRef.current = true;
		const nextValue = input.slice(0, cursorOffset - 1) + input.slice(cursorOffset);
		setInput(nextValue);
		setCursorOffset(cursorOffset - 1);
	};

	useInput((chunk, key) => {
		if (busy) {
			return;
		}
		if (key.ctrl && chunk === 'c') {
			return;
		}
		if (key.upArrow || key.downArrow || key.tab || (key.shift && key.tab) || key.escape) {
			return;
		}

		if (key.return) {
			if (key.shift) {
				insertText('\n');
				return;
			}
			if (!suppressSubmit) {
				onSubmit(input);
			}
			return;
		}

		if (key.leftArrow) {
			setCursorOffset((offset) => Math.max(0, offset - 1));
			return;
		}
		if (key.rightArrow) {
			setCursorOffset((offset) => Math.min(input.length, offset + 1));
			return;
		}
		if (key.backspace || key.delete) {
			removeBeforeCursor();
			return;
		}

		if (key.ctrl || key.meta) {
			return;
		}

		insertText(chunk);
	}, {isActive: !busy});

	if (busy) {
		return (
			<Box>
				<Spinner label={toolName ? `Running ${toolName}...` : undefined} />
			</Box>
		);
	}

	const rendered = input.slice(0, cursorOffset) + '|' + input.slice(cursorOffset);
	const renderWidth = Math.max(10, (stdout?.columns ?? process.stdout.columns ?? 80) - 4);
	const wrappedLines = wrapInput(rendered, renderWidth);

	return (
		<Box flexDirection="column">
			<Box>
				<Text color={theme.colors.primary} bold>{'> '}</Text>
				<Text>{wrappedLines[0] ?? ''}</Text>
			</Box>
			{wrappedLines.slice(1).map((line, index) => (
				<Box key={index}>
					<Text color={theme.colors.primary}>{'  '}</Text>
					<Text>{line}</Text>
				</Box>
			))}
		</Box>
	);
}
