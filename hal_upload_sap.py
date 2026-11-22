"""
================================================================
PROSES 2 — UPLOAD SAP B1 → File Invoicing kolom L, M, O, P
================================================================
Diuji terhadap 748 baris SAP nyata dan 1.185 catatan File
Invoicing nyata sebelum kode ini ditulis.

SASARAN MUTU YANG DISEPAKATI (Opsi A)
  100% dari baris SAP yang PASANGANNYA ADA di spreadsheet harus
  terisi otomatis. Baris yang pasangannya memang tidak ada bukan
  kegagalan mesin — tidak ada rumus yang bisa mencocokkan sesuatu
  dengan yang tidak ada.
  Hasil uji: 276 tertulis + 1 sengaja ditahan, dari 277 terjangkau.

ATURAN PENCOCOKAN

  TINGKAT 1 — lewat NOMOR INVOICE  (jalur utama)
    Kolom "No AP" pada ekspor SAP ternyata berisi NOMOR INVOICE
    VENDOR (SE700243, 591/INV-RTJ/VI/2026), bukan nomor dokumen
    internal. Nomor invoice hampir unik, jadi jauh lebih dapat
    dipercaya daripada menebak dari kemiripan nama.

    NOMINAL BUKAN SYARAT. Kolom L memang berasal dari SAP,
    sedangkan kolom E dicatat Purchasing dari invoice fisik.
    Menolak menulis karena keduanya berbeda justru menyembunyikan
    hal yang paling perlu dilihat. Selisihnya tetap ditulis, lalu
    ditandai agar terlihat.

    PENGAMAN. Nomor invoice pendek bisa bertabrakan. Kasus nyata:
    nomor "143" milik Pirmatasa tertaut ke Aifa Cutaka Plastik.
    Karena itu, selain nomor invoice, harus cocok juga SALAH SATU
    dari nama supplier atau nominal. Nomor yang panjangnya di
    bawah 5 karakter wajib cocok namanya.

  TINGKAT 2 — lewat NAMA SUPPLIER + NOMINAL  (jalur cadangan)
    Dipakai hanya untuk baris yang tidak tertangani Tingkat 1.
    Toleran terhadap variasi penulisan nama, TAPI menolak
    kecocokan yang hanya bertumpu pada kata umum (PT,
    International, Sejahtera). Kasus nyata yang tertutup aturan
    ini: "Pacific Metro International" pernah salah tertaut ke
    "Acme International".
    Nominal harus sama dengan Document Total ATAU Document Total
    dikurangi WTax (kasus nyata "DSI Laser": Document Total sudah
    termasuk PPh).

  BERLAKU DI KEDUA TINGKAT
    Baris yang kolom L-nya SUDAH TERISI tidak pernah ditimpa.
    Bila lebih dari satu baris sama-sama cocok, tidak dipilih —
    ditandai PERLU CEK. Sistem tidak menebak.
================================================================
"""

import io
import time
import math
import re
import difflib
from collections import defaultdict
from datetime import datetime

import streamlit as st
import pandas as pd

CFG = {
    "SHEET_INVOICE": "INV 2026",
    "SHEET_LOG": "Log Upload SAP",
    "KATA_UMUM": {"PT","CV","TBK","INDONESIA","INTERNATIONAL","GLOBAL","INDO",
                  "NUSANTARA","JAYA","SEJAHTERA","UTAMA","MANDIRI","ABADI","PERKASA"},
    "PANJANG_AMAN": 5,   # nomor invoice lebih pendek dari ini wajib cocok nama
}

# Kolom pada file export SAP B1 (List of A/P Invoices)
KOL_SAP = {"vendor": "Vendor", "no_ap": "No AP", "doc_total": "Document Total",
           "due_date": "Due Date", "wtax": "WTax Amount"}

# Kolom OPSIONAL. Kolom "No AP" (E) sebenarnya berisi nomor invoice VENDOR
# (AR-260900001, 401/2026, ...) dan dipakai untuk MENCOCOKKAN dengan kolom D
# spreadsheet. Nomor dokumen AP milik SAP ada di kolom lain (372601753, ...)
# yang judulnya memuat "No Ap Invoice". Itulah yang semestinya masuk ke
# kolom O spreadsheet. Bila kolom itu tidak ada di ekspor, sistem kembali
# memakai "No AP" seperti sebelumnya dan memberi tahu di layar.
KOL_SAP_OPSIONAL = {"no_ap_dok": "No Ap Invoice"}


def pilih_no_ap(no_ap_dok, no_ap_vendor):
    """Nilai untuk kolom O spreadsheet.

    Utamakan nomor dokumen AP dari SAP. Bila tidak ada atau rusak notasi
    ilmiah, kembali ke nomor invoice vendor; bila itu pun rusak, kosongkan
    daripada menulis angka yang salah.

    Dipakai Tingkat 1 DAN Tingkat 2 — jangan menyalin aturannya ke tempat
    lain, karena pernah terjadi kedua tingkat menulis nilai berbeda.
    """
    if no_ap_dok and not notasi_ilmiah(no_ap_dok):
        return no_ap_dok
    if no_ap_vendor and not notasi_ilmiah(no_ap_vendor):
        return no_ap_vendor
    return ""

