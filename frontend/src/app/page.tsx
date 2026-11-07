"use client";

import React, { useEffect, useRef, useState } from "react";
import ScenarioLauncher from "../components/ScenarioLauncher";
import ClarifyAndPicModal from "../components/ClarifyAndPicModal";
import ApprovalInbox from "../components/ApprovalInbox";
import OutboxCountdown from "../components/OutboxCountdown";
import CustomerContextPanel from "../components/CustomerContextPanel";
import AuditTimeline from "../components/AuditTimeline";
import { ScenarioDefinition } from "../lib/types";
import { formatAuditTimestamp } from "../lib/formatTime";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
const SEKRE_API_KEY = process.env.NEXT_PUBLIC_SEKRE_API_KEY || "sekre-dev-key-2026";
const authHeaders = {
  "Content-Type": "application/json",
  "X-API-Key": SEKRE_API_KEY,
};

function isPendingRequest(req: any): boolean {
  if (!req) return false;
  if (req.status === "executed" || req.status === "rejected") return false;
  return Boolean(req.interrupt) || Boolean(req.state?.plan);
}

function getRequestSummary(req: any) {
  const plan = req?.interrupt?.plan || req?.state?.plan;
  const firstAction = plan?.actions?.[0];
  const amb = req?.interrupt?.ambiguities?.[0];
  const unk = req?.interrupt?.unknown_names?.[0];

  const recipientName =
    firstAction?.who?.name ||
    amb?.queried_name ||
    unk?.raw_name ||
    "Penerima";
  const orgName =
    firstAction?.who?.org_name ||
    unk?.raw_org ||
    firstAction?.who?.city ||
    "";
  const channel = firstAction?.channel || "whatsapp";
  const destination =
    channel === "whatsapp"
      ? firstAction?.who?.phone || "Menunggu nomor WA"
      : firstAction?.who?.email || "Menunggu alamat email";

  let statusLabel = "⏳ Menunggu Persetujuan";
  let statusColor = "border-amber-500/40 bg-amber-500/15 text-amber-300";

  if (req?.interrupt?.type === "CLARIFY") {
    statusLabel = "🔍 Perlu Pilih Kontak / Jam";
    statusColor = "border-indigo-500/40 bg-indigo-500/15 text-indigo-300";
  } else if (req?.interrupt?.type === "PIC_INTAKE") {
    statusLabel = "👤 Kontak Baru Belum Terdaftar";
    statusColor = "border-amber-500/40 bg-amber-500/15 text-amber-300";
  } else if (req?.status === "executed") {
    statusLabel = "✅ Sudah Disetujui";
    statusColor = "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
  } else if (req?.status === "rejected") {
    statusLabel = "❌ Dibatalkan";
    statusColor = "border-red-500/40 bg-red-500/15 text-red-300";
  }

  return {
    recipientName,
    orgName,
    channel,
    destination,
    statusLabel,
    statusColor,
    subject: firstAction?.what?.subject || req?.state?.raw_input || "",
  };
}

