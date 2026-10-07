import type { LegendEntry } from "./encode";

export function CommunityLegend({ entries }: { entries: readonly LegendEntry[] }) {
  return (
    <div className="gx-legend card" aria-label="Legend: research communities">
      <strong className="small">Community</strong>
      {entries.map((e) => (
        <div key={e.key} className="gx-legend-item">
          <span className="dot" style={{ background: e.colour }} aria-hidden="true" />
          <span title={e.label}>{e.label}</span>
          <span className="n">{e.count}</span>
        </div>
      ))}
    </div>
  );
}

export function YearLegend({ min, max, ramp }: { min: number; max: number; ramp: readonly string[] }) {
  return (
    <div className="gx-legend card" aria-label="Legend: publication year">
      <strong className="small">Publication year</strong>
      <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden" }} aria-hidden="true">
        {ramp.map((c) => (
          <span key={c} style={{ flex: 1, background: c }} />
        ))}
      </div>
      <div className="gx-legend-item small">
        <span>{min}</span>
        <span className="n">{max}</span>
      </div>
    </div>
  );
}
