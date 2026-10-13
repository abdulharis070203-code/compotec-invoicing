"""
================================================================
SISTEM INVOICING — PT COMPOTEC INTERNATIONAL
================================================================
Berkas utama. Seluruh menu didaftarkan di sini lewat
st.navigation, sehingga TIDAK diperlukan folder "pages".

Semua berkas berada di satu tingkat — tidak ada folder sama
sekali. Ini menghilangkan kemungkinan berkas salah tempat saat
diunggah.

Karena setiap permintaan masuk melalui berkas ini lebih dulu,
pemeriksaan kata sandi cukup dipasang sekali di sini.
================================================================
"""

import streamlit as st

st.set_page_config(
    page_title="Sistem Invoicing — PT Compotec International",
    page_icon="📋",
    layout="centered",
)

from auth import cek_password, tombol_keluar
from tampilan import pasang_tema, logo_sidebar

# Kunci pintu lebih dulu. Bila belum masuk, fungsi ini menampilkan
# halaman kata sandi lalu menghentikan eksekusi di sini.
cek_password()

# Latar belakang terang untuk halaman kerja. Dipasang sebelum menu
# dijalankan supaya gaya kartu sudah siap saat halaman digambar.
pasang_tema(halaman_masuk=False)
logo_sidebar()

menu = st.navigation([
    st.Page("hal_beranda.py",       title="Beranda",       icon="📋", default=True),
    st.Page("hal_foto_invoice.py",  title="Foto Invoice",  icon="📷"),
    st.Page("hal_upload_sap.py",    title="Upload SAP B1", icon="🧾"),
])

tombol_keluar()
menu.run()
