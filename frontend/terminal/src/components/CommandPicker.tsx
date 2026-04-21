import React from 'react';
import {Box, Text} from 'ink';

function CommandPickerInner({
	hints,
	selectedIndex,
}: {
	hints: string[];
	selectedIndex: number;
}): React.JSX.Element | null {
	if (hints.length === 0) {
		return null;
	}

	return (
		<Box flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1} marginBottom={0}>
			<Text dimColor bold> Commands</Text>
			{hints.map((hint, i) => {
				const isSelected = i === selectedIndex;
				return (
					<Box key={hint}>
						<Text color={isSelected ? 'cyan' : undefined} bold={isSelected}>
							{isSelected ? '\u276F ' : '  '}
							{hint}
						</Text>
						{isSelected ? <Text dimColor> [enter]</Text> : null}
					</Box>
				);
			})}
			<Text dimColor> {'\u2191\u2193'} navigate{'  '}{'\u23CE'} select{'  '}esc dismiss</Text>
		</Box>
	);
}

export const CommandPicker = React.memo(CommandPickerInner);
