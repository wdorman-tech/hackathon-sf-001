import { useId, useState } from "react";
import type { Idea } from "../data";
import { formatUsd } from "../lib/format";
import { TrackChip } from "./TrackChip";
import {
  IconChevron,
  IconCreativity,
  IconFunctionality,
  IconTechnical,
  IconTerac,
} from "./Icons";

const RECOMMENDED_RANK_CEILING = 3;

export function IdeaCard({ idea }: { idea: Idea }) {
  const [open, setOpen] = useState(idea.rank === 1);
  const panelId = useId();
  const recommended = idea.rank <= RECOMMENDED_RANK_CEILING;
  const totalHours = idea.buildPlan.reduce((sum, step) => sum + step.hours, 0);

  return (
    <article className={`idea-card${recommended ? " is-recommended" : ""}${open ? " is-open" : ""}`}>
      <button
        type="button"
        className="idea-summary"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="idea-rank mono">{String(idea.rank).padStart(2, "0")}</span>

        <span className="idea-heading">
          <span className="idea-name-row">
            <span className="idea-name">{idea.name}</span>
            {idea.rank === 1 ? <span className="pick-badge">Top pick</span> : null}
          </span>
          <p className="idea-tagline">{idea.tagline}</p>
          <span className="idea-tracks" style={{ marginTop: 8, display: "flex" }}>
            {idea.tracksHit.map((t) => (
              <TrackChip key={t} trackId={t} />
            ))}
          </span>
        </span>

        <span className="idea-metrics">
          <span className="metric prize">
            <span className="label">Prize potential</span>
            <span className="value">{formatUsd(idea.prizePotentialUsd)}</span>
          </span>
          <span className="metric">
            <span className="label">Effort</span>
            <span className="value">{idea.effort}/10</span>
          </span>
          <span className="metric">
            <span className="label">Impact</span>
            <span className="value">{idea.impact}/10</span>
          </span>
          <span className="metric">
            <span className="label">Demo risk</span>
            <span className="value">{idea.demoRisk}/10</span>
          </span>
        </span>

        <span className="chevron">
          <IconChevron />
        </span>
      </button>

      {open ? (
        <div className="idea-detail" id={panelId}>
          <div className="detail-col">
            <div className="detail-block">
              <p className="detail-label">Core demo</p>
              <p className="detail-copy">{idea.coreDemo}</p>
            </div>

            <div className="detail-block">
              <p className="detail-label">Why it wins</p>
              <div className="why-grid">
                <div className="why-row">
                  <span className="why-icon">
                    <IconTechnical />
                  </span>
                  <div>
                    <h4>Technical impressiveness</h4>
                    <p>{idea.whyItWins.technical}</p>
                  </div>
                </div>
                <div className="why-row">
                  <span className="why-icon">
                    <IconCreativity />
                  </span>
                  <div>
                    <h4>Creativity</h4>
                    <p>{idea.whyItWins.creativity}</p>
                  </div>
                </div>
                <div className="why-row">
                  <span className="why-icon">
                    <IconFunctionality />
                  </span>
                  <div>
                    <h4>Functionality</h4>
                    <p>{idea.whyItWins.functionality}</p>
                  </div>
                </div>
              </div>
            </div>

            {idea.teracLoop ? (
              <div className="terac-callout">
                <p className="detail-label">
                  <IconTerac /> Terac loop
                </p>
                <p>{idea.teracLoop}</p>
              </div>
            ) : null}
          </div>

          <div className="detail-col">
            <div className="detail-block">
              <p className="detail-label">Stack</p>
              <div className="stack-chips">
                {idea.stack.map((s) => (
                  <span key={s} className="stack-chip">
                    {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="detail-block">
              <p className="detail-label">Build plan</p>
              <div className="build-timeline">
                {idea.buildPlan.map((step, i) => (
                  <div className="build-step" key={step.phase}>
                    <span className="idx mono">{String(i + 1).padStart(2, "0")}</span>
                    <span className="phase">{step.phase}</span>
                    <span className="hours mono">{step.hours}h</span>
                    <span className="desc">{step.description}</span>
                  </div>
                ))}
              </div>
              <p className="build-total">~{totalHours}h estimated build time</p>
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}
