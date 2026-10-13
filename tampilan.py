"""
================================================================
TAMPILAN BERSAMA — SISTEM INVOICING COMPOTEC
================================================================
Satu tempat untuk warna, latar belakang, dan logo, supaya
halaman masuk dan halaman beranda tidak pernah berbeda gaya.

TENTANG LOGO
  Logo dibaca dari berkas "logo.png" yang diletakkan satu
  tingkat dengan berkas ini (langsung di akar repo GitHub).
  Bila berkas itu belum ada, halaman TETAP tampil normal —
  logo diganti tulisan nama perusahaan. Jadi aplikasi tidak
  pernah rusak hanya karena berkas gambar belum diunggah.

TENTANG LATAR BELAKANG
  Latar dibuat dari gradasi warna (CSS), bukan berkas gambar.
  Alasannya: tidak menambah berkas yang harus diunggah, tidak
  memperlambat halaman, dan ketajamannya tetap di layar HP
  maupun monitor besar.
================================================================
"""

from pathlib import Path
import base64

import streamlit as st

# ---------------------------------------------------------------
# WARNA RESMI — diambil dari template PPT perusahaan
# ---------------------------------------------------------------
NAVY = "#1A3A6B"
BIRU = "#2E5E9E"
HIJAU = "#18A303"
GOLD = "#C99C00"
ABU = "#5F6368"

BERKAS_LOGO = Path(__file__).parent / "logo.png"


# ---------------------------------------------------------------
# LOGO
# ---------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _baca_logo(penanda):
    """Baca logo.png menjadi data URI.

    Memakai data URI (gambar ditanam langsung di dalam HTML) supaya
    logo ikut tampil di dalam blok st.markdown — berkas biasa tidak
    bisa dipanggil dari dalam HTML di Streamlit.
    """
    try:
        isi = BERKAS_LOGO.read_bytes()
    except OSError:
        return None
    if not isi:
        return None
    return "data:image/png;base64," + base64.b64encode(isi).decode("ascii")


def _logo_uri():
    """Logo sebagai data URI, atau None bila berkas belum diunggah.

    Penanda (waktu ubah + ukuran berkas) ikut menjadi kunci cache,
    sehingga logo yang baru diunggah atau diganti langsung terbaca
    tanpa perlu menunggu aplikasi dinyalakan ulang.
    """
    try:
        s = BERKAS_LOGO.stat()
    except OSError:
        return None
    return _baca_logo((s.st_mtime_ns, s.st_size))


def ada_logo():
    """True bila berkas logo.png tersedia."""
    return _logo_uri() is not None


def html_logo(tinggi=52):
    """Potongan HTML logo. Otomatis beralih ke tulisan bila berkas belum ada."""
    uri = _logo_uri()
    if uri:
        return (
            f'<img src="{uri}" alt="PT Compotec International" '
            f'style="height:{tinggi}px;width:auto;display:block;margin:0 auto">'
        )

    # Cadangan — nama perusahaan sebagai tulisan.
    besar = max(14, int(tinggi * 0.42))
    kecil = max(9, int(tinggi * 0.20))
    return (
        '<div style="text-align:center;line-height:1.05">'
        f'<div style="font-size:{besar}px;font-weight:800;letter-spacing:.14em;'
        f'color:{NAVY}">COMPOTEC</div>'
        f'<div style="font-size:{kecil}px;letter-spacing:.34em;color:{HIJAU};'
        'text-transform:lowercase">international</div>'
        '</div>'
    )


