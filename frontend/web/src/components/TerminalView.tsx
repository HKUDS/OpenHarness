import { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import 'xterm/css/xterm.css';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/TerminalView.module.css';

export function TerminalView() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const { messages, sessionState } = useAppStore();

  useEffect(() => {
    if (!terminalRef.current || xtermRef.current) return;

    const term = new XTerm({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'JetBrains Mono, Fira Code, Consolas, monospace',
      theme: {
        background: '#0f0f0f',
        foreground: '#e0e0e0',
        cursor: '#00ff00',
        cursorAccent: '#000000',
        black: '#000000',
        red: '#ff5555',
        green: '#50fa7b',
        yellow: '#f1fa8c',
        blue: '#bd93f9',
        magenta: '#ff79c6',
        cyan: '#8be9fd',
        white: '#bfbfbf',
        brightBlack: '#4d4d4d',
        brightRed: '#ff6e67',
        brightGreen: '#5af78e',
        brightYellow: '#f4f99d',
        brightBlue: '#caa9ff',
        brightMagenta: '#ff92d0',
        brightCyan: '#9aedfe',
        brightWhite: '#e6e6e6',
      },
      convertEol: true,
      scrollback: 10000,
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();
    
    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);
    term.open(terminalRef.current);
    fitAddon.fit();

    xtermRef.current = term;

    const handleResize = () => fitAddon.fit();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      term.dispose();
      xtermRef.current = null;
    };
  }, []);

  useEffect(() => {
    const term = xtermRef.current;
    if (!term) return;

    // Clear and render all messages
    term.clear();
    
    messages.forEach((message) => {
      const rolePrefix = message.role === 'user' ? '\x1b[36m❯\x1b[0m ' :
                         message.role === 'assistant' ? '\x1b[32m●\x1b[0m ' :
                         message.role === 'system' ? '\x1b[33m!\x1b[0m ' :
                         message.role === 'tool' ? '\x1b[35m⚙\x1b[0m ' : '';
      
      term.writeln(`${rolePrefix}${message.content}`);
      
      if (message.tool_input) {
        term.writeln(`\x1b[90m${JSON.stringify(message.tool_input, null, 2)}\x1b[0m`);
      }
      
      term.writeln('');
    });

    term.scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const term = xtermRef.current;
    if (!term) return;

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    fitAddon.fit();
  }, []);

  return (
    <div className={styles.terminalView}>
      <div className={styles.terminalHeader}>
        <span className={styles.terminalTitle}>
          {sessionState?.working_directory || '~/workspace'}
        </span>
        <div className={styles.terminalControls}>
          <span className={styles.controlDot} />
          <span className={styles.controlDot} />
          <span className={styles.controlDot} />
        </div>
      </div>
      <div ref={terminalRef} className={styles.terminalContainer} />
    </div>
  );
}
