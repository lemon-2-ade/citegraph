import { useState } from "react";

export interface BarDatum {
  key: string;
  label: string;
  value: number;
  colour: string;
  detail?: string;
}

/** Horizontal bars with the label and value written out, so colour is never the only identity. */
export function BarList({ data, unit }: { data: readonly BarDatum[]; unit: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="bars">
      {data.map((d) => (
        <div key={d.key} className="bar-row" title={d.detail}>
          <span className="bar-label">
            <span className="dot" style={{ background: d.colour }} aria-hidden="true" />
            <span>{d.label}</span>
          </span>
          <span className="bar-value">
            {d.value} {unit}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(d.value / max) * 100}%`, background: d.colour, display: "block" }} />
          </span>
        </div>
      ))}
    </div>
  );
}

export interface ColumnDatum {
  label: string;
  value: number;
}

/** Single-series column chart with a hover tooltip; the exact values are in the accessible table. */
export function ColumnChart({ data, colour, unit, caption }: { data: readonly ColumnDatum[]; colour: string; unit: string; caption: string }) {
  const [active, setActive] = useState<number | null>(null);
  const W = 640;
  const H = 190;
  const m = { top: 12, right: 8, bottom: 24, left: 30 };
  const max = Math.max(1, ...data.map((d) => d.value));
  const niceMax = Math.ceil(max / 5) * 5 || 5;
  const iw = W - m.left - m.right;
  const ih = H - m.top - m.bottom;
  const step = iw / Math.max(1, data.length);
  const bw = Math.max(4, Math.min(34, step * 0.62));
  const ticks = [0, niceMax / 2, niceMax];
  const labelEvery = Math.ceil(data.length / 8);
  const a = active !== null ? data[active] : undefined;
  return (
    <div style={{ position: "relative" }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={caption}>
        {ticks.map((t) => {
          const y = m.top + ih - (t / niceMax) * ih;
          return (
            <g key={t}>
              <line x1={m.left} x2={W - m.right} y1={y} y2={y} stroke="var(--grid)" strokeWidth={1} />
              <text x={m.left - 6} y={y + 4} textAnchor="end">
                {t}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const h = (d.value / niceMax) * ih;
          const x = m.left + i * step + (step - bw) / 2;
          const y = m.top + ih - h;
          return (
            <g key={d.label} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}>
              <rect x={m.left + i * step} y={m.top} width={step} height={ih} fill="transparent" />
              {d.value > 0 && (
                <path
                  d={`M${x},${m.top + ih} V${y + 4} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 V${m.top + ih} Z`}
                  fill={colour}
                  opacity={active === null || active === i ? 1 : 0.55}
                />
              )}
              {i % labelEvery === 0 && (
                <text x={x + bw / 2} y={H - 6} textAnchor="middle">
                  {d.label}
                </text>
              )}
            </g>
          );
        })}
        <line x1={m.left} x2={W - m.right} y1={m.top + ih} y2={m.top + ih} stroke="var(--axis)" strokeWidth={1} />
      </svg>
      {a && active !== null && (
        <div className="chart-tip" style={{ left: `${((m.left + active * step + step / 2) / W) * 100}%`, top: 4 }}>
          {a.label}: {a.value} {unit}
        </div>
      )}
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <th scope="row">{d.label}</th>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
