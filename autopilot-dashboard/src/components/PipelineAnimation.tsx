/**
 * PipelineAnimation — a rich, orbital visualization of the autopilot pipeline.
 *
 * Central hub surrounded by 5 stage nodes in a circuit layout, with
 * data packets flowing through connecting paths, background grid,
 * ambient particles, and pulsing energy rings. Fills the entire
 * container with minimal dead space.
 */
export function PipelineAnimation() {
  const cx = 200;
  const cy = 105;
  const rx = 145;
  const ry = 65;

  const stages = [
    { label: "QUEUE", angle: Math.PI },
    { label: "PREP", angle: Math.PI + Math.PI * 2 / 5 },
    { label: "RUN", angle: Math.PI + (Math.PI * 2 / 5) * 2 },
    { label: "CHECK", angle: Math.PI + (Math.PI * 2 / 5) * 3 },
    { label: "MERGE", angle: Math.PI + (Math.PI * 2 / 5) * 4 },
  ].map((s) => ({
    ...s,
    x: cx + Math.cos(s.angle) * rx,
    y: cy + Math.sin(s.angle) * ry,
  }));

  // Build the orbital path for traveling packets
  const orbitPath = stages
    .map((s, i) => `${i === 0 ? "M" : "L"} ${s.x.toFixed(1)} ${s.y.toFixed(1)}`)
    .join(" ") + " Z";

  // Ambient floating particles
  const particles = [
    { x: 40, y: 30, r: 1.2, dur: 3, d: 0 },
    { x: 340, y: 50, r: 0.8, dur: 4, d: 1 },
    { x: 80, y: 170, r: 1, dur: 3.5, d: 2 },
    { x: 320, y: 160, r: 1.3, dur: 2.8, d: 0.5 },
    { x: 170, y: 25, r: 0.7, dur: 4.2, d: 1.5 },
    { x: 250, y: 185, r: 0.9, dur: 3.2, d: 3 },
    { x: 120, y: 100, r: 0.6, dur: 5, d: 2.5 },
    { x: 300, y: 110, r: 1.1, dur: 3.8, d: 0.8 },
    { x: 50, y: 120, r: 0.8, dur: 4.5, d: 1.2 },
    { x: 370, y: 90, r: 0.7, dur: 3.6, d: 2.2 },
  ];

  // Background grid lines
  const hLines = [35, 70, 105, 140, 175];
  const vLines = [40, 80, 120, 160, 200, 240, 280, 320, 360];

  return (
    <svg
      viewBox="0 0 400 210"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Autopilot pipeline"
      style={{ width: "100%", height: "100%" }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <radialGradient id="pipe-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.85" />
          <stop offset="40%" stopColor="#00d4aa" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="hub-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00d4aa" stopOpacity="0.15" />
          <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="edge-fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#00d4aa" stopOpacity="0" />
          <stop offset="50%" stopColor="#00d4aa" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#00d4aa" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Background grid */}
      {hLines.map((y, i) => (
        <line key={`h${i}`} x1="0" y1={y} x2="400" y2={y}
          stroke="#00d4aa" strokeOpacity="0.04" strokeWidth="1" />
      ))}
      {vLines.map((x, i) => (
        <line key={`v${i}`} x1={x} y1="0" x2={x} y2="210"
          stroke="#00d4aa" strokeOpacity="0.04" strokeWidth="1" />
      ))}

      {/* Central radial glow */}
      <circle cx={cx} cy={cy} r="80" fill="url(#hub-glow)" />

      {/* Orbital ring (background) */}
      <path d={orbitPath} fill="none" stroke="#00d4aa" strokeOpacity="0.08" strokeWidth="1" />

      {/* Animated dashed orbital ring */}
      <path d={orbitPath} fill="none" stroke="#00d4aa" strokeOpacity="0.18"
        strokeWidth="1" strokeDasharray="4 8">
        <animate attributeName="stroke-dashoffset" values="0;-24" dur="2s" repeatCount="indefinite" />
      </path>

      {/* Spokes from center to each node */}
      {stages.map((s, i) => (
        <g key={`spoke-${i}`}>
          <line x1={cx} y1={cy} x2={s.x} y2={s.y}
            stroke="#00d4aa" strokeOpacity="0.06" strokeWidth="1" />
          {/* Data pulse along spoke */}
          <circle r="1.5" fill="#00d4aa">
            <animateMotion
              dur="2s"
              begin={`${i * 0.4}s`}
              repeatCount="indefinite"
              path={`M ${cx} ${cy} L ${s.x} ${s.y}`}
            />
            <animate attributeName="opacity" values="0;0.8;0.8;0"
              keyTimes="0;0.1;0.8;1" dur="2s" begin={`${i * 0.4}s`} repeatCount="indefinite" />
          </circle>
        </g>
      ))}

      {/* Stage nodes */}
      {stages.map((s, i) => {
        const colors = ["#64748b", "#0f766e", "#00d4aa", "#3b82f6", "#8b5cf6"];
        const c = colors[i];
        return (
          <g key={s.label}>
            {/* Node glow */}
            <circle cx={s.x} cy={s.y} r="28" fill="url(#node-glow)" />

            {/* Outer ring */}
            <circle cx={s.x} cy={s.y} r="18" fill="#0a0a0a"
              stroke={c} strokeOpacity="0.5" strokeWidth="1" />

            {/* Corner brackets */}
            <g stroke={c} strokeOpacity="0.7" strokeWidth="1" strokeLinecap="round">
              <path d={`M ${s.x-13} ${s.y-13} l 5 0 M ${s.x-13} ${s.y-13} l 0 5`} />
              <path d={`M ${s.x+13} ${s.y-13} l -5 0 M ${s.x+13} ${s.y-13} l 0 5`} />
              <path d={`M ${s.x-13} ${s.y+13} l 5 0 M ${s.x-13} ${s.y+13} l 0 -5`} />
              <path d={`M ${s.x+13} ${s.y+13} l -5 0 M ${s.x+13} ${s.y+13} l 0 -5`} />
            </g>

            {/* Inner pulsing dot */}
            <circle cx={s.x} cy={s.y} r="4" fill={c}>
              <animate attributeName="r" values="4;6;4" dur="2.4s"
                begin={`${i * 0.5}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.5;1;0.5" dur="2.4s"
                begin={`${i * 0.5}s`} repeatCount="indefinite" />
            </circle>

            {/* Expanding pulse ring */}
            <circle cx={s.x} cy={s.y} r="18" fill="none" stroke={c} strokeWidth="1">
              <animate attributeName="r" values="18;30" dur="3s"
                begin={`${i * 0.6}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.45;0" dur="3s"
                begin={`${i * 0.6}s`} repeatCount="indefinite" />
            </circle>

            {/* Label */}
            <text x={s.x} y={s.y + 30} fontSize="7" fill={c} fillOpacity="0.7"
              textAnchor="middle" fontFamily="JetBrains Mono, monospace"
              letterSpacing="1.5" fontWeight="700">
              {s.label}
            </text>
          </g>
        );
      })}

      {/* Central hub */}
      <circle cx={cx} cy={cy} r="14" fill="#0a0a0a" stroke="#00d4aa" strokeOpacity="0.6" strokeWidth="1.2" />
      <circle cx={cx} cy={cy} r="14" fill="none" stroke="#00d4aa" strokeWidth="1">
        <animate attributeName="r" values="14;22" dur="2.4s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.4;0" dur="2.4s" repeatCount="indefinite" />
      </circle>
      {/* Hub icon — infinity / loop symbol */}
      <text x={cx} y={cy + 4} fontSize="11" fill="#00d4aa" fillOpacity="0.9"
        textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontWeight="700">
        &#x221E;
      </text>

      {/* Traveling packet 1 — clockwise */}
      <circle r="16" fill="url(#pipe-glow)" opacity="0.6">
        <animateMotion dur="5s" repeatCount="indefinite" path={orbitPath} rotate="auto" />
      </circle>
      <circle r="3.5" fill="#00d4aa">
        <animateMotion dur="5s" repeatCount="indefinite" path={orbitPath} rotate="auto" />
        <animate attributeName="r" values="3.5;2.5;3.5" dur="1s" repeatCount="indefinite" />
      </circle>

      {/* Traveling packet 2 — offset, different speed */}
      <circle r="10" fill="url(#pipe-glow)" opacity="0.35">
        <animateMotion dur="7s" begin="2.5s" repeatCount="indefinite" path={orbitPath} rotate="auto" />
      </circle>
      <circle r="2" fill="#8b5cf6">
        <animateMotion dur="7s" begin="2.5s" repeatCount="indefinite" path={orbitPath} rotate="auto" />
        <animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
      </circle>

      {/* Ambient particles */}
      {particles.map((p, i) => (
        <circle key={`p${i}`} cx={p.x} cy={p.y} r={p.r}
          fill={i % 3 === 0 ? "#8b5cf6" : "#00d4aa"}>
          <animate attributeName="opacity" values="0.05;0.25;0.05"
            dur={`${p.dur}s`} begin={`${p.d}s`} repeatCount="indefinite" />
          <animate attributeName="r" values={`${p.r};${p.r * 1.5};${p.r}`}
            dur={`${p.dur}s`} begin={`${p.d}s`} repeatCount="indefinite" />
        </circle>
      ))}

      {/* Scan line */}
      <line x1="0" y1="0" x2="400" y2="0" stroke="#00d4aa" strokeOpacity="0" strokeWidth="1">
        <animateTransform attributeName="transform" type="translate"
          from="0 0" to="0 210" dur="4s" repeatCount="indefinite" />
        <animate attributeName="stroke-opacity" values="0;0.12;0.12;0"
          keyTimes="0;0.05;0.95;1" dur="4s" repeatCount="indefinite" />
      </line>

      {/* Bottom caption */}
      <text x={cx} y="204" fontSize="7" fill="#00d4aa" fillOpacity="0.4"
        textAnchor="middle" fontFamily="JetBrains Mono, monospace" letterSpacing="2.5">
        AUTOPILOT · PIPELINE
      </text>
    </svg>
  );
}
