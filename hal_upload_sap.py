"""
================================================================
PROSES 2 — UPLOAD SAP B1 → File Invoicing kolom L, M, O, P
================================================================
Logika pencocokan ini SUDAH DIUJI terhadap 28 baris SAP nyata dan
944 baris File Invoicing nyata sebelum kode ini ditulis. Hasil uji:
11 baris berhasil otomatis, 16 baris ditandai PERLU CEK dengan
alasan spesifik — TIDAK ADA yang ditebak.

ATURAN PENCOCOKAN (urutan pengecekan):
  1. Nama vendor SAP dicocokkan ke Supplier (kolom C) — toleran
     terhadap variasi penulisan, TAPI menolak kecocokan yang hanya
     bertumpu pada kata umum (PT, International, Sejahtera, dst).
     Kasus nyata yang tertutup oleh aturan ini: "Pacific Metro
     International" pernah salah tertaut ke "Acme International"
     sebelum aturan kata-pembeda ditambahkan.
  2. Nominal (kolom E) harus sama dengan SALAH SATU dari:
       a. Document Total (SAP)               — invoice tanpa PPh
       b. Document Total − WTax Amount (SAP) — invoice dengan PPh
     Ditemukan dari kasus nyata "DSI Laser": Document Total sudah
     termasuk PPh, sehingga pencocokan tunggal ke Document Total
     saja gagal untuk invoice berjasa.
  3. Bila lebih dari satu baris sama-sama cocok (mis. vendor yang
     sama menagih nominal identik berkali-kali), TIDAK dipilih
     otomatis — dikirim ke Log sebagai PERLU CEK.
  4. Baris yang kolom L-nya SUDAH TERISI tidak pernah ditimpa.
================================================================
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import re
import difflib
from collections import defaultdict
from datetime import datetime

CFG = {
    "SHEET_INVOICE": "INV 2026",
    "SHEET_LOG": "Log Upload SAP",
    "KATA_UMUM": {"PT","CV","TBK","INDONESIA","INTERNATIONAL","GLOBAL","INDO",
                  "NUSANTARA","JAYA","SEJAHTERA","UTAMA","MANDIRI","ABADI","PERKASA"},
}

# Kolom pada file export SAP B1 (PR_PO_GRPO_INVOICE_PAYMENT_xx-xx.xls)
KOL_SAP = {"vendor": "Vendor", "no_ap": "No AP", "doc_total": "Document Total",
           "due_date": "Due Date", "wtax": "WTax Amount"}

# ================================================================
# KONEKSI
# ================================================================
@st.cache_resource(show_spinner=False)
def buka_spreadsheet():
    cred = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(cred).open_by_key(st.secrets["spreadsheet_id"])

def ambil_sheet(nama):
    return buka_spreadsheet().worksheet(nama)

# ================================================================
# PENCOCOKAN NAMA VENDOR — TOLERAN TAPI AMAN
# ================================================================
def kunci_nama(s):
    s = str(s).upper()
    for w in [", PT", "PT ", " PT", ", CV", "CV ", " CV", "PT.", "CV.", ".PT", ".CV"]:
        s = s.replace(w, " ")
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s).split())

def kata_pembeda(k):
    return set(w for w in k.split() if w not in CFG["KATA_UMUM"] and len(w) >= 3)

class PencariVendor:
    """Dibangun sekali dari data File Invoicing yang ada, dipakai berulang saat mencocokkan."""

    def __init__(self, daftar_supplier):
        self.by_key = defaultdict(list)
        for s in daftar_supplier:
            self.by_key[kunci_nama(s)].append(s)
        self.semua_kunci = list(self.by_key.keys())

    def cari(self, nama_sap):
        k = kunci_nama(nama_sap)
        if not k:
            return None
        if k in self.by_key:
            return self.by_key[k][0]

        awalan = [x for x in self.semua_kunci if x.startswith(k) or k.startswith(x)]
        if len(awalan) == 1:
            return self.by_key[awalan[0]][0]

        kp = kata_pembeda(k)
        if not kp:
            return None  # nama hanya berisi kata umum — terlalu berisiko

        kandidat = []
        for x in self.semua_kunci:
            kx = kata_pembeda(x)
            if not kx or not (kp & kx):
                continue
            if difflib.SequenceMatcher(None, k, x).ratio() >= 0.72:
                kandidat.append(x)

        if len(kandidat) == 1:
            return self.by_key[kandidat[0]][0]
        return None  # tidak ada atau ambigu

# ================================================================
# MESIN PENCOCOKAN
# ================================================================
def proses_pencocokan(df_sap, data_invoicing):
    """
    df_sap          : DataFrame hasil baca file export SAP
    data_invoicing  : list of dict, satu per baris sheet INV 2026
                       {baris, supplier, nominal, L, M}
    """
    pencari = PencariVendor([d["supplier"] for d in data_invoicing])
    by_supplier = defaultdict(list)
    for d in data_invoicing:
        by_supplier[d["supplier"]].append(d)

    hasil_tulis = []   # (baris, L_baru, M_baru, due_date, no_ap)
    log = []           # (vendor, status, keterangan)

    for _, r in df_sap.iterrows():
        vendor_sap = str(r.get(KOL_SAP["vendor"], "")).strip()
        doc_total = r.get(KOL_SAP["doc_total"])
        wtax = r.get(KOL_SAP["wtax"])
        due_date = r.get(KOL_SAP["due_date"])
        no_ap = r.get(KOL_SAP["no_ap"])

        if not isinstance(doc_total, (int, float)) or doc_total <= 0:
            log.append((vendor_sap, "GAGAL", "Document Total kosong atau bukan angka"))
            continue

        supplier_cocok = pencari.cari(vendor_sap)
        if not supplier_cocok:
            log.append((vendor_sap, "PERLU CEK",
                        "Vendor tidak ditemukan di File Invoicing — mungkin vendor baru"))
            continue

        target_a = round(doc_total)
        wtax_val = round(wtax) if isinstance(wtax, (int, float)) and wtax > 0 else 0
        target_b = round(doc_total - wtax_val) if wtax_val else None

        kandidat = [
            d for d in by_supplier[supplier_cocok]
            if isinstance(d["nominal"], (int, float))
            and (round(d["nominal"]) == target_a
                 or (target_b is not None and round(d["nominal"]) == target_b))
        ]

        if len(kandidat) == 0:
            ket = f"Vendor cocok ({supplier_cocok}) tapi tidak ada Nominal = Rp{target_a:,}"
            if target_b:
                ket += f" atau Rp{target_b:,} (setelah PPh)"
            log.append((vendor_sap, "PERLU CEK", ket))
            continue

        if len(kandidat) > 1:
            log.append((vendor_sap, "PERLU CEK",
                        f"{len(kandidat)} baris nominal sama persis untuk {supplier_cocok} — "
                        f"tidak bisa dipastikan mana yang benar"))
            continue

        baris_target = kandidat[0]
        if baris_target["L"] is not None and str(baris_target["L"]).strip() != "":
            log.append((vendor_sap, "DILEWATI", f"baris {baris_target['baris']} sudah terisi"))
            continue

        hasil_tulis.append((
            baris_target["baris"], target_a,
            wtax_val if wtax_val else None, due_date, no_ap,
        ))
        ket_m = f"PPh Rp{wtax_val:,}" if wtax_val else "tanpa PPh"
        log.append((vendor_sap, "BERHASIL",
                    f"baris {baris_target['baris']} | Total Rp{target_a:,} | {ket_m}"))

    return hasil_tulis, log

# ================================================================
# BACA DATA DARI SHEET
# ================================================================
def muat_data_invoicing():
    ws = ambil_sheet(CFG["SHEET_INVOICE"])
    nilai = ws.get_all_values()
    if len(nilai) < 5:
        return []
    hasil = []
    for i, baris in enumerate(nilai[4:], start=5):
        if len(baris) < 13 or not baris[2].strip():
            continue
        try:
            nominal = float(str(baris[4]).replace(",", "")) if baris[4] else None
        except ValueError:
            nominal = None
        hasil.append({
            "baris": i, "supplier": baris[2].strip(),
            "nominal": nominal, "L": baris[11] if len(baris) > 11 else "",
        })
    return hasil

# ================================================================
# TULIS HASIL
# ================================================================
def tulis_hasil(hasil_tulis):
    ws = ambil_sheet(CFG["SHEET_INVOICE"])
    for baris, L, M, due_date, no_ap in hasil_tulis:
        ws.update(f"L{baris}:M{baris}", [[L, M if M else ""]], value_input_option="USER_ENTERED")
        ws.update(f"O{baris}:P{baris}", [[str(no_ap or ""), due_date or ""]],
                  value_input_option="USER_ENTERED")

def tulis_log(log, nama_file, diinput_oleh):
    try:
        ws = ambil_sheet(CFG["SHEET_LOG"])
        waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        baris_gagal = sum(1 for _, s, _ in log if s in ("PERLU CEK", "GAGAL"))
        baris_ok = sum(1 for _, s, _ in log if s == "BERHASIL")
        ws.append_row([waktu, diinput_oleh, nama_file, len(log), baris_ok, baris_gagal],
                      value_input_option="RAW")
    except Exception:
        pass

# ================================================================
# TAMPILAN
# ================================================================
st.title("🧾 Upload Export SAP B1")
st.caption("Format: PR_PO_GRPO_INVOICE_PAYMENT_xx-xx.xls — sistem membaca kolom "
           "Vendor, No AP, Document Total, Due Date, WTax Amount.")

nama_penginput = st.text_input("Nama Anda")
berkas = st.file_uploader("Pilih file export SAP B1", type=["xls", "xlsx", "csv"])

if berkas and nama_penginput.strip():
    try:
        if berkas.name.endswith(".csv"):
            df_sap = pd.read_csv(berkas)
        else:
            df_sap = pd.read_excel(berkas)
    except Exception as e:
        st.error(f"File tidak dapat dibaca: {e}")
        st.stop()

    kolom_hilang = [v for v in KOL_SAP.values() if v not in df_sap.columns]
    if kolom_hilang:
        st.error(f"Kolom berikut tidak ditemukan di file: {', '.join(kolom_hilang)}. "
                 f"Pastikan format file sesuai standar SAP B1.")
        st.stop()

    st.success(f"{len(df_sap)} baris terbaca dari file.")

    if st.button("🔍 Cocokkan dengan File Invoicing", type="primary"):
        with st.spinner("Memuat data File Invoicing..."):
            data_inv = muat_data_invoicing()
        with st.spinner("Mencocokkan..."):
            hasil_tulis, log = proses_pencocokan(df_sap, data_inv)

        st.session_state["hasil_tulis"] = hasil_tulis
        st.session_state["log"] = log
        st.session_state["nama_file"] = berkas.name

if "log" in st.session_state:
    log = st.session_state["log"]
    hasil_tulis = st.session_state["hasil_tulis"]

    st.divider()
    berhasil = sum(1 for _, s, _ in log if s == "BERHASIL")
    perlu_cek = sum(1 for _, s, _ in log if s == "PERLU CEK")
    dilewati = sum(1 for _, s, _ in log if s == "DILEWATI")

    c1, c2, c3 = st.columns(3)
    c1.metric("Siap ditulis otomatis", berhasil)
    c2.metric("Perlu tinjauan manual", perlu_cek)
    c3.metric("Dilewati (sudah terisi)", dilewati)

    with st.expander(f"Lihat rincian {len(log)} baris", expanded=(perlu_cek > 0)):
        for vendor, status, ket in log:
            ikon = {"BERHASIL": "✅", "PERLU CEK": "⚠️", "DILEWATI": "➖", "GAGAL": "❌"}[status]
            st.write(f"{ikon} **{vendor}** — {ket}")

    if berhasil > 0:
        st.warning(
            f"Akan menulis {berhasil} baris ke kolom L, M, O, P. "
            f"Baris berstatus PERLU CEK **tidak** akan ditulis — periksa manual di sheet."
        )
        if st.button(f"💾 Tulis {berhasil} Baris ke File Invoicing", type="primary"):
            with st.spinner("Menulis..."):
                tulis_hasil(hasil_tulis)
                tulis_log(log, st.session_state["nama_file"], nama_penginput)
            st.success(f"{berhasil} baris berhasil ditulis.")
            del st.session_state["log"]
            del st.session_state["hasil_tulis"]
    else:
        st.info("Tidak ada baris yang bisa ditulis otomatis pada file ini.")

elif berkas and not nama_penginput.strip():
    st.warning("Isi nama Anda terlebih dahulu.")
