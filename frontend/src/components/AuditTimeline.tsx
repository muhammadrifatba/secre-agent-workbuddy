"use client";

import React from "react";
import { formatAuditTimestamp } from "../lib/formatTime";

interface AuditTimelineProps {
  events: any[];
  verification: {
    valid: boolean;
    total_events: number;
    head_hash?: string;
    reason?: string;
  } | null;
  onVerifyChain: () => void;
}

const EVENT_LABELS: Record<string, string> = {
  ingested_and_sanitized: "1. Pesan Diterima & Diperiksa Keamanannya",
  injection_detected: "⚠️ Instruksi Mencurigakan Diblokir",
  extracted: "2. Inti Pesan & Tujuan Diekstrak",
  planned: "3. Rencana Pengiriman Disusun",
  resolved_and_evaluated: "4. Kontak & Zona Waktu Disesuaikan",
  interrupt_clarify: "⏸️ Menunggu Pilihan Kontak/Jadwal",
  clarify_resolved: "✅ Kontak & Jadwal Dipilih",
  interrupt_pic_intake: "⏸️ Menunggu Info Kontak Baru",
  pic_intake_saved: "✅ Kontak Baru Disimpan",
  context_built: "5. Riwayat Komplain & Komitmen Dimuat",
  drafted: "6. Draf Pesan Selesai Dibuat",
  pre_send_checked: "7. Pemeriksaan Kelayakan Pesan Selesai",
  validated: "8. Validasi Keamanan Lulus",
  approval_gate_reached: "📬 Menunggu Konfirmasi Pengiriman Anda",
  plan_approved: "✅ Pengiriman Disetujui oleh Pengguna",
  plan_rejected: "❌ Pengiriman Ditolak",
  action_executed: "🚀 Pesan Diproses / Siap Dikirim",
  outbox_queued: "⏳ Masuk Antrean Pengaman 60 Detik",
  outbox_undone: "↩️ Pengiriman Dibatalkan oleh Pengguna",
  outbox_sent: "✉️ Pesan Berhasil Dikirim",
};

export const AuditTimeline: React.FC<AuditTimelineProps> = ({
  events = [],
  verification,
  onVerifyChain,
}) => {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 shadow-lg space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white">
            🛡️ Riwayat Aktivitas &amp; Keamanan
          </h3>
          <p className="text-xs text-slate-400">
            Catatan otomatis setiap proses dari penerimaan hingga pengiriman
          </p>
        </div>

        <button
          onClick={onVerifyChain}
          className="rounded-lg border border-emerald-500/40 bg-emerald-950/50 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/50"
        >
          Segarkan Status
        </button>
      </div>

      {verification && (
        <div
          className={`rounded-xl border p-3 text-xs ${
            verification.valid
              ? "border-emerald-500/30 bg-emerald-950/25 text-emerald-200"
              : "border-red-500/40 bg-red-950/40 text-red-200"
          }`}
        >
          <strong>
            {verification.valid
              ? `✅ Sistem Aman (${verification.total_events} aktivitas tercatat utuh)`
              : `⚠️ Peringatan Keamanan: ${verification.reason}`}
          </strong>
        </div>
      )}

      <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
        {events.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">
            Belum ada aktivitas. Kirim pesan dari WorkBuddy atau pilih contoh skenario di atas.
          </p>
        ) : (
          events.map((ev: any) => (
            <div
              key={ev.id}
              className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-100">
                  {EVENT_LABELS[ev.event_type] || ev.event_type}
                </span>
                <span className="rounded bg-slate-900 px-2 py-0.5 font-mono text-[11px] text-slate-400 border border-slate-800">
                  {formatAuditTimestamp(ev.timestamp)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AuditTimeline;
