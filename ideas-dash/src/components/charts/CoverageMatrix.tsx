import type { Idea, Track } from "../../data";
import { slotVar } from "../../lib/colors";

export function CoverageMatrix({ ideas, tracks }: { ideas: Idea[]; tracks: Track[] }) {
  return (
    <div className="chart-card">
      <div className="chart-card-head">
        <div>
          <h3 className="chart-title">Idea &times; track coverage</h3>
          <p className="chart-caption">Which prize tracks each idea can legitimately claim.</p>
        </div>
      </div>

      <div className="matrix-scroll">
        <table className="matrix-table">
          <caption className="sr-only">Coverage matrix of ideas against prize tracks</caption>
          <thead>
            <tr>
              <th scope="col" aria-hidden="true" />
              {tracks.map((track) => (
                <th
                  key={track.id}
                  scope="col"
                  className="matrix-col-label"
                  style={{ borderBottom: `2px solid ${slotVar(track.colorSlot)}` }}
                  title={track.name}
                >
                  {track.code}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ideas.map((idea) => (
              <tr key={idea.id}>
                <th scope="row" className="matrix-row-label">
                  <span className="rank-tag">{String(idea.rank).padStart(2, "0")}</span>
                  {idea.name}
                </th>
                {tracks.map((track) => {
                  const hit = idea.tracksHit.includes(track.id);
                  return (
                    <td key={track.id}>
                      <div
                        className={`matrix-cell${hit ? " hit" : ""}`}
                        style={hit ? { ["--cell-color" as string]: slotVar(track.colorSlot) } : undefined}
                        title={`${idea.name} ${hit ? "targets" : "does not target"} ${track.name}`}
                      >
                        <span className="sr-only">
                          {idea.name} {hit ? "targets" : "does not target"} {track.name}
                        </span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="matrix-legend">
        {tracks.map((track) => (
          <span className="item" key={track.id}>
            <span className="swatch" style={{ background: slotVar(track.colorSlot) }} aria-hidden="true" />
            <span className="mono">{track.code}</span>&nbsp;&mdash;&nbsp;{track.name}
          </span>
        ))}
      </div>
    </div>
  );
}
