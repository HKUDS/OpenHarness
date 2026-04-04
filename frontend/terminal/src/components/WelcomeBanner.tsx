import React from 'react';
import {Box, Text} from 'ink';

const VERSION = '0.1.0';

export function WelcomeBanner(): React.JSX.Element {
	return (
		<Box flexDirection="column" marginBottom={1}>
			<Box flexDirection="column" paddingX={0}>
				<Text color="cyan" bold>{'  OpenHarness'}</Text>
				<Text dimColor>{'  AI-powered coding assistant  v'}{VERSION}</Text>
				<Text> </Text>
				<Text>
					<Text dimColor>{'  '}</Text>
					<Text color="cyan">/help</Text>
					<Text dimColor> commands</Text>
					<Text dimColor>{'  '}|{'  '}</Text>
					<Text color="cyan">/model</Text>
					<Text dimColor> switch</Text>
					<Text dimColor>{'  '}|{'  '}</Text>
					<Text color="cyan">Ctrl+C</Text>
					<Text dimColor> exit</Text>
				</Text>
			</Box>
		</Box>
	);
}
