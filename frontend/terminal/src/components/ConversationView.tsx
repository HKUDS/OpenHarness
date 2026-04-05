import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';
import {ToolCallDisplay} from './ToolCallDisplay.js';
import {WelcomeBanner} from './WelcomeBanner.js';

export function ConversationView({
	items,
	assistantBuffer,
	showWelcome,
}: {
	items: TranscriptItem[];
	assistantBuffer: string;
	showWelcome: boolean;
}): React.JSX.Element {
	const {theme} = useTheme();
	// Show the most recent items that fit the viewport
	const visible = items.slice(-40);

	return (
		<Box flexDirection="column" flexGrow={1}>
			{showWelcome && items.length === 0 ? <WelcomeBanner /> : null}

			{visible.map((item, index) => (
				<MessageRow key={index} item={item} theme={theme} />
			))}

			{assistantBuffer ? (
				<Box flexDirection="row" marginTop={0}>
					<Text color={theme.colors.success} bold>{theme.icons.assistant}</Text>
					<Text>{assistantBuffer}</Text>
				</Box>
			) : null}
		</Box>
	);
}

function MessageRow({item, theme}: {item: TranscriptItem; theme: ReturnType<typeof useTheme>['theme']}): React.JSX.Element {
	switch (item.role) {
		case 'user':
			return (
				<Box marginTop={1} marginBottom={0}>
					<Text>
						<Text color={theme.colors.secondary} bold>{theme.icons.user}</Text>
						<Text>{item.text}</Text>
					</Text>
				</Box>
			);

		case 'assistant':
			return (
				<Box marginTop={1} marginBottom={0} flexDirection="column">
					<Text>
						<Text color={theme.colors.success} bold>{theme.icons.assistant}</Text>
						<Text>{item.text}</Text>
					</Text>
				</Box>
			);

		case 'tool':
		case 'tool_result':
			return <ToolCallDisplay item={item} />;

		case 'system':
			return (
				<Box marginTop={0}>
					<Text>
						<Text color={theme.colors.warning}>{theme.icons.system}</Text>
						<Text color={theme.colors.warning}>{item.text}</Text>
					</Text>
				</Box>
			);

		case 'log':
			return (
				<Box>
					<Text dimColor>{item.text}</Text>
				</Box>
			);

		default:
			return (
				<Box>
					<Text>{item.text}</Text>
				</Box>
			);
	}
}