# ---------------------------------------------------------------
# LATAR BELAKANG + GAYA
# ---------------------------------------------------------------
def pasang_tema(halaman_masuk=False):
    """Pasang latar belakang dan gaya.

    halaman_masuk=True  -> latar biru tua (halaman kata sandi)
    halaman_masuk=False -> latar terang (halaman kerja)

    Halaman kerja sengaja dibuat terang: layar ini dipakai berjam-jam
    oleh Divisi Finance, jadi tulisan harus tetap mudah dibaca.
    """

    if halaman_masuk:
        latar = f"""
            radial-gradient(900px 520px at 12% -8%,  rgba(46,94,158,.55), transparent 60%),
            radial-gradient(760px 480px at 92% 108%, rgba(24,163,3,.26),  transparent 62%),
            linear-gradient(160deg, {NAVY} 0%, #142E55 55%, #0E2242 100%)
        """
    else:
        latar = """
            radial-gradient(820px 460px at  -6%  -4%, rgba(46,94,158,.13), transparent 62%),
            radial-gradient(700px 420px at 104%  12%, rgba(24,163,3,.10),  transparent 60%),
            radial-gradient(900px 520px at  50% 108%, rgba(201,156,0,.07), transparent 64%),
            linear-gradient(180deg, #F7F9FC 0%, #EEF3F9 100%)
        """

    # Gaya khusus halaman kata sandi hanya berlaku di halaman itu.
    # Di halaman kerja, pemilih diarahkan ke kelas yang tidak pernah
    # dipakai, sehingga aturannya tidak pernah aktif.
    sel_masuk = ".stApp" if halaman_masuk else ".ctc-nonaktif"

    st.markdown(
        f"""
        <style>
          /* Latar belakang utama */
          .stApp {{
              background-image: {latar};
              background-attachment: fixed;
              background-size: cover;
          }}

          /* Bilah atas Streamlit dibuat tembus pandang supaya
             tidak ada garis putih yang memotong latar belakang. */
          [data-testid="stHeader"] {{
              background: transparent;
          }}

          /* Garis warna tipis di tepi atas — motif dari template PPT */
          .stApp::before {{
              content: "";
              position: fixed;
              top: 0; left: 0; right: 0;
              height: 4px;
              z-index: 999;
              background: linear-gradient(90deg,
                  {NAVY} 0%, {BIRU} 34%, {HIJAU} 68%, {GOLD} 100%);
          }}

          /* Panel menu di kiri */
          [data-testid="stSidebar"] {{
              background: rgba(255,255,255,.90);
              border-right: 1px solid rgba(26,58,107,.12);
          }}

          /* ---- Komponen bersama ---- */

          .ctc-kepala {{
              background: linear-gradient(135deg, {NAVY} 0%, {BIRU} 100%);
              border-radius: 14px;
              padding: 1.15rem 1.4rem;
              margin-bottom: 1.3rem;
              box-shadow: 0 8px 22px rgba(26,58,107,.18);
              display: flex;
              align-items: center;
              gap: 1.1rem;
          }}
          .ctc-kepala .ctc-logo {{
              background: #fff;
              border-radius: 9px;
              padding: .45rem .7rem;
              flex: 0 0 auto;
          }}
          .ctc-kepala h1 {{
              color: #fff;
              font-size: 1.42rem;
              font-weight: 700;
              margin: 0;
              line-height: 1.2;
          }}
          .ctc-kepala p {{
              color: rgba(255,255,255,.80);
              font-size: .86rem;
              margin: .18rem 0 0 0;
          }}

          .ctc-kartu {{
              background: rgba(255,255,255,.96);
              border: 1px solid rgba(26,58,107,.10);
              border-left: 4px solid {BIRU};
              border-radius: 11px;
              padding: .95rem 1.15rem;
              margin-bottom: .8rem;
              box-shadow: 0 2px 10px rgba(26,58,107,.06);
          }}
          .ctc-kartu.hijau {{ border-left-color: {HIJAU}; }}
          .ctc-kartu h4 {{
              color: {NAVY};
              font-size: 1rem;
              font-weight: 700;
              margin: 0 0 .3rem 0;
          }}
          .ctc-kartu p {{
              color: #3C4043;
              font-size: .89rem;
              line-height: 1.55;
              margin: 0;
          }}

          /* ---- Halaman kata sandi ----
             Kotak putih dibentuk dari DUA bagian yang saling menempel:
             bagian atas (logo + judul) berupa HTML, bagian bawah adalah
             st.form milik Streamlit. Widget Streamlit tidak bisa
             diletakkan di dalam blok HTML, jadi keduanya disamakan
             warna dan sudutnya agar terlihat sebagai satu kotak. */

          .ctc-masuk-atas {{
              background: #fff;
              border-radius: 16px 16px 0 0;
              padding: 2rem 1.6rem .2rem 1.6rem;
              text-align: center;
          }}
          .ctc-masuk-atas h2 {{
              color: {NAVY};
              font-size: 1.3rem;
              font-weight: 700;
              margin: 1.1rem 0 .15rem 0;
          }}
          .ctc-masuk-atas p {{
              color: {ABU};
              font-size: .85rem;
              margin: 0;
          }}
          .ctc-masuk-atas .ctc-garis {{
              height: 3px;
              border-radius: 3px;
              margin: 1rem auto 0 auto;
              width: 68px;
              background: linear-gradient(90deg, {NAVY}, {BIRU}, {HIJAU}, {GOLD});
          }}

          /* Bagian bawah kotak = st.form.
             Aman memakai pemilih umum karena blok gaya ini hanya
             dipasang di halaman kata sandi, dan di halaman itu
             tidak ada formulir lain. */
          {sel_masuk} [data-testid="stForm"] {{
              background: #fff;
              border: none;
              border-radius: 0 0 16px 16px;
              padding: 1.1rem 1.6rem 1.5rem 1.6rem;
              margin-top: 0;
              box-shadow: 0 18px 44px rgba(0,0,0,.28);
          }}
          /* Tombol "Masuk" memakai warna perusahaan */
          {sel_masuk} [data-testid="stForm"] button {{
              background: linear-gradient(135deg, {NAVY}, {BIRU});
              color: #fff;
              border: none;
              font-weight: 600;
          }}
          {sel_masuk} [data-testid="stForm"] button:hover {{
              background: linear-gradient(135deg, {BIRU}, {NAVY});
              color: #fff;
          }}
          /* Keterangan di bawah kotak dibuat terang agar terbaca
             di atas latar biru tua. */
          {sel_masuk} [data-testid="stCaptionContainer"] {{
              color: rgba(255,255,255,.72);
              text-align: center;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def kepala_halaman(judul, anak_judul):
    """Bilah judul biru dengan logo di sebelah kiri."""
    st.markdown(
        f"""
        <div class="ctc-kepala">
          <div class="ctc-logo">{html_logo(34)}</div>
          <div>
            <h1>{judul}</h1>
            <p>{anak_judul}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def logo_sidebar():
    """Logo kecil di atas daftar menu."""
    with st.sidebar:
        st.markdown(
            f'<div style="padding:.5rem 0 .9rem 0">{html_logo(30)}</div>',
            unsafe_allow_html=True,
        )
