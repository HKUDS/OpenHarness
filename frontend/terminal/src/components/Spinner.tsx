import React, {useEffect, useState} from 'react';
import {Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

const VERBS = [
	'Thinking',
	'Processing',
	'Analyzing',
	'Reasoning',
	'Working',
	'Computing',
	'Evaluating',
	'Considering',
];

const WINDOWS_SAFE_FRAMES = ['-', '\\', '|', '/'];

export function Spinner({label}: {label?: string}): React.JSX.Element {
	const {theme} = useTheme();
	const frames = process.platform === 'win32' ? WINDOWS_SAFE_FRAMES : theme.icons.spinner;
	const [frame, setFrame] = useState(0);
	const [verbIndex, setVerbIndex] = useState(0);

	useEffect(() => {
		const timer = setInterval(() => {
			setFrame((f) => (f + 1) % frames.length);
		}, 100);
		return () => clearInterval(timer);
	}, [frames.length]);

	useEffect(() => {
		const timer = setInterval(() => {
			setVerbIndex((v) => (v + 1) % VERBS.length);
		}, 3000);
		return () => clearInterval(timer);
	}, []);

	const verb = label ?? `${VERBS[verbIndex]}...`;

	return (
		<Text>
			<Text color={theme.colors.primary}>{frames[frame]}</Text>
			<Text dimColor> {verb}</Text>
		</Text>
	);
}
