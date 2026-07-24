import { useState } from "react";
import type { Idea } from "../../data";
import { formatUsd } from "../../lib/format";
import { useTooltip } from "./useTooltip";

const WIDTH = 640;
const MARGIN = { top: 10, right: 74, bottom: 30, left: 214 };
const ROW_H = 46;
const BAR_H = 22;
const RADIUS = 4;
const RECOMMENDED_RANK_CEILING = 3;
const DOMAIN_MAX = 5000;
const TICKS = [0, 1000, 2000, 3000, 4000, 5000];

function roundedRightBar(x0: number, y0: number, x1: number, h: number, r: number) {
  const rr = Math.min(r, Math.max(0, x1 - x0));
  return `M${x0},${y0} L${x1 - rr},${y0} Q${x1},${y0} ${x1},${y0 + rr} L${x1},${y0 + h - rr} Q${x1},${y0 + h} ${x1 - rr},${y0 + h} L${x0},${y0 + h} Z`;
}

export function PrizeBars({ ideas }: { ideas: Idea[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const { containerRef, tooltip, show, hide } = useTooltip<Idea>();

  const sorted = [...ideas].sort((a, b) => b.prizePotentialUsd - a.prizePotentialUsd);
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
  const height = MARGIN.top + MARGIN.bottom + sorted.length * ROW_H;

  function xScale(v: number) {
    return MARGIN.left + (v / DOMAIN_MAX) * plotWidth;
  }

  return (
    <div className="chart-card">
      <div className="chart-card-head">
        <div>
          <h3 className="chart-title">Prize potential</h3>
          <p className="chart-caption">Addressable prize dollars if every track the idea targets is won.</p>
        </div>
        <div className="view-toggle" role="group" aria-label="Chart view">
          <button type="button" className={view === "chart" ? "active" : ""} onClick={() => setView("chart")}>
            Chart
          </button>
          <button type="button" className={view === "table" ? "active" : ""} onClick={() => setView("table")}>
            Table
          </button>
        </div>
      </div>

      {view === "chart" ? (
        <div className="chart-svg-wrap" ref={containerRef} style={{ position: "relative" }}>
          <svg viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label="Horizontal bar chart of prize potential per idea in US dollars">
            {TICKS.map((t) => (
              <line
                key={t}
                className="grid-line"
                x1={xScale(t)}
                x2={xScale(t)}
                y1={MARGIN.top}
                y2={height - MARGIN.bottom}
              />
            ))}
            <line
              className="baseline-line"
              x1={MARGIN.left}
              x2={MARGIN.left}
              y1={MARGIN.top}
              y2={height - MARGIN.bottom}
            />
            {TICKS.map((t) => (
              <text key={t} className="axis-label" x={xScale(t)} y={height - MARGIN.bottom + 18} textAnchor="middle">
                {t === 0 ? "$0" : `$${t / 1000}k`}
              </text>
            ))}

            {sorted.map((idea, i) => {
              const y0 = MARGIN.top + i * ROW_H + (ROW_H - BAR_H) / 2;
              const x1 = xScale(idea.prizePotentialUsd);
              const recommended = idea.rank <= RECOMMENDED_RANK_CEILING;
              const hovered = hoveredId === idea.id;

              return (
                <g key={idea.id}>
                  <text
                    x={8}
                    y={y0 + BAR_H / 2 + 4}
                    textAnchor="start"
                    fontFamily="var(--font-mono)"
                    fontSize={10.5}
                    fill="var(--text-muted)"
                  >
                    <tspan>{String(idea.rank).padStart(2, "0")}</tspan>
                  </text>
                  <text
                    x={MARGIN.left - 14}
                    y={y0 + BAR_H / 2 + 4}
                    textAnchor="end"
                    fontFamily="var(--font-sans)"
                    fontSize={13}
                    fontWeight={recommended ? 700 : 500}
                    fill="var(--text-primary)"
                  >
                    {idea.name}
                  </text>
                  <path
                    d={roundedRightBar(MARGIN.left, y0, x1, BAR_H, RADIUS)}
                    fill={recommended ? "var(--accent)" : "var(--de-emphasis)"}
                    opacity={hovered ? 1 : recommended ? 0.95 : 0.8}
                    style={{ transition: "opacity 0.15s ease" }}
                  />
                  <text
                    x={x1 + 10}
                    y={y0 + BAR_H / 2 + 4}
                    fontFamily="var(--font-mono)"
                    fontSize={12.5}
                    fontWeight={600}
                    fill="var(--text-primary)"
                  >
                    {formatUsd(idea.prizePotentialUsd)}
                  </text>
                  <rect
                    className="data-point"
                    x={MARGIN.left}
                    y={y0 - 6}
                    width={plotWidth}
                    height={BAR_H + 12}
                    fill="transparent"
                    tabIndex={0}
                    role="button"
                    aria-label={`${idea.name}: ${formatUsd(idea.prizePotentialUsd)} prize potential`}
                    onPointerEnter={(e) => {
                      setHoveredId(idea.id);
                      show(e, idea);
                    }}
                    onPointerLeave={() => {
                      setHoveredId(null);
                      hide();
                    }}
                    onFocus={(e) => {
                      setHoveredId(idea.id);
                      show(e, idea);
                    }}
                    onBlur={() => {
                      setHoveredId(null);
                      hide();
                    }}
                  />
                </g>
              );
            })}
          </svg>

          {tooltip ? (
            <div className="viz-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
              <div className="tt-title">{tooltip.data.name}</div>
              <div className="tt-row">
                <span
                  className="tt-key"
                  style={{ background: tooltip.data.rank <= RECOMMENDED_RANK_CEILING ? "var(--accent)" : "var(--de-emphasis)" }}
                />
                Prize potential <span className="tt-value">{formatUsd(tooltip.data.prizePotentialUsd)}</span>
              </div>
              <div className="tt-row">
                <span className="tt-key" style={{ background: "transparent" }} />
                Rank <span className="tt-value">#{tooltip.data.rank}</span>
              </div>
            </div>
          ) : null}

          <div className="chart-legend">
            <span className="item">
              <span className="legend-mark filled" /> Top-3 recommended
            </span>
            <span className="item">
              <span className="legend-mark outline" style={{ background: "var(--de-emphasis)", border: "none" }} /> Under consideration
            </span>
          </div>
        </div>
      ) : (
        <table className="viz-table">
          <thead>
            <tr>
              <th>Idea</th>
              <th>Prize potential</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((idea) => (
              <tr key={idea.id}>
                <td>{idea.name}</td>
                <td className="num">{formatUsd(idea.prizePotentialUsd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
