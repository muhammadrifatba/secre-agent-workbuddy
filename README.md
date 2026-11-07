# SEKRE v3 — Heavy Machinery Transcript-to-WhatsApp Agent & Governance Console
### *Executive Office Secretary & After-Sales Service Agent for Tencent WorkBuddy & Web*

[![Acceptance Tests](https://img.shields.io/badge/Acceptance%20Tests-16%20Passed-brightgreen)](file:///d:/Project/Hackathon/backend/tests/test_acceptance_t1_t5.py)
[![Tencent WorkBuddy](https://img.shields.io/badge/Tencent-WorkBuddy%20Skill-0052D9?logo=tencent)](file:///d:/Project/Hackathon/workbuddy/SKILL.md)
[![FastAPI](https://img.shields.io/badge/FastAPI-v3.0.0-009688?logo=fastapi)](file:///d:/Project/Hackathon/backend/app/main.py)
[![Next.js](https://img.shields.io/badge/Next.js-14%20(Tailwind)-black?logo=next.js)](file:///d:/Project/Hackathon/frontend/src/app/page.tsx)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Process%20Checkpoints-blue)](file:///d:/Project/Hackathon/backend/app/graph/workflow.py)

---

## 📖 Ringkasan Proyek (Overview)

**SEKRE v3** adalah sistem AI Agent cerdas untuk industri **Penjualan & Layanan Purna Jual Alat Berat (*Heavy Machinery Selling & After-Sales Service*)** — PT Nusantara Alat Berat.

Sistem ini memecahkan masalah komunikasi operasional tambang/konstruksi:
1. **Ekstraksi Transkrip Suara Alami:** Mengambil rekaman suara percakapan telepon, *voice note* WhatsApp, atau catatan rapat lapangan (*site meeting*) yang berantakan, lalu membedahnya secara otomatis menjadi **Tabel Komplain Teknis (*Service Breakdown*)** vs. **Tabel Permintaan Komersial (*Demand Penjualan Unit/Kontrak*)** lengkap dengan SLA dan divisi penanggung jawab.
2. **Aturan Urutan Bisnis Emas (*Golden Hierarchy*):** Komplain teknis dan janji dokumen wajib diselesaikan terlebih dahulu sebelum mengajukan penawaran komersial baru.
3. **Arsitektur Hybrid (Tencent WorkBuddy + Web Console):** Perintah dapat dijalankan langsung di dalam **Tencent WorkBuddy** (via FastMCP), tersinkronisasi secara *real-time* ke **Web Governance Console (`http://localhost:3000`)**, dan menghasilkan tautan langsung kirim WhatsApp (`wa.me`) dengan nomor tujuan yang akurat.
4. **Sistem Tata Kelola & Keamanan Deterministik:**
   - 🛡️ **Pertahanan Prompt Injection:** Mendeteksi dan membuang instruksi jahat tersembunyi di lampiran/notulen rapat.
   - 🔒 **Pencegahan Peracunan Profil (*Profile Poisoning*):** Menolak pengubahan nomor kontak/rekening dari sumber tidak terdaftar.
   - 🔑 **Ikatan Kriptografis SHA-256 (*Approval Gate*):** Draf divalidasi dengan hash kriptografis sehingga isi pesan tidak dapat dimanipulasi setelah disetujui.
   - ⚠️ **Gesekan Kognitif (*Step-Up Cognitive Friction*):** Mengharuskan konfirmasi nama penerima saat mengirim ke pelanggan eksternal.
   - ⏳ **Antrean Pengaman 60 Detik (*Outbox Undo*):** Waktu tunda 60 detik untuk membatalkan pengiriman email/tiket CRM.
   - 📜 **Log Audit Kriptografis HMAC-SHA256 (*Tamper-Evident*):** Setiap perubahan status dicatat dalam *hash chain* anti-manipulasi.
   - 🕌 **Sensitivitas Zona Waktu & Waktu Ibadah:** Mengenali WIB/WITA/WIT dan secara otomatis menghindari waktu Sholat Jumat (11:30–13:00).

---

## 🏗️ Arsitektur Sistem

```
┌────────────────────────────────┐         ┌─────────────────────────────────────┐
│      Tencent WorkBuddy         │         │      Web Governance Console         │
│      (Desktop AI Agent)        │         │      (Next.js 14 @ localhost:3000)  │
│                                │         │                                     │
│  • Voice Transcript Breakdown  │         │  • Multi-Request Approval Inbox     │
│  • Complaint vs Demand Mapping │         │  • Recipient & WA Phone Display     │
│  • FastMCP Client (stdio)      │         │  • 60s Outbox Countdown & Undo      │
└──────────────┬─────────────────┘         └──────────────────┬──────────────────┘
               │                                              │
               │ (FastMCP: sekre_submit_input)                │ (REST API: /api/v1/*)
               ▼                                              ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                           SEKRE v3 BACKEND (FastAPI)                           │
│                                                                                │
│  • LangGraph State Machine (12+ Isolated Deterministic & LLM Nodes)            │
│  • SQLite Multi-Process Checkpointer (langgraph_checkpoints.db)                │
│  • Context Store & Contact Registry (pic.json / orgs_and_news.json)           │
│  • Security Engine (Prompt Injection, Hash-Chaining, Friction Verification)    │
│  • Channel Adapters (wa.me link generator, 60s Outbox Queue)                   │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📋 Prasyarat Sistem (Prerequisites)

Sebelum memulai instalasi, pastikan sistem Anda memiliki:
- **Python 3.10+** (disarankan Python 3.11 atau 3.12)
- **Node.js 18+** & **npm** (untuk antarmuka web)
- **Git**
- *(Opsional tapi disarankan)* **Tencent WorkBuddy** Desktop Client

---

## 🚀 Panduan Instalasi & Menjalankan Proyek

### 1. Clone Repository

```bash
git clone https://github.com/muhammadrifatba/secre-agent-workbuddy.git
cd secre-agent-workbuddy
```

---

### 2. Setup Backend (FastAPI & LangGraph)

1. Masuk ke direktori `backend`:
   ```bash
   cd backend
   ```

2. Buat dan aktifkan *virtual environment* Python:
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Pasang dependensi:
   ```bash
   pip install -e .
   ```

4. Buat file konfigurasi `.env`:
   ```bash
   cp .env.example .env
   ```
   *(Secara default, `USE_MOCK_LLM_FALLBACK=true` sudah aktif sehingga sistem dapat berjalan 100% offline tanpa API Key pihak ketiga. Jika ingin menggunakan Google Gemini atau Tencent Hunyuan/DeepSeek, isi `GOOGLE_API_KEY` atau `TENCENT_LLM_API_KEY` pada file `.env`).*

5. Jalankan server FastAPI Backend:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *Backend kini aktif di: `http://127.0.0.1:8000` (Dokumentasi API: `http://127.0.0.1:8000/docs`).*

---

### 3. Setup Frontend (Web Governance Console)

1. Buka terminal baru dan masuk ke direktori `frontend`:
   ```bash
   cd frontend
   ```

2. Pasang dependensi Node.js:
   ```bash
   npm install
   ```

3. Buat file environment frontend:
   ```bash
   cp .env.local.example .env.local
   ```

4. Jalankan server pengembangan Next.js:
   ```bash
   npm run dev
   ```
   *Frontend kini aktif di: `http://localhost:3000`.*

---

### 4. Konfigurasi Tencent WorkBuddy (Agent & Skill)

Terdapat 2 cara mudah menghubungkan SEKRE ke Tencent WorkBuddy:

#### Opsi A: Menambahkan MCP Tool ke Tencent WorkBuddy (Direkomendasikan)
Di WorkBuddy Desktop:
1. Buka **Settings** $\rightarrow$ **MCP Servers** $\rightarrow$ **Add Server**.
2. Masukkan konfigurasi JSON berikut (sesuaikan path absolut ke instalasi Python environment Anda):

```json
{
  "mcpServers": {
    "sekre_governance": {
      "command": "d:/Project/Hackathon/backend/.venv/Scripts/python.exe",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "d:/Project/Hackathon/backend"
      }
    }
  }
}
```

#### Opsi B: Memasang Skill WorkBuddy
File instruksi skill telah disediakan lengkap di direktori:
- [`workbuddy/SKILL.md`](file:///d:/Project/Hackathon/workbuddy/SKILL.md)
- Arsip siap impor: [`skills/sekre-office-agent-skill.zip`](file:///d:/Project/Hackathon/skills/sekre-office-agent-skill.zip) atau [`skills/transcript-wa-heavy-machinery-skill.zip`](file:///d:/Project/Hackathon/skills/transcript-wa-heavy-machinery-skill.zip).

---

## 🧪 Cara Menggunakan & Skenario Uji Coba

### Cara 1: Menguji via Tencent WorkBuddy (Chat Interaktif)
Ketik atau *paste* salah satu transkrip percakapan suara pelanggan ke kolom chat WorkBuddy:

```text
Tolong ekstrak transkrip voice note ini menjadi mapping Komplain dan Demand beserta follow-up-nya, lalu jalankan perintah kirim WA via SEKRE:

"Halo Pak Rifat, selamat pagi menjelang siang... Ini Budi Santoso dari PT Mahakam Coal Energi di Balikpapan. Pak, saya kirim voice note aja ya biar cepat. Tadi pagi kepala tambang saya di site Bengalon lapor, ada 2 unit Bulldozer D85ESS-2 kita yang tiba-tiba low power gara-gara common rail fuel injector-nya bermasalah dan filter solarnya mampet, padahal baru diservis dua minggu lalu. Tim site kita agak kecewa karena klaim penggantian injector-nya belum di-acc sama cabang sejak kemarin. Yang kedua Pak, untuk kuartal IV ini kita mau finalisasi PO perpanjangan kontrak Full Maintenance Contract (FMC) armada kita, plus kita lagi butuh tambahan 2 unit Motor Grader GD535-5 buat merapikan jalan hauling yang habis kena hujan deras minggu ini. Tolong dibantu bereskan komplain injector D85ESS-2 tadi dulu ya Pak, terus kabari saya via WA untuk penawaran 2 unit Motor Grader GD535-5 sama jadwal rapat finalisasi kontrak FMC-nya."
```

WorkBuddy akan:
1. Menampilkan **Tabel Identitas Transkrip & Unit Alat Berat**.
2. Menampilkan **Tabel Mapping Komplain $\rightarrow$ Follow-Up Solusi & Target SLA**.
3. Menampilkan **Tabel Mapping Demand $\rightarrow$ Follow-Up Penawaran Komersial**.
4. Memanggil MCP `sekre_submit_input` dan menampilkan pratinjau draf pesan.
5. Membuka persetujuan di Web Console atau di chat WorkBuddy hingga menghasilkan tautan `https://wa.me/6281227676794?text=...`.

---

### Cara 2: Menguji via Web Governance Console (`http://localhost:3000`)
1. Buka browser di `http://localhost:3000`.
2. Klik tombol pada panel **"🚜 Uji Skenario Mapping Komplain & Demand Alat Berat"**:
   - **Skenario 1 — PT Borneo Karya Tambang (Pak Hendra):** Menguji pendaftaran kontak baru (*PIC Intake*) + Komplain hydraulic pump Dump Truck HD785 terlambat 5 hari + Janji brosur TCO + Penawaran 4 unit Excavator PC200-8M0.
   - **Skenario 2 — PT Mahakam Coal Energi (Pak Budi Santoso):** Menguji komplain klaim garansi fuel injector Bulldozer D85ESS-2 + Perpanjangan kontrak servis FMC Q4 + Penawaran 2 unit Motor Grader GD535-5.
   - **Skenario 3 — PT Konawe Nikel Perkasa (Pak Rendi Pratama):** Menguji komplain keausan dini undercarriage PC400LC-8 + Mundurnya jadwal PM 1.000 HM + Penawaran 3 unit Excavator PC300-8M0 & paket sparepart 6 bulan.
   - **Skenario 4 — PT Kalimantan Prima Konstruksi (Pak Surya Dharma):** Menguji komplain kebocoran radiator Wheel Loader WA380-6 & lambatnya respon hotline + Janji pelatihan operator + Penawaran 5 unit alat berat jalan.
3. Di panel **Approval Inbox**, periksa nama penerima dan nomor WhatsApp/Email tujuan (`+628...`).
4. Centang konfirmasi persetujuan, lalu klik tombol hijau **`✅ Setujui & Kirim`**.
5. Klik tombol **`📲 Buka & Kirim ke WhatsApp`** untuk langsung membuka obrolan WhatsApp dengan isi pesan yang tersusun rapi.

---

## 🛡️ Menjalankan Pengujian Otomatis (*Acceptance Tests*)

Sistem telah dilengkapi dengan *suite* pengujian otomatis menyeluruh (T1–T5, MCP tools, dan pertahanan keamanan):

```bash
# Dari direktori root proyek:
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_acceptance_t1_t5.py -v
```

Hasil uji: **16 passed in ~10s** (100% lulus tanpa kegagalan).

---

## 📁 Struktur Direktori Proyek

```
Hackathon/
├── backend/                       # Python FastAPI & LangGraph Backend
│   ├── app/
│   │   ├── adapters/              # Channel delivery (WhatsApp wa.me, Email, CRM, STT)
│   │   ├── core/                  # Security engine, Audit logger, Outbox, Contact store
│   │   ├── graph/                 # LangGraph nodes, Workflow graph, Checkpointer
│   │   ├── models/                # Pydantic schemas (Domain, State, API)
│   │   ├── main.py                # REST API endpoints & Auth middleware
│   │   └── mcp_server.py          # FastMCP server untuk Tencent WorkBuddy
│   ├── config/fixtures/           # pic.json (daftar kontak), orgs_and_news.json
│   └── tests/                     # Acceptance test suite (test_acceptance_t1_t5.py)
├── frontend/                      # Next.js 14 Web Governance Console
│   ├── src/
│   │   ├── app/page.tsx           # Dashboard utama (Multi-Request Approval Console)
│   │   ├── components/            # ApprovalInbox, ClarifyModal, Outbox, AuditTimeline
│   │   └── lib/                   # API client, Type definitions, FormatTime utilities
├── skills/                        # Direktori Skill untuk AI Agents
│   ├── sekre-office-agent/        # Core Sekre Skill
│   └── transcript-wa-heavy-machinery/ # Heavy Machinery Transcript Skill
├── workbuddy/                     # Konfigurasi & Data Dummy Tencent WorkBuddy
│   ├── SKILL.md                   # Instruksi agent Tencent WorkBuddy
│   └── dummy_transcripts_heavy_machinery.json # 4 Data dummy percakapan suara alat berat
├── .gitignore                     # Filter git untuk mengamankan secret & file besar
└── README.md                      # Dokumentasi lengkap proyek
```

---

## 👥 Tim & Lisensi

- **Pengembang:** Muhammad Rifat ([@muhammadrifatba](https://github.com/muhammadrifatba))
- **Organisasi:** PT Nusantara Alat Berat
- **Platform:** Tencent WorkBuddy Hackathon
- **Lisensi:** MIT License (2026)
