import { TRACKS } from "../data";
import { slotVar } from "../lib/colors";
import { formatUsd } from "../lib/format";

export function TrackStrip() {
  return (
    <section aria-labelledby="tracks-heading">
      <div className="section-head">
        <div>
          <h2 id="tracks-heading">Prize tracks</h2>
          <p className="section-sub">
            Every idea below is scored against one or more of these six tracks. Color identifies the
            track everywhere it reappears — badges, the coverage matrix, the charts.
          </p>
        </div>
        <span className="section-index">01 / TRACKS</span>
      </div>

      <div className="track-strip">
        {TRACKS.map((track) => (
          <article
            key={track.id}
            className="track-card bracket-frame"
            style={{ ["--slot" as string]: slotVar(track.colorSlot) }}
          >
            <div className="track-card-top">
              <span className="track-code">{track.code}</span>
              <span className="track-category">{track.category}</span>
            </div>
            <h3 className="track-name">{track.name}</h3>
            <p className="track-prize mono">
              {formatUsd(track.prizeCashUsd)}
              {track.prizeRunnerUpUsd ? (
                <span className="runner"> / {formatUsd(track.prizeRunnerUpUsd)} R-UP</span>
              ) : null}
              {track.prizeExtraUsd ? (
                <span className="runner">
                  {" "}
                  + {formatUsd(track.prizeExtraUsd)} {track.prizeExtraLabel}
                </span>
              ) : null}
            </p>
            <p className="track-oneliner">{track.oneLiner}</p>
            {track.note ? <p className="track-note">{track.note}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
