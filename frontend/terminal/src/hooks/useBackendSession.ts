import {useEffect, useMemo, useRef, useState} from 'react';
import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import readline from 'node:readline';

import type {
	BackendEvent,
	BridgeSessionSnapshot,
	FrontendConfig,
	McpServerSnapshot,
	SelectOptionPayload,
	SwarmNotificationSnapshot,
	SwarmTeammateSnapshot,
	TaskSnapshot,
	TranscriptItem,
} from '../types.js';

const PROTOCOL_PREFIX = 'OHJSON:';
const ASSISTANT_DELTA_FLUSH_MS = 33;
const ASSISTANT_DELTA_FLUSH_CHARS = 256;

export function useBackendSession(config: FrontendConfig, onExit: (code?: number | null) => void) {
	const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
	const [assistantBuffer, setAssistantBuffer] = useState('');
	const [status, setStatus] = useState<Record<string, unknown>>({});
	const [tasks, setTasks] = useState<TaskSnapshot[]>([]);
	const [commands, setCommands] = useState<string[]>([]);
	const [mcpServers, setMcpServers] = useState<McpServerSnapshot[]>([]);
	const [bridgeSessions, setBridgeSessions] = useState<BridgeSessionSnapshot[]>([]);
	const [modal, setModal] = useState<Record<string, unknown> | null>(null);
	const [selectRequest, setSelectRequest] = useState<{title: string; command: string; options: SelectOptionPayload[]} | null>(null);
	const [busy, setBusy] = useState(false);
	const [busyLabel, setBusyLabel] = useState<string | undefined>(undefined);
	const [ready, setReady] = useState(false);
	const [todoMarkdown, setTodoMarkdown] = useState('');
	const [swarmTeammates, setSwarmTeammates] = useState<SwarmTeammateSnapshot[]>([]);
	const [swarmNotifications, setSwarmNotifications] = useState<SwarmNotificationSnapshot[]>([]);
	const childRef = useRef<ChildProcessWithoutNullStreams | null>(null);
	const sentInitialPrompt = useRef(false);

	// Streaming deltas can arrive one token at a time; updating Ink state for each
	// delta causes heavy re-rendering/flicker. Buffer and flush at ~30fps.
	const assistantBufferRef = useRef('');
	const pendingAssistantDeltaRef = useRef('');
	const assistantFlushTimerRef = useRef<NodeJS.Timeout | null>(null);

	const flushAssistantDelta = (): void => {
		const pending = pendingAssistantDeltaRef.current;
		if (!pending) {
			return;
		}
		pendingAssistantDeltaRef.current = '';
		assistantBufferRef.current += pending;
		setAssistantBuffer(assistantBufferRef.current);
	};

	const clearAssistantDelta = (): void => {
		pendingAssistantDeltaRef.current = '';
		assistantBufferRef.current = '';
		if (assistantFlushTimerRef.current) {
			clearTimeout(assistantFlushTimerRef.current);
			assistantFlushTimerRef.current = null;
		}
		setAssistantBuffer('');
	};

	const sendRequest = (payload: Record<string, unknown>): void => {
		const child = childRef.current;
		if (!child || child.stdin.destroyed) {
			return;
		}
		child.stdin.write(JSON.stringify(payload) + '\n');
	};

	useEffect(() => {
		const [command, ...args] = config.backend_command;
		const useDetachedGroup = process.platform !== 'win32';
		const child = spawn(command, args, {
			stdio: ['pipe', 'pipe', 'inherit'],
			env: process.env,
			// On Windows, a detached child gets its own console window and can
			// flash open/closed. Keep detached groups for POSIX only.
			detached: useDetachedGroup,
			windowsHide: true,
		});
		childRef.current = child;

		const reader = readline.createInterface({input: child.stdout});
		reader.on('line', (line) => {
			if (!line.startsWith(PROTOCOL_PREFIX)) {
				setTranscript((items) => [...items, {role: 'log', text: line}]);
				return;
			}
			const event = JSON.parse(line.slice(PROTOCOL_PREFIX.length)) as BackendEvent;
			handleEvent(event);
		});

		child.on('exit', (code) => {
			setTranscript((items) => [...items, {role: 'system', text: `backend exited with code ${code ?? 0}`}]);
			process.exitCode = code ?? 0;
			onExit(code);
		});

		// Ensure child processes are killed on parent exit (prevents stale processes)
		const killChild = (): void => {
			if (!child.killed) {
				// Kill the whole process group on POSIX. On Windows, terminate the
				// direct child to avoid relying on negative PIDs.
				try {
					if (useDetachedGroup && child.pid) {
						process.kill(-child.pid, 'SIGTERM');
					} else {
						child.kill('SIGTERM');
					}
				} catch {
					child.kill('SIGTERM');
				}
			}
			if (assistantFlushTimerRef.current) {
				clearTimeout(assistantFlushTimerRef.current);
				assistantFlushTimerRef.current = null;
			}
		};
		process.on('exit', killChild);
		process.on('SIGINT', killChild);
		process.on('SIGTERM', killChild);

		return () => {
			reader.close();
			killChild();
			process.removeListener('exit', killChild);
			process.removeListener('SIGINT', killChild);
			process.removeListener('SIGTERM', killChild);
		};
	}, []);

	const handleEvent = (event: BackendEvent): void => {
		if (event.type === 'ready') {
			setReady(true);
			setStatus(event.state ?? {});
			setTasks(event.tasks ?? []);
			setCommands(event.commands ?? []);
			setMcpServers(event.mcp_servers ?? []);
			setBridgeSessions(event.bridge_sessions ?? []);
			if (config.initial_prompt && !sentInitialPrompt.current) {
				sentInitialPrompt.current = true;
				sendRequest({type: 'submit_line', line: config.initial_prompt});
				setBusy(true);
			}
			return;
		}
		if (event.type === 'state_snapshot') {
			setStatus(event.state ?? {});
			setMcpServers(event.mcp_servers ?? []);
			setBridgeSessions(event.bridge_sessions ?? []);
			return;
		}
		if (event.type === 'tasks_snapshot') {
			setTasks(event.tasks ?? []);
			return;
		}
		if (event.type === 'transcript_item' && event.item) {
			setTranscript((items) => [...items, event.item as TranscriptItem]);
			return;
		}
		if (event.type === 'status') {
			const message = event.message?.trim();
			if (!message) {
				return;
			}
			setTranscript((items) => [...items, {role: 'status', text: message}]);
			if (busy) {
				setBusyLabel(message);
			}
			return;
		}
		if (event.type === 'compact_progress') {
			const phase = String(event.compact_phase ?? '');
			const trigger = String(event.compact_trigger ?? '');
			const attempt = event.attempt != null ? Number(event.attempt) : undefined;
			if (phase === 'hooks_start') {
				setBusyLabel(
					trigger === 'reactive'
						? 'Preparing retry compaction…'
						: 'Preparing conversation compaction…',
				);
			} else if (phase === 'context_collapse_start') {
				setBusyLabel('Collapsing oversized context…');
			} else if (phase === 'context_collapse_end') {
				setBusyLabel('Context collapse complete…');
			} else if (phase === 'session_memory_start') {
				setBusyLabel('Condensing earlier conversation…');
			} else if (phase === 'compact_start') {
				setBusyLabel(
					trigger === 'reactive'
						? 'Context is too large. Compacting and retrying…'
						: 'Compacting conversation memory…',
				);
			} else if (phase === 'compact_retry') {
				setBusyLabel(attempt ? `Retrying compaction (${attempt})…` : 'Retrying compaction…');
			} else if (phase === 'compact_end') {
				setBusyLabel('Compaction complete. Continuing…');
			} else if (phase === 'compact_failed') {
				setBusyLabel('Compaction failed. Continuing without it…');
			}
			if (event.message) {
				setTranscript((items) => [...items, {role: 'status', text: event.message!}]);
			}
			return;
		}
		if (event.type === 'assistant_delta') {
			const delta = event.message ?? '';
			if (!delta) {
				return;
			}
			pendingAssistantDeltaRef.current += delta;
			if (pendingAssistantDeltaRef.current.length >= ASSISTANT_DELTA_FLUSH_CHARS) {
				flushAssistantDelta();
				return;
			}
			if (!assistantFlushTimerRef.current) {
				assistantFlushTimerRef.current = setTimeout(() => {
					assistantFlushTimerRef.current = null;
					flushAssistantDelta();
				}, ASSISTANT_DELTA_FLUSH_MS);
			}
			return;
		}
		if (event.type === 'assistant_complete') {
			if (assistantFlushTimerRef.current) {
				clearTimeout(assistantFlushTimerRef.current);
				assistantFlushTimerRef.current = null;
			}
			flushAssistantDelta();
			const text = event.message ?? assistantBufferRef.current;
			setTranscript((items) => [...items, {role: 'assistant', text}]);
			clearAssistantDelta();
			// Do NOT reset busy here: tool calls may follow this event.
			// busy is reset by line_complete (the true end-of-turn signal).
			setBusyLabel(undefined);
			return;
		}
		if (event.type === 'line_complete') {
			// Final end-of-turn: clear everything, stop spinner.
			clearAssistantDelta();
			setBusy(false);
			setBusyLabel(undefined);
			return;
		}
		if ((event.type === 'tool_started' || event.type === 'tool_completed') && event.item) {
			if (event.type === 'tool_started') {
				setBusy(true);
				setBusyLabel(`Running ${event.tool_name ?? 'tool'}...`);
			} else {
				setBusyLabel('Processing...');
			}
			const enrichedItem: TranscriptItem = {
				...event.item,
				tool_name: event.item.tool_name ?? event.tool_name ?? undefined,
				tool_input: event.item.tool_input ?? undefined,
				is_error: event.item.is_error ?? event.is_error ?? undefined,
			};
			setTranscript((items) => [...items, enrichedItem]);
			return;
		}
		if (event.type === 'clear_transcript') {
			setTranscript([]);
			clearAssistantDelta();
			setBusyLabel(undefined);
			return;
		}
		if (event.type === 'select_request') {
			const m = event.modal ?? {};
			setSelectRequest({
				title: String(m.title ?? 'Select'),
				command: String(m.command ?? ''),
				options: event.select_options ?? [],
			});
			return;
		}
		if (event.type === 'modal_request') {
			setModal(event.modal ?? null);
			return;
		}
		if (event.type === 'error') {
			setTranscript((items) => [...items, {role: 'system', text: `error: ${event.message ?? 'unknown error'}`}]);
			clearAssistantDelta();
			setBusy(false);
			setBusyLabel(undefined);
			return;
		}
		if (event.type === 'todo_update') {
			if (event.todo_markdown != null) {
				setTodoMarkdown(event.todo_markdown);
			}
			return;
		}
		if (event.type === 'swarm_status') {
			if (event.swarm_teammates != null) {
				setSwarmTeammates(event.swarm_teammates);
			}
			if (event.swarm_notifications != null) {
				setSwarmNotifications((prev) => [...prev, ...event.swarm_notifications!].slice(-20));
			}
			return;
		}
		if (event.type === 'plan_mode_change') {
			if (event.plan_mode != null) {
				setStatus((s) => ({...s, permission_mode: event.plan_mode}));
			}
			return;
		}
		if (event.type === 'shutdown') {
			onExit(0);
		}
	};

	return useMemo(
		() => ({
			transcript,
			assistantBuffer,
			status,
			tasks,
			commands,
			mcpServers,
			bridgeSessions,
			modal,
			selectRequest,
			busy,
			busyLabel,
			ready,
			todoMarkdown,
			swarmTeammates,
			swarmNotifications,
			setModal,
			setSelectRequest,
			setBusy,
			sendRequest,
		}),
		[assistantBuffer, bridgeSessions, busy, busyLabel, commands, mcpServers, modal, ready, selectRequest, status, swarmNotifications, swarmTeammates, tasks, todoMarkdown, transcript]
	);
}
