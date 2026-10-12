"""
================================================================
PROTEKSI AKSES — SISTEM INVOICING COMPOTEC
================================================================
Aplikasi ini menulis ke Google Sheets. Karena dideploy sebagai
aplikasi publik di Streamlit Community Cloud, siapa pun yang tahu
alamatnya bisa membukanya — maka pintu masuknya harus dikunci.

Dipanggil di AWAL setiap halaman, termasuk halaman di folder
pages/. Streamlit mengizinkan membuka URL halaman secara langsung
(misalnya .../Foto_Invoice) tanpa melewati halaman utama, jadi
memasang proteksi hanya di app.py tidak cukup.

CATATAN KEAMANAN:
  Ini proteksi tingkat dasar — memadai untuk tahap uji coba di
  lingkungan internal. Saat migrasi ke VPS perusahaan, proteksi
  ini digantikan autentikasi per pengguna agar terlihat siapa
  menginput apa.
================================================================
"""

import streamlit as st
import hmac


def cek_password():
    """Hentikan halaman bila pengguna belum memasukkan kata sandi yang benar."""

    if st.session_state.get("terotentikasi"):
        return

    st.markdown(
        """
        <div style="text-align:center;padding:2rem 0 1rem 0">
          <h2 style="color:#1A3A6B;margin-bottom:0.2rem">Sistem Invoicing</h2>
          <p style="color:#5F6368;margin-top:0">PT Compotec International</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kiri, tengah, kanan = st.columns([1, 2, 1])
    with tengah:
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
