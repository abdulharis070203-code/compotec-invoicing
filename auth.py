"""
================================================================
PROTEKSI AKSES — SISTEM INVOICING COMPOTEC
================================================================
Aplikasi ini menulis ke Google Sheets. Karena dideploy sebagai
aplikasi publik di Streamlit Community Cloud, siapa pun yang tahu
alamatnya bisa membukanya — maka pintu masuknya harus dikunci.

Dipanggil di AWAL app.py, sebelum menu didaftarkan, sehingga
tidak ada halaman yang bisa tampil tanpa kata sandi.

CATATAN KEAMANAN:
  Ini proteksi tingkat dasar — memadai untuk tahap uji coba di
  lingkungan internal. Saat migrasi ke VPS perusahaan, proteksi
  ini digantikan autentikasi per pengguna agar terlihat siapa
  menginput apa.
================================================================
"""

import streamlit as st
import hmac

from tampilan import pasang_tema, html_logo


def cek_password():
    """Hentikan halaman bila pengguna belum memasukkan kata sandi yang benar."""

    if st.session_state.get("terotentikasi"):
        return

    # Latar belakang biru tua — hanya untuk halaman ini.
    pasang_tema(halaman_masuk=True)

    # Panel menu disembunyikan selama belum masuk, supaya nama-nama
    # menu tidak terbaca oleh orang yang tidak berhak.
    st.markdown(
        '<style>[data-testid="stSidebar"]{display:none}</style>',
        unsafe_allow_html=True,
    )

    kiri, tengah, kanan = st.columns([1, 2, 1])
    with tengah:
        # Bagian atas kotak putih: logo, judul, garis warna.
        st.markdown(
            f"""
            <div class="ctc-masuk-atas">
              {html_logo(46)}
              <h2>Sistem Invoicing</h2>
              <p>PT Compotec International</p>
              <div class="ctc-garis"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Bagian bawah kotak putih: formulir kata sandi.
        with st.form("form_masuk"):
            kata_sandi = st.text_input("Kata sandi", type="password")
            kirim = st.form_submit_button("Masuk", use_container_width=True)

        if kirim:
            benar = st.secrets.get("app_password", "")
            # hmac.compare_digest: perbandingan berwaktu tetap.
            # Perbandingan biasa (==) berhenti di karakter pertama yang
            # berbeda, sehingga selisih waktunya bisa dipakai menebak.
            if benar and hmac.compare_digest(str(kata_sandi), str(benar)):
                st.session_state["terotentikasi"] = True
                st.rerun()
            else:
                st.error("Kata sandi salah.")

        st.caption(
            "Aplikasi ini hanya untuk staff PT Compotec International. "
            "Kata sandi diberikan oleh Divisi Purchasing."
        )

    st.stop()


def tombol_keluar():
    """Tombol keluar di sidebar — berguna bila memakai perangkat bersama."""
    with st.sidebar:
        st.divider()
        if st.button("Keluar", use_container_width=True):
            st.session_state.pop("terotentikasi", None)
            st.rerun()
