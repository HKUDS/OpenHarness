import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp, useInput} from 'ink';

import {CommandPicker} from './components/CommandPicker.js';
import {ConversationView} from './components/ConversationView.js';
import {ModalHost} from './components/ModalHost.js';
import {PromptInput} from './components/PromptInput.js';
import {SelectModal, type SelectOption} from './components/SelectModal.js';
import {StatusBar} from './components/StatusBar.js';
import {useBackendSession} from './hooks/useBackendSession.js';
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

const PERMISSION_MODES: SelectOption[] = [
	{value: 'default', label: 'Default', description: 'Ask before write/execute operations'},
	{value: 'full_auto', label: 'Auto', description: 'Allow all tools automatically'},
	{value: 'plan', label: 'Plan Mode', description: 'Block all write operations'},
];

type SelectModalState = {
	title: string;
	options: SelectOption[];
	onSelect: (value: string) => void;
} | null;

export function App({config}: {config: FrontendConfig}): React.JSX.Element {
	const {exit} = useApp();
	const [input, setInput] = useState('');
	const [modalInput, setModalInput] = useState('');
	const [history, setHistory] = useState<string[]>([]);
	const [historyIndex, setHistoryIndex] = useState(-1);
	const [scriptIndex, setScriptIndex] = useState(0);
	const [pickerIndex, setPickerIndex] = useState(0);
	const [selectModal, setSelectModal] = useState<SelectModalState>(null);
	const [selectIndex, setSelectIndex] = useState(0);
	const session = useBackendSession(config, () => exit());

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
		setSelectIndex(0);
		setSelectModal({
			title: req.title,
			options: req.options.map((o) => ({value: o.value, label: o.label, description: o.description})),
			onSelect: (value) => {
				session.sendRequest({type: 'submit_line', line: `${req.submitPrefix}${value}`});
				session.setBusy(true);
				setSelectModal(null);
			},
		});
		session.setSelectRequest(null);
	}, [session.selectRequest]);

	// Intercept special commands that need interactive UI
	const handleCommand = (cmd: string): boolean => {
		const trimmed = cmd.trim();

		// /permissions → show mode picker
		if (trimmed === '/permissions' || trimmed === '/permissions show') {
			const currentMode = String(session.status.permission_mode ?? 'default');
			const options = PERMISSION_MODES.map((opt) => ({
				...opt,
				active: opt.value === currentMode,
			}));
			const initialIndex = options.findIndex((o) => o.active);
			setSelectIndex(initialIndex >= 0 ? initialIndex : 0);
			setSelectModal({
				title: 'Permission Mode',
				options,
				onSelect: (value) => {
					session.sendRequest({type: 'submit_line', line: `/permissions set ${value}`});
					session.setBusy(true);
					setSelectModal(null);
				},
			});
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
			session.sendRequest({type: 'list_sessions'});
			return true;
		}

		return false;
	};

	useInput((chunk, key) => {
		// Ctrl+C → exit
		if (key.ctrl && chunk === 'c') {
			session.sendRequest({type: 'shutdown'});
			exit();
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

		// --- Permission modal ---
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
		if (!value.trim() || session.busy) {
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
					showWelcome={true}
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

			{/* Status bar */}
			<StatusBar status={session.status} tasks={session.tasks} />

			{/* Input */}
			{session.modal || selectModal ? null : (
				<PromptInput
					busy={session.busy}
					input={input}
					setInput={setInput}
					onSubmit={onSubmit}
					toolName={session.busy ? currentToolName : undefined}
					suppressSubmit={showPicker}
				/>
			)}

			{/* Keyboard hints */}
			{!session.modal && !session.busy && !selectModal ? (
				<Box>
					<Text dimColor>
						<Text color="cyan">enter</Text> send{'  '}
						<Text color="cyan">/</Text> commands{'  '}
						<Text color="cyan">{'\u2191\u2193'}</Text> history{'  '}
						<Text color="cyan">ctrl+c</Text> exit
					</Text>
				</Box>
			) : null}
		</Box>
	);
}
