import {useEffect, useMemo, useState} from 'react';
import {useStdout} from 'ink';

const DEFAULT_TERMINAL_COLUMNS = 80;
const DEFAULT_RESERVED_COLUMNS = 2;
const MIN_RULE_LENGTH = 16;

function normalizeColumns(columns: unknown): number {
	const value = Number(columns);
	return Number.isFinite(value) && value > 0 ? Math.floor(value) : DEFAULT_TERMINAL_COLUMNS;
}

export function useTerminalColumns(): number {
	const {stdout} = useStdout();
	const [columns, setColumns] = useState(() => normalizeColumns(stdout.columns));

	useEffect(() => {
		const updateColumns = (): void => {
			setColumns(normalizeColumns(stdout.columns));
		};

		updateColumns();
		stdout.on('resize', updateColumns);

		return () => {
			stdout.off('resize', updateColumns);
		};
	}, [stdout]);

	return columns;
}

export function useHorizontalRule(options?: {reservedColumns?: number; minLength?: number; char?: string}): string {
	const columns = useTerminalColumns();
	const reservedColumns = options?.reservedColumns ?? DEFAULT_RESERVED_COLUMNS;
	const minLength = options?.minLength ?? MIN_RULE_LENGTH;
	const char = options?.char ?? '─';

	return useMemo(() => {
		const length = Math.max(minLength, columns - reservedColumns);
		return char.repeat(length);
	}, [char, columns, minLength, reservedColumns]);
}
