import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp, useInput} from 'ink';

import {CommandPicker} from './components/CommandPicker.js';
import {ConversationView} from './components/ConversationView.js';
import {ModalHost} from './components/ModalHost.js';
import {PromptInput} from './components/PromptInput.js';
import {SelectModal, type SelectOption} from './components/SelectModal.js';
import {StatusBar} from './components/StatusBar.js';
import {SwarmPanel} from './components/SwarmPanel.js';
import {TodoPanel} from './components/TodoPanel.js';
import {useBackendSession} from './hooks/useBackendSession.js';
import {ThemeProvider, useTheme} from './theme/ThemeContext.js';
import type {FrontendConfig} from './types.js';

const rawReturnSubmit = process.env.OPENHARNESS_FRONTEND_RAW_RETURN === '1';
const scriptedSteps = (() => {
	const raw = process.env.OPENHARNESS_FRONTEND_SCRIPT;
	if (!raw) {
		return [] as string[];
	}
	try {
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
	} catch {
		return [];
	}
})();

const SELECTABLE_COMMANDS = new Set([
	'/provider',
	'/model',
	'/theme',
	'/output-style',
	'/permissions',
	'/resume',
	'/effort',
	'/passes',
	'/turns',
	'/fast',
	'/vim',
	'/voice',
]);

type SelectModalState = {
	title: string;
	options: SelectOption[];
	onSelect: (value: string) => void;
} | null;

export function App({config}: {config: FrontendConfig}): React.JSX.Element {
	const initialTheme = String((config as Record<string, unknown>).theme ?? 'default');
	return (
		<ThemeProvider initialTheme={initialTheme}>
			<AppInner config={config} />
		</ThemeProvider>
	);
}

