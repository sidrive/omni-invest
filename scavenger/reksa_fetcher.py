"""
reksa_fetcher.py — Auto-fetch NAB Reksa Dana dari Bibit.id
==========================================================
Endpoint yang bekerja (confirmed di STB Armbian):
  GET https://api.bibit.id/products/<RD_CODE>/simulations?range=120
  → Response: {"data": [nav1, nav2, ..., nav_terbaru]}
  → NAB terbaru = data[-1] (elemen terakhir)

Fallback: nilai NAB terakhir dari cache Firestore
"""

import json
import time
import logging
import requests
from datetime import datetime, date

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Redmi Note 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.210 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9",
    "Referer": "https://bibit.id/",
    "Origin": "https://bibit.id",
}

# =============================================================================
# MAPPING REKSA DANA
# Isi rd_code dari URL bibit.id/reksadana/<rd_code>/<slug>
# =============================================================================
REKSA_MAPPING = {
    "BRI_INDEKS_SYARIAH": {
        "rd_code": "RD562",
        "slug": "bri-indeks-syariah",
        "nama_display": "BRI Indeks Syariah",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SYARIAH": {
        "rd_code": "RD424",
        "slug": "bnp-paripas-pesona-syariah",
        "nama_display": "BNP Paripas Pesona Syariah",
        "jenis": "unknown",
    },
    "BNI_AM_INDEX": {
        "rd_code": "RD337",
        "slug": "bni-am-indexs",
        "nama_display": "BNI AM Indexs",
        "jenis": "unknown",
    },
    "MANDIRI_INVESTA_SYARIAH": {
        "rd_code": "RD860",
        "slug": "mandiri-investa-dana-syariah-kelas-a",
        "nama_display": "Mandiri Investa Dana Syariah Kelas A",
        "jenis": "unknown",
    },
    "TRIMEGAH_DANA_SYARIAH": {
        "rd_code": "RD3480",
        "slug": "trimegah-dana-tetap-syariah-kelas-a",
        "nama_display": "Trimegah Dana Tetap Syariah Kelas A",
        "jenis": "unknown",
    },
    "BNI_AM_PENDAPATAN_TETAP_SYARIAH": {
        "rd_code": "RD332",
        "slug": "bni-am-pendapatan-tetap-syariah-ardhani",
        "nama_display": "BNI-AM Pendapatan Tetap Syariah Ardhani",
        "jenis": "unknown",
    },
    "MAJORIS_SUKUK_NEGARA": {
        "rd_code": "RD838",
        "slug": "majoris-sukuk-negara-indonesia",
        "nama_display": "Majoris Sukuk Negara Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_MES_SYARIAH_G": {
        "rd_code": "RD1721",
        "slug": "bahana-mes-syariah-fund-kelas-g",
        "nama_display": "Bahana MES Syariah Fund Kelas G",
        "jenis": "unknown",
    },
    "MANULIFE_OBLIGASI_ID_II_A": {
        "rd_code": "RD994",
        "slug": "manulife-obligasi-negara-indonesia-ii-kelas-a",
        "nama_display": "Manulife Obligasi Negara Indonesia II Kelas A",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SUKUK_RK1": {
        "rd_code": "RD6524",
        "slug": "bnp-paripas-sukuk-negara-kelas-rk1",
        "nama_display": "BNP Paripas Sukuk Negara Kelas RK1",
        "jenis": "unknown",
    },
    "MAJORIS_PASAR_UANG_SYARIAH_ID": {
        "rd_code": "RD832",
        "slug": "majoris-pasar-uang-syariah-indonesia",
        "nama_display": "Majoris Pasar Uang Syariah Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_LIKUID_SYARIAH": {
        "rd_code": "RD3595",
        "slug": "bahana-likuid-syariah-kelas-g",
        "nama_display": "Bahana Likuid Syariah Kelas G",
        "jenis": "unknown",
    },
    "TRIMEGAH_KAS_SYARIAH": {
        "rd_code": "RD1775",
        "slug": "trimegah-kas-syariah",
        "nama_display": "Trimegah Kas Syariah",
        "jenis": "unknown",
    },
    "SUCORINVEST_SHARIA_MONEY": {
        "rd_code": "RD1669",
        "slug": "sucorinvest-sharia-money-market-fund",
        "nama_display": "Sucorinvest Sharia Money Market Fund",
        "jenis": "unknown",
    },
    "BATAVIA_DANA_KAS_MAXIMA": {
        "rd_code": "RD205",
        "slug": "batavia-dana-kas-maxima",
        "nama_display": "Batavia Dana Kas Maxima",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SYARIAH": {
        "rd_code": "RD424",
        "slug": "bnp-paripas-pesona-syariah",
        "nama_display": "BNP Paripas Pesona Syariah",
        "jenis": "unknown",
    },
    "BNI_AM_INDEX": {
        "rd_code": "RD337",
        "slug": "bni-am-indexs",
        "nama_display": "BNI AM Indexs",
        "jenis": "unknown",
    },
    "MANDIRI_INVESTA_SYARIAH": {
        "rd_code": "RD860",
        "slug": "mandiri-investa-dana-syariah-kelas-a",
        "nama_display": "Mandiri Investa Dana Syariah Kelas A",
        "jenis": "unknown",
    },
    "TRIMEGAH_DANA_SYARIAH": {
        "rd_code": "RD3480",
        "slug": "trimegah-dana-tetap-syariah-kelas-a",
        "nama_display": "Trimegah Dana Tetap Syariah Kelas A",
        "jenis": "unknown",
    },
    "BNI_AM_PENDAPATAN_TETAP_SYARIAH": {
        "rd_code": "RD332",
        "slug": "bni-am-pendapatan-tetap-syariah-ardhani",
        "nama_display": "BNI-AM Pendapatan Tetap Syariah Ardhani",
        "jenis": "unknown",
    },
    "MAJORIS_SUKUK_NEGARA": {
        "rd_code": "RD838",
        "slug": "majoris-sukuk-negara-indonesia",
        "nama_display": "Majoris Sukuk Negara Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_MES_SYARIAH_G": {
        "rd_code": "RD1721",
        "slug": "bahana-mes-syariah-fund-kelas-g",
        "nama_display": "Bahana MES Syariah Fund Kelas G",
        "jenis": "unknown",
    },
    "MANULIFE_OBLIGASI_ID_II_A": {
        "rd_code": "RD994",
        "slug": "manulife-obligasi-negara-indonesia-ii-kelas-a",
        "nama_display": "Manulife Obligasi Negara Indonesia II Kelas A",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SUKUK_RK1": {
        "rd_code": "RD6524",
        "slug": "bnp-paripas-sukuk-negara-kelas-rk1",
        "nama_display": "BNP Paripas Sukuk Negara Kelas RK1",
        "jenis": "unknown",
    },
    "MAJORIS_PASAR_UANG_SYARIAH_ID": {
        "rd_code": "RD832",
        "slug": "majoris-pasar-uang-syariah-indonesia",
        "nama_display": "Majoris Pasar Uang Syariah Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_LIKUID_SYARIAH": {
        "rd_code": "RD3595",
        "slug": "bahana-likuid-syariah-kelas-g",
        "nama_display": "Bahana Likuid Syariah Kelas G",
        "jenis": "unknown",
    },
    "TRIMEGAH_KAS_SYARIAH": {
        "rd_code": "RD1775",
        "slug": "trimegah-kas-syariah",
        "nama_display": "Trimegah Kas Syariah",
        "jenis": "unknown",
    },
    "SUCORINVEST_SHARIA_MONEY": {
        "rd_code": "RD1669",
        "slug": "sucorinvest-sharia-money-market-fund",
        "nama_display": "Sucorinvest Sharia Money Market Fund",
        "jenis": "unknown",
    },
    "BATAVIA_DANA_KAS_MAXIMA": {
        "rd_code": "RD205",
        "slug": "batavia-dana-kas-maxima",
        "nama_display": "Batavia Dana Kas Maxima",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SYARIAH": {
        "rd_code": "RD424",
        "slug": "bnp-paripas-pesona-syariah",
        "nama_display": "BNP Paripas Pesona Syariah",
        "jenis": "unknown",
    },
    "BNI_AM_INDEX": {
        "rd_code": "RD337",
        "slug": "bni-am-indexs",
        "nama_display": "BNI AM Indexs",
        "jenis": "unknown",
    },
    "MANDIRI_INVESTA_SYARIAH": {
        "rd_code": "RD860",
        "slug": "mandiri-investa-dana-syariah-kelas-a",
        "nama_display": "Mandiri Investa Dana Syariah Kelas A",
        "jenis": "unknown",
    },
    "TRIMEGAH_DANA_SYARIAH": {
        "rd_code": "RD3480",
        "slug": "trimegah-dana-tetap-syariah-kelas-a",
        "nama_display": "Trimegah Dana Tetap Syariah Kelas A",
        "jenis": "unknown",
    },
    "BNI_AM_PENDAPATAN_TETAP_SYARIAH": {
        "rd_code": "RD332",
        "slug": "bni-am-pendapatan-tetap-syariah-ardhani",
        "nama_display": "BNI-AM Pendapatan Tetap Syariah Ardhani",
        "jenis": "unknown",
    },
    "MAJORIS_SUKUK_NEGARA": {
        "rd_code": "RD838",
        "slug": "majoris-sukuk-negara-indonesia",
        "nama_display": "Majoris Sukuk Negara Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_MES_SYARIAH_G": {
        "rd_code": "RD1721",
        "slug": "bahana-mes-syariah-fund-kelas-g",
        "nama_display": "Bahana MES Syariah Fund Kelas G",
        "jenis": "unknown",
    },
    "MANULIFE_OBLIGASI_ID_II_A": {
        "rd_code": "RD994",
        "slug": "manulife-obligasi-negara-indonesia-ii-kelas-a",
        "nama_display": "Manulife Obligasi Negara Indonesia II Kelas A",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SUKUK_RK1": {
        "rd_code": "RD6524",
        "slug": "bnp-paripas-sukuk-negara-kelas-rk1",
        "nama_display": "BNP Paripas Sukuk Negara Kelas RK1",
        "jenis": "unknown",
    },
    "MAJORIS_PASAR_UANG_SYARIAH_ID": {
        "rd_code": "RD832",
        "slug": "majoris-pasar-uang-syariah-indonesia",
        "nama_display": "Majoris Pasar Uang Syariah Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_LIKUID_SYARIAH": {
        "rd_code": "RD3595",
        "slug": "bahana-likuid-syariah-kelas-g",
        "nama_display": "Bahana Likuid Syariah Kelas G",
        "jenis": "unknown",
    },
    "TRIMEGAH_KAS_SYARIAH": {
        "rd_code": "RD1775",
        "slug": "trimegah-kas-syariah",
        "nama_display": "Trimegah Kas Syariah",
        "jenis": "unknown",
    },
    "SUCORINVEST_SHARIA_MONEY": {
        "rd_code": "RD1669",
        "slug": "sucorinvest-sharia-money-market-fund",
        "nama_display": "Sucorinvest Sharia Money Market Fund",
        "jenis": "unknown",
    },
    "BATAVIA_DANA_KAS_MAXIMA": {
        "rd_code": "RD205",
        "slug": "batavia-dana-kas-maxima",
        "nama_display": "Batavia Dana Kas Maxima",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SYARIAH": {
        "rd_code": "RD424",
        "slug": "bnp-paripas-pesona-syariah",
        "nama_display": "BNP Paripas Pesona Syariah",
        "jenis": "unknown",
    },
    "BNI_AM_INDEX": {
        "rd_code": "RD337",
        "slug": "bni-am-indexs",
        "nama_display": "BNI AM Indexs",
        "jenis": "unknown",
    },
    "MANDIRI_INVESTA_SYARIAH": {
        "rd_code": "RD860",
        "slug": "mandiri-investa-dana-syariah-kelas-a",
        "nama_display": "Mandiri Investa Dana Syariah Kelas A",
        "jenis": "unknown",
    },
    "TRIMEGAH_DANA_SYARIAH": {
        "rd_code": "RD3480",
        "slug": "trimegah-dana-tetap-syariah-kelas-a",
        "nama_display": "Trimegah Dana Tetap Syariah Kelas A",
        "jenis": "unknown",
    },
    "BNI_AM_PENDAPATAN_TETAP_SYARIAH": {
        "rd_code": "RD332",
        "slug": "bni-am-pendapatan-tetap-syariah-ardhani",
        "nama_display": "BNI-AM Pendapatan Tetap Syariah Ardhani",
        "jenis": "unknown",
    },
    "MAJORIS_SUKUK_NEGARA": {
        "rd_code": "RD838",
        "slug": "majoris-sukuk-negara-indonesia",
        "nama_display": "Majoris Sukuk Negara Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_MES_SYARIAH_G": {
        "rd_code": "RD1721",
        "slug": "bahana-mes-syariah-fund-kelas-g",
        "nama_display": "Bahana MES Syariah Fund Kelas G",
        "jenis": "unknown",
    },
    "MANULIFE_OBLIGASI_ID_II_A": {
        "rd_code": "RD994",
        "slug": "manulife-obligasi-negara-indonesia-ii-kelas-a",
        "nama_display": "Manulife Obligasi Negara Indonesia II Kelas A",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SUKUK_RK1": {
        "rd_code": "RD6524",
        "slug": "bnp-paripas-sukuk-negara-kelas-rk1",
        "nama_display": "BNP Paripas Sukuk Negara Kelas RK1",
        "jenis": "unknown",
    },
    "MAJORIS_PASAR_UANG_SYARIAH_ID": {
        "rd_code": "RD832",
        "slug": "majoris-pasar-uang-syariah-indonesia",
        "nama_display": "Majoris Pasar Uang Syariah Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_LIKUID_SYARIAH": {
        "rd_code": "RD3595",
        "slug": "bahana-likuid-syariah-kelas-g",
        "nama_display": "Bahana Likuid Syariah Kelas G",
        "jenis": "unknown",
    },
    "TRIMEGAH_KAS_SYARIAH": {
        "rd_code": "RD1775",
        "slug": "trimegah-kas-syariah",
        "nama_display": "Trimegah Kas Syariah",
        "jenis": "unknown",
    },
    "SUCORINVEST_SHARIA_MONEY": {
        "rd_code": "RD1669",
        "slug": "sucorinvest-sharia-money-market-fund",
        "nama_display": "Sucorinvest Sharia Money Market Fund",
        "jenis": "unknown",
    },
    "BATAVIA_DANA_KAS_MAXIMA": {
        "rd_code": "RD205",
        "slug": "batavia-dana-kas-maxima",
        "nama_display": "Batavia Dana Kas Maxima",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SYARIAH": {
        "rd_code": "RD424",
        "slug": "bnp-paripas-pesona-syariah",
        "nama_display": "BNP Paripas Pesona Syariah",
        "jenis": "unknown",
    },
    "BNI_AM_INDEX": {
        "rd_code": "RD337",
        "slug": "bni-am-indexs",
        "nama_display": "BNI AM Indexs",
        "jenis": "unknown",
    },
    "MANDIRI_INVESTA_SYARIAH": {
        "rd_code": "RD860",
        "slug": "mandiri-investa-dana-syariah-kelas-a",
        "nama_display": "Mandiri Investa Dana Syariah Kelas A",
        "jenis": "unknown",
    },
    "TRIMEGAH_DANA_SYARIAH": {
        "rd_code": "RD3480",
        "slug": "trimegah-dana-tetap-syariah-kelas-a",
        "nama_display": "Trimegah Dana Tetap Syariah Kelas A",
        "jenis": "unknown",
    },
    "BNI_AM_PENDAPATAN_TETAP_SYARIAH": {
        "rd_code": "RD332",
        "slug": "bni-am-pendapatan-tetap-syariah-ardhani",
        "nama_display": "BNI-AM Pendapatan Tetap Syariah Ardhani",
        "jenis": "unknown",
    },
    "MAJORIS_SUKUK_NEGARA": {
        "rd_code": "RD838",
        "slug": "majoris-sukuk-negara-indonesia",
        "nama_display": "Majoris Sukuk Negara Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_MES_SYARIAH_G": {
        "rd_code": "RD1721",
        "slug": "bahana-mes-syariah-fund-kelas-g",
        "nama_display": "Bahana MES Syariah Fund Kelas G",
        "jenis": "unknown",
    },
    "MANULIFE_OBLIGASI_ID_II_A": {
        "rd_code": "RD994",
        "slug": "manulife-obligasi-negara-indonesia-ii-kelas-a",
        "nama_display": "Manulife Obligasi Negara Indonesia II Kelas A",
        "jenis": "unknown",
    },
    "BNP_PARIPAS_SUKUK_RK1": {
        "rd_code": "RD6524",
        "slug": "bnp-paripas-sukuk-negara-kelas-rk1",
        "nama_display": "BNP Paripas Sukuk Negara Kelas RK1",
        "jenis": "unknown",
    },
    "MAJORIS_PASAR_UANG_SYARIAH_ID": {
        "rd_code": "RD832",
        "slug": "majoris-pasar-uang-syariah-indonesia",
        "nama_display": "Majoris Pasar Uang Syariah Indonesia",
        "jenis": "unknown",
    },
    "BAHANA_LIKUID_SYARIAH": {
        "rd_code": "RD3595",
        "slug": "bahana-likuid-syariah-kelas-g",
        "nama_display": "Bahana Likuid Syariah Kelas G",
        "jenis": "unknown",
    },
    "TRIMEGAH_KAS_SYARIAH": {
        "rd_code": "RD1775",
        "slug": "trimegah-kas-syariah",
        "nama_display": "Trimegah Kas Syariah",
        "jenis": "unknown",
    },
    "SUCORINVEST_SHARIA_MONEY": {
        "rd_code": "RD1669",
        "slug": "sucorinvest-sharia-money-market-fund",
        "nama_display": "Sucorinvest Sharia Money Market Fund",
        "jenis": "unknown",
    },
    "BATAVIA_DANA_KAS_MAXIMA": {
        "rd_code": "RD205",
        "slug": "batavia-dana-kas-maxima",
        "nama_display": "Batavia Dana Kas Maxima",
        "jenis": "unknown",
    }
}


# =============================================================================
# FETCH SATU REKSA DANA
# =============================================================================

def _scrape_nav_from_html(rd_code: str, slug: str = None) -> float | None:
    """
    Scrape NAV per unit dari halaman HTML Bibit.
    Data ada di __NEXT_DATA__ → props.pageProps → nav.value
    Ini adalah NAV yang BENAR (per unit), bukan nilai simulasi.
    """
    url = f"https://bibit.id/reksadana/{rd_code}"
    if slug:
        url = f"https://bibit.id/reksadana/{rd_code}/{slug}"

    headers_html = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "id-ID,id;q=0.9",
    }

    import re
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers_html, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.warning(f"[reksa] HTML {resp.status_code} → {url}")
                return None

            html = resp.text

            # Extract __NEXT_DATA__
            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if match:
                data = json.loads(match.group(1))
                text = json.dumps(data)
                # Cari nav.value — format: "nav": {..., "value": 1783.48}
                nav_match = re.search(
                    r'"nav".*?"value".*?([0-9]+\.[0-9]+)',
                    text
                )
                if nav_match:
                    nab = float(nav_match.group(1))
                    if nab > 0:
                        return nab

            logger.warning(f"[reksa] NAV tidak ditemukan di HTML → {url}")
            return None

        except Exception as e:
            logger.warning(f"[reksa] HTML scrape error attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    return None


def fetch_single_reksa(kode: str, config: dict, last_nab: float = None) -> dict:
    """
    Fetch NAB satu reksa dana via endpoint simulations Bibit.
    NAB terbaru = elemen terakhir dari array simulations.
    """
    rd_code = config["rd_code"]
    nama    = config["nama_display"]
    url     = f"https://api.bibit.id/products/{rd_code}/simulations?range=120"

    nab    = None
    source = None

    # ── 1. HTML scraping (NAV per unit yang akurat) ──────────────────────
    slug = config.get("slug", "")
    nab = _scrape_nav_from_html(rd_code, slug)
    if nab:
        source = "bibit_html"
        logger.info(f"[reksa] ✅ {nama} = Rp {nab:,.4f} ({rd_code}) [html]")

    # ── 2. Fallback: simulations endpoint ────────────────────────────────
    if not nab:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    nav_list = data.get("data", [])
                    if nav_list and isinstance(nav_list, list) and len(nav_list) > 0:
                        nab    = float(nav_list[-1])
                        source = "bibit_simulations"
                        logger.warning(f"[reksa] ⚠️  {nama} = Rp {nab:,.4f} (simulations — bukan NAV per unit!)")
                        break
                elif resp.status_code == 404:
                    logger.warning(f"[reksa] 404 {nama} ({rd_code})")
                    break
                else:
                    logger.warning(f"[reksa] HTTP {resp.status_code} attempt {attempt}/{MAX_RETRIES} — {nama}")
            except Exception as e:
                logger.warning(f"[reksa] Error attempt {attempt}/{MAX_RETRIES} — {nama}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    # ── Fallback: cache terakhir ──────────────────────────────────────────
    if nab is None and last_nab:
        nab    = last_nab
        source = "cache"
        logger.warning(f"[reksa] ⚠️  {nama} — pakai NAB cache = Rp {nab:,.4f}")

    if nab is None:
        logger.error(f"[reksa] ❌ {nama} ({rd_code}) — gagal semua, NAB tidak tersedia")

    return {
        "kode":        kode,
        "rd_code":     rd_code,
        "nama":        nama,
        "jenis":       config.get("jenis", "unknown"),
        "current_nab": nab,
        "nav_date":    date.today().isoformat(),
        "source":      source,
        "fetch_time":  datetime.now().isoformat(),
        "ok":          nab is not None,
    }


# =============================================================================
# FETCH SEMUA REKSA DANA
# =============================================================================

def fetch_all_reksa(watchlist: list = None, last_data: dict = None) -> dict:
    """
    Fetch NAB semua reksa dana dalam REKSA_MAPPING.

    Args:
        watchlist  : list kode internal, None = ambil semua
        last_data  : dict NAB terakhir dari Firestore untuk fallback
                     format: { "KODE_INTERNAL": {"current_nab": 1234.5} }

    Returns:
        {
            "results":    { "KODE": {result_dict}, ... },
            "summary":    { "total": N, "ok": N, "failed": N, "cached": N },
            "fetch_time": "ISO string",
        }
    """
    last_data   = last_data or {}
    target_keys = watchlist if watchlist else list(REKSA_MAPPING.keys())

    results = {}
    stats   = {"total": 0, "ok": 0, "failed": 0, "cached": 0}

    for kode in target_keys:
        if kode not in REKSA_MAPPING:
            logger.warning(f"[reksa] Kode '{kode}' tidak ada di REKSA_MAPPING — skip")
            continue

        config   = REKSA_MAPPING[kode]
        last_nab = last_data.get(kode, {}).get("current_nab")

        result        = fetch_single_reksa(kode, config, last_nab)
        results[kode] = result

        stats["total"] += 1
        if result["ok"]:
            stats["ok"] += 1
            if result["source"] == "cache":
                stats["cached"] += 1
        else:
            stats["failed"] += 1

        # Jeda antar request — hindari rate limit
        time.sleep(1)

    logger.info(
        f"[reksa] Selesai: {stats['ok']}/{stats['total']} berhasil, "
        f"{stats['cached']} dari cache, {stats['failed']} gagal"
    )

    return {
        "results":    results,
        "summary":    stats,
        "fetch_time": datetime.now().isoformat(),
    }


# =============================================================================
# FORMAT UNTUK FIRESTORE & ANALYST ENGINE
# =============================================================================

def format_for_firestore(fetch_result: dict) -> dict:
    """
    Convert output fetch_all_reksa() ke format siap simpan ke Firestore.
    Hanya reksa dana yang berhasil di-fetch (ok=True) yang dimasukkan.
    """
    return {
        kode: {
            "current_nab": v["current_nab"],
            "nama":        v["nama"],
            "jenis":       v["jenis"],
            "nav_date":    v["nav_date"],
            "source":      v["source"],
            "fetch_time":  v["fetch_time"],
        }
        for kode, v in fetch_result["results"].items()
        if v["ok"]
    }


# =============================================================================
# TEST STANDALONE — jalankan: python3 reksa_fetcher.py
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    print("=" * 65)
    print("OMNI-INVEST — Reksa Dana Auto-Fetch (Bibit simulations)")
    print("=" * 65)

    data = fetch_all_reksa()

    print(f"\n{'KODE':<35} {'NAB':>14}  {'SOURCE'}")
    print("-" * 65)
    for kode, r in data["results"].items():
        status  = "✅" if r["ok"] else "❌"
        nab_str = f"Rp {r['current_nab']:>12,.4f}" if r["current_nab"] else "          N/A"
        src     = f"[{r['source']}]" if r["source"] else "[FAILED]"
        print(f"  {status} {kode:<33} {nab_str}  {src}")

    print(f"\nSummary : {data['summary']}")
    print(f"Waktu   : {data['fetch_time']}")
