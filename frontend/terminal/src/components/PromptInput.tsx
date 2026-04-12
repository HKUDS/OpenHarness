import React from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';

import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';

const RUNNING_HINT_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

const noop = (): void => {};

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

	return (
		<Box flexDirection="column">
			{busy ? (
				<Box flexDirection="column" marginBottom={0}>
					<Box>
						<Spinner label={statusLabel ?? (toolName ? `Running ${toolName}...` : 'Running...')} />
					</Box>
					<Box>
						<Text color={theme.colors.warning} bold>
							{RUNNING_HINT_FRAMES.join(' ')} Agent is working…
						</Text>
					</Box>
				</Box>
			) : null}
			<Box>
				<Text color={theme.colors.primary} bold>{busy ? '… ' : '> '}</Text>
				<TextInput value={input} onChange={setInput} onSubmit={suppressSubmit || busy ? noop : onSubmit} />
			</Box>
		</Box>
	);
}
