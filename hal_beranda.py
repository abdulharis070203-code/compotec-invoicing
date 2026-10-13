"""Halaman pembuka — penjelasan singkat dan urutan kerja."""

import streamlit as st

from tampilan import kepala_halaman

kepala_halaman("Sistem Invoicing", "PT Compotec International — Divisi Finance")

st.subheader("Menu Tersedia")

st.markdown(
    """
    <div class="ctc-kartu">
      <h4>📷 Foto Invoice</h4>
      <p>Unggah foto invoice dari HP atau komputer. Sistem membaca tanggal,
      supplier, nomor invoice, dan nominal secara otomatis. Hasil bacaan
      ditampilkan lebih dulu untuk diperiksa sebelum disimpan.</p>
    </div>

    <div class="ctc-kartu hijau">
      <h4>🧾 Upload SAP B1</h4>
      <p>Unggah berkas export SAP B1. Sistem mencocokkan tiap baris dengan data
      yang sudah ada, lalu mengisi Total Invoice, PPh, No AP Invoice, dan
      Tanggal Jatuh Tempo. Baris yang tidak dapat dipastikan kecocokannya
      ditandai untuk diperiksa manual — tidak ditebak.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info("Pilih menu di panel sebelah kiri untuk mulai.")

with st.expander("Urutan kerja yang disarankan"):
    st.markdown("""
    1. **Foto Invoice** dulu — membuat baris baru di File Invoicing
    2. **Upload SAP B1** setelahnya — mengisi kolom L, M, O, P pada baris yang sudah ada
    3. Kolom **Nilai Dibayar (Neto)** terhitung otomatis setelah langkah 2

    Urutan ini tidak boleh dibalik: tanpa baris dari langkah 1,
    tidak ada yang bisa dicocokkan pada langkah 2.
    """)
