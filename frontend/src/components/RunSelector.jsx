import React, { useState } from "react";
import { fetchRuns, fetchRun } from "../api";
import { useApi } from "../hooks/useApi";

/**
 * Run Selector - displays list of available simulation runs
 *
 * Fetches: GET /api/runs
 *
 * Expected response:
 *   {
 *     runs: [
 *       {
 *         id: number
 *         name: string
 *         date: string (YYYY-MM-DD)
 *         scenario: string
 *         hw: string (e.g., "Radxa Zero" or "ESP32")
 *         duration: string (e.g., "24h", "12h", "8h")
 *         status: "pass" | "warning" | "fail"
 *       }
 *     ]
 *   }
 *
 * Props:
 *   page: string - current page (used to trigger refetch when navigating back)
 *   onOpen: (run) => void - called when user opens a run
 */
export default function RunSelector({ page, onOpen }) {
  const { data, loading } = useApi(() => fetchRuns(), [page]);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  if (loading) return <div style={{ padding: 24 }}>Loading runs…</div>;
  const runs = data?.runs || [];

  // Filter runs based on search query
  const filteredRuns = runs.filter((r) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      r.name.toLowerCase().includes(query) ||
      (r.scenario && r.scenario.toLowerCase().includes(query)) ||
      (r.shamanProcessor && r.shamanProcessor.toLowerCase().includes(query)) ||
      r.date.includes(query)
    );
  });

  function selectRun(i) {
    setSelectedIdx(selectedIdx === i ? null : i);
  }

  async function openSelected() {
    if (selectedIdx === null) return;
    const r = filteredRuns[selectedIdx];
    try {
      const detail = await fetchRun(r.id);
      onOpen(detail);
    } catch (e) {
      onOpen(r);
    }
  }

  return (
    <div style={{ overflowY: "auto", padding: 24 }}>
      <div className="pg-header">
        <div>
          <div className="pg-title">Run Selector</div>
        </div>
        <button
          className="btn btn-primary"
          disabled={selectedIdx === null}
          onClick={openSelected}
        >
          Open Run
        </button>
      </div>

      <div className="controls-row">
        <input
          type="text"
          className="search-input"
          placeholder="Search…"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setSelectedIdx(null);
          }}
        />
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th className="cb-cell"></th>
              <th>Run Name</th>
              <th>Date</th>
              <th>Shaman Processor</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody id="runsTableBody">
            {filteredRuns.length > 0 ? (
              filteredRuns.map((r, i) => (
                <tr
                  key={r.id}
                  onClick={() => selectRun(i)}
                  className={`${selectedIdx === i ? "selected" : ""}`}
                >
                  <td className="cb-cell">
                    <div
                      className={`custom-cb ${selectedIdx === i ? "checked" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        selectRun(i);
                      }}
                    ></div>
                  </td>
                  <td>{r.name}</td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    {r.date}
                  </td>
                  <td>
                    <span className="badge badge-hw">
                      {r.shamanProcessor || "—"}
                    </span>
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    {r.duration}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan="5"
                  style={{
                    textAlign: "center",
                    padding: "24px",
                    color: "var(--text-muted)",
                  }}
                >
                  {runs.length === 0
                    ? "No runs created yet."
                    : `No runs match "${searchQuery}"`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
