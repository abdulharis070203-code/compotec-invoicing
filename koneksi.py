"""
================================================================
KONEKSI GOOGLE SHEETS — DIPAKAI BERSAMA SEMUA HALAMAN
================================================================
Sebelumnya tiap halaman punya kode koneksi sendiri. Akibatnya
perbaikan harus dilakukan dua kali dan mudah terlewat. Semua
koneksi sekarang lewat berkas ini.

DUA MASALAH YANG DITANGANI DI SINI
  1. spreadsheet_id yang ditempel sebagai ALAMAT LENGKAP
     Bila isi Secrets berupa
         https://docs.google.com/spreadsheets/d/1lOi.../edit
     bukan hanya 1lOi..., alamat permintaan ke Google jadi salah
     bentuk dan Google membalas HALAMAN HTML, bukan jawaban API.
     gspread tidak bisa membaca HTML itu, lalu melemparnya apa
     adanya ke layar — ribuan karakter kode yang tidak berarti
     bagi staff. Di sini ID selalu disaring lebih dulu.

  2. Pesan kesalahan yang tidak bisa dipakai
     Pesan asli Google panjang dan teknis. Fungsi pesan_ramah()
     menerjemahkannya menjadi satu kalimat beserta tindakan yang
     harus diambil.
================================================================
"""

import re

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound

LINGKUP = ["https://www.googleapis.com/auth/spreadsheets"]

# ID spreadsheet Google selalu berupa 25 karakter atau lebih dari
# huruf, angka, garis bawah, dan tanda hubung.
POLA_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]{25,})")
POLA_ID_POLOS = re.compile(r"^[a-zA-Z0-9_-]{25,}$")


def id_spreadsheet():
    """Ambil ID murni dari Secrets, baik ditulis sebagai ID maupun alamat lengkap."""
    mentah = str(st.secrets.get("spreadsheet_id", "")).strip().strip('"').strip("'")

    if not mentah:
        raise RuntimeError(
            "spreadsheet_id belum diisi di Secrets aplikasi. "
            "Buka Manage app → Settings → Secrets."
        )

    if POLA_ID_POLOS.match(mentah):
        return mentah

    cocok = POLA_ID.search(mentah)
    if cocok:
        return cocok.group(1)

    raise RuntimeError(
        "spreadsheet_id di Secrets tidak dikenali sebagai ID maupun alamat "
        "Google Sheets. Isi dengan bagian di antara /d/ dan /edit pada alamat "
        "spreadsheet."
    )


def email_layanan():
    """Email service account — yang harus diberi akses Editor pada spreadsheet."""
    return st.secrets.get("gcp_service_account", {}).get("client_email", "(tidak ada)")


@st.cache_resource(show_spinner=False)
def _spreadsheet(kunci):
    """Objek spreadsheet. Kunci ikut jadi penanda cache agar ID yang
    diperbaiki di Secrets langsung dipakai."""
    cred = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=LINGKUP
    )
    return gspread.authorize(cred).open_by_key(kunci)


def buka_spreadsheet():
    return _spreadsheet(id_spreadsheet())


def ambil_sheet(nama):
    """Ambil satu sheet, dengan pesan jelas bila namanya tidak ada."""
    try:
        return buka_spreadsheet().worksheet(nama)
    except WorksheetNotFound:
        try:
            ada = ", ".join(w.title for w in buka_spreadsheet().worksheets())
        except Exception:
            ada = "(tidak dapat dibaca)"
        raise RuntimeError(
            f'Sheet bernama "{nama}" tidak ditemukan. '
            f"Sheet yang ada: {ada}. Periksa ejaan dan spasi nama sheet."
        ) from None


