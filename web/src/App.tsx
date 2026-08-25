/**
 * Shell and tab router.
 *
 * Two screens today: the live console and the results. Deliberately not a
 * router library — two tabs and a piece of state is the whole requirement, and
 * CLAUDE.md §5 says nothing heavier than the chart library.
 */

import { useEffect, useState } from "react";
import Console from "./Console";
import Results from "./Results";
import { API_BASE } from "./api";

type Tab = "console" | "results";

export default function App() {
  const [tab, setTab] = useState<Tab>("console");
  const [health, setHealth] = useState<{ atlas_cards: number; schema_version: string } | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>MANTIS</h1>
          <span className="sub">MANDATE FIREWALL · AGENTIC COMMERCE</span>
        </div>
        {health && (
          <span className="hint num">
            schema v{health.schema_version} · {health.atlas_cards} attack cards
          </span>
        )}
        <nav className="tabs">
          <button className={`tab ${tab === "console" ? "on" : ""}`} onClick={() => setTab("console")}>
            Live console
          </button>
          <button className={`tab ${tab === "results" ? "on" : ""}`} onClick={() => setTab("results")}>
            Results
          </button>
        </nav>
      </header>
      <main className="main">{tab === "console" ? <Console /> : <Results />}</main>
    </div>
  );
}
