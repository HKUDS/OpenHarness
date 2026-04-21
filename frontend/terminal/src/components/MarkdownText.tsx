import React from 'react';
import {Box, Text} from 'ink';
import {lexer, type Token, type Tokens} from 'marked';
import stringWidth from 'string-width';

import {useTheme} from '../theme/ThemeContext.js';
import type {ThemeConfig} from '../theme/builtinThemes.js';

function getInlineFallbackText(token: Token): string {
	if ('text' in token && typeof token.text === 'string') {
		return token.text;
	}

	return token.raw;
}

function getInlineDisplayText(tokens: Token[] | undefined): string {
	if (!tokens || tokens.length === 0) {
		return '';
	}

	return tokens.map((token) => {
		switch (token.type) {
			case 'text': {
				const t = token as Tokens.Text;
				return t.tokens && t.tokens.length > 0 ? getInlineDisplayText(t.tokens) : t.text;
			}
			case 'strong':
			case 'em':
			case 'del':
				return getInlineDisplayText((token as Tokens.Strong | Tokens.Em | Tokens.Del).tokens);
			case 'codespan':
				return (token as Tokens.Codespan).text;
			case 'link': {
				const l = token as Tokens.Link;
				return l.text || l.href;
			}
			case 'image': {
				const image = token as Tokens.Image;
				return image.text || image.href;
			}
			case 'br':
				return '\n';
			case 'escape':
				return (token as Tokens.Escape).text;
			default:
				return getInlineFallbackText(token);
		}
	}).join('');
}

function getTableCellDisplayText(cell: Tokens.TableCell): string {
	const displayText = getInlineDisplayText(cell.tokens);
	return displayText.length > 0 ? displayText : cell.text;
}

// Inline token renderer — returns an array of <Text> elements.
function renderInline(tokens: Token[] | undefined, theme: ThemeConfig): React.ReactNode {
	if (!tokens || tokens.length === 0) {
		return null;
	}
	return tokens.map((token, i) => {
		switch (token.type) {
			case 'text': {
				const t = token as Tokens.Text;
				// Text tokens can themselves contain inline children, such as list items.
				if (t.tokens && t.tokens.length > 0) {
					return <React.Fragment key={i}>{renderInline(t.tokens, theme)}</React.Fragment>;
				}
				return <Text key={i}>{t.text}</Text>;
			}
			case 'strong': {
				const s = token as Tokens.Strong;
				return (
					<Text key={i} bold>
						{renderInline(s.tokens, theme)}
					</Text>
				);
			}
			case 'em': {
				const e = token as Tokens.Em;
				return (
					<Text key={i} italic>
						{renderInline(e.tokens, theme)}
					</Text>
				);
			}
			case 'del': {
				const d = token as Tokens.Del;
				return (
					<Text key={i} strikethrough>
						{renderInline(d.tokens, theme)}
					</Text>
				);
			}
			case 'codespan': {
				const c = token as Tokens.Codespan;
				return (
					<Text key={i} color={theme.colors.accent}>
						{c.text}
					</Text>
				);
			}
			case 'link': {
				const l = token as Tokens.Link;
				const label = l.text || l.href;
				return (
					<Text key={i} color={theme.colors.info}>
						{label}
					</Text>
				);
			}
			case 'image': {
				const image = token as Tokens.Image;
				return <Text key={i}>{image.text || image.href}</Text>;
			}
			case 'br':
				return <Text key={i}>{'\n'}</Text>;
			case 'escape': {
				const es = token as Tokens.Escape;
				return <Text key={i}>{es.text}</Text>;
			}
			default:
				return <Text key={i}>{getInlineFallbackText(token)}</Text>;
		}
	});
}

function renderBlocks(tokens: Token[] | undefined, theme: ThemeConfig): React.ReactNode {
	if (!tokens || tokens.length === 0) {
		return null;
	}

	return tokens.map((token, i) => (
		<MarkdownBlock key={i} token={token} theme={theme} />
	));
}

