import React from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';

import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';

const noop = (): void => {};

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

	if (busy) {
		return (
			<Box>
				<Spinner label={toolName ? `Running ${toolName}...` : undefined} />
			</Box>
		);
	}

	return (
		<Box>
			<Text color={theme.colors.primary} bold>{'> '}</Text>
			<TextInput value={input} onChange={setInput} onSubmit={suppressSubmit ? noop : onSubmit} />
		</Box>
	);
}
