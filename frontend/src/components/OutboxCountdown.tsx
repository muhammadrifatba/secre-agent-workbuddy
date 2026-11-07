"use client";

import React, { useEffect, useState } from "react";

interface OutboxItem {
  outbox_id: string;
  action_id: string;
  request_id: string;
  channel: string;
  recipient_name: string;
  recipient_address: string;
  subject: string;
  remaining_seconds: number;
  status: string;
}

interface OutboxCountdownProps {
  items: OutboxItem[];
  onUndo: (actionId: string) => void;
  onRefresh?: () => void;
}

export const OutboxCountdown: React.FC<OutboxCountdownProps> = ({ items, onUndo, onRefresh }) => {
  const [secondsLeftMap, setSecondsLeftMap] = useState<Record<string, number>>({});

  useEffect(() => {
    const initial: Record<string, number> = {};
    items.forEach((item) => {
      if (item.status === "queued_outbox") {
        initial[item.action_id] = item.remaining_seconds ?? 60;
      }
    });
    setSecondsLeftMap(initial);
  }, [items]);

  useEffect(() => {
    const timer = setInterval(() => {
      setSecondsLeftMap((prev) => {
        let hasHitZero = false;
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          if (next[key] > 0) {
            next[key] -= 1;
            if (next[key] === 0) hasHitZero = true;
          }
        }
        if (hasHitZero && onRefresh) {
          onRefresh();
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [onRefresh]);

  if (!items || items.length === 0) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-5xl rounded-2xl border border-slate-700 bg-slate-900/95 p-4 shadow-2xl backdrop-blur">
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-bold uppercase tracking-wider text-amber-400">
          ⏳ Antrean Pengiriman Email (Waktu Tunda Pengaman 60 Detik)
        </span>
        <span className="text-xs text-slate-400">
          Anda masih dapat membatalkan pengiriman sebelum hitung mundur selesai
        </span>
      </div>

      <div className="space-y-2">
        {items.map((item) => {
          const rem = secondsLeftMap[item.action_id] ?? item.remaining_seconds ?? 0;
          const pct = Math.min(100, Math.max(0, Math.round((rem / 60) * 100)));
          const isQueued = item.status === "queued_outbox";

          return (
            <div
              key={item.outbox_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950 p-3.5"
            >
              <div className="min-w-[220px] flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] font-bold uppercase text-sky-300">
                    {item.channel}
                  </span>
                  <span className="text-sm font-bold text-white">
                    Kepada: {item.recipient_name}
                  </span>
                  <span className="rounded bg-indigo-950/60 px-2 py-0.5 font-mono text-xs text-indigo-300 border border-indigo-500/30">
                    {item.recipient_address}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                      item.status === "undone"
                        ? "bg-red-500/20 text-red-300"
                        : item.status === "sent"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "bg-amber-500/20 text-amber-300"
                    }`}
                  >
                    {item.status === "queued_outbox"
                      ? "Menunggu Dikirim"
                      : item.status === "undone"
                      ? "Dibatalkan"
                      : "Terkirim"}
                  </span>
                </div>
                <p className="mt-1 truncate text-xs text-slate-400">Subjek: {item.subject}</p>

                {isQueued && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full bg-amber-400 transition-all duration-1000"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3">
                {isQueued ? (
                  <>
                    <span className="font-mono text-sm font-bold text-amber-300">
                      {rem} dtk
                    </span>
                    <button
                      onClick={() => onUndo(item.action_id)}
                      className="rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-red-500"
                    >
                      Batalkan Pengiriman
                    </button>
                  </>
                ) : item.status === "undone" ? (
                  <span className="text-xs font-semibold text-red-400">
                    Pengiriman Dibatalkan
                  </span>
                ) : (
                  <span className="text-xs font-semibold text-emerald-400">
                    Berhasil Dikirim
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default OutboxCountdown;
