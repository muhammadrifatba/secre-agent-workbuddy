"use client";

import React, { useState } from "react";
import {
  HEAVY_MACHINERY_SCENARIOS,
  JUDGE_SCENARIOS,
  ScenarioDefinition,
} from "../lib/types";

interface ScenarioLauncherProps {
  activeScenarioId?: string;
  loading?: boolean;
  onRunScenario: (scenario: ScenarioDefinition) => void;
}

export const ScenarioLauncher: React.FC<ScenarioLauncherProps> = ({
  activeScenarioId,
  loading = false,
  onRunScenario,
}) => {
  const [isOpen, setIsOpen] = useState(true);
  const [mode, setMode] = useState<"heavy_machinery" | "governance">(
    "heavy_machinery"
  );

  const activeList =
    mode === "heavy_machinery" ? HEAVY_MACHINERY_SCENARIOS : JUDGE_SCENARIOS;

  return (
    <section className="w-full rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-indigo-500/20 border border-indigo-500/40 px-2.5 py-1 text-xs font-bold text-indigo-300">
            🚜 Uji Skenario Mapping Komplain &amp; Demand Alat Berat
          </span>
          {isOpen && (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setMode("heavy_machinery")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  mode === "heavy_machinery"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                4 Skenario Transkrip Alat Berat
              </button>
              <button
                type="button"
                onClick={() => setMode("governance")}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  mode === "governance"
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                5 Skenario Keamanan &amp; Jadwal
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
        >
          {isOpen ? "Sembunyikan Panel Uji Skenario" : "Tampilkan Pilihan Skenario"}
        </button>
      </div>

      {isOpen && (
        <div
          className={`mt-3.5 grid grid-cols-1 gap-2.5 border-t border-slate-800 pt-3.5 ${
            mode === "heavy_machinery"
              ? "sm:grid-cols-2 lg:grid-cols-4"
              : "sm:grid-cols-2 lg:grid-cols-5"
          }`}
        >
          {activeList.map((sc) => {
            const isActive = activeScenarioId === sc.id;
            return (
              <button
                key={sc.id}
                disabled={loading}
                onClick={() => onRunScenario(sc)}
                className={`group flex flex-col justify-between rounded-xl border p-3.5 text-left transition-all ${
                  isActive
                    ? "border-indigo-500 bg-indigo-950/60 text-white shadow-md"
                    : "border-slate-800 bg-slate-950/60 text-slate-200 hover:border-indigo-500/50 hover:bg-slate-800/60"
                } disabled:opacity-50`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1">
                    <span className="rounded bg-indigo-950/80 border border-indigo-500/30 px-2 py-0.5 font-mono text-[10px] font-bold text-indigo-300">
                      {sc.badge}
                    </span>
                  </div>
                  <p className="mt-2 text-xs font-bold leading-snug text-white group-hover:text-indigo-300">
                    {sc.label.replace(/^Run T\d:\s*/, "")}
                  </p>
                  <p className="mt-1 line-clamp-3 text-[11px] text-slate-400 leading-relaxed">
                    {sc.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default ScenarioLauncher;
