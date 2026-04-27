import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

function CommandPickerInner({
	hints,
	selectedIndex,
}: {
	hints: string[];
	selectedIndex: number;
}): React.JSX.Element | null {
	const {theme} = useTheme();

	if (hints.length === 0) {
		return null;
	}

	return (
		<Box flexDirection="column" marginBottom={0}>
			{hints.map((hint, i) => {
				const isSelected = i === selectedIndex;
				return (
					<Box key={hint}>
						<Text color={isSelected ? theme.colors.secondary : theme.colors.muted} bold={isSelected}>
							{isSelected ? '\u276f ' : '  '}
							{hint}
						</Text>
					</Box>
				);
			})}
		</Box>
	);
}

export const CommandPicker = React.memo(CommandPickerInner);
