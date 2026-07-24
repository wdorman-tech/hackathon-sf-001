import { useState } from "react";
import type { Idea } from "../../data";
import { formatUsd } from "../../lib/format";
import { useTooltip } from "./useTooltip";

const WIDTH = 760;
const HEIGHT = 460;
const MARGIN = { top: 24, right: 34, bottom: 46, left: 50 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;
const DOMAIN_MAX = 10;
const R_MIN = 8;
const R_MAX = 27;
const RECOMMENDED_RANK_CEILING = 3;

const TICKS = [0, 2, 4, 6, 8, 10];

function xScale(v: number) {
  return MARGIN.left + (v / DOMAIN_MAX) * PLOT_W;
}
function yScale(v: number) {
  return MARGIN.top + PLOT_H - (v / DOMAIN_MAX) * PLOT_H;
}
function radiusScale(risk: number) {
  const t = (risk - 1) / 9;
  return R_MIN + Math.sqrt(Math.max(0, t)) * (R_MAX - R_MIN);
}

/** Hand-placed direct-label offsets — 5 fixed data points, tuned to avoid collisions. */
const LABEL_OFFSETS: Record<string, { anchor: "start" | "middle" | "end"; dx: number; dy: number }> = {
  bubblebid: { anchor: "middle", dx: 0, dy: -34 },
  "mole-in-the-machine": { anchor: "end", dx: -30, dy: 5 },
  "consensus-arena": { anchor: "middle", dx: 0, dy: 40 },
  tell: { anchor: "middle", dx: 0, dy: -30 },
  splitsquad: { anchor: "middle", dx: -8, dy: -26 },
};

export function ScatterChart({ ideas }: { ideas: Idea[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const { containerRef, tooltip, show, hide } = useTooltip<Idea>();

  return (
    <div className="chart-card full">
      <div className="chart-card-head">
        <div>
          <h3 className="chart-title">Effort vs. impact</h3>
          <p className="chart-caption">
            Bubble size is demo risk. Filled = top-3 recommended pick, outline = under consideration.
          </p>
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
          <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Scatter plot of effort versus impact per idea, bubble size is demo risk">
            {/* gridlines */}
            {TICKS.map((t) => (
              <line
                key={`vx-${t}`}
                className="grid-line"
                x1={xScale(t)}
                x2={xScale(t)}
                y1={MARGIN.top}
                y2={MARGIN.top + PLOT_H}
              />
            ))}
            {TICKS.map((t) => (
              <line
                key={`vy-${t}`}
                className="grid-line"
                x1={MARGIN.left}
                x2={MARGIN.left + PLOT_W}
                y1={yScale(t)}
                y2={yScale(t)}
              />
            ))}
            <line
              className="baseline-line"
              x1={MARGIN.left}
              x2={MARGIN.left}
              y1={MARGIN.top}
              y2={MARGIN.top + PLOT_H}
            />
            <line
              className="baseline-line"
              x1={MARGIN.left}
              x2={MARGIN.left + PLOT_W}
              y1={MARGIN.top + PLOT_H}
              y2={MARGIN.top + PLOT_H}
            />

            {/* tick labels */}
            {TICKS.map((t) => (
              <text key={`tx-${t}`} className="axis-label" x={xScale(t)} y={MARGIN.top + PLOT_H + 18} textAnchor="middle">
                {t}
              </text>
            ))}
            {TICKS.map((t) => (
              <text key={`ty-${t}`} className="axis-label" x={MARGIN.left - 10} y={yScale(t) + 3} textAnchor="end">
                {t}
              </text>
            ))}

            <text className="axis-title" x={MARGIN.left + PLOT_W / 2} y={HEIGHT - 6} textAnchor="middle">
              EFFORT (1 low → 10 high)
            </text>
            <text
              className="axis-title"
              x={-(MARGIN.top + PLOT_H / 2)}
              y={16}
              textAnchor="middle"
              transform="rotate(-90)"
            >
              IMPACT (1 low → 10 high)
            </text>

            {/* bubbles */}
            {ideas.map((idea) => {
              const cx = xScale(idea.effort);
              const cy = yScale(idea.impact);
              const r = radiusScale(idea.demoRisk);
              const recommended = idea.rank <= RECOMMENDED_RANK_CEILING;
              const hit = Math.max(r + 6, 16);
              const label = LABEL_OFFSETS[idea.id] ?? { anchor: "middle" as const, dx: 0, dy: -(r + 12) };
              const isHovered = tooltip?.data.id === idea.id;

              return (
                <g key={idea.id}>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill={recommended ? "var(--accent)" : "var(--de-emphasis-fill)"}
                    stroke={recommended ? "var(--surface-1)" : "var(--de-emphasis)"}
                    strokeWidth={recommended ? 2 : 2}
                    opacity={isHovered ? 1 : recommended ? 0.92 : 0.85}
                    style={{ transition: "opacity 0.15s ease" }}
                  />
                  <text
                    x={cx + label.dx}
                    y={cy + label.dy}
                    textAnchor={label.anchor}
                    fontFamily="var(--font-mono)"
                    fontSize={11.5}
                    fontWeight={recommended ? 600 : 500}
                    fill={recommended ? "var(--text-primary)" : "var(--text-secondary)"}
                  >
                    {idea.name}
                  </text>
                  <circle
                    className="data-point"
                    cx={cx}
                    cy={cy}
                    r={hit}
                    fill="transparent"
                    tabIndex={0}
                    role="button"
                    aria-label={`${idea.name}: effort ${idea.effort}, impact ${idea.impact}, demo risk ${idea.demoRisk}`}
                    onPointerEnter={(e) => show(e, idea)}
                    onPointerLeave={hide}
                    onFocus={(e) => show(e, idea)}
                    onBlur={hide}
                  />
                </g>
              );
            })}
          </svg>

          {tooltip ? (
            <div className="viz-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
              <div className="tt-title">{tooltip.data.name}</div>
              <div className="tt-row">
                <span className="tt-key" style={{ background: "var(--accent)" }} />
                Effort <span className="tt-value">{tooltip.data.effort}/10</span>
              </div>
              <div className="tt-row">
                <span className="tt-key" style={{ background: "var(--slot-3)" }} />
                Impact <span className="tt-value">{tooltip.data.impact}/10</span>
              </div>
              <div className="tt-row">
                <span className="tt-key" style={{ background: "var(--slot-4)" }} />
                Demo risk <span className="tt-value">{tooltip.data.demoRisk}/10</span>
              </div>
              <div className="tt-row">
                <span className="tt-key" style={{ background: "var(--slot-2)" }} />
                Prize <span className="tt-value">{formatUsd(tooltip.data.prizePotentialUsd)}</span>
              </div>
            </div>
          ) : null}

          <div className="chart-legend">
            <span className="item">
              <span className="legend-mark filled" /> Top-3 recommended
            </span>
            <span className="item">
              <span className="legend-mark outline" /> Under consideration
            </span>
          </div>
        </div>
      ) : (
        <table className="viz-table">
          <thead>
            <tr>
              <th>Idea</th>
              <th>Effort</th>
              <th>Impact</th>
              <th>Demo risk</th>
              <th>Prize potential</th>
            </tr>
          </thead>
          <tbody>
            {ideas.map((idea) => (
              <tr key={idea.id}>
                <td>{idea.name}</td>
                <td className="num">{idea.effort}/10</td>
                <td className="num">{idea.impact}/10</td>
                <td className="num">{idea.demoRisk}/10</td>
                <td className="num">{formatUsd(idea.prizePotentialUsd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
