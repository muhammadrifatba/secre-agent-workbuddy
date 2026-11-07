"use client";

import React, { useEffect, useState } from "react";
import { formatScheduleTime } from "../lib/formatTime";

interface ApprovalInboxProps {
  requestId: string;
  plan: any;
  findings: any[];
  injectionFlags: any[];
  approvalHash: string;
  onApprove: (
    decision: "approve" | "edit" | "reject",
    cognitiveConfirmation: string,
    editedBody?: string
  ) => void;
  onSimulateTamper?: () => void;
}

export const ApprovalInbox: React.FC<ApprovalInboxProps> = ({
  requestId,
  plan,
  findings = [],
  injectionFlags = [],
  approvalHash,
  onApprove,
  onSimulateTamper,
}) => {
  const [stepUpChecked, setStepUpChecked] = useState(false);
  const [confirmationText, setConfirmationText] = useState("");
  const [editModeId, setEditModeId] = useState<string | null>(null);
  const [editedBody, setEditedBody] = useState("");
  const [showTechDetails, setShowTechDetails] = useState(false);

  const firstAction = plan?.actions?.[0];
  const defaultConfirmPhrase = firstAction
    ? `Confirm external recipient: ${firstAction.who?.org_name || firstAction.who?.name}`
    : "";

  // Reset confirmation state when a new request arrives
  useEffect(() => {
    setStepUpChecked(false);
    setConfirmationText("");
    setEditModeId(null);
  }, [requestId, approvalHash]);

  if (!plan || !plan.actions) return null;

  const hasHighRisk = plan.actions.some((a: any) => a.risk_tier === "high");
  const isAlreadyExecuted = plan.actions.every(
    (a: any) =>
      a.status === "handed_off" ||
      a.status === "queued_outbox" ||
      a.status === "sent" ||
      Boolean(a.wa_handoff_link)
  );
  const isRejected = plan.actions.every((a: any) => a.status === "rejected");

  const getChannelLabel = (channel: string) => {
    if (channel === "whatsapp") return "📲 WhatsApp";
    if (channel === "email") return "✉️ Email";
    if (channel === "crm") return "🗂️ Tiket CRM";
    return channel.toUpperCase();
  };

  const getDestinationContact = (who: any, channel: string) => {
    if (channel === "whatsapp") {
      return who?.phone || "Nomor belum tersedia";
    }
    if (channel === "email") {
      return who?.email || "Email belum tersedia";
    }
    return who?.phone || who?.email || who?.org_name || "-";
  };

  const getDestinationLabel = (channel: string) => {
    if (channel === "whatsapp") return "Nomor WhatsApp Tujuan";
    if (channel === "email") return "Alamat Email Tujuan";
    return "Kontak Tujuan";
  };

  return (
    <div className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/95 p-6 shadow-2xl">
      {/* Peringatan Keamanan jika ada instruksi mencurigakan di dokumen */}
      {injectionFlags.length > 0 && (
        <div className="rounded-xl border border-red-500/50 bg-red-950/60 p-4 text-red-200">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-300">
            <span>🛡️ Peringatan Keamanan: Instruksi Mencurigakan Diblokir</span>
          </div>
          <p className="mt-1 text-xs text-red-200/90">
            Sistem mendeteksi dan menghapus perintah tersembunyi dari dokumen lampiran agar tidak dieksekusi:
          </p>
          {injectionFlags.map((flg: any) => (
            <p key={flg.flag_id} className="mt-1.5 rounded bg-red-950/80 px-2.5 py-1 font-mono text-xs text-red-200">
              &quot;{flg.offending_excerpt}&quot;
            </p>
          ))}
        </div>
      )}

      {/* Header Kartu Persetujuan */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/15 px-3 py-0.5 text-xs font-semibold text-indigo-300 border border-indigo-500/30">
            {isAlreadyExecuted
              ? "✅ Pesan Telah Disetujui & Siap Dikirim"
              : isRejected
              ? "❌ Pengiriman Dibatalkan"
              : "📬 Konfirmasi Pengiriman Pesan"}
          </span>
          <h2 className="mt-1.5 text-lg font-bold text-white">
            Periksa Tujuan &amp; Isi Pesan Sebelum Dikirim
          </h2>
        </div>

        <button
          type="button"
          onClick={() => setShowTechDetails(!showTechDetails)}
          className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs text-slate-400 hover:border-slate-700 hover:text-slate-200"
        >
          {showTechDetails ? "Sembunyikan Info Teknis" : "Info Keamanan"}
        </button>
      </div>

      {showTechDetails && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/80 px-3.5 py-2 text-[11px] text-slate-400">
          <span>
            ID Permintaan: <code className="text-slate-200">{requestId}</code>
          </span>
          <span>
            Kode Verifikasi Draf: <code className="text-indigo-300">{approvalHash?.slice(0, 20)}...</code>
          </span>
        </div>
      )}

      {/* Daftar Pesan yang Akan Dikirim */}
      <div className="space-y-4">
        {plan.actions.map((action: any) => {
          const isEditing = editModeId === action.action_id;
          const isWA = action.channel === "whatsapp";
          const destinationValue = getDestinationContact(action.who, action.channel);
          const destinationLabel = getDestinationLabel(action.channel);

          return (
            <div
              key={action.action_id}
              className="rounded-xl border border-slate-800 bg-slate-950/80 p-5 space-y-4"
            >
              {/* Baris Atas: Saluran & Status */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-lg px-3 py-1 text-xs font-bold ${
                      isWA
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                    }`}
                  >
                    {getChannelLabel(action.channel)}
                  </span>
                  <span className="rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-medium text-slate-300 border border-slate-800">
                    {action.who?.category === "customer" ? "Pelanggan Eksternal" : "Rekan Internal"}
                  </span>
                </div>

                <div className="text-xs text-slate-400">
                  Jadwal Kirim:{" "}
                  <span className="rounded-md bg-slate-900 px-2.5 py-1 font-semibold text-slate-200 border border-slate-800">
                    🗓️ {formatScheduleTime(action.when?.send_at, action.when?.tz_label || action.when?.tz)}
                  </span>
                </div>
              </div>

              {/* Kotak Informasi Penerima & Nomor/Email Tujuan (Sangat Jelas) */}
              <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-800/90 bg-slate-900/90 p-4 sm:grid-cols-2">
                <div>
                  <div className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                    Penerima &amp; Perusahaan
                  </div>
                  <div className="mt-1 text-base font-bold text-white">
                    {action.who?.name}
                  </div>
                  <div className="text-xs text-slate-300">
                    {action.who?.org_name || "Internal"} · {action.who?.city} ({action.when?.tz_label})
                  </div>
                </div>

                <div className="rounded-lg border border-indigo-500/30 bg-indigo-950/30 p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-300">
                    {destinationLabel}
                  </div>
                  <div className="mt-1 font-mono text-base font-extrabold text-white break-all">
                    {destinationValue}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-400">
                    {isWA
                      ? "Pesan akan diarahkan langsung ke nomor WhatsApp ini"
                      : "Email akan dikirimkan ke alamat ini"}
                  </div>
                </div>
              </div>

              {/* Subjek & Isi Draf Pesan */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-slate-300">
                    Subjek / Perihal:{" "}
                    <span className="font-bold text-white">{action.what?.subject}</span>
                  </div>
                  {!isEditing && !isAlreadyExecuted && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditModeId(action.action_id);
                        setEditedBody(action.what?.body_draft || "");
                      }}
                      className="rounded-lg border border-indigo-500/40 bg-indigo-950/50 px-3 py-1 text-xs font-semibold text-indigo-300 hover:bg-indigo-900/60"
                    >
                      ✏️ Ubah Isi Pesan
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div className="space-y-2.5 pt-1">
                    <textarea
                      value={editedBody}
                      onChange={(e) => setEditedBody(e.target.value)}
                      rows={5}
                      className="w-full rounded-xl border border-indigo-500/50 bg-slate-900 p-3.5 text-sm text-white focus:outline-none"
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setEditModeId(null)}
                        className="rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-1.5 text-xs font-semibold text-slate-300"
                      >
                        Batal
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          onApprove("edit", confirmationText || defaultConfirmPhrase, editedBody);
                          setEditModeId(null);
                        }}
                        className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-indigo-500"
                      >
                        Simpan Perubahan Draf
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                      Isi Pesan {isWA ? "WhatsApp" : "Email"}:
                    </div>
                    <p className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-100">
                      {action.what?.body_draft}
                    </p>
                  </div>
                )}
              </div>

              {/* Tombol Buka WhatsApp setelah di-Approve */}
              {action.wa_handoff_link && (
                <div className="rounded-xl border-2 border-emerald-500/70 bg-emerald-950/50 p-4 text-emerald-100 shadow-lg">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-extrabold text-emerald-300">
                        ✅ Pesan WhatsApp Siap Dikirim!
                      </div>
                      <div className="mt-0.5 text-xs text-emerald-200/90">
                        Penerima: <strong>{action.who?.name}</strong> ({action.who?.org_name}) · Nomor WA:{" "}
                        <strong className="font-mono underline">{action.who?.phone}</strong>
                      </div>
                    </div>
                    <a
                      href={action.wa_handoff_link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-2.5 text-sm font-extrabold text-slate-950 shadow-lg hover:bg-emerald-400 transition"
                    >
                      <span>📲 Buka &amp; Kirim ke WhatsApp ({action.who?.phone})</span>
                    </a>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Catatan Pemeriksaan Otomatis (Hanya tampil jika ada hal penting yang ramah pengguna) */}
      {findings.length > 0 && showTechDetails && (
        <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5">
          <p className="text-xs font-semibold text-slate-300">
            Pemeriksaan Otomatis Sebelum Kirim:
          </p>
          <ul className="mt-1.5 space-y-1 text-xs text-slate-400">
            {findings.map((f: any) => (
              <li key={f.finding_id} className="flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full bg-amber-400" />
                <span>{f.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bagian Konfirmasi Pengiriman (Proses Accept) */}
      {!isAlreadyExecuted && !isRejected && firstAction && (
        <div className="space-y-4 rounded-xl border border-emerald-500/30 bg-slate-950/90 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                Ringkasan Konfirmasi Pengiriman
              </div>
              <div className="mt-1 text-sm text-slate-200">
                Anda akan mengirim <strong>{getChannelLabel(firstAction.channel)}</strong> kepada{" "}
                <strong className="text-white">{firstAction.who?.name}</strong> (
                {firstAction.who?.org_name || firstAction.who?.city}) di tujuan:{" "}
                <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono font-bold text-emerald-300 border border-emerald-500/40">
                  {getDestinationContact(firstAction.who, firstAction.channel)}
                </span>
              </div>
            </div>
          </div>

          {hasHighRisk && (
            <label className="flex items-start gap-3 cursor-pointer rounded-lg border border-amber-500/30 bg-amber-950/20 p-3.5 hover:bg-amber-950/30 transition">
              <input
                type="checkbox"
                checked={stepUpChecked}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setStepUpChecked(checked);
                  if (checked) {
                    setConfirmationText(defaultConfirmPhrase);
                  } else {
                    setConfirmationText("");
                  }
                }}
                className="mt-0.5 h-4 w-4 rounded border-amber-500 accent-emerald-500"
              />
              <div className="text-xs leading-relaxed text-amber-100">
                <span className="font-bold text-amber-300">
                  Konfirmasi Penerima Eksternal:{" "}
                </span>
                Saya telah memeriksa isi pesan di atas dan menyetujui pengiriman ke{" "}
                <strong>{firstAction.who?.name}</strong> ({firstAction.who?.org_name}) melalui{" "}
                <strong className="font-mono underline">
                  {getDestinationContact(firstAction.who, firstAction.channel)}
                </strong>
                .
              </div>
            </label>
          )}

          <div className="flex flex-wrap items-center justify-end gap-3 pt-1">
            {onSimulateTamper && showTechDetails && (
              <button
                type="button"
                onClick={onSimulateTamper}
                className="rounded-lg border border-red-500/50 bg-red-950/60 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-900/60"
              >
                Simulasi Manipulasi Draf
              </button>
            )}
            <button
              type="button"
              onClick={() => onApprove("reject", "")}
              className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-700"
            >
              Tolak / Batalkan
            </button>
            <button
              type="button"
              disabled={hasHighRisk && !stepUpChecked}
              onClick={() =>
                onApprove(
                  "approve",
                  (confirmationText || defaultConfirmPhrase).trim()
                )
              }
              className="rounded-xl bg-emerald-600 px-6 py-2.5 text-sm font-extrabold text-white shadow-lg hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40 transition"
            >
              ✅ Setujui &amp; Kirim ke {getDestinationContact(firstAction.who, firstAction.channel)}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApprovalInbox;
