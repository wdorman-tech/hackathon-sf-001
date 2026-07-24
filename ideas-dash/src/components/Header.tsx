import {
  HACKATHON,
  IDEAS,
  JUDGING_CRITERIA,
  JUDGING_PENALTIES,
  SUBMISSION_REQUIREMENTS,
  TOTAL_PRIZE_POOL_USD,
  TRACKS,
} from "../data";
import { formatUsd } from "../lib/format";
import { IconMoon, IconSun } from "./Icons";

function trackPoolTotal(category: "General" | "Sponsor"): number {
  return TRACKS.filter((t) => t.category === category).reduce(
    (sum, t) => sum + t.prizeCashUsd + (t.prizeRunnerUpUsd ?? 0) + (t.prizeExtraUsd ?? 0),
    0,
  );
}

interface HeaderProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export function Header({ theme, onToggleTheme }: HeaderProps) {
  const generalPool = trackPoolTotal("General");
  const sponsorPool = trackPoolTotal("Sponsor");

  return (
    <header className="site-header">
      <div className="brand-block">
        <p className="eyebrow">
          <span className="dot" aria-hidden="true" />
          Internal planning dashboard &middot; idea selection
        </p>
        <h1 className="brand-title">
          {HACKATHON.name}
          <br />
          <em>&mdash; {HACKATHON.location}</em>
        </h1>
        <ul className="brand-meta">
          <li>{HACKATHON.dateLabel}</li>
          <li>{TRACKS.length} prize tracks</li>
          <li>{IDEAS.length} candidate ideas</li>
        </ul>

        <div className="judging-panel" style={{ marginTop: 22 }}>
          <div className="judging-col criteria">
            <h3>Judged on</h3>
            <ul>
              {JUDGING_CRITERIA.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
          <div className="judging-col penalties">
            <h3>Penalized for</h3>
            <ul>
              {JUDGING_PENALTIES.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
          <div className="judging-col submission">
            <h3>Submission</h3>
            <ul>
              {SUBMISSION_REQUIREMENTS.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-end" }}>
        <button
          type="button"
          className="theme-toggle"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? <IconSun /> : <IconMoon />}
          {theme === "dark" ? "Light" : "Dark"}
        </button>

        <div className="header-stats">
          <div className="stat-tile is-hero">
            <span className="eyebrow">Total addressable pool</span>
            <span className="stat-figure">{formatUsd(TOTAL_PRIZE_POOL_USD)}</span>
          </div>
          <div className="stat-tile">
            <span className="eyebrow">General tracks</span>
            <span className="stat-figure small">{formatUsd(generalPool)}</span>
          </div>
          <div className="stat-tile">
            <span className="eyebrow">Sponsor tracks</span>
            <span className="stat-figure small">{formatUsd(sponsorPool)}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