from gspread.exceptions import APIError
from koneksi import ambil_sheet, pesan_ramah, panel_diagnosis


# ================================================================
# PENGURAI NILAI
# ================================================================
def ke_angka(x):
    """Teks angka -> float.

    Ekspor SAP memakai format Indonesia (95.545.748,00). Cara lama
    hanya membuang koma, sehingga nilai itu terbaca 95,545748 —
    salah lebih dari sejuta kali lipat. Fungsi ini menerima format
    Indonesia maupun Inggris.
    """
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return None if (isinstance(x, float) and math.isnan(x)) else float(x)
    s = str(x).strip().replace("\xa0", "").replace(" ", "")
    if not s or s.lower() in ("nan", "none", "nat", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = re.sub(r"[^0-9.,\-]", "", s)
    if not s or s in ("-", ".", ","):
        return None

    def ribuan(teks, tanda):
        bag = teks.split(tanda)
        return len(bag) > 2 or (len(bag) == 2 and len(bag[1]) == 3)

    if "." in s and "," in s:
        # Pemisah desimal adalah tanda yang muncul paling belakang.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if ribuan(s, ",") else s.replace(",", ".")
    elif "." in s:
        if ribuan(s, "."):
            s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def ke_tanggal(x):
    """Tanggal SAP (DD/MM/YYYY) -> 'YYYY-MM-DD'.

    Bentuk ISO dipakai karena Google Sheets membacanya sebagai
    tanggal asli tanpa terpengaruh pengaturan wilayah.
    """
    if x is None:
        return ""
    if hasattr(x, "strftime"):
        try:
            return x.strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(x).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
    if m:
        h, b, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= h <= 31 and 1 <= b <= 12:
            return "%04d-%02d-%02d" % (t, b, h)
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return ""


def ke_teks(x):
    """Nilai sel -> teks bersih. NaN dan sejenisnya jadi kosong,
    supaya tidak ada tulisan 'nan' yang masuk ke spreadsheet."""
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    s = str(x).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def notasi_ilmiah(s):
    """True bila nomor invoice rusak jadi notasi ilmiah (1,00001E+11).

    Terjadi saat SAP mengekspor nomor invoice yang seluruhnya angka.
    Nilai aslinya tidak dapat dipulihkan dari berkas ini — satu-
    satunya perbaikan adalah menyetel kolom itu sebagai Teks saat
    ekspor dari SAP.
    """
    return bool(re.match(r"^\d+[.,]?\d*E[+-]?\d+$", str(s).strip(), re.I))


def kunci_invoice(s):
    """Nomor invoice tanpa tanda baca, huruf besar — sama dengan
    rumus kolom V di spreadsheet."""
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()


# ================================================================
# PEMBACA BERKAS
# ================================================================
def baca_berkas_sap(berkas):
    """Membaca ekspor SAP apa pun bungkusnya.

    SAP B1 memberi nama berkas .xls padahal isinya teks bertabulasi
    berkode UTF-16. pandas.read_excel menolaknya mentah-mentah.
    Beberapa cara dicoba berurutan sampai ada yang menghasilkan
    kolom-kolom yang dibutuhkan.

    Mengembalikan (DataFrame, keterangan_cara_baca).
    """
    perlu = set(KOL_SAP.values())

    def petakan(df):
        """Cocokkan judul kolom SAP walau diberi anotasi.

        SAP mengekspor judul polos ("No AP"), tapi pengguna sering menambah
        catatan di baris judul ("No AP = Nomor AP Invoice (Kolom O)").
        Tanpa ini, berkas beranotasi ditolak mentah-mentah.

        Urutan: cocok persis dulu (penting — "Vendor" harus menang atas
        "Customer/Vendor Code"), baru cocok sebagian. Sebagian yang
        menghasilkan lebih dari satu calon dianggap gagal, bukan ditebak.
        """
        sisa = list(df.columns)
        peta = {}
        for butuh in perlu:                       # tahap 1: persis
            if butuh in sisa:
                peta[butuh] = butuh
                sisa.remove(butuh)
        for butuh in perlu - set(peta):           # tahap 2: diawali nama baku
            calon = [c for c in sisa if c.lower().startswith(butuh.lower())]
            if len(calon) == 1:
                peta[butuh] = calon[0]
                sisa.remove(calon[0])
        for butuh in perlu - set(peta):           # tahap 3: memuat nama baku
            calon = [c for c in sisa if butuh.lower() in c.lower()]
            if len(calon) == 1:
                peta[butuh] = calon[0]
                sisa.remove(calon[0])
        return peta

    def petakan_opsional(df, sudah):
        """Kolom tambahan yang boleh tidak ada. Dicari dari sisa kolom saja,
        supaya tidak pernah merebut kolom yang sudah dipakai kolom wajib."""
        sisa = [c for c in df.columns if c not in sudah]
        hasil = {}
        for baku in KOL_SAP_OPSIONAL.values():
            calon = [c for c in sisa if baku.lower() in c.lower()]
            if len(calon) == 1:
                hasil[baku] = calon[0]
                sisa.remove(calon[0])
        return hasil

    percobaan = [
        ("Excel", lambda b: pd.read_excel(b, dtype=str)),
        ("teks bertabulasi UTF-16", lambda b: pd.read_csv(b, sep="\t", encoding="utf-16", dtype=str)),
        ("teks bertabulasi UTF-8",  lambda b: pd.read_csv(b, sep="\t", encoding="utf-8-sig", dtype=str)),
        ("CSV koma",     lambda b: pd.read_csv(b, encoding="utf-8-sig", dtype=str)),
        ("CSV titikkoma", lambda b: pd.read_csv(b, sep=";", encoding="utf-8-sig", dtype=str)),
    ]
    kegagalan = []
    for nama, fn in percobaan:
        try:
            berkas.seek(0)
        except Exception:
            pass
        try:
            df = fn(berkas)
        except Exception as e:
            kegagalan.append(f"{nama}: {type(e).__name__}")
            continue
        df.columns = [str(c).strip() for c in df.columns]
        peta = petakan(df)
        if len(peta) == len(perlu):
            # seragamkan jadi judul baku supaya sisa kode tidak perlu tahu
            ubah = {asli: baku for baku, asli in peta.items() if asli != baku}
            ops = petakan_opsional(df, set(peta.values()))
            ubah.update({asli: baku for baku, asli in ops.items() if asli != baku})
            if ubah:
                df = df.rename(columns=ubah)
                nama += f" ({len(ubah)} judul beranotasi dikenali)"
            if KOL_SAP_OPSIONAL["no_ap_dok"] in df.columns:
                nama += " + kolom No Ap Invoice dipakai untuk kolom O"
            return df, nama
        hilang = sorted(perlu - set(peta))
        kegagalan.append(f"{nama}: terbaca tapi kolom tidak lengkap — "
                         f"belum ketemu: {', '.join(hilang)}")
    raise ValueError(
        "Berkas tidak dapat dibaca sebagai ekspor SAP. Yang sudah dicoba — "
        + "; ".join(kegagalan)
    )


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
    df_sap         : DataFrame hasil baca ekspor SAP
    data_invoicing : list of dict per baris sheet INV 2026
                     {baris, no, supplier, nominal, L, kunci}

    Mengembalikan (hasil_tulis, log, temuan, ringkas).
    """
    pencari = PencariVendor([d["supplier"] for d in data_invoicing])
    by_supplier = defaultdict(list)
    by_kunci = defaultdict(list)
    for d in data_invoicing:
        by_supplier[d["supplier"]].append(d)
        if d.get("kunci"):
            by_kunci[d["kunci"]].append(d)

    hasil_tulis = []
    log = []
    temuan = {"selisih": [], "vendor_baru": [], "invoice_belum_dicatat": [],
              "noap_rusak": [], "total_nol": [], "ambigu": []}
    dipakai = set()
    sisa = []
    terjangkau = 0

    def catat(vendor, status, ket):
        log.append((vendor, status, ket))

    # ---------------- TINGKAT 1 — nomor invoice ----------------
    for _, r in df_sap.iterrows():
        vendor = ke_teks(r.get(KOL_SAP["vendor"]))
        noap_asli = ke_teks(r.get(KOL_SAP["no_ap"]))
        # nomor dokumen AP yang akan ditulis ke kolom O; bila kolom itu
        # tidak ada, kembali memakai nomor invoice vendor seperti dulu
        noap_dok = ke_teks(r.get(KOL_SAP_OPSIONAL["no_ap_dok"])) or noap_asli
        total = ke_angka(r.get(KOL_SAP["doc_total"]))
        wtax = ke_angka(r.get(KOL_SAP["wtax"])) or 0
        due = ke_tanggal(r.get(KOL_SAP["due_date"]))

        baris_sap = {"vendor": vendor, "noap": noap_asli, "noap_dok": noap_dok,
                     "total": total, "wtax": wtax, "due": due}

        if total is None or total <= 0:
            temuan["total_nol"].append({**baris_sap, "sebab": "Document Total nol atau bukan angka"})
            catat(vendor, "GAGAL", f"Document Total tidak terpakai ({ke_teks(r.get(KOL_SAP['doc_total']))})")
            continue

        rusak = notasi_ilmiah(noap_asli)
        if not noap_asli or rusak:
            temuan["noap_rusak"].append({
                **baris_sap,
                "sebab": "No AP rusak jadi notasi ilmiah" if rusak else "No AP kosong"})
            sisa.append(baris_sap)
            continue

        k = kunci_invoice(noap_asli)
        kandidat = by_kunci.get(k, [])
        if not kandidat:
            sisa.append(baris_sap)
            continue

        terjangkau += 1
        if len(kandidat) > 1:
            # Nomor invoice yang sama dipakai beberapa baris. Bukan berarti
            # harus menyerah: nominal adalah bukti KEDUA yang berdiri
            # sendiri. Bila tepat satu baris yang nominalnya sepakat,
            # itu bukan tebakan — itu dua bukti yang menunjuk satu baris.
            saring = [c for c in kandidat
                      if isinstance(c["nominal"], (int, float))
                      and round(c["nominal"]) in (round(total), round(total - wtax))]
            if len(saring) == 1:
                kandidat = saring
            else:
                temuan["ambigu"].append({**baris_sap,
                    "sebab": f"Nomor invoice ini dipakai {len(kandidat)} baris di spreadsheet "
                             f"dan nominal tidak memisahkannya"})
                catat(vendor, "PERLU CEK",
                      f"Nomor {noap_asli} ada di {len(kandidat)} baris spreadsheet — tidak ditebak")
                continue

        d = kandidat[0]
        if str(d["L"]).strip():
            catat(vendor, "DILEWATI", f"No {d['no']} sudah terisi")
            continue

        nominal_cocok = (isinstance(d["nominal"], (int, float))
                         and round(d["nominal"]) in (round(total), round(total - wtax)))
        nama_cocok = kunci_nama(vendor) == kunci_nama(d["supplier"])

        # Pengaman tabrakan nomor pendek.
        if len(k) < CFG["PANJANG_AMAN"] and not nama_cocok:
            temuan["ambigu"].append({**baris_sap,
                "sebab": f"Nomor invoice hanya {len(k)} karakter dan nama supplier berbeda "
                         f"(spreadsheet: {d['supplier']})"})
            catat(vendor, "PERLU CEK",
                  f"Nomor {noap_asli} terlalu pendek dan nama berbeda dari No {d['no']} "
                  f"({d['supplier']}) — ditahan")
            continue

        if not nominal_cocok and not nama_cocok:
            temuan["ambigu"].append({**baris_sap,
                "sebab": f"Nomor cocok tetapi nama dan nominal sama-sama berbeda "
                         f"(spreadsheet: {d['supplier']} Rp{d['nominal']:,.0f})"})
            catat(vendor, "PERLU CEK",
                  f"Nomor {noap_asli} cocok ke No {d['no']} tetapi nama DAN nominal "
                  f"berbeda — ditahan")
            continue

        no_ap_tulis = pilih_no_ap(noap_dok, noap_asli)
        hasil_tulis.append((d["baris"], round(total),
                            round(wtax) if wtax else None, due, no_ap_tulis, d["kunci"]))
        dipakai.add(d["baris"])

        if nominal_cocok:
            ket_m = f"PPh Rp{round(wtax):,}" if wtax else "tanpa PPh"
            catat(vendor, "BERHASIL", f"No {d['no']} | Total Rp{round(total):,} | {ket_m}")
        else:
            selisih = d["nominal"] - total
            temuan["selisih"].append({
                **baris_sap, "no_urut": d["no"], "supplier_sheet": d["supplier"],
                "nominal_sheet": d["nominal"], "selisih": selisih,
                "sebab": "Nominal spreadsheet berbeda dari Document Total SAP"})
            catat(vendor, "SELISIH",
                  f"No {d['no']} ditulis | sheet Rp{d['nominal']:,.0f} vs SAP "
                  f"Rp{round(total):,} | selisih Rp{selisih:,.0f}")

    # ---------------- TINGKAT 2 — nama supplier + nominal ----------------
    for b in sisa:
        total, wtax = b["total"], b["wtax"]
        supplier_cocok = pencari.cari(b["vendor"])
        if not supplier_cocok:
            temuan["vendor_baru"].append({**b, "sebab": "Vendor belum pernah ada di File Invoicing"})
            catat(b["vendor"], "PERLU CEK", "Vendor belum ada di File Invoicing")
            continue

        target_a = round(total)
        wtax_val = round(wtax) if wtax else 0
        target_b = round(total - wtax_val) if wtax_val else None

        kandidat = [d for d in by_supplier[supplier_cocok]
                    if d["baris"] not in dipakai
                    and isinstance(d["nominal"], (int, float))
                    and (round(d["nominal"]) == target_a
                         or (target_b is not None and round(d["nominal"]) == target_b))]

        # Baris yang kolom L-nya sudah terisi tidak pernah ditimpa, jadi
        # ia bukan kandidat sama sekali. Menyaringnya lebih dulu sering
        # menyisakan tepat satu baris — menghilangkan keraguan tanpa
        # menebak apa pun.
        belum_terisi = [d for d in kandidat if not str(d["L"]).strip()]
        if len(belum_terisi) == 1:
            kandidat = belum_terisi

        if not kandidat:
            temuan["invoice_belum_dicatat"].append({
                **b, "supplier_sheet": supplier_cocok,
                "sebab": "Vendor dikenal, tetapi tidak ada baris bernominal sama"})
            ket = f"Vendor cocok ({supplier_cocok}) tetapi tidak ada Nominal = Rp{target_a:,}"
            if target_b:
                ket += f" atau Rp{target_b:,} (setelah PPh)"
            catat(b["vendor"], "PERLU CEK", ket)
            continue

        # Pasangannya ADA di spreadsheet, walau belum tentu dapat
        # dipastikan yang mana. Tetap dihitung terjangkau agar angka
        # 100% tidak dibesarkan dengan menyembunyikan yang ambigu.
        terjangkau += 1

        if len(kandidat) > 1:
            temuan["ambigu"].append({**b, "supplier_sheet": supplier_cocok,
                "sebab": f"{len(kandidat)} baris bernominal sama persis untuk vendor ini"})
            catat(b["vendor"], "PERLU CEK",
                  f"{len(kandidat)} baris nominal sama persis untuk {supplier_cocok} — tidak ditebak")
            continue

        d = kandidat[0]
        if str(d["L"]).strip():
            catat(b["vendor"], "DILEWATI", f"No {d['no']} sudah terisi")
            continue

        rusak = notasi_ilmiah(b["noap"])
        hasil_tulis.append((d["baris"], target_a, wtax_val if wtax_val else None,
                            b["due"], pilih_no_ap(b.get("noap_dok"), b["noap"]),
                            d["kunci"]))
        dipakai.add(d["baris"])
        ket_m = f"PPh Rp{wtax_val:,}" if wtax_val else "tanpa PPh"
        tanda = " (No AP tidak terpakai — rusak di ekspor SAP)" if rusak else ""
        catat(b["vendor"], "BERHASIL", f"No {d['no']} | Total Rp{target_a:,} | {ket_m}{tanda}")

    ringkas = {
        "total_sap": len(df_sap),
        "terjangkau": terjangkau,
        "ditulis": len(hasil_tulis),
        "selisih": len(temuan["selisih"]),
        "dilewati": sum(1 for _, s, _ in log if s == "DILEWATI"),
        "perlu_cek": sum(1 for _, s, _ in log if s == "PERLU CEK"),
        "gagal": sum(1 for _, s, _ in log if s == "GAGAL"),
    }
    return hasil_tulis, log, temuan, ringkas


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
        nominal = ke_angka(baris[4]) if baris[4] else None
        # Kunci Invoice diambil dari kolom V; bila kosong, dihitung
        # ulang dari kolom D supaya baris lama tetap bisa dicocokkan.
        kunci = (baris[21].strip() if len(baris) > 21 else "")
        if not kunci:
            kunci = kunci_invoice(baris[3] if len(baris) > 3 else "")
        hasil.append({
            "baris": i,
            "no": ke_teks(baris[0]) or i - 4,
            "supplier": baris[2].strip(),
            "nominal": nominal,
            "L": baris[11] if len(baris) > 11 else "",
            "kunci": kunci,
        })
    return hasil


# ================================================================
# TULIS HASIL
# ================================================================
# Satu panggilan batch_update menampung banyak rentang sekaligus.
# Google membatasi sekitar 60 permintaan TULIS per menit per pengguna;
# menulis baris per baris (2 permintaan per baris) menabrak batas itu
# pada sekitar baris ke-30. 50 baris per kelompok = 1 permintaan per 50
# baris, sehingga 170 baris cukup 4 permintaan.
BARIS_PER_KELOMPOK = 50
JEDA_ULANG = [5, 15, 30, 60]      # detik, bila Google tetap menolak


def kirim_kelompok(ws, permintaan):
    """Kirim satu kelompok rentang; ulangi dengan jeda bila kena 429."""
    galat = None
    for ke, jeda in enumerate([0] + JEDA_ULANG):
        if jeda:
            time.sleep(jeda)
        try:
            ws.batch_update(permintaan, value_input_option="USER_ENTERED")
            return
        except APIError as e:
            if getattr(e, "code", None) not in (429, 503):
                raise
            galat = e
    raise galat


def tulis_hasil(hasil_tulis, lapor=None):
    """Menulis L, M, O, P — dengan memeriksa ulang posisi baris lebih dulu.

    Sejak invoice baru disisipkan di atas, nomor baris bisa bergeser
    antara saat data dibaca dan saat ditulis. Menulis ke nomor baris
    yang basi berarti menimpa invoice yang keliru, maka posisinya
    dicari ulang lewat Kunci Invoice (kolom V) tepat sebelum menulis.

    Mengembalikan (jumlah_ditulis, daftar_dilewati).
    """
    ws = ambil_sheet(CFG["SHEET_INVOICE"])

    peta = {}
    for i, nilai in enumerate(ws.col_values(22)[4:], start=5):
        k = str(nilai).strip()
        if k:
            peta.setdefault(k, i)

    # Satu baris = dua rentang (L:M dan O:P). Keduanya TIDAK digabung jadi
    # L:P karena kolom N (Nilai Dibayar Neto) diisi rumus dan tidak boleh
    # tertimpa.
    dilewati = []
    satuan = []          # [(rentang_LM, nilai_LM, rentang_OP, nilai_OP)]
    for baris, L, M, due_date, no_ap, kunci in hasil_tulis:
        tujuan = peta.get(kunci, baris) if kunci else baris
        if kunci and kunci not in peta:
            dilewati.append(f"Kunci {kunci} tidak ditemukan lagi di sheet — dilewati")
            continue
        satuan.append((
            {"range": f"L{tujuan}:M{tujuan}", "values": [[L, M if M else ""]]},
            {"range": f"O{tujuan}:P{tujuan}", "values": [[ke_teks(no_ap), due_date or ""]]},
        ))

    ditulis = 0
    for i in range(0, len(satuan), BARIS_PER_KELOMPOK):
        kelompok = satuan[i:i + BARIS_PER_KELOMPOK]
        permintaan = [r for pasang in kelompok for r in pasang]
        try:
            kirim_kelompok(ws, permintaan)
        except Exception as e:
            # Sebagian sudah tertulis. Beri tahu apa adanya, jangan
            # mengaku seluruhnya gagal — baris yang terisi tidak akan
            # ditimpa saat dijalankan ulang.
            raise RuntimeError(
                f"{ditulis} baris berhasil ditulis, lalu terhenti. "
                f"{len(satuan) - ditulis} baris belum ditulis. "
                f"Jalankan lagi — baris yang sudah terisi otomatis dilewati. "
                f"Penyebab: {e}"
            ) from e
        ditulis += len(kelompok)
        if lapor:
            lapor(ditulis, len(satuan))
    return ditulis, dilewati


def tulis_log(log, nama_file, diinput_oleh):
    try:
        ws = ambil_sheet(CFG["SHEET_LOG"])
        waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gagal = sum(1 for _, s, _ in log if s in ("PERLU CEK", "GAGAL"))
        ok = sum(1 for _, s, _ in log if s in ("BERHASIL", "SELISIH"))
        ws.append_row([waktu, diinput_oleh, nama_file, len(log), ok, gagal],
                      value_input_option="RAW")
    except Exception:
        pass


# ================================================================
# BERKAS DAFTAR PERIKSA
# ================================================================
def berkas_periksa(temuan):
    """Excel berisi semua yang perlu ditindaklanjuti manusia.

    Dibuat di memori agar bisa diunduh langsung tanpa menyimpan
    apa pun di server.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    lembar = [
        ("Selisih Nominal", "selisih",
         ["No Urut", "Supplier (sheet)", "Nomor Invoice", "Nominal Sheet",
          "Document Total SAP", "Selisih", "Keterangan"],
         lambda t: [t.get("no_urut", ""), t.get("supplier_sheet", ""), t.get("noap", ""),
                    t.get("nominal_sheet", ""), t.get("total", ""), t.get("selisih", ""),
                    t.get("sebab", "")]),
        ("Vendor Belum Ada", "vendor_baru",
         ["Vendor SAP", "Nomor Invoice", "Document Total", "Jatuh Tempo", "Keterangan"],
         lambda t: [t.get("vendor", ""), t.get("noap", ""), t.get("total", ""),
                    t.get("due", ""), t.get("sebab", "")]),
        ("Invoice Belum Dicatat", "invoice_belum_dicatat",
         ["Vendor SAP", "Nama di Sheet", "Nomor Invoice", "Document Total", "Jatuh Tempo", "Keterangan"],
         lambda t: [t.get("vendor", ""), t.get("supplier_sheet", ""), t.get("noap", ""),
                    t.get("total", ""), t.get("due", ""), t.get("sebab", "")]),
        ("No AP Rusak", "noap_rusak",
         ["Vendor SAP", "No AP apa adanya", "Document Total", "Jatuh Tempo", "Keterangan"],
         lambda t: [t.get("vendor", ""), t.get("noap", ""), t.get("total", ""),
                    t.get("due", ""), t.get("sebab", "")]),
        ("Document Total Nol", "total_nol",
         ["Vendor SAP", "Nomor Invoice", "Keterangan"],
         lambda t: [t.get("vendor", ""), t.get("noap", ""), t.get("sebab", "")]),
        ("Ambigu", "ambigu",
         ["Vendor SAP", "Nomor Invoice", "Document Total", "Keterangan"],
         lambda t: [t.get("vendor", ""), t.get("noap", ""), t.get("total", ""), t.get("sebab", "")]),
    ]

    wb = Workbook()
    wb.remove(wb.active)
    NAVY = "FF0B2545"
    for judul, kunci, kepala, ambil in lembar:
        isi = temuan.get(kunci, [])
        ws = wb.create_sheet(f"{judul} ({len(isi)})"[:31])
        for i, h in enumerate(kepala, 1):
            c = ws.cell(row=1, column=i, value=h)
            c.font = Font(bold=True, color="FFFFFFFF", size=9)
            c.fill = PatternFill("solid", start_color=NAVY)
            c.alignment = Alignment(horizontal="center", wrap_text=True)
        for b, t in enumerate(isi, 2):
            for j, v in enumerate(ambil(t), 1):
                sel = ws.cell(row=b, column=j, value=v)
                sel.font = Font(size=9)
                sel.alignment = Alignment(wrap_text=True, vertical="top")
                if isinstance(v, (int, float)):
                    sel.number_format = "#,##0"
        for kol, lbr in zip("ABCDEFG", (11, 30, 24, 16, 18, 15, 52)):
            ws.column_dimensions[kol].width = lbr
        ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ================================================================
# PENYARING RENTANG TANGGAL
# ================================================================
KOL_TANGGAL_SARING = ["Date", "Document Date", "Due Date"]


def tanggal_saring(nilai):
    """Ubah satu sel tanggal SAP jadi date; None bila tidak terbaca."""
    s = str(nilai or "").strip()
    if not s:
        return None
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def rentang_kolom(df, kolom):
    """(tanggal paling awal, paling akhir, jumlah terbaca) pada satu kolom."""
    v = [tanggal_saring(x) for x in df[kolom]] if kolom in df.columns else []
    v = [x for x in v if x]
    return (min(v), max(v), len(v)) if v else (None, None, 0)


def saring_tanggal(df, kolom, dari, sampai):
    """Sisakan baris yang tanggalnya di dalam rentang (batas ikut terhitung).

    Baris yang tanggalnya tidak terbaca DIBUANG, bukan diloloskan diam-diam —
    supaya cakupan yang dilaporkan benar-benar sesuai yang diminta.
    """
    if kolom not in df.columns:
        return df, 0
    ok = df[kolom].apply(lambda x: (lambda d: d is not None and dari <= d <= sampai)(tanggal_saring(x)))
    return df[ok], int((~ok).sum())


# ================================================================
# TAMPILAN
# ================================================================
st.title("🧾 Upload Export SAP B1")
st.caption("Kolom yang dibaca: Vendor, No AP, Document Total, Due Date, WTax Amount. "
           "Pencocokan utama lewat nomor invoice pada kolom No AP.")

nama_penginput = st.text_input("Nama Anda")
berkas = st.file_uploader("Pilih file export SAP B1", type=["xls", "xlsx", "csv"])

if berkas and nama_penginput.strip():
    try:
        df_sap, cara = baca_berkas_sap(berkas)
    except Exception as e:
        st.error(f"File tidak dapat dibaca — {e}")
        st.stop()

    st.success(f"{len(df_sap)} baris terbaca (format: {cara}).")

    # ---- batasi cakupan agar bisa dijalankan bertahap ----
    tersedia = [k for k in KOL_TANGGAL_SARING if k in df_sap.columns]
    pakai_saring = st.checkbox(
        "Batasi berdasarkan rentang tanggal",
        value=False,
        help="Untuk menjalankan sistem bertahap: cocokkan dulu sebagian periode, "
             "sisanya menyusul. Tanpa ini, seluruh baris diproses.")

    buang = 0
    if pakai_saring and tersedia:
        kol_tgl = st.selectbox("Tanggal yang dipakai menyaring", tersedia, index=0,
                               help="Date = tanggal posting di SAP. "
                                    "Document Date = tanggal dokumen vendor.")
        awal, akhir, terbaca = rentang_kolom(df_sap, kol_tgl)
        if not terbaca:
            st.warning(f"Kolom {kol_tgl} tidak berisi tanggal yang dapat dibaca. Penyaring dilewati.")
        else:
            st.caption(f"Pada kolom {kol_tgl}, berkas ini berisi "
                       f"{awal:%d-%m-%Y} s/d {akhir:%d-%m-%Y} ({terbaca} baris terbaca).")
            k1, k2 = st.columns(2)
            dari = k1.date_input("Dari tanggal", value=awal,
                                 min_value=awal, max_value=akhir, format="DD/MM/YYYY")
            sampai = k2.date_input("Sampai tanggal", value=akhir,
                                   min_value=awal, max_value=akhir, format="DD/MM/YYYY")
            if dari > sampai:
                st.error("Tanggal awal melewati tanggal akhir.")
                st.stop()
            df_sap, buang = saring_tanggal(df_sap, kol_tgl, dari, sampai)
            if df_sap.empty:
                st.error("Tidak ada baris pada rentang itu. Ubah tanggalnya.")
                st.stop()
            st.info(f"**{len(df_sap)} baris** akan diproses "
                    f"({dari:%d-%m-%Y} s/d {sampai:%d-%m-%Y}). "
                    f"{buang} baris di luar rentang tidak disentuh.")

    if st.button("🔍 Cocokkan dengan File Invoicing", type="primary"):
        # Dibungkus supaya kegagalan membuka spreadsheet tampil sebagai
        # satu kalimat yang bisa ditindaklanjuti, bukan jejak galat mentah.
        try:
            with st.spinner("Memuat data File Invoicing..."):
                data_inv = muat_data_invoicing()
            if not data_inv:
                st.error("Sheet INV 2026 terbuka tapi tidak ada baris data "
                         "yang terbaca mulai baris 5. Periksa nama sheet dan isinya.")
                st.stop()
            with st.spinner("Mencocokkan..."):
                hasil_tulis, log, temuan, ringkas = proses_pencocokan(df_sap, data_inv)
        except Exception as e:
            st.error(f"Gagal membaca File Invoicing — {pesan_ramah(e)}")
            st.stop()
        st.session_state.update({"hasil_tulis": hasil_tulis, "log": log,
                                 "temuan": temuan, "ringkas": ringkas,
                                 "nama_file": berkas.name})

if "log" in st.session_state:
    log = st.session_state["log"]
    hasil_tulis = st.session_state["hasil_tulis"]
    temuan = st.session_state["temuan"]
    ringkas = st.session_state["ringkas"]

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pasangannya ada di sheet", ringkas["terjangkau"])
    c2.metric("Siap ditulis", ringkas["ditulis"])
    c3.metric("Ditulis dengan selisih", ringkas["selisih"])
    c4.metric("Dilewati (sudah terisi)", ringkas["dilewati"])

    jangkau = ringkas["terjangkau"]
    if jangkau:
        persen = (ringkas["ditulis"] + ringkas["dilewati"]) / jangkau * 100
        st.progress(min(persen / 100, 1.0),
                    text=f"{persen:.1f}% dari baris yang pasangannya ada di spreadsheet tertangani")

    if ringkas["selisih"]:
        st.warning(
            f"{ringkas['selisih']} baris ditulis **meskipun nominalnya berbeda** dari "
            "catatan Purchasing. Kolom L diisi angka SAP; selisihnya sengaja dibiarkan "
            "terlihat supaya bisa ditelusuri. Rinciannya ada di berkas daftar periksa."
        )

    judul_temuan = {
        "selisih": "Selisih nominal (tetap ditulis)",
        "vendor_baru": "Vendor belum ada di File Invoicing",
        "invoice_belum_dicatat": "Vendor dikenal, invoice belum dicatat",
        "noap_rusak": "No AP rusak atau kosong di ekspor SAP",
        "total_nol": "Document Total bernilai nol",
        "ambigu": "Ambigu — sengaja tidak ditebak",
    }
    for kunci, judul in judul_temuan.items():
        isi = temuan.get(kunci, [])
        if not isi:
            continue
        with st.expander(f"{judul} — {len(isi)} baris"):
            for t in isi[:60]:
                total = t.get("total")
                nominal = f"Rp{total:,.0f}" if isinstance(total, (int, float)) else "-"
                st.write(f"• **{t.get('vendor','')}** — {t.get('noap','(tanpa nomor)')} "
                         f"| {nominal} — {t.get('sebab','')}")
            if len(isi) > 60:
                st.caption(f"... dan {len(isi)-60} baris lagi. Lihat berkas daftar periksa.")

    if any(temuan.values()):
        st.download_button(
            "⬇️ Unduh daftar periksa (Excel)",
            data=berkas_periksa(temuan),
            file_name=f"Daftar_Periksa_SAP_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if ringkas["ditulis"] > 0:
        st.warning(
            f"Akan menulis {ringkas['ditulis']} baris ke kolom L, M, O, P. "
            "Baris PERLU CEK tidak ditulis."
        )
        if st.button(f"💾 Tulis {ringkas['ditulis']} Baris ke File Invoicing", type="primary"):
            try:
                with st.spinner("Menulis..."):
                    bar = st.progress(0.0, text="Menulis...")

                    def lapor(sudah, total):
                        bar.progress(sudah / total,
                                     text=f"Menulis {sudah} dari {total} baris...")

                    ditulis, gagal = tulis_hasil(hasil_tulis, lapor=lapor)
                    bar.empty()
                    tulis_log(log, st.session_state["nama_file"], nama_penginput)
                st.success(f"{ditulis} baris berhasil ditulis.")
                for pesan in gagal:
                    st.warning(pesan)
                for k in ("log", "hasil_tulis", "temuan", "ringkas"):
                    st.session_state.pop(k, None)
            except Exception as e:
                st.error(f"Gagal menulis — {pesan_ramah(e)}")
    else:
        st.info("Tidak ada baris yang dapat ditulis otomatis pada berkas ini.")

elif berkas and not nama_penginput.strip():
    st.warning("Isi nama Anda terlebih dahulu.")

panel_diagnosis()