function MarkdownBlock({
	token,
	theme,
}: {
	token: Token;
	theme: ThemeConfig;
}): React.JSX.Element | null {
	switch (token.type) {
		case 'heading': {
			const h = token as Tokens.Heading;
			const headingColors: string[] = [
				theme.colors.primary,
				theme.colors.secondary,
				theme.colors.accent,
				theme.colors.info,
				theme.colors.muted,
				theme.colors.muted,
			];
			const color = headingColors[h.depth - 1] ?? theme.colors.primary;
			const isMajor = h.depth <= 2;
			return (
				<Box marginTop={1} flexDirection="column">
					<Text color={color} bold={isMajor} underline={h.depth === 1}>
						{renderInline(h.tokens, theme)}
					</Text>
					{h.depth === 1 ? <Text color={color} dimColor>{'━'.repeat(32)}</Text> : null}
				</Box>
			);
		}

		case 'paragraph': {
			const p = token as Tokens.Paragraph;
			return (
				<Box marginTop={0} flexWrap="wrap">
					<Text>{renderInline(p.tokens, theme)}</Text>
				</Box>
			);
		}

		case 'code': {
			const c = token as Tokens.Code;
			const lines = c.text.split('\n');
			return (
				<Box flexDirection="column" marginTop={1} marginLeft={2} borderStyle="round" paddingX={1} borderColor={theme.colors.muted}>
					{c.lang ? (
						<Text dimColor>{c.lang}</Text>
					) : null}
					{lines.map((line, i) => (
						<Text key={i} color={theme.colors.accent}>
							{line}
						</Text>
					))}
				</Box>
			);
		}

		case 'blockquote': {
			const bq = token as Tokens.Blockquote;
			return (
				<Box flexDirection="column" marginTop={0} marginLeft={0}>
					{bq.tokens.map((t, i) => (
						<Box key={i} flexDirection="row">
							<Text color={theme.colors.muted}>{'│ '}</Text>
							<Box flexDirection="column" flexGrow={1}>
								{renderBlocks([t], theme)}
							</Box>
						</Box>
					))}
				</Box>
			);
		}

		case 'list': {
			const l = token as Tokens.List;
			return (
				<Box flexDirection="column" marginTop={0} marginLeft={2}>
					{l.items.map((item, i) => {
						// For tight lists, item.tokens = [{type:'text', tokens:[...inline]}]
						// For loose lists, item.tokens = [{type:'paragraph', tokens:[...inline]}]
						const inlineTokens: Token[] = item.tokens.flatMap((t) =>
							'tokens' in t && t.tokens ? (t.tokens as Token[]) : [],
						);
						const bullet = l.ordered ? `${(Number(l.start) || 1) + i}. ` : '• ';
						return (
							<Box key={i} flexDirection="row">
								<Text color={theme.colors.primary}>{bullet}</Text>
								<Box flexGrow={1}>
									<Text>
										{inlineTokens.length > 0
											? renderInline(inlineTokens, theme)
											: item.text}
									</Text>
								</Box>
							</Box>
						);
					})}
				</Box>
			);
		}

		case 'hr':
			return (
				<Box marginTop={1}>
					<Text dimColor>{'─'.repeat(48)}</Text>
				</Box>
			);

		case 'space':
			return null;

		case 'table': {
			const t = token as Tokens.Table;
			const headerTexts = t.header.map(getTableCellDisplayText);
			const rowTexts = t.rows.map((row) => row.map(getTableCellDisplayText));
			// Use stringWidth for correct CJK and wide-char column widths.
			const colCount = t.header.length;
			const colWidths: number[] = headerTexts.map((cellText) => stringWidth(cellText));
			for (const row of rowTexts) {
				for (let c = 0; c < colCount; c++) {
					colWidths[c] = Math.max(colWidths[c] ?? 0, stringWidth(row[c] ?? ''));
				}
			}
			const trailing = (cellText: string, c: number): string =>
				' '.repeat(Math.max(0, (colWidths[c] ?? 0) - stringWidth(cellText)));
			const top = '┌' + colWidths.map((w) => '─'.repeat(w + 2)).join('┬') + '┐';
			const mid = '├' + colWidths.map((w) => '─'.repeat(w + 2)).join('┼') + '┤';
			const bot = '└' + colWidths.map((w) => '─'.repeat(w + 2)).join('┴') + '┘';
			return (
				<Box flexDirection="column" marginTop={1} marginLeft={1}>
					<Text color={theme.colors.muted}>{top}</Text>
					<Text>
						<Text color={theme.colors.muted}>{'│'}</Text>
						{t.header.map((cell, c) => (
							<React.Fragment key={c}>
								<Text color={theme.colors.primary} bold>
									{' '}{renderInline(cell.tokens, theme)}{trailing(headerTexts[c] ?? '', c)}{' '}
								</Text>
								<Text color={theme.colors.muted}>{'│'}</Text>
							</React.Fragment>
						))}
					</Text>
					<Text color={theme.colors.muted}>{mid}</Text>
					{t.rows.map((row, i) => (
						<Text key={i}>
							<Text color={theme.colors.muted}>{'│'}</Text>
							{row.map((cell, c) => (
								<React.Fragment key={c}>
									<Text>
										{' '}{renderInline(cell.tokens, theme)}{trailing(rowTexts[i]?.[c] ?? '', c)}{' '}
									</Text>
									<Text color={theme.colors.muted}>{'│'}</Text>
								</React.Fragment>
							))}
						</Text>
					))}
					<Text color={theme.colors.muted}>{bot}</Text>
				</Box>
			);
		}

		default:
			if ((token as Token).raw) {
				return <Text>{(token as Token).raw}</Text>;
			}
			return null;
	}
}

export const MarkdownText = React.memo(function MarkdownText({content}: {content: string}): React.JSX.Element {
	const {theme} = useTheme();
	const tokens = React.useMemo(() => lexer(content), [content]);
	return (
		<Box flexDirection="column">
			{renderBlocks(tokens, theme)}
		</Box>
	);
});
