import React from 'react';
import {Box, Text} from 'ink';

import type {TranscriptItem} from '../types.js';

export function TranscriptPane({
	items,
	assistantBuffer,
}: {
	items: TranscriptItem[];
	assistantBuffer: string;
}): React.JSX.Element {
	const visible = items.slice(-24);
	return (
		<Box flexDirection="column" width="68%" paddingRight={1}>
			<Text bold>Transcript</Text>
			<Box flexDirection="column" borderStyle="round" paddingX={1} minHeight={24}>
				{visible.map((item, index) => (
					<Text key={`${index}-${item.role}`} color={roleColor(item.role)}>
						{labelFor(item.role)} {item.text}
					</Text>
				))}
				{assistantBuffer ? <Text color="green">assistant&gt; {assistantBuffer}</Text> : null}
			</Box>
		</Box>
	);
}

function labelFor(role: TranscriptItem['role']): string {
	switch (role) {
		case 'tool':
			return 'tool>';
		case 'tool_result':
			return 'tool_result>';
		case 'thinking':
			return 'Think:';
		default:
			return `${role}>`;
	}
}

function roleColor(role: TranscriptItem['role']): string | undefined {
	if (role === 'assistant') {
		return 'green';
	}
	if (role === 'thinking') {
		return 'gray';
	}
	if (role === 'tool') {
		return 'cyan';
	}
	if (role === 'tool_result') {
		return 'yellow';
	}
	if (role === 'system') {
		return 'magenta';
	}
	if (role === 'log') {
		return 'gray';
	}
	return undefined;
}