# ================================================================
# PENERJEMAH PESAN KESALAHAN
# ================================================================
def pesan_ramah(e):
    """Ubah kesalahan Google menjadi satu kalimat yang bisa ditindaklanjuti."""

    if isinstance(e, (RuntimeError, SpreadsheetNotFound, WorksheetNotFound)):
        if isinstance(e, SpreadsheetNotFound):
            return (
                "Spreadsheet tidak ditemukan. Periksa spreadsheet_id di Secrets, "
                f"dan pastikan {email_layanan()} sudah diberi akses Editor."
            )
        return str(e)

    # gspread 6 melempar PermissionError BAWAAN PYTHON (bukan APIError)
    # saat Google membalas 403 pada open_by_key. Tanpa cabang ini, pesannya
    # jatuh ke keranjang terakhir dan pengguna hanya melihat jejak galat.
    if isinstance(e, PermissionError):
        return (
            "Service account ditolak membuka spreadsheet. Dua kemungkinan, "
            "periksa berurutan:\n\n"
            f"1. Spreadsheet belum dibagikan ke **{email_layanan()}** "
            "dengan hak **Editor**. Buka spreadsheet > Share > tempel email itu "
            "> pilih Editor > Send.\n"
            "2. Google Sheets API atau Google Drive API belum aktif pada project "
            "Google Cloud service account ini.\n\n"
            "Spreadsheet-nya sendiri ADA — kalau ID-nya salah, pesannya akan "
            "berbunyi 'tidak ditemukan', bukan 'ditolak'."
        )

    if isinstance(e, APIError):
        kode = getattr(e, "code", None)
        pesan = str(e.error.get("message", ""))[:400]

        if kode == -1:
            # Google membalas HTML, bukan JSON — alamat permintaan salah bentuk.
            return (
                "Google membalas halaman web, bukan jawaban API. Ini hampir "
                "selalu berarti spreadsheet_id di Secrets ditulis sebagai alamat "
                "lengkap, atau ada spasi/tanda kutip ikut tersalin. Isi hanya "
                "bagian di antara /d/ dan /edit."
            )
        if kode == 403:
            if "SERVICE_DISABLED" in pesan or "has not been used" in pesan:
                return (
                    "Google Sheets API belum diaktifkan pada project Google Cloud "
                    "yang dipakai service account ini. Aktifkan Google Sheets API "
                    "di console.cloud.google.com, lalu tunggu 1–2 menit."
                )
            return (
                f"Akses ditolak. Bagikan spreadsheet ke {email_layanan()} "
                "dengan hak Editor."
            )
        if kode == 404:
            return (
                "Spreadsheet tidak ditemukan. Periksa spreadsheet_id di Secrets."
            )
        if kode == 429:
            return "Kuota Google Sheets sedang penuh. Tunggu satu menit, lalu ulangi."
        return f"Google menolak permintaan (kode {kode}). {pesan}"

    return f"{type(e).__name__}: {str(e)[:400]}"


# ================================================================
# PANEL DIAGNOSIS
# ================================================================
def panel_diagnosis():
    """Uji koneksi langkah demi langkah, supaya letak masalah terlihat."""
    with st.expander("Diagnosis koneksi Spreadsheet"):
        st.caption(
            "Tekan tombol di bawah bila penyimpanan gagal. "
            "Pemeriksaan ini tidak mengubah data apa pun."
        )

        if not st.button("Uji koneksi sekarang", key="uji_koneksi"):
            return

        # Langkah 1 — ID
        try:
            kunci = id_spreadsheet()
            st.success(f"1. ID spreadsheet terbaca: `{kunci}`")
        except Exception as e:
            st.error(f"1. ID spreadsheet bermasalah — {pesan_ramah(e)}")
            return

        # Langkah 2 — service account
        st.info(f"2. Service account: `{email_layanan()}`")

        # Langkah 3 — buka spreadsheet
        try:
            sp = buka_spreadsheet()
            judul = sp.title
            st.success(f"3. Spreadsheet terbuka: **{judul}**")
        except Exception as e:
            st.error(f"3. Tidak dapat membuka spreadsheet — {pesan_ramah(e)}")
            return

        # Langkah 4 — daftar sheet
        try:
            nama_sheet = [w.title for w in sp.worksheets()]
            st.success(f"4. Sheet terbaca: {', '.join(nama_sheet)}")
        except Exception as e:
            st.error(f"4. Daftar sheet tidak terbaca — {pesan_ramah(e)}")
            return

        # Langkah 5 — sheet yang dipakai aplikasi
        for perlu in ("INV 2026", "Log Upload Foto", "Log Upload SAP"):
            if perlu in nama_sheet:
                st.success(f"5. Sheet `{perlu}` ada.")
            else:
                st.error(f"5. Sheet `{perlu}` TIDAK ada — periksa ejaan nama sheet.")
