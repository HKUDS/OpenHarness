import React, {useEffect, useState} from 'react';
import {Box, Text, useInput} from 'ink';
import chalk from 'chalk';

import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';

const noop = (): void => {};

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

	useEffect(() => {
		setCursorOffset((previous) => Math.min(previous, value.length));
	}, [value]);

	useInput(
		(input, key) => {
			if (!focus) {
				return;
			}

			if (key.upArrow || key.downArrow || key.tab || (key.shift && key.tab) || key.escape || (key.ctrl && input === 'c')) {
				return;
			}

			if (key.return) {
				if (key.shift) {
					const nextValue = value.slice(0, cursorOffset) + '\n' + value.slice(cursorOffset);
					setCursorOffset(cursorOffset + 1);
					onChange(nextValue);
					return;
				}
				onSubmit?.(value);
				return;
			}

			if (key.leftArrow) {
				setCursorOffset((previous) => Math.max(0, previous - 1));
				return;
			}

			if (key.rightArrow) {
				setCursorOffset((previous) => Math.min(value.length, previous + 1));
				return;
			}

			if (key.backspace) {
				if (cursorOffset === 0) {
					return;
				}
				const nextValue = value.slice(0, cursorOffset - 1) + value.slice(cursorOffset);
				setCursorOffset(cursorOffset - 1);
				onChange(nextValue);
				return;
			}

			if (key.delete) {
				if (cursorOffset >= value.length) {
					return;
				}
				const nextValue = value.slice(0, cursorOffset) + value.slice(cursorOffset + 1);
				onChange(nextValue);
				return;
			}

			if (!input) {
				return;
			}

			const nextValue = value.slice(0, cursorOffset) + input + value.slice(cursorOffset);
			setCursorOffset(cursorOffset + input.length);
			onChange(nextValue);
		},
		{isActive: focus},
	);

	let renderedValue = value;
	if (focus) {
		if (value.length === 0) {
			renderedValue = chalk.inverse(' ');
		} else {
			renderedValue = '';
			let index = 0;
			for (const char of value) {
				if (index === cursorOffset) {
					renderedValue += chalk.inverse(char === '\n' ? ' ' : char);
				} else {
					renderedValue += char;
				}
				index += 1;
			}
			if (cursorOffset === value.length) {
				renderedValue += chalk.inverse(' ');
			}
		}
	}

	const lines = renderedValue.split('\n');
	const indent = ' '.repeat(promptPrefix.length);
	return (
		<Box flexDirection="column">
			{lines.map((line, index) => (
				<Box key={`${index}:${line}`}>
					<Text color={promptColor} bold>
						{index === 0 ? promptPrefix : indent}
					</Text>
					<Text>{line.length > 0 ? line : ' '}</Text>
				</Box>
			))}
		</Box>
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
	const promptPrefix = busy ? '… ' : '> ';

	return (
		<Box flexDirection="column">
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
				promptColor={theme.colors.primary}
			/>
		</Box>
	);
}
