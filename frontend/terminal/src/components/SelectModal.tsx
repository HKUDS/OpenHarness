import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

export type SelectOption = {
	value: string;
	label: string;
	description?: string;
	active?: boolean;
};

export function SelectModal({
	title,
	options,
	selectedIndex,
}: {
	title: string;
	options: SelectOption[];
	selectedIndex: number;
}): React.JSX.Element {
	const {theme} = useTheme();

	return (
		<Box flexDirection="column" borderStyle="single" borderColor={theme.colors.primary} paddingX={1} marginTop={1}>
			<Text bold color={theme.colors.primary}>{title}</Text>
			<Text> </Text>
			{options.map((opt, i) => {
				const isSelected = i === selectedIndex;
				const isCurrent = opt.active;
				return (
					<Box key={opt.value} flexDirection="column" marginBottom={0}>
						<Text color={isSelected ? theme.colors.secondary : theme.colors.foreground} bold={isSelected}>
							{isSelected ? '\u276f ' : '  '}
							{i + 1}. {opt.label}
						</Text>
						{opt.description ? (
							<Text dimColor>{'   '}{opt.description}</Text>
						) : null}
						{isCurrent ? <Text dimColor>{'   '}current</Text> : null}
					</Box>
				);
			})}
			<Text> </Text>
			<Text color={theme.colors.muted}>Enter to confirm · Esc to cancel</Text>
		</Box>
	);
}
