import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { TrackStrip } from "./components/TrackStrip";
import { IdeaCard } from "./components/IdeaCard";
import { ScatterChart } from "./components/charts/ScatterChart";
import { CoverageMatrix } from "./components/charts/CoverageMatrix";
import { PrizeBars } from "./components/charts/PrizeBars";
import { IDEAS_RANKED, RECOMMENDATION, TRACKS } from "./data";

type Theme = "dark" | "light";
const STORAGE_KEY = "ideas-dash-theme";

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
}

function App() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  return (
    <div className="page">
      <Header theme={theme} onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} />

      <TrackStrip />

      <section aria-labelledby="ideas-heading">
        <div className="section-head">
          <div>
            <h2 id="ideas-heading">Ranked ideas</h2>
            <p className="section-sub">{RECOMMENDATION.rationale}</p>
          </div>
          <span className="section-index">02 / IDEAS</span>
        </div>
        <div className="idea-list">
          {IDEAS_RANKED.map((idea) => (
            <IdeaCard key={idea.id} idea={idea} />
          ))}
        </div>
      </section>

      <section aria-labelledby="charts-heading">
        <div className="section-head">
          <div>
            <h2 id="charts-heading">The numbers</h2>
            <p className="section-sub">
              Same five ideas, three angles: cost vs. payoff, track coverage, and dollars on the table.
            </p>
          </div>
          <span className="section-index">03 / CHARTS</span>
        </div>
        <div className="chart-grid">
          <ScatterChart ideas={IDEAS_RANKED} />
          <CoverageMatrix ideas={IDEAS_RANKED} tracks={TRACKS} />
          <PrizeBars ideas={IDEAS_RANKED} />
        </div>
      </section>

      <footer className="site-footer">
        <span>IDEAS-DASH &middot; INTERNAL USE ONLY &middot; NO BACKEND, DATA COMPILED IN SRC/DATA.TS</span>
        <span>{IDEAS_RANKED.length} IDEAS &middot; {TRACKS.length} TRACKS &middot; GENERATED FOR TEAM DECISION</span>
      </footer>
    </div>
  );
}

export default App;
