"""
================================================================
SISTEM INVOICING — PT COMPOTEC INTERNATIONAL
================================================================
Halaman pembuka. Menu sebenarnya ada di panel kiri (folder pages/).
================================================================
"""

import streamlit as st

st.set_page_config(
    page_title="Sistem Invoicing — PT Compotec International",
    page_icon="📋",
    layout="centered",
)

st.title("📋 Sistem Invoicing")
st.caption("PT Compotec International — Divisi Finance")

st.divider()

st.subheader("Menu Tersedia")

st.markdown("""
**📷 Foto Invoice**  
Unggah foto invoice dari HP atau komputer. Sistem membaca tanggal, supplier,
nomor invoice, dan nominal secara otomatis. Hasil bacaan ditampilkan lebih
dulu untuk diperiksa sebelum disimpan.

**🧾 Upload SAP B1**  
Unggah berkas export SAP B1. Sistem mencocokkan tiap baris dengan data yang
sudah ada, lalu mengisi Total Invoice, PPh, No AP Invoice, dan Tanggal Jatuh
Tempo. Baris yang tidak dapat dipastikan kecocokannya ditandai untuk diperiksa
manual — tidak ditebak.
""")

st.divider()

st.info(
    "Pilih menu di panel sebelah kiri untuk mulai. "
    "Bila panel tersembunyi, klik tanda **»** di pojok kiri atas."
)

with st.expander("Urutan kerja yang disarankan"):
    st.markdown("""
    1. **Foto Invoice** dulu — membuat baris baru di File Invoicing
    2. **Upload SAP B1** setelahnya — mengisi kolom L, M, O, P pada baris yang sudah ada
    3. Kolom **Nilai Dibayar (Neto)** terhitung otomatis setelah langkah 2

    Urutan ini tidak boleh dibalik: tanpa baris dari langkah 1,
    tidak ada yang bisa dicocokkan pada langkah 2.
    """)
