import React, {useState} from 'react';
import {Box, Text, useInput} from 'ink';

export type SwarmTeammate = {
	name: string;
	status: 'running' | 'idle' | 'done' | 'error';
	duration?: number; // seconds
	task?: string;
};

export type SwarmNotification = {
	from: string;
	message: string;
	timestamp: number;
};

function statusIcon(status: SwarmTeammate['status']): string {
	switch (status) {
		case 'running':
			return '🟢';
		case 'idle':
			return '🟡';
		case 'done':
			return '✅';
		case 'error':
			return '🔴';
	}
}

function formatDuration(seconds: number): string {
	if (seconds < 60) {
		return `${seconds}s`;
	}
	const m = Math.floor(seconds / 60);
	const s = seconds % 60;
	return `${m}m${s}s`;
}

function SwarmPanelInner({
	teammates,
	notifications,
	collapsed: initialCollapsed = false,
}: {
	teammates: SwarmTeammate[];
	notifications: SwarmNotification[];
	collapsed?: boolean;
}): React.JSX.Element | null {
	const [collapsed, setCollapsed] = useState(initialCollapsed);

	useInput((chunk, key) => {
		if (key.ctrl && chunk === 'w') {
			setCollapsed((c) => !c);
		}
	});

	if (teammates.length === 0 && notifications.length === 0) {
		return null;
	}

	const activeCount = teammates.filter((t) => t.status === 'running').length;

	if (collapsed) {
		return (
			<Box>
				<Text color="cyan" bold>
					{'⚡ '}
				</Text>
				<Text dimColor>
					Swarm: {teammates.length} agents ({activeCount} active)
				</Text>
				<Text dimColor> [ctrl+w expand]</Text>
			</Box>
		);
	}

	return (
		<Box flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1} marginTop={1}>
			<Box>
				<Text color="cyan" bold>
					{'⚡ '}
				</Text>
				<Text bold>Swarm</Text>
				<Text dimColor>
					{' '}
					({activeCount}/{teammates.length} active) [ctrl+w collapse]
				</Text>
			</Box>

			{teammates.length > 0 && (
				<Box flexDirection="column" marginTop={1}>
					{teammates.map((teammate) => (
						<Box key={teammate.name} flexDirection="row" marginBottom={0}>
							<Text>{statusIcon(teammate.status)} </Text>
							<Box flexDirection="column">
								<Box>
									<Text bold color={teammate.status === 'running' ? 'green' : teammate.status === 'error' ? 'red' : undefined}>
										{teammate.name}
									</Text>
									{teammate.duration !== undefined && (
										<Text dimColor> ({formatDuration(teammate.duration)})</Text>
									)}
								</Box>
								{teammate.task && (
									<Text dimColor>   {teammate.task.slice(0, 60)}{teammate.task.length > 60 ? '…' : ''}</Text>
								)}
							</Box>
						</Box>
					))}
				</Box>
			)}

			{notifications.length > 0 && (
				<Box flexDirection="column" marginTop={1}>
					<Text dimColor bold>Recent notifications:</Text>
					{notifications.slice(-3).map((n, i) => (
						<Box key={i}>
							<Text dimColor>[{n.from}] </Text>
							<Text>{n.message.slice(0, 70)}{n.message.length > 70 ? '…' : ''}</Text>
						</Box>
					))}
				</Box>
			)}
		</Box>
	);
}

export const SwarmPanel = React.memo(SwarmPanelInner);