export default function SekreGovernanceConsole() {
  const [activeScenario, setActiveScenario] = useState<ScenarioDefinition | null>(null);
  const [allRequests, setAllRequests] = useState<any[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [showAllPending, setShowAllPending] = useState<boolean>(false);
  const [queueTab, setQueueTab] = useState<"pending" | "history">("pending");
  const [outboxItems, setOutboxItems] = useState<any[]>([]);
  const [auditData, setAuditData] = useState<{ verification: any; events: any[] }>({
    verification: null,
    events: [],
  });
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [liveSyncEnabled, setLiveSyncEnabled] = useState(true);

  const lastSyncedSignature = useRef<string>("");
  const selectedRequestIdRef = useRef<string | null>(null);
  const detailSectionRef = useRef<HTMLDivElement | null>(null);

  const selectRequest = (reqId: string | null, scrollToDetail = false) => {
    selectedRequestIdRef.current = reqId;
    setSelectedRequestId(reqId);
    setShowAllPending(false);
    setErrorBanner(null);
    if (reqId) {
      refreshAuditAndOutbox(reqId);
    }
    if (scrollToDetail && detailSectionRef.current) {
      detailSectionRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  const refreshAuditAndOutbox = async (reqId?: string) => {
    try {
      const [obRes, audRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/v1/outbox${reqId ? `?request_id=${reqId}` : ""}`, {
          headers: { "X-API-Key": SEKRE_API_KEY },
        }).then((r) => r.json()),
        fetch(`${BACKEND_URL}/api/v1/audit/verify${reqId ? `?request_id=${reqId}` : ""}`, {
          headers: { "X-API-Key": SEKRE_API_KEY },
        }).then((r) => r.json()),
      ]);
      setOutboxItems(obRes.items || []);
      setAuditData(audRes);
    } catch {
      // Ignore network poll errors during offline preview
    }
  };

  const syncRequestsFromBackend = async (force = false, preferRequestId?: string) => {
    try {
      const listResp = await fetch(`${BACKEND_URL}/api/v1/requests`, {
        headers: { "X-API-Key": SEKRE_API_KEY },
      });

      let requestsList: any[] = [];
      if (listResp.ok) {
        const listData = await listResp.json();
        requestsList = listData.requests || [];
      } else {
        const latestResp = await fetch(`${BACKEND_URL}/api/v1/requests/latest`, {
          headers: { "X-API-Key": SEKRE_API_KEY },
        });
        if (latestResp.ok) {
          const latestData = await latestResp.json();
          if (latestData && latestData.request_id && latestData.status !== "unknown") {
            requestsList = [latestData];
          }
        }
      }

      const sig = requestsList
        .map(
          (r) =>
            `${r.request_id}:${r.status}:${r.interrupt?.type || "none"}:${
              r.interrupt?.approval_hash || ""
            }:${r.state?.plan?.actions?.[0]?.who?.phone || ""}`
        )
        .join("|");

      if (force || sig !== lastSyncedSignature.current) {
        lastSyncedSignature.current = sig;
        setAllRequests(requestsList);

        const currentSelected = preferRequestId || selectedRequestIdRef.current;
        const stillExists =
          currentSelected && requestsList.some((r) => r.request_id === currentSelected);

        const nextTargetId = stillExists
          ? currentSelected
          : requestsList.find(isPendingRequest)?.request_id ||
            requestsList[0]?.request_id ||
            null;

        selectedRequestIdRef.current = nextTargetId;
        setSelectedRequestId(nextTargetId);
        await refreshAuditAndOutbox(nextTargetId || undefined);
      }
    } catch {
      // Ignore offline errors
    }
  };

  useEffect(() => {
    syncRequestsFromBackend(true);
    if (!liveSyncEnabled) return;
    const interval = setInterval(() => {
      syncRequestsFromBackend(false);
    }, 2500);
    return () => clearInterval(interval);
  }, [liveSyncEnabled]);

  const upsertRequestInList = (updatedSnap: any) => {
    if (!updatedSnap?.request_id) return;
    setAllRequests((prev) => {
      const exists = prev.some((r) => r.request_id === updatedSnap.request_id);
      if (exists) {
        return prev.map((r) =>
          r.request_id === updatedSnap.request_id ? updatedSnap : r
        );
      }
      return [updatedSnap, ...prev];
    });
    selectedRequestIdRef.current = updatedSnap.request_id;
    setSelectedRequestId(updatedSnap.request_id);
  };

  const handleRunScenario = async (scenario: ScenarioDefinition) => {
    setLoading(true);
    setErrorBanner(null);
    setActiveScenario(scenario);
    try {
      const resp = await fetch(`${BACKEND_URL}/api/v1/requests`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify(scenario.payload),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setErrorBanner(data.detail || "Permintaan ditolak oleh sistem keamanan");
      } else {
        upsertRequestInList(data);
        setQueueTab("pending");
        setShowAllPending(false);
        await syncRequestsFromBackend(true, data.request_id);
      }
    } catch (err: any) {
      setErrorBanner(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResolveClarify = async (
    targetRequestId: string,
    contactId: string,
    selectedSlot: string
  ) => {
    if (!targetRequestId) return;
    setLoading(true);
    const resp = await fetch(`${BACKEND_URL}/api/v1/requests/${targetRequestId}/resolve`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({
        interrupt_type: "CLARIFY",
        user_response: { contact_id: contactId, selected_slot: selectedSlot },
      }),
    });
    const data = await resp.json();
    upsertRequestInList(data);
    await syncRequestsFromBackend(true, targetRequestId);
    setLoading(false);
  };

  const handleResolvePicIntake = async (targetRequestId: string, sentence: string) => {
    if (!targetRequestId) return;
    setLoading(true);
    const resp = await fetch(`${BACKEND_URL}/api/v1/requests/${targetRequestId}/resolve`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({
        interrupt_type: "PIC_INTAKE",
        user_response: sentence,
      }),
    });
    const data = await resp.json();
    upsertRequestInList(data);
    await syncRequestsFromBackend(true, targetRequestId);
    setLoading(false);
  };

  const handleApproveOrEdit = async (
    targetSnapshot: any,
    decision: "approve" | "edit" | "reject",
    cognitiveConfirmation: string,
    editedBody?: string
  ) => {
    const reqId = targetSnapshot?.request_id;
    if (!reqId) return;
    setLoading(true);
    setErrorBanner(null);
    const approvalHash =
      targetSnapshot?.interrupt?.approval_hash ||
      targetSnapshot?.state?.approval_hash ||
      "";
    const resp = await fetch(`${BACKEND_URL}/api/v1/requests/${reqId}/approve`, {
      method: "POST",
      headers: authHeaders,
      body: JSON.stringify({
        decision,
        approval_hash: approvalHash,
        cognitive_confirmation: cognitiveConfirmation,
        edited_body: editedBody || "",
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      setErrorBanner(data.detail || "Gagal memproses konfirmasi");
    } else {
      upsertRequestInList(data);
    }
    await syncRequestsFromBackend(true, reqId);
    setLoading(false);
  };

  const handleUndoOutbox = async (actionId: string) => {
    await fetch(`${BACKEND_URL}/api/v1/outbox/${actionId}/undo`, {
      method: "POST",
      headers: { "X-API-Key": SEKRE_API_KEY },
    });
    await refreshAuditAndOutbox(selectedRequestIdRef.current || undefined);
  };

  const pendingRequests = allRequests.filter(isPendingRequest);
  const completedRequests = allRequests.filter((r) => !isPendingRequest(r));
  const currentTabList = queueTab === "pending" ? pendingRequests : completedRequests;

  const selectedSnapshot =
    allRequests.find((r) => r.request_id === selectedRequestId) ||
    currentTabList[0] ||
    allRequests[0] ||
    null;

  const selectedIndexInTab = selectedSnapshot
    ? currentTabList.findIndex((r) => r.request_id === selectedSnapshot.request_id)
    : -1;

  // When showAllPending is true on the pending tab, render all pending items;
  // otherwise render ONLY the currently selected item so clicking any card in the top list
  // immediately updates the bottom section to that exact item.
  const displayedSnapshots: any[] =
    queueTab === "pending" && showAllPending && pendingRequests.length > 0
      ? pendingRequests
      : selectedSnapshot
      ? [selectedSnapshot]
      : [];

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6 pb-32 space-y-6 max-w-7xl mx-auto">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-extrabold tracking-tight text-white">
            SEKRE — Pusat Konfirmasi Pengiriman Pesan (WhatsApp &amp; Email)
          </h1>
          <p className="mt-0.5 text-xs text-slate-400">
            PT Nusantara Alat Berat · Terhubung Otomatis dengan Tencent WorkBuddy
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setLiveSyncEnabled(!liveSyncEnabled)}
            className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition ${
              liveSyncEnabled
                ? "border-emerald-500/40 bg-emerald-950/50 text-emerald-300"
                : "border-slate-700 bg-slate-900 text-slate-400"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                liveSyncEnabled ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
              }`}
            />
            {liveSyncEnabled
              ? "Sinkronisasi WorkBuddy: Aktif"
              : "Sinkronisasi WorkBuddy: Nonaktif"}
          </button>
          <button
            onClick={() => syncRequestsFromBackend(true)}
            className="rounded-xl border border-indigo-500/40 bg-indigo-950/60 px-3.5 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-900/60"
          >
            🔄 Muat Ulang Semua Pesan
          </button>
        </div>
      </header>

      <ScenarioLauncher
        activeScenarioId={activeScenario?.id}
        loading={loading}
        onRunScenario={handleRunScenario}
      />

      {errorBanner && (
        <div className="rounded-xl border border-red-500 bg-red-950/70 p-4 text-xs font-semibold text-red-200">
          ⚠️ Peringatan Sistem: {errorBanner}
        </div>
      )}

      {/* Panel Daftar Antrean Permintaan (Klik kartu mana saja untuk langsung melihat & menyetujui di bawah) */}
      {allRequests.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold text-white">
                📥 Daftar Permintaan Pengiriman Pesan
              </h2>
              <button
                type="button"
                onClick={() => {
                  setQueueTab("pending");
                  if (pendingRequests[0]) {
                    selectRequest(pendingRequests[0].request_id, false);
                  }
                }}
                className={`rounded-lg px-3 py-1 text-xs font-bold transition ${
                  queueTab === "pending"
                    ? "bg-amber-500 text-slate-950"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                ⏳ Perlu Konfirmasi ({pendingRequests.length})
              </button>
              <button
                type="button"
                onClick={() => {
                  setQueueTab("history");
                  if (completedRequests[0]) {
                    selectRequest(completedRequests[0].request_id, false);
                  }
                }}
                className={`rounded-lg px-3 py-1 text-xs font-bold transition ${
                  queueTab === "history"
                    ? "bg-emerald-500 text-slate-950"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                ✅ Selesai / Riwayat ({completedRequests.length})
              </button>
            </div>

            {queueTab === "pending" && pendingRequests.length > 1 && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowAllPending(false)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                    !showAllPending
                      ? "border-indigo-400 bg-indigo-600 text-white"
                      : "border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600"
                  }`}
                >
                  🎯 Tampilkan yang Diklik Saja
                </button>
                <button
                  type="button"
                  onClick={() => setShowAllPending(true)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                    showAllPending
                      ? "border-indigo-400 bg-indigo-600 text-white"
                      : "border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600"
                  }`}
                >
                  📋 Tampilkan Semua Sekaligus ({pendingRequests.length})
                </button>
              </div>
            )}
          </div>

          <p className="text-xs text-slate-400">
            💡 Klik salah satu kartu di bawah ini untuk langsung membuka dan menyetujui pesan tersebut pada bagian detail di bawah:
          </p>

          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 lg:grid-cols-3">
            {currentTabList.map((req, idx) => {
              const info = getRequestSummary(req);
              const isSelected =
                !showAllPending && req.request_id === selectedSnapshot?.request_id;
              return (
                <div
                  key={req.request_id}
                  onClick={() => selectRequest(req.request_id, true)}
                  className={`cursor-pointer rounded-xl border p-3.5 transition-all ${
                    isSelected
                      ? "border-indigo-400 bg-indigo-950/60 ring-2 ring-indigo-500/40 shadow-lg"
                      : "border-slate-800 bg-slate-950/70 hover:border-indigo-500/40 hover:bg-slate-900"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${info.statusColor}`}
                    >
                      #{idx + 1} · {info.statusLabel}
                    </span>
                    <span className="font-mono text-[10px] text-slate-400">
                      {formatAuditTimestamp(req.updated_at_iso)}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold text-white truncate">
                    {info.recipientName}{" "}
                    {info.orgName ? (
                      <span className="font-normal text-slate-300">
                        — {info.orgName}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2 text-xs">
                    <span className="font-mono font-semibold text-indigo-300 truncate">
                      {info.channel === "whatsapp" ? "📲 " : "✉️ "}
                      {info.destination}
                    </span>
                    {isSelected && (
                      <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300">
                        Sedang Dibuka
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <div ref={detailSectionRef} className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {displayedSnapshots.length === 0 && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-10 text-center space-y-2">
              <div className="text-2xl">📲</div>
              <h3 className="text-base font-bold text-white">
                Menunggu Perintah dari Tencent WorkBuddy
              </h3>
              <p className="mx-auto max-w-md text-xs text-slate-400 leading-relaxed">
                Kirimkan transkrip suara atau perintah pengiriman pesan di{" "}
                <strong>Tencent WorkBuddy</strong>. Semua draf pesan beserta nomor WhatsApp /
                alamat Email tujuan akan otomatis tampil di halaman ini untuk Anda setujui.
              </p>
            </div>
          )}

          {displayedSnapshots.map((snapItem, idx) => {
            const intr = snapItem?.interrupt;
            const st = snapItem?.state || {};
            const info = getRequestSummary(snapItem);
            const displayNumber = showAllPending
              ? idx + 1
              : selectedIndexInTab >= 0
              ? selectedIndexInTab + 1
              : 1;
            const totalInCurrentMode = showAllPending
              ? displayedSnapshots.length
              : currentTabList.length;

            return (
              <div key={snapItem.request_id || idx} className="space-y-4">
                {totalInCurrentMode > 1 && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-500/40 bg-indigo-950/40 px-4 py-2.5 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-indigo-600 px-2 py-0.5 font-bold text-white">
                        Permintaan #{displayNumber} dari {totalInCurrentMode}
                      </span>
                      <span className="font-bold text-white">
                        {info.recipientName}
                      </span>
                      {info.orgName && (
                        <span className="text-slate-300">— {info.orgName}</span>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-400">
                        Waktu Masuk: {formatAuditTimestamp(snapItem.updated_at_iso)}
                      </span>
                      {!showAllPending && currentTabList.length > 1 && (
                        <div className="flex items-center gap-1 ml-2">
                          <button
                            type="button"
                            disabled={selectedIndexInTab <= 0}
                            onClick={() => {
                              const prev = currentTabList[selectedIndexInTab - 1];
                              if (prev) selectRequest(prev.request_id, false);
                            }}
                            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-40"
                          >
                            ⬅️ Sebelumnya
                          </button>
                          <button
                            type="button"
                            disabled={
                              selectedIndexInTab < 0 ||
                              selectedIndexInTab >= currentTabList.length - 1
                            }
                            onClick={() => {
                              const next = currentTabList[selectedIndexInTab + 1];
                              if (next) selectRequest(next.request_id, false);
                            }}
                            className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-40"
                          >
                            Selanjutnya ➡️
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {intr && (intr.type === "CLARIFY" || intr.type === "PIC_INTAKE") && (
                  <ClarifyAndPicModal
                    interrupt={intr}
                    onResolveClarify={(cid, slot) =>
                      handleResolveClarify(snapItem.request_id, cid, slot)
                    }
                    onResolvePicIntake={(sentence) =>
                      handleResolvePicIntake(snapItem.request_id, sentence)
                    }
                  />
                )}

                {(intr?.type === "APPROVAL_GATE" || st?.plan) && (
                  <ApprovalInbox
                    requestId={snapItem?.request_id}
                    plan={intr?.plan || st?.plan}
                    findings={intr?.findings || st?.findings || []}
                    injectionFlags={
                      intr?.injection_flags || st?.injection_flags || []
                    }
                    approvalHash={
                      intr?.approval_hash || st?.approval_hash || ""
                    }
                    onApprove={(decision, confirmText, editedBody) =>
                      handleApproveOrEdit(
                        snapItem,
                        decision,
                        confirmText,
                        editedBody
                      )
                    }
                  />
                )}

                {st?.context && (
                  <CustomerContextPanel contextMap={st.context} />
                )}
              </div>
            );
          })}
        </div>

        <div className="space-y-6">
          <AuditTimeline
            events={auditData.events}
            verification={auditData.verification}
            onVerifyChain={() =>
              refreshAuditAndOutbox(selectedSnapshot?.request_id)
            }
          />
        </div>
      </div>

      <OutboxCountdown
        items={outboxItems}
        onUndo={handleUndoOutbox}
        onRefresh={() => refreshAuditAndOutbox(selectedSnapshot?.request_id)}
      />
    </main>
  );
}
