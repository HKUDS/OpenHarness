import React from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';

export function Composer({
	busy,
	input,
	setInput,
	onSubmit,
	historyIndex,
}: {
	busy: boolean;
	input: string;
	setInput: (value: string) => void;
	onSubmit: (value: string) => void;
	historyIndex: number;
}): React.JSX.Element {
	return (
		<Box flexDirection="column" marginTop={1}>
			<Box borderStyle="round" paddingX={1}>
				<Text color={busy ? 'yellow' : 'green'}>{busy ? 'busy' : 'ready'}</Text>
				<Text> </Text>
				<TextInput value={input} onChange={setInput} onSubmit={onSubmit} />
			</Box>
			<Box marginTop={1}>
				<Text dimColor>
					shift+enter=newline enter=submit tab=complete ctrl-p/ctrl-n=history history_index={String(historyIndex)}
				</Text>
			</Box>
		</Box>
	);
}
