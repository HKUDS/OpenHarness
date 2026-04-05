import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';

export function ToolCallDisplay({item}: {item: TranscriptItem}): React.JSX.Element {
	const {theme} = useTheme();

	if (item.role === 'tool') {
		const toolName = item.tool_name ?? 'tool';
		const summary = summarizeInput(toolName, item.tool_input, item.text);
		return (
			<Box marginLeft={2} flexDirection="column">
				<Text>
					<Text color={theme.colors.accent} bold>{theme.icons.tool}</Text>
					<Text color={theme.colors.accent} bold>{toolName}</Text>
					<Text dimColor> {summary}</Text>
				</Text>
			</Box>
		);
	}

	if (item.role === 'tool_result') {
		const lines = item.text.split('\n');
		const maxLines = 12;
		const display = lines.length > maxLines ? [...lines.slice(0, maxLines), `... (${lines.length - maxLines} more lines)`] : lines;
		const color = item.is_error ? theme.colors.error : undefined;
		return (
			<Box marginLeft={4} flexDirection="column">
				{display.map((line, i) => (
					<Text key={i} color={color} dimColor={!item.is_error}>
						{line}
					</Text>
				))}
			</Box>
		);
	}

	return <Text>{item.text}</Text>;
}

function summarizeInput(toolName: string, toolInput?: Record<string, unknown>, fallback?: string): string {
	if (!toolInput) {
		return fallback?.slice(0, 80) ?? '';
	}
	const lower = toolName.toLowerCase();
	if (lower === 'bash' && toolInput.command) {
		return String(toolInput.command).slice(0, 120);
	}
	if ((lower === 'read' || lower === 'fileread') && toolInput.file_path) {
		return String(toolInput.file_path);
	}
	if ((lower === 'write' || lower === 'filewrite') && toolInput.file_path) {
		return String(toolInput.file_path);
	}
	if ((lower === 'edit' || lower === 'fileedit') && toolInput.file_path) {
		return String(toolInput.file_path);
	}
	if (lower === 'grep' && toolInput.pattern) {
		return `/${String(toolInput.pattern)}/`;
	}
	if (lower === 'glob' && toolInput.pattern) {
		return String(toolInput.pattern);
	}
	if (lower === 'agent' && toolInput.description) {
		return String(toolInput.description);
	}
	// Fallback: show first key=value
	const entries = Object.entries(toolInput);
	if (entries.length > 0) {
		const [key, val] = entries[0];
		return `${key}=${String(val).slice(0, 60)}`;
	}
	return fallback?.slice(0, 80) ?? '';
}