function AppInner({config}: {config: FrontendConfig}): React.JSX.Element {
	const {exit} = useApp();
	const {theme, setThemeName} = useTheme();
	const [input, setInput] = useState('');
	const [modalInput, setModalInput] = useState('');
	const [history, setHistory] = useState<string[]>([]);
	const [historyIndex, setHistoryIndex] = useState(-1);
	const [lastEscapeAt, setLastEscapeAt] = useState(0);
	const [scriptIndex, setScriptIndex] = useState(0);
	const [pickerIndex, setPickerIndex] = useState(0);
	const [selectModal, setSelectModal] = useState<SelectModalState>(null);
	const [selectIndex, setSelectIndex] = useState(0);
	const session = useBackendSession(config, () => exit());

	useEffect(() => {
		const nextTheme = session.status.theme;
		if (typeof nextTheme === 'string' && nextTheme) {
			setThemeName(nextTheme);
		}
	}, [session.status.theme, setThemeName]);

	// Current tool name for spinner
	const currentToolName = useMemo(() => {
		for (let i = session.transcript.length - 1; i >= 0; i--) {
			const item = session.transcript[i];
			if (item.role === 'tool') {
				return item.tool_name ?? 'tool';
			}
			if (item.role === 'tool_result' || item.role === 'assistant') {
				break;
			}
		}
		return undefined;
	}, [session.transcript]);

	// Command hints
	const commandHints = useMemo(() => {
		const value = input.trim();
		if (!value.startsWith('/')) {
			return [] as string[];
		}
		return session.commands.filter((cmd) => cmd.startsWith(value)).slice(0, 10);
	}, [session.commands, input]);

	const showPicker = commandHints.length > 0 && !session.busy && !session.modal && !selectModal;

	useEffect(() => {
		setPickerIndex(0);
	}, [commandHints.length, input]);

	// Handle backend-initiated select requests (e.g. /resume session list)
	useEffect(() => {
		if (!session.selectRequest) {
			return;
		}
		const req = session.selectRequest;
		if (req.options.length === 0) {
			session.setSelectRequest(null);
			return;
		}
		const initialIndex = req.options.findIndex((option) => option.active);
		setSelectIndex(initialIndex >= 0 ? initialIndex : 0);
		setSelectModal({
			title: req.title,
			options: req.options.map((o) => ({value: o.value, label: o.label, description: o.description, active: o.active})),
			onSelect: (value) => {
				session.sendRequest({type: 'apply_select_command', command: req.command, value});
				session.setBusy(true);
				setSelectModal(null);
			},
		});
		session.setSelectRequest(null);
	}, [session.selectRequest]);

	// Intercept special commands that need interactive UI
	const handleCommand = (cmd: string): boolean => {
		const trimmed = cmd.trim();

		if (SELECTABLE_COMMANDS.has(trimmed)) {
			session.sendRequest({type: 'select_command', command: trimmed.slice(1)});
			return true;
		}

		// /permissions → show mode picker
		if (trimmed === '/permissions' || trimmed === '/permissions show') {
			session.sendRequest({type: 'select_command', command: 'permissions'});
			return true;
		}

		// /plan → toggle plan mode
		if (trimmed === '/plan') {
			const currentMode = String(session.status.permission_mode ?? 'default');
			if (currentMode === 'plan') {
				session.sendRequest({type: 'submit_line', line: '/plan off'});
			} else {
				session.sendRequest({type: 'submit_line', line: '/plan on'});
			}
			session.setBusy(true);
			return true;
		}

		// /resume → request session list from backend (will trigger select_request)
		if (trimmed === '/resume') {
			session.sendRequest({type: 'select_command', command: 'resume'});
			return true;
		}

		return false;
	};

	useInput((chunk, key) => {
		const isPaste = chunk.length > 1 && !key.ctrl && !key.meta;

		// Ctrl+C → exit
		if (key.ctrl && chunk === 'c') {
			session.sendRequest({type: 'shutdown'});
			exit();
			return;
		}

		// Let ink-text-input handle pasted text directly.
		if (isPaste) {
			return;
		}

		// --- Select modal (permissions picker etc.) ---
		if (selectModal) {
			if (key.upArrow) {
				setSelectIndex((i) => Math.max(0, i - 1));
				return;
			}
			if (key.downArrow) {
				setSelectIndex((i) => Math.min(selectModal.options.length - 1, i + 1));
				return;
			}
			if (key.return) {
				const selected = selectModal.options[selectIndex];
				if (selected) {
					selectModal.onSelect(selected.value);
				}
				return;
			}
			if (key.escape) {
				setSelectModal(null);
				return;
			}
			// Number keys for quick selection
			const num = parseInt(chunk, 10);
			if (num >= 1 && num <= selectModal.options.length) {
				const selected = selectModal.options[num - 1];
				if (selected) {
					selectModal.onSelect(selected.value);
				}
				return;
			}
			return;
		}

		// --- Scripted raw return ---
		if (rawReturnSubmit && key.return) {
			if (session.modal?.kind === 'question') {
				session.sendRequest({
					type: 'question_response',
					request_id: session.modal.request_id,
					answer: modalInput,
				});
				session.setModal(null);
				setModalInput('');
				return;
			}
			if (!session.modal && !session.busy && input.trim()) {
				onSubmit(input);
				return;
			}
		}

		// --- Permission modal (MUST be before busy check — modal appears while busy) ---
		if (session.modal?.kind === 'permission') {
			if (chunk.toLowerCase() === 'y') {
				session.sendRequest({
					type: 'permission_response',
					request_id: session.modal.request_id,
					allowed: true,
				});
				session.setModal(null);
				return;
			}
			if (chunk.toLowerCase() === 'n' || key.escape) {
				session.sendRequest({
					type: 'permission_response',
					request_id: session.modal.request_id,
					allowed: false,
				});
				session.setModal(null);
				return;
			}
			return;
		}

		// --- Question modal (also appears while busy) ---
		if (session.modal?.kind === 'question') {
			return; // Let TextInput in ModalHost handle input
		}

		// --- Ignore input while busy ---
		if (session.busy) {
			return;
		}

		// --- Command picker ---
		if (showPicker) {
			if (key.upArrow) {
				setPickerIndex((i) => Math.max(0, i - 1));
				return;
			}
			if (key.downArrow) {
				setPickerIndex((i) => Math.min(commandHints.length - 1, i + 1));
				return;
			}
			if (key.return) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setInput('');
					if (!handleCommand(selected)) {
						onSubmit(selected);
					}
				}
				return;
			}
			if (key.tab) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setInput(selected + ' ');
				}
				return;
			}
			if (key.escape) {
				setInput('');
				return;
			}
		}

		if (key.escape) {
			const now = Date.now();
			if (input && now - lastEscapeAt < 500) {
				setInput('');
				setHistoryIndex(-1);
				setLastEscapeAt(0);
				return;
			}
			setLastEscapeAt(now);
			return;
		}

		// --- History navigation ---
		if (!showPicker && key.upArrow) {
			const nextIndex = Math.min(history.length - 1, historyIndex + 1);
			if (nextIndex >= 0) {
				setHistoryIndex(nextIndex);
				setInput(history[history.length - 1 - nextIndex] ?? '');
			}
			return;
		}
		if (!showPicker && key.downArrow) {
			const nextIndex = Math.max(-1, historyIndex - 1);
			setHistoryIndex(nextIndex);
			setInput(nextIndex === -1 ? '' : (history[history.length - 1 - nextIndex] ?? ''));
			return;
		}

		// Note: normal Enter submission is handled by TextInput's onSubmit in
		// PromptInput.  Do NOT duplicate it here — that causes double requests.
	});

	const onSubmit = (value: string): void => {
		if (session.modal?.kind === 'question') {
			session.sendRequest({
				type: 'question_response',
				request_id: session.modal.request_id,
				answer: value,
			});
			session.setModal(null);
			setModalInput('');
			return;
		}
		if (!value.trim() || session.busy || !session.ready) {
			return;
		}
		// Check if it's an interactive command
		if (handleCommand(value)) {
			setHistory((items) => [...items, value]);
			setHistoryIndex(-1);
			setInput('');
			return;
		}
		session.sendRequest({type: 'submit_line', line: value});
		setHistory((items) => [...items, value]);
		setHistoryIndex(-1);
		setInput('');
		session.setBusy(true);
	};

	// Scripted automation
	useEffect(() => {
		if (scriptIndex >= scriptedSteps.length) {
			return;
		}
		if (session.busy || session.modal || selectModal) {
			return;
		}
		const step = scriptedSteps[scriptIndex];
		const timer = setTimeout(() => {
			onSubmit(step);
			setScriptIndex((index) => index + 1);
		}, 200);
		return () => clearTimeout(timer);
	}, [scriptIndex, session.busy, session.modal, selectModal]);

	return (
		<Box flexDirection="column" paddingX={1} height="100%">
			{/* Conversation area */}
			<Box flexDirection="column" flexGrow={1}>
				<ConversationView
					items={session.transcript}
					assistantBuffer={session.assistantBuffer}
					showWelcome={session.ready}
				/>
			</Box>

			{/* Backend modal (permission confirm, question, mcp auth) */}
			{session.modal ? (
				<ModalHost
					modal={session.modal}
					modalInput={modalInput}
					setModalInput={setModalInput}
					onSubmit={onSubmit}
				/>
			) : null}

			{/* Frontend select modal (permissions picker, etc.) */}
			{selectModal ? (
				<SelectModal
					title={selectModal.title}
					options={selectModal.options}
					selectedIndex={selectIndex}
				/>
			) : null}

			{/* Command picker */}
			{showPicker ? (
				<CommandPicker hints={commandHints} selectedIndex={pickerIndex} />
			) : null}

			{/* Todo panel */}
			{session.ready && session.todoMarkdown ? (
				<TodoPanel markdown={session.todoMarkdown} />
			) : null}

			{/* Swarm panel */}
			{session.ready && (session.swarmTeammates.length > 0 || session.swarmNotifications.length > 0) ? (
				<SwarmPanel teammates={session.swarmTeammates} notifications={session.swarmNotifications} />
			) : null}

			{/* Status bar (only after backend is ready) */}
			{session.ready ? (
				<StatusBar status={session.status} tasks={session.tasks} activeToolName={session.busy ? currentToolName : undefined} />
			) : null}

			{/* Input — show loading indicator until backend is ready */}
			{!session.ready ? (
				<Box>
					<Text color={theme.colors.warning}>Connecting to backend...</Text>
				</Box>
			) : session.modal || selectModal ? null : (
				<PromptInput
					busy={session.busy}
					input={input}
					setInput={setInput}
					onSubmit={onSubmit}
					toolName={session.busy ? currentToolName : undefined}
					statusLabel={session.busy ? (session.busyLabel ?? (currentToolName ? `Running ${currentToolName}...` : 'Running agent loop...')) : undefined}
					suppressSubmit={showPicker}
				/>
			)}

			{/* Keyboard hints (only after backend is ready) */}
			{session.ready && !session.modal && !selectModal ? (
				<Box>
					<Text dimColor>
						<Text color={theme.colors.primary}>enter</Text> send{'  '}
						<Text color={theme.colors.primary}>/</Text> commands{'  '}
						<Text color={theme.colors.primary}>{'\u2191\u2193'}</Text> history{'  '}
						<Text color={theme.colors.primary}>ctrl+c</Text> exit
					</Text>
				</Box>
			) : null}
		</Box>
	);
}
