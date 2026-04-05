import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TaskSnapshot} from '../types.js';

const SEP = ' \u2502 ';

export function StatusBar({status, tasks}: {status: Record<string, unknown>; tasks: TaskSnapshot[]}): React.JSX.Element {
	const {theme} = useTheme();
	const model = String(status.model ?? 'unknown');
	const mode = String(status.permission_mode ?? 'default');
	const taskCount = tasks.length;
	const mcpCount = Number(status.mcp_connected ?? 0);
	const inputTokens = Number(status.input_tokens ?? 0);
	const outputTokens = Number(status.output_tokens ?? 0);

	return (
		<Box flexDirection="column">
			<Text dimColor>{'─'.repeat(60)}</Text>
			<Box flexDirection="row">
				<Text>
					<Text color={theme.colors.primary} dimColor>model: {model}</Text>
					<Text dimColor>{SEP}</Text>
					{inputTokens > 0 || outputTokens > 0 ? (
						<>
							<Text dimColor>tokens: {formatNum(inputTokens)}{'\u2193'} {formatNum(outputTokens)}{'\u2191'}</Text>
							<Text dimColor>{SEP}</Text>
						</>
					) : null}
					<Text dimColor>mode: {mode}</Text>
					{taskCount > 0 ? (
						<>
							<Text dimColor>{SEP}</Text>
							<Text dimColor>tasks: {taskCount}</Text>
						</>
					) : null}
					{mcpCount > 0 ? (
						<>
							<Text dimColor>{SEP}</Text>
							<Text dimColor>mcp: {mcpCount}</Text>
						</>
					) : null}
				</Text>
			</Box>
		</Box>
	);
}

function formatNum(n: number): string {
	if (n >= 1000) {
		return `${(n / 1000).toFixed(1)}k`;
	}
	return String(n);
}
