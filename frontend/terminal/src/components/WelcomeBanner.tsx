import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

const VERSION = '0.1.7';
const ROBOT = [
	'   ▄▄▄▄   ',
	'  █  ▄█   ',
	'  ████▄   ',
	'  █ ██ █  ',
	'   ▀  ▀   ',
];

function compactPath(rawPath: string): string {
	if (!rawPath) {
		return '~';
	}
	const home = process.env.HOME ?? '';
	if (home && rawPath.startsWith(home)) {
		return `~${rawPath.slice(home.length)}`;
	}
	return rawPath;
}

function DividerLine({
	themeColor,
	children,
	bold = false,
	dim = false,
}: {
	themeColor: string;
	children: React.ReactNode;
	bold?: boolean;
	dim?: boolean;
}): React.JSX.Element {
	return (
		<Text>
			<Text color={themeColor}>│ </Text>
			<Text bold={bold} dimColor={dim}>{children}</Text>
		</Text>
	);
}

export function WelcomeBanner({
	model,
	provider,
	cwd,
}: {
	model?: string;
	provider?: string;
	cwd?: string;
}): React.JSX.Element {
	const {theme} = useTheme();
	const runtimeModel = (model ?? '').trim() || 'model not selected';
	const runtimeProvider = (provider ?? '').trim() || 'provider not selected';
	const runtimePath = compactPath((cwd ?? '').trim());

	return (
		<Box flexDirection="column" marginBottom={1}>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.primary} paddingX={1}>
				<Text>
					<Text color={theme.colors.primary}>── </Text>
					<Text color={theme.colors.primary} bold>OpenHarness</Text>
					<Text dimColor>{` v${VERSION}`}</Text>
				</Text>
				<Box flexDirection="row" marginTop={0}>
					<Box flexDirection="column" width={32} marginRight={1}>
						<Text bold>Welcome back!</Text>
						<Text> </Text>
						{ROBOT.map((line, index) => (
							<Text key={index} color={theme.colors.primary}>{line}</Text>
						))}
						<Text> </Text>
						<Text dimColor>{runtimeModel} · {runtimeProvider}</Text>
						<Text dimColor>{runtimePath}</Text>
					</Box>
					<Box flexDirection="column" flexGrow={1}>
						<DividerLine themeColor={theme.colors.primary} bold>Tips for getting started</DividerLine>
						<DividerLine themeColor={theme.colors.primary}>Run /init to create a CLAUDE.md file with instructions</DividerLine>
						<DividerLine themeColor={theme.colors.primary}>for your current project.</DividerLine>
						<Text color={theme.colors.primary}>│</Text>
						<DividerLine themeColor={theme.colors.primary} bold>Recent activity</DividerLine>
						<DividerLine themeColor={theme.colors.primary} dim>No recent activity</DividerLine>
					</Box>
				</Box>
			</Box>
		</Box>
	);
}
