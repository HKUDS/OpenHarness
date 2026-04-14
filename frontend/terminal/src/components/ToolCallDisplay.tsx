import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';

export function ToolCallDisplay({
	item,
	resultItem,
	outputStyle,
}: {
	item: TranscriptItem;
	resultItem?: TranscriptItem;
	outputStyle?: string;
}): React.JSX.Element {
	const {theme} = useTheme();
	const isCodexStyle = outputStyle === 'codex';

	if (item.role === 'tool') {
		const toolName = item.tool_name ?? 'tool';
		const summary = summarizeInput(toolName, item.tool_input, item.text).replace(/\s+/g, ' ').trim();

		let statusNode: React.ReactNode = null;
		let errorLines: string[] | null = null;

		if (resultItem) {
			if (resultItem.is_error) {
				statusNode = isCodexStyle
					? <Text color={theme.colors.error}> error</Text>
					: <Text color={theme.colors.error}> {theme.icons.error.trim()}</Text>;
				const lines = resultItem.text.split('\n').filter((l) => l.trim());
				const maxErrLines = isCodexStyle ? 8 : 5;
				errorLines = lines.length > maxErrLines
					? [...lines.slice(0, maxErrLines), `... (${lines.length - maxErrLines} more lines)`]
					: lines;
			} else if (!isCodexStyle) {
				const lineCount = resultItem.text.split('\n').filter((l) => l.trim()).length;
				const resultLabel = lineCount > 0 ? `${lineCount}L` : theme.icons.success.trim();
				statusNode = <Text dimColor> → {resultLabel}</Text>;
			} else {
				const lineCount = resultItem.text.split('\n').filter((l) => l.trim()).length;
				statusNode = <Text dimColor>{lineCount > 0 ? ` ${lineCount}L` : ''}</Text>;
			}
		}

		if (isCodexStyle) {
			return (
				<Box marginLeft={0} flexDirection="column">
					<Text dimColor>{`• Ran ${toolName}${summary ? ` ${summary}` : ''}`}{statusNode}</Text>
					{errorLines?.map((line, i) => {
						const prefix = i === errorLines.length - 1 ? '└ ' : '│ ';
						return (
							<Text key={i} color={theme.colors.error}>
								{prefix}
								{line}
							</Text>
						);
					})}
				</Box>
			);
		}

		return (
			<Box marginLeft={2} flexDirection="column">
				<Text>
					<Text color={theme.colors.accent} bold>{theme.icons.tool}</Text>
					<Text color={theme.colors.accent} bold>{toolName}</Text>
					<Text dimColor> {summary}</Text>
					{statusNode}
				</Text>
				{errorLines?.map((line, i) => (
					<Box key={i} marginLeft={4}>
						<Text color={theme.colors.error}>{line}</Text>
					</Box>
				))}
			</Box>
		);
	}

	if (item.role === 'tool_result') {
		if (!item.is_error) {
			return <></>;
		}
		const lines = item.text.length > 0
			? item.text.split('\n').filter((l) => l.trim())
			: [''];
		const maxLines = isCodexStyle ? 8 : 5;
		const display = lines.length > maxLines ? [...lines.slice(0, maxLines), `... (${lines.length - maxLines} more lines)`] : lines;
		if (isCodexStyle) {
			return (
				<Box marginLeft={0} flexDirection="column">
					{display.map((line, i) => {
						const prefix = i === display.length - 1 ? '└ ' : '│ ';
						return (
							<Text key={i} color={theme.colors.error}>
								{prefix}
								{line}
							</Text>
						);
					})}
				</Box>
			);
		}
		return (
			<Box marginLeft={4} flexDirection="column">
				{display.map((line, i) => (
					<Text key={i} color={theme.colors.error}>{line}</Text>
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
	const entries = Object.entries(toolInput);
	if (entries.length > 0) {
		const [key, val] = entries[0];
		return `${key}=${String(val).slice(0, 60)}`;
	}
	return fallback?.slice(0, 80) ?? '';
}
