"""
=============================================================
  SIRALI SKOR EŞLEŞMELERİ ANALİZ UYGULAMASI (GELİŞMİŞ SÜRÜM)
  Teknoloji: Python + Streamlit + SQLite
  Özellik: 2 Farklı Karşılaştırma Modu + Maç Sonucu Tahmini
=============================================================
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import os
import random
import json
from supabase import create_client, Client

# ─────────────────────────────────────────────
#  1. SAYFA & TEMA YAPILANDIRMASI
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Sıralı Skor Eşleşme Analizi",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── Genel Tema ── */
html, body, [class*="css"] { background-color: #0e0e12; color: #e8e8f0; font-family: 'Segoe UI', sans-serif; }
.stApp { background-color: #0e0e12; }
section[data-testid="stSidebar"] { background-color: #15151e; border-right: 1px solid #2a2a3a; }

/* Başlıklar */
h1, h2, h3, h4 { color: #c9d1ff; }
h1 { border-bottom: 2px solid #3b3bff33; padding-bottom: 8px; }

/* Input kutuları */
input[type="text"], .stTextInput > div > div > input { background-color: #1e1e2e !important; color: #e8e8f0 !important; border: 1px solid #3a3a5a !important; border-radius: 6px !important; }

/* Butonlar */
.stButton > button { background: linear-gradient(135deg, #3b3bff 0%, #7b5ef5 100%); color: white; border: none; border-radius: 8px; padding: 10px 28px; font-weight: 700; transition: all 0.2s ease; width: 100%; }
.stButton > button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px #3b3bff55; }

/* Tablo / DF */
.stDataFrame { background-color: #15151e !important; border-radius: 10px; }

/* Bildirim Kutuları ve Badgeler */
.match-card { background: #1a1a2e; border: 1px solid #2d2d4a; border-radius: 10px; padding: 14px 18px; margin-bottom: 10px; margin-top: 5px;}
.badge-green { background: #1a3a2a; border: 1px solid #2adf7a; color: #2adf7a; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; display: inline-block; }
.badge-neutral { background: #2a2a3a; border: 1px solid #555577; color: #8888aa; padding: 2px 10px; border-radius: 12px; font-size: 12px; display: inline-block; }
.badge-partial { background: #2a2200; border: 1px solid #f0a500; color: #f0a500; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 700; display: inline-block; }

/* Divider */
hr { border-color: #2a2a3a; }

/* Select / Date vb */
.stSelectbox > div > div, .stDateInput > div > div > input { background-color: #1e1e2e !important; color: #e8e8f0 !important; border: 1px solid #3a3a5a !important; }
.streamlit-expanderHeader { background-color: #1a1a2e !important; color: #c9d1ff !important; border: 1px solid #2d2d4a !important; border-radius: 8px !important; }

/* Metric Box */
[data-testid="stMetric"] { background: #1a1a2e; border: 1px solid #2d2d4a; border-radius: 10px; padding: 14px; }
[data-testid="stMetricLabel"] { color: #9999bb !important; font-size: 13px; }
[data-testid="stMetricValue"] { color: #c9d1ff !important; font-size: 28px; font-weight: 800; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  2. VERİTABANI KATMANI (SUPABASE)
# ─────────────────────────────────────────────

TAKIMLAR = ["Galatasaray", "Fenerbahçe", "Beşiktaş", "Trabzonspor", "Başakşehir", "Sivasspor", "Antalyaspor", "Adana Demirspor", "Kasımpaşa", "Alanyaspor", "Konyaspor", "Kayserispor"]
SKORLAR = ["0-0", "1-0", "0-1", "1-1", "2-0", "0-2", "2-1", "1-2", "2-2", "3-0", "0-3", "3-1", "1-3"]

@st.cache_resource
def init_supabase() -> Client:
    try:
        url = os.environ.get("SUPABASE_URL")
        if not url and hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets:
            url = st.secrets["SUPABASE_URL"]
            
        key = os.environ.get("SUPABASE_KEY")
        if not key and hasattr(st, "secrets") and "SUPABASE_KEY" in st.secrets:
            key = st.secrets["SUPABASE_KEY"]
            
        if not url or not key:
            raise ValueError("SUPABASE_URL veya SUPABASE_KEY eksik")
            
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase bağlantısı kurulamadı. Lütfen ortam değişkenlerini kontrol edin. Hata: {e}")
        st.stop()

supabase = init_supabase()

def _clean(d):
    """Postgres unquoted columns are inherently lowercase. We lower all dict keys to match."""
    return {k.lower(): v for k, v in d.items()}

def build_skor_dict(ev_s, dep_s):
    d = {}
    for i in range(1, 6):
        d[f"ev_HT_{i}"] = ev_s.get(f"HT_{i}", "")
        d[f"ev_FT_{i}"] = ev_s.get(f"FT_{i}", "")
        d[f"dep_HT_{i}"] = dep_s.get(f"HT_{i}", "")
        d[f"dep_FT_{i}"] = dep_s.get(f"FT_{i}", "")
    return d

# DB İşlemleri - Ortak (Mod 1)
def kayit_ekle_mod1(tarih, ev, dep, sonuc_ht, sonuc_ft, ev_skorlar, dep_skorlar, is_sample=0):
    data = {
        "tarih": str(tarih), "ev_takimi": ev.strip(), "dep_takimi": dep.strip(),
        "sonuc_HT": sonuc_ht.strip() if sonuc_ht else "", "sonuc_FT": sonuc_ft.strip() if sonuc_ft else "",
        "is_sample": is_sample,
        **build_skor_dict(ev_skorlar, dep_skorlar)
    }
    # Postgres ignores case in unquoted inserts, but supabase-py passes exact dict keys
    res = supabase.table("mac_arsivi").insert(_clean(data)).execute()
    return res.data[0]["id"] if res.data else None

def liste_mod1():
    res = supabase.table("mac_arsivi").select("*").order("tarih", desc=True).order("id", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def sil_mod1(k_id): supabase.table("mac_arsivi").delete().eq("id", k_id).execute()
def ornek_sil_mod1(): supabase.table("mac_arsivi").delete().eq("is_sample", 1).execute()

def guncelle_skor_mod1(k_id, sht, sft):
    supabase.table("mac_arsivi").update(_clean({"sonuc_HT": sht, "sonuc_FT": sft})).eq("id", k_id).execute()

# DB İşlemleri - Detaylı (Mod 2)
def kayit_ekle_mod2(tarih, ev, dep, sonuc_ht, sonuc_ft, ev_skorlar, dep_skorlar, is_sample=0):
    data = {
        "tarih": str(tarih), "ev_takimi": ev.strip(), "dep_takimi": dep.strip(),
        "sonuc_HT": sonuc_ht.strip() if sonuc_ht else "", "sonuc_FT": sonuc_ft.strip() if sonuc_ft else "",
        "is_sample": is_sample,
        **build_skor_dict(ev_skorlar, dep_skorlar)
    }
    res = supabase.table("mac_arsivi_detayli").insert(_clean(data)).execute()
    return res.data[0]["id"] if res.data else None

def liste_mod2():
    res = supabase.table("mac_arsivi_detayli").select("*").order("tarih", desc=True).order("id", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def sil_mod2(k_id): supabase.table("mac_arsivi_detayli").delete().eq("id", k_id).execute()
def ornek_sil_mod2(): supabase.table("mac_arsivi_detayli").delete().eq("is_sample", 1).execute()

def guncelle_skor_mod2(k_id, sht, sft):
    supabase.table("mac_arsivi_detayli").update(_clean({"sonuc_HT": sht, "sonuc_FT": sft})).eq("id", k_id).execute()

# Tahmin Geçmişi (Backtest) DB İşlemleri
def tahmin_kaydet(tarih, ev, dep, mod, girilen_skorlar, eslesen_idler, eslesen_detay, eslesen_sayisi):
    data = {
        "tarih": str(tarih), "ev_takimi": ev.strip(), "dep_takimi": dep.strip(), "mod": mod,
        "girilen_skorlar": girilen_skorlar, # jsonb
        "eslesen_idler": eslesen_idler,
        "eslesen_detay": eslesen_detay,
        "eslesen_sayisi": eslesen_sayisi
    }
    supabase.table("tahmin_gecmisi").insert(_clean(data)).execute()

def tahmin_listele():
    res = supabase.table("tahmin_gecmisi").select("*").order("id", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def tahmin_skor_guncelle(t_id, sht, sft):
    supabase.table("tahmin_gecmisi").update(_clean({"sonuc_HT": sht, "sonuc_FT": sft})).eq("id", t_id).execute()

def tahmin_sil(t_id):
    supabase.table("tahmin_gecmisi").delete().eq("id", t_id).execute()

def tahmin_tumunu_sil():
    # Supabase'de tüm satırları silmek için ID > 0 kullanabiliriz
    supabase.table("tahmin_gecmisi").delete().gt("id", 0).execute()

def db_ist_mod(tbl):
    try:
        res = supabase.table(tbl).select("tarih", count="exact").execute()
        t = res.count if res.count else 0
        data_res = supabase.table(tbl).select("tarih").execute()
        df = pd.DataFrame(data_res.data)
        if not df.empty and "tarih" in df.columns:
            yn = df["tarih"].max()
            es = df["tarih"].min()
        else:
            yn, es = "-", "-"
        return {"toplam": t, "yeni": yn, "eski": es}
    except:
        return {"toplam": 0, "yeni": "-", "eski": "-"}

# Rastgele veri üretici
def rastgele_tarih(): return date.today() - timedelta(days=random.randrange(365))

def ornek_yukle_mod1(adet=50):
    for _ in range(adet):
        e, d = random.sample(TAKIMLAR, 2)
        sht = random.choice(["0-0","1-0","0-1","1-1","2-0"])
        sft = random.choice(["1-0","2-1","1-1","0-1","3-1","2-2"])
        skor_e = {f"{t}_{i}": random.choice(SKORLAR) for t in ["HT","FT"] for i in range(1,6)}
        skor_d = {f"{t}_{i}": random.choice(SKORLAR) for t in ["HT","FT"] for i in range(1,6)}
        kayit_ekle_mod1(rastgele_tarih(), e, d, sht, sft, skor_e, skor_d, is_sample=1)

def ornek_yukle_mod2(adet=50):
    for _ in range(adet):
        e, d = random.sample(TAKIMLAR, 2)
        sht = random.choice(["0-0","1-0","0-1","1-1","2-0"])
        sft = random.choice(["1-0","2-1","1-1","0-1","3-1","2-2"])
        skor_e = {f"{t}_{i}": random.choice(SKORLAR) for t in ["HT","FT"] for i in range(1,6)}
        skor_d = {f"{t}_{i}": random.choice(SKORLAR) for t in ["HT","FT"] for i in range(1,6)}
        kayit_ekle_mod2(rastgele_tarih(), e, d, sht, sft, skor_e, skor_d, is_sample=1)


# ─────────────────────────────────────────────
#  3. ANALİZ MOTORLARI VE HELPERS
# ─────────────────────────────────────────────
def nor(s): 
    x = str(s).strip().lower() if s else ""
    if x in ("","-","x","?","boş","bos","none","nan"): return ""
    # format if previously missed
    if len(x) == 2 and x.isdigit(): x = f"{x[0]}-{x[1]}"
    x = x.replace(" ", "-").replace(".", "-").replace(",", "-").replace("/", "-")
    return x

def ht_badge(detay_listesi: list) -> str:
    parcalar = []
    for p in detay_listesi:
        poz = p["pozisyon"]
        dur = p["durum"]
        ht = p["ht_db"] or "?"
        ft = p["ft_db"] or "?"
        lbl = f"M{poz}: {ht}/{ft}"
        if dur == "tam": parcalar.append(f'<span class="badge-green">✓ {lbl}</span>')
        elif dur == "kismi": parcalar.append(f'<span class="badge-partial">~ {lbl}</span>')
        elif dur == "yok": parcalar.append(f'<span class="badge-neutral">✗ M{poz}</span>')
    return " ".join(parcalar)

def fmt_in(val):
    v = str(val).strip().lower()
    if len(v) == 2 and v.isdigit(): return f"{v[0]}-{v[1]}"
    return v.replace(" ", "-").replace(".", "-").replace(",", "-").replace("/", "-")

def input_skor_ui(prefix):
    """5 maç İY/MS satırı çizer ve değerleri sözlük döner."""
    d = {}
    cols = st.columns(5)
    for i in range(1, 6):
        with cols[i-1]:
            st.markdown(f"<div style='text-align:center; color:#c9d1ff; font-weight:bold; margin-bottom:5px;'>Maç {i}</div>", unsafe_allow_html=True)
            ht = st.text_input(f"İY {i}", key=f"{prefix}iy{i}", placeholder="İY (10)", label_visibility="collapsed")
            ft = st.text_input(f"MS {i}", key=f"{prefix}ms{i}", placeholder="MS (21)", label_visibility="collapsed")
            d[f"HT_{i}"] = fmt_in(ht)
            d[f"FT_{i}"] = fmt_in(ft)
    
    # CSS injection for tighter spacing
    st.markdown("""
    <style>
      div[data-testid="stForm"] .stTextInput { margin-bottom: -15px; }
    </style>
    """, unsafe_allow_html=True)
    return d

def eslesme_hesapla_mod1(ev_g, dep_g, kayit):
    """Mod 1 artık ev/dep ayrı — mod 2 ile aynı mantık."""
    ev_tam=0; dep_tam=0; kars=0; ev_detay=[]; dep_detay=[]
    # Supabase Postgres lowers unquoted column names!
    # kayit comes from a pandas dataframe out of supabase dicts. Let's use get with case insensitive or explicitly lower.
    def get_col(prefix, typ, idx):
        # We explicitly created columns like ev_HT_1, ev_FT_1 in the Supabase script, but Postgres makes them ev_ht_1.
        # Fallback dictionary get
        col = f"{prefix}_{typ}_{idx}"
        return kayit.get(col, kayit.get(col.lower(), ""))

    for i in range(1, 6):
        # Ev
        hg = nor(ev_g.get(f"HT_{i}")); fg = nor(ev_g.get(f"FT_{i}"))
        hd = nor(get_col("ev", "HT", i)); fd = nor(get_col("ev", "FT", i))
        if not hg and not fg: ev_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; ev_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            ev_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd})
        # Dep
        hg = nor(dep_g.get(f"HT_{i}")); fg = nor(dep_g.get(f"FT_{i}"))
        hd = nor(get_col("dep", "HT", i)); fd = nor(get_col("dep", "FT", i))
        if not hg and not fg: dep_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; dep_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            dep_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd})
    toplam_tam = ev_tam + dep_tam
    oran = (toplam_tam/kars*100) if kars>0 else 0
    return {"tam": toplam_tam, "kars": kars, "oran": oran, "ev_detay": ev_detay, "dep_detay": dep_detay}



def eslesme_hesapla_mod2(ev_g, dep_g, kayit):
    ev_tam=0; dep_tam=0; kars=0; ev_detay=[]; dep_detay=[]
    
    def get_col(prefix, typ, idx):
        col = f"{prefix}_{typ}_{idx}"
        return kayit.get(col, kayit.get(col.lower(), ""))

    for i in range(1, 6):
        # Ev
        hg = nor(ev_g.get(f"HT_{i}")); fg = nor(ev_g.get(f"FT_{i}"))
        hd = nor(get_col("ev", "HT", i)); fd = nor(get_col("ev", "FT", i))
        if not hg and not fg: ev_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; ev_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            ev_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd})
            
        # Dep
        hg = nor(dep_g.get(f"HT_{i}")); fg = nor(dep_g.get(f"FT_{i}"))
        hd = nor(get_col("dep", "HT", i)); fd = nor(get_col("dep", "FT", i))
        if not hg and not fg: dep_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; dep_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            dep_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd})
    
    toplam_tam = ev_tam + dep_tam
    oran = (toplam_tam/kars*100) if kars>0 else 0
    return {"tam": toplam_tam, "kars": kars, "oran": oran, "ev_detay": ev_detay, "dep_detay": dep_detay}


# ─────────────────────────────────────────────
#  4. ARAYÜZ (UI) MANTIKLARI
# ─────────────────────────────────────────────

# Sidebar Seçimi
with st.sidebar:
    st.markdown("## ⚙️ Karşılaştırma Modu")
    secilen_mod = st.radio(
        "Lütfen Analiz Yöntemini Seçin:",
        [
            "1️⃣ Ortak 5 Maç (Genel Yöntem)",
            "2️⃣ Ev / Dep Ayrı 5 Maç (Detaylı)"
        ],
        help="Mod 1 önceki mantıkta çalışır. Mod 2'de ev sahibi ve deplasman geçmişleri ayrı ayrı girilir."
    )
    st.markdown("---")
    
    if "1️⃣" in secilen_mod:
        istat = db_ist_mod("mac_arsivi")
    else:
        istat = db_ist_mod("mac_arsivi_detayli")
        
    st.markdown("### 📊 Aktif DB Durumu")
    st.metric("Kayıt Sayısı", f"{istat['toplam']:,}")
    st.caption(f"En yeni: {istat['yeni']} \nEn eski: {istat['eski']}")

# ─── Mod 1 (Ortak 5 Maç) Çizimi ───
if "1️⃣" in secilen_mod:
    st.markdown("<h1>⚽ Ortak Skor Eşleşme Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>Ev sahibi ve deplasman takımlarının <b>son 5 maçını ayrı ayrı</b> girerek analiz yapın.</p><hr>", unsafe_allow_html=True)
    
    t1, t2, t3, t4 = st.tabs(["🔍 Analiz Yap", "➕ Kayıt Ekle", "📋 Tüm Veriler", "📈 Tahmin Geçmişi"])
    
    with t1:
        with st.form("form_a1"):
            st.markdown("### 🔍 Analiz Yap + Otomatik Kayıt")
            st.caption("Veriler otomatik olarak veritabanına kaydedilir. Maç bitince skoru güncellersiniz.")
            
            ac1, ac2, ac3 = st.columns([2, 2, 1])
            a_ev = ac1.text_input("🏠 Ev Sahibi Takım", placeholder="Örn: Galatasaray", key="a1_ev")
            a_dep = ac2.text_input("✈️ Deplasman Takımı", placeholder="Örn: Fenerbahçe", key="a1_dep")
            a_tar = ac3.date_input("📅 Tarih", value=date.today(), key="a1_tar")
            
            st.markdown("---")
            st.markdown("#### 🏠 Ev Sahibi Son 5 Maç")
            ev_gir1 = input_skor_ui("a1_ev")
            st.markdown("<br>#### ✈️ Deplasman Son 5 Maç", unsafe_allow_html=True)
            dep_gir1 = input_skor_ui("a1_dep")
            
            st.markdown("---")
            c1, c2 = st.columns([2,1])
            min_e = c1.slider("Min Tam Eşleşme (Max 10)", 1, 10, 1)
            basla = c2.form_submit_button("🔍 Analizi Başlat")
            
        if basla:
            if a_ev.strip() and a_dep.strip():
                kayit_ekle_mod1(a_tar, a_ev, a_dep, "", "", ev_gir1, dep_gir1)
                st.info(f"💾 **{a_ev} vs {a_dep}** veritabanına kaydedildi.")
            
            df = liste_mod1()
            sonuclar = []
            eslesen_id_liste = []
            eslesen_detay_liste = []
            for _, r in df.iterrows():
                res = eslesme_hesapla_mod1(ev_gir1, dep_gir1, r)
                if res["tam"] >= min_e:
                    sht = r.get("sonuc_HT", r.get("sonuc_ht", "?")) or "?"
                    sft = r.get("sonuc_FT", r.get("sonuc_ft", "?")) or "?"
                    sonuclar.append({"id":r["id"], "tarih":r["tarih"], "ev":r["ev_takimi"], "dep":r["dep_takimi"], "sht": sht, "sft": sft, **res})
                    eslesen_id_liste.append(int(r["id"]))
                    eslesen_detay_liste.append({
                        "id": int(r["id"]), "tarih": r["tarih"], "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                        "sht": sht, "sft": sft, "tam": res["tam"], "kars": res["kars"],
                        "oran": res["oran"], "ev_detay": res["ev_detay"], "dep_detay": res["dep_detay"]
                    })
            
            if a_ev.strip() and a_dep.strip():
                birlesik = {"ev": ev_gir1, "dep": dep_gir1}
                tahmin_kaydet(a_tar, a_ev, a_dep, 1, birlesik, eslesen_id_liste, eslesen_detay_liste, len(sonuclar))
            
            if not sonuclar:
                st.warning("Eşleşen kayıt bulunamadı.")
            else:
                sdf = pd.DataFrame(sonuclar).sort_values(["tam", "oran"], ascending=False)
                st.success(f"✅ {len(sdf)} adet eşleşme bulundu!")
                for t_val in sorted(sdf["tam"].unique(), reverse=True):
                    g = sdf[sdf["tam"]==t_val]
                    st.markdown(f"### {t_val}/10 Eşleşme ({len(g)} Kayıt)")
                    for _, row in g.iterrows():
                        st.markdown(f"""
                        <div class="match-card">
                          <div style="display:flex; justify-content:space-between; margin-bottom: 8px;">
                            <div><b>🏠 {row['ev']}</b> vs <b>{row['dep']} ✈️</b> <span style="color:#888;font-size:12px">({row['tarih']})</span></div>
                            <div>Eşleşme: <b style="color:#2adf7a">{row['tam']}/{row['kars']}</b></div>
                          </div>
                          <div style="background-color: #212133; padding: 6px 12px; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid #ffcc00;">
                              <span style="font-size: 15px;">🎯 <b>Biten Maç Sonucu:</b> <span style="color:#ffcc00; font-weight:bold;">İY {row['sht']} / MS {row['sft']}</span></span>
                          </div>
                          <div>
                              <div style="margin-bottom:4px;"><span style="color:#bbb; font-weight:bold; display:inline-block; width:45px;"> Ev:</span> {ht_badge(row['ev_detay'])}</div>
                              <div><span style="color:#bbb; font-weight:bold; display:inline-block; width:45px;"> Dep:</span> {ht_badge(row['dep_detay'])}</div>
                          </div>
                        </div>""", unsafe_allow_html=True)
                        
    with t2:
        with st.form("form_k1", clear_on_submit=True):
            st.markdown("### ➕ Yeni Maç Kaydı")
            c1, c2, c3 = st.columns([2,2,1])
            yev = c1.text_input("🏠 Ev Takımı", placeholder="Örn: Galatasaray")
            ydep = c2.text_input("✈️ Dep Takımı", placeholder="Örn: Fenerbahçe")
            ytar = c3.date_input("📅 Tarih", value=date.today())
            
            st.markdown("#### 🎯 Maçın Bitiş Skoru")
            st.caption("Maç bitmeden boş bırakabilirsiniz, sonradan güncellersiniz.")
            sc1, sc2 = st.columns(2)
            sonuc_ht = sc1.text_input("İY Sonucu", placeholder="0-0", key="k1_sht")
            sonuc_ft = sc2.text_input("MS Sonucu", placeholder="1-0", key="k1_sft")
            
            st.markdown("---")
            st.markdown("#### 🏠 Ev Sahibi Son 5 Maç")
            ev_sk1 = input_skor_ui("k1_ev")
            st.markdown("---")
            st.markdown("#### ✈️ Deplasman Son 5 Maç")
            dep_sk1 = input_skor_ui("k1_dep")
            st.markdown("---")
            if st.form_submit_button("💾 Kaydet"):
                yid = kayit_ekle_mod1(ytar, yev, ydep, sonuc_ht, sonuc_ft, ev_sk1, dep_sk1)
                st.success(f"Kayıt Eklendi! (ID: {yid})")
        
        st.markdown("---")
        with st.expander("📥 Test Verisi Yükle / Sil"):
            c_y, c_s = st.columns(2)
            if c_y.button("✅ 50 Adet Örnek Veri Yükle", key="o1"):
                ornek_yukle_mod1(50); st.success("Yüklendi!"); st.rerun()
            if c_s.button("🗑️ Tüm Örnek Verileri Sil", key="s1"):
                ornek_sil_mod1(); st.success("Silindi!"); st.rerun()

        st.markdown("---")
        st.markdown("### 📂 Excel'den Toplu Veri Yükle")
        st.caption("""
        Beklenen kolonlar: **tarih, ev_takimi, dep_takimi, sonuc_HT, sonuc_FT,  
        ev_HT_1, ev_FT_1 ... ev_HT_5, ev_FT_5, dep_HT_1, dep_FT_1 ... dep_HT_5, dep_FT_5**
        """)
        excel_file = st.file_uploader("📄 Excel dosyası seçin (.xlsx)", type=["xlsx", "xls", "csv"], key="exc1")

        if excel_file is not None:
            try:
                if excel_file.name.endswith(".csv"):
                    edf = pd.read_csv(excel_file)
                else:
                    edf = pd.read_excel(excel_file)
                
                edf.columns = [c.strip().lower().replace(" ","_") for c in edf.columns]
                
                gerekli = ["tarih", "ev_takimi", "dep_takimi"]
                eksik = [k for k in gerekli if k not in edf.columns]
                if eksik:
                    st.error(f"❌ Eksik kolonlar: {', '.join(eksik)}")
                else:
                    st.success(f"✅ {len(edf)} satır okundu. Önizleme:")
                    st.dataframe(edf.head(10), use_container_width=True, hide_index=True)
                    
                    if st.button(f"🚀 {len(edf)} Kaydı Veritabanına Aktar", key="imp1", type="primary"):
                        basarili = 0
                        for _, row in edf.iterrows():
                            ev_s = {f"{t}_{i}": str(row.get(f"ev_{t.lower()}_{i}", "") or "") for t in ["HT","FT"] for i in range(1,6)}
                            dep_s = {f"{t}_{i}": str(row.get(f"dep_{t.lower()}_{i}", "") or "") for t in ["HT","FT"] for i in range(1,6)}
                            kayit_ekle_mod1(
                                str(row.get("tarih", date.today())),
                                str(row.get("ev_takimi", "")),
                                str(row.get("dep_takimi", "")),
                                str(row.get("sonuc_ht", "") or ""),
                                str(row.get("sonuc_ft", "") or ""),
                                ev_s, dep_s
                            )
                            basarili += 1
                        st.success(f"🎉 {basarili} kayıt başarıyla yüklendi!")
                        st.balloons()
                        st.rerun()
            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")

    with t3:
        # Üst Panel (Yenile / Sil)
        b1, b2, b3 = st.columns([1, 2, 3])
        if b1.button("🔄 Tabloyu Yenile", key="y1", use_container_width=True): st.rerun()
        if b2.button("🗑️ SADECE Örnek Verileri Sil", type="primary", key="sd1", use_container_width=True):
            ornek_sil_mod1()
            st.success("Test amacıyla yüklenen tüm sahte / örnek kayıtlar başarıyla silindi!")
            st.rerun()
            
        df1 = liste_mod1()
        st.dataframe(df1.drop(columns=["olusturulma"], errors="ignore"), use_container_width=True, hide_index=True)
        
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("✏️ Maç Skoru Güncelle"):
                st.caption("Sonradan biten maçın skorunu buraya girebilirsiniz.")
                g_id = st.number_input("Güncellenecek ID", min_value=1, key="g_id1")
                g_ht = st.text_input("Yeni İY Sonucu", placeholder="0-0", key="g_ht1")
                g_ft = st.text_input("Yeni MS Sonucu", placeholder="1-0", key="g_ft1")
                if st.button("Güncelle", key="gb1"):
                    guncelle_skor_mod1(g_id, g_ht, g_ft)
                    st.success(f"#{g_id} güncellendi!"); st.rerun()

        with c2:
            with st.expander("🗑️ Spesifik Kayıt Sil"):
                sid = st.number_input("Silinecek ID", min_value=1)
                if st.button("Kaydı Uçur", key="ds1"):
                    sil_mod1(sid); st.success(f"#{sid} silindi!"); st.rerun()

# ─── Mod 2 (Ev & Dep Ayrı 5 Maç) Çizimi ───
else:
    st.markdown("<h1>⚽ Detaylı Skor Eşleşme Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>Ev sahibi için ayrı son 5 maç, deplasman için ayrı son 5 maç girilir. Geçmişte <b>iki takımın da aynı durumla sahaya çıktığı</b> maçlar aranır.</p><hr>", unsafe_allow_html=True)
    
    t1, t2, t3, t4 = st.tabs(["🔍 Analiz Yap", "➕ Kayıt Ekle", "📋 Tüm Veriler", "📈 Tahmin Geçmişi"])
    
    with t1:
        with st.form("form_a2"):
            st.markdown("### 🔍 Detaylı Analiz + Otomatik Kayıt")
            st.caption("Veriler otomatik olarak veritabanına kaydedilir. Maç bitince skoru 'Tüm Veriler' sekmesinden güncellersiniz.")
            
            ac1, ac2, ac3 = st.columns([2, 2, 1])
            a_ev2 = ac1.text_input("🏠 Ev Sahibi Takım", placeholder="Örn: Galatasaray", key="a2_ev_takim")
            a_dep2 = ac2.text_input("✈️ Deplasman Takımı", placeholder="Örn: Fenerbahçe", key="a2_dep_takim")
            a_tar2 = ac3.date_input("📅 Tarih", value=date.today(), key="a2_tar")
            
            st.markdown("---")
            st.markdown("#### 🏠 Ev Sahibi Geçmişi")
            e_gir = input_skor_ui("a2_ev")
            st.markdown("<br>#### ✈️ Deplasman Geçmişi", unsafe_allow_html=True)
            d_gir = input_skor_ui("a2_dep")
            
            st.markdown("---")
            c1, c2 = st.columns([2,1])
            min_e = c1.slider("Min Toplam Tam Eşleşme (Max. 10)", 1, 10, 1)
            basla2 = c2.form_submit_button("🔍 Detaylı Analizi Başlat")
            
        if basla2:
            # Önce veritabanına kaydet
            if a_ev2.strip() and a_dep2.strip():
                kayit_ekle_mod2(a_tar2, a_ev2, a_dep2, "", "", e_gir, d_gir)
                st.info(f"💾 **{a_ev2} vs {a_dep2}** veritabanına kaydedildi.")
            
            df2 = liste_mod2()
            sonuclar = []
            eslesen_id_liste2 = []
            eslesen_detay_liste2 = []
            for _, r in df2.iterrows():
                res = eslesme_hesapla_mod2(e_gir, d_gir, r)
                if res["tam"] >= min_e:
                    sht = r.get("sonuc_HT", r.get("sonuc_ht", "?")) or "?"
                    sft = r.get("sonuc_FT", r.get("sonuc_ft", "?")) or "?"
                    sonuclar.append({"id":r["id"], "tarih":r["tarih"], "ev":r["ev_takimi"], "dep":r["dep_takimi"], "sht": sht, "sft": sft, **res})
                    eslesen_id_liste2.append(int(r["id"]))
                    eslesen_detay_liste2.append({
                        "id": int(r["id"]), "tarih": r["tarih"], "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                        "sht": sht, "sft": sft, "tam": res["tam"], "kars": res["kars"],
                        "oran": res["oran"], "ev_detay": res["ev_detay"], "dep_detay": res["dep_detay"]
                    })
            
            # Tahmin geçmişine kaydet
            if a_ev2.strip() and a_dep2.strip():
                birlesik_skor = {"ev": e_gir, "dep": d_gir}
                tahmin_kaydet(a_tar2, a_ev2, a_dep2, 2, birlesik_skor, eslesen_id_liste2, eslesen_detay_liste2, len(sonuclar))
            
            if not sonuclar:
                st.warning("Bu kriterlere uygun detaylı kayıt bulunamadı.")
            else:
                sdf = pd.DataFrame(sonuclar).sort_values(["tam", "oran"], ascending=False)
                st.success(f"✅ {len(sdf)} adet eşleşme bulundu!")
                for t_val in sorted(sdf["tam"].unique(), reverse=True):
                    g = sdf[sdf["tam"]==t_val]
                    st.markdown(f"### {t_val}/10 Eşleşme ({len(g)} Kayıt)")
                    for _, row in g.iterrows():
                        st.markdown(f"""
                        <div class="match-card">
                          <div style="display:flex; justify-content:space-between; margin-bottom: 8px;">
                            <div style="font-size:18px;"><b>🏠 {row['ev']}</b> vs <b>{row['dep']} ✈️</b> <span style="color:#888;font-size:14px">({row['tarih']})</span></div>
                            <div style="font-size:18px;">Eşleşme: <b style="color:#2adf7a">{row['tam']}/{row['kars']}</b></div>
                          </div>
                          
                          <div style="background-color: #212133; padding: 6px 12px; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid #ffcc00;">
                              <span style="font-size: 15px;">🎯 <b>Biten Maç Sonucu:</b> <span style="color:#ffcc00; font-weight:bold;">İY {row['sht']} / MS {row['sft']}</span></span>
                          </div>

                          <div>
                              <div style="margin-bottom:4px;"><span style="color:#bbb; font-weight:bold; display:inline-block; width:45px;"> Ev:</span> {ht_badge(row['ev_detay'])}</div>
                              <div><span style="color:#bbb; font-weight:bold; display:inline-block; width:45px;"> Dep:</span> {ht_badge(row['dep_detay'])}</div>
                          </div>
                        </div>""", unsafe_allow_html=True)

    with t2:
        with st.form("form_k2", clear_on_submit=True):
            st.markdown("### ➕ Yeni Detaylı Maç Kaydı")
            c1, c2, c3 = st.columns([2,2,1])
            yev = c1.text_input("🏠 Ev Takımı", placeholder="Örn: Galatasaray")
            ydep = c2.text_input("✈️ Dep Takımı", placeholder="Örn: Fenerbahçe")
            ytar = c3.date_input("📅 Tarih", value=date.today())
            
            st.markdown("#### 🎯 Maçın Bitiş Skoru (Oynanan Ana Maç)")
            st.caption("Bu maçın gerçekte nasıl sonuçlandığını buraya girin.")
            sc1, sc2 = st.columns(2)
            sonuc_ht = sc1.text_input("İY Sonucu", placeholder="0-0", key="k2_sht")
            sonuc_ft = sc2.text_input("MS Sonucu", placeholder="1-0", key="k2_sft")

            st.markdown("---")
            st.markdown("#### 🏠 Ev Sahibi (Maca Çıkmadan Önceki Son 5 Maçı)")
            ev_sk = input_skor_ui("k2_ev")
            
            st.markdown("---")
            st.markdown("#### ✈️ Deplasman (Maca Çıkmadan Önceki Son 5 Maçı)")
            dep_sk = input_skor_ui("k2_dep")
            
            st.markdown("---")
            if st.form_submit_button("💾 Detaylı Kaydet"):
                yid = kayit_ekle_mod2(ytar, yev, ydep, sonuc_ht, sonuc_ft, ev_sk, dep_sk)
                st.success(f"Detaylı Kayıt Eklendi! (ID: {yid})")

        st.markdown("---")
        with st.expander("📥 Detaylı Test Verisi Yükle / Sil"):
            c_y, c_s = st.columns(2)
            if c_y.button("✅ 50 Adet Örnek Veri Yükle", key="o2"):
                ornek_yukle_mod2(50); st.success("Yüklendi!"); st.rerun()
            if c_s.button("🗑️ Tüm Örnek Verileri Sil", key="s2"):
                ornek_sil_mod2(); st.success("Silindi!"); st.rerun()

        st.markdown("---")
        st.markdown("### 📂 Excel'den Toplu Veri Yükle (Detaylı Mod)")
        st.caption("""
        Beklenen kolonlar: **tarih, ev_takimi, dep_takimi, sonuc_HT, sonuc_FT,  
        ev_HT_1, ev_FT_1 ... ev_HT_5, ev_FT_5, dep_HT_1, dep_FT_1 ... dep_HT_5, dep_FT_5**
        """)
        excel_file2 = st.file_uploader("📄 Excel dosyası seçin (.xlsx)", type=["xlsx", "xls", "csv"], key="exc2")

        if excel_file2 is not None:
            try:
                if excel_file2.name.endswith(".csv"):
                    edf2 = pd.read_csv(excel_file2)
                else:
                    edf2 = pd.read_excel(excel_file2)

                edf2.columns = [c.strip().lower().replace(" ","_") for c in edf2.columns]

                gerekli = ["tarih", "ev_takimi", "dep_takimi"]
                eksik = [k for k in gerekli if k not in edf2.columns]
                if eksik:
                    st.error(f"❌ Eksik kolonlar: {', '.join(eksik)}")
                else:
                    st.success(f"✅ {len(edf2)} satır okundu. Önizleme:")
                    st.dataframe(edf2.head(10), use_container_width=True, hide_index=True)

                    if st.button(f"🚀 {len(edf2)} Kaydı Veritabanına Aktar", key="imp2", type="primary"):
                        basarili = 0
                        for _, row in edf2.iterrows():
                            ev_s = {f"{t}_{i}": str(row.get(f"ev_{t.lower()}_{i}", "") or "") for t in ["HT","FT"] for i in range(1,6)}
                            dep_s = {f"{t}_{i}": str(row.get(f"dep_{t.lower()}_{i}", "") or "") for t in ["HT","FT"] for i in range(1,6)}
                            kayit_ekle_mod2(
                                str(row.get("tarih", date.today())),
                                str(row.get("ev_takimi", "")),
                                str(row.get("dep_takimi", "")),
                                str(row.get("sonuc_ht", "") or ""),
                                str(row.get("sonuc_ft", "") or ""),
                                ev_s, dep_s
                            )
                            basarili += 1
                        st.success(f"🎉 {basarili} kayıt başarıyla yüklendi!")
                        st.balloons()
                        st.rerun()
            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")

    with t3:
        # Üst Panel (Yenile / Sil)
        b1, b2, b3 = st.columns([1, 2, 3])
        if b1.button("🔄 Tabloyu Yenile", key="y2", use_container_width=True): st.rerun()
        if b2.button("🗑️ SADECE Örnek Verileri Sil", type="primary", key="sd2", use_container_width=True):
            ornek_sil_mod2()
            st.success("Test amacıyla yüklenen (Detaylı Mod) tüm sahte önek kayıtlar başarıyla silindi!")
            st.rerun()
            
        df2 = liste_mod2()
        st.dataframe(df2.drop(columns=["olusturulma"], errors="ignore"), use_container_width=True, hide_index=True)
        
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("✏️ Maç Skoru Güncelle"):
                st.caption("Sonradan biten maçın skorunu buraya girebilirsiniz.")
                g_id = st.number_input("Güncellenecek ID", min_value=1, key="g_id2")
                g_ht = st.text_input("Yeni İY Sonucu", placeholder="0-0", key="g_ht2")
                g_ft = st.text_input("Yeni MS Sonucu", placeholder="1-0", key="g_ft2")
                if st.button("Güncelle", key="gb2"):
                    guncelle_skor_mod2(g_id, g_ht, g_ft)
                    st.success(f"#{g_id} güncellendi!"); st.rerun()

        with c2:
            with st.expander("🗑️ Spesifik Kayıt Sil (Detaylı Tablo)"):
                sid = st.number_input("Silinecek ID", min_value=1)
                if st.button("Kaydı Uçur", key="ds2"):
                    sil_mod2(sid); st.success(f"#{sid} silindi!"); st.rerun()

# ═════════════════════════════════════════════════════
# TAHMiN GEÇMİŞİ (BACKTEST) SEKMESİ — Her iki mod için ortak
# ═════════════════════════════════════════════════════

def render_backtest_tab(aktif_mod):
    """Her iki modun 4. sekmesinde (t4) çağrılır."""
    st.markdown("## 📈 Tahmin Geçmişi / Backtest")
    st.caption("Analiz Yap sekmesinde yapılan her tahmin burada saklanır. Maç bitince skoru güncelleyerek backtest yapabilirsiniz.")
    
    tdf = tahmin_listele()
    
    # Supabase tablosu henüz boşsa columns dönmez
    if tdf.empty or "mod" not in tdf.columns:
        st.info("ℹ️ Henüz tahmin geçmişi yok. 'Analiz Yap' sekmesinden bir analiz başlatın.")
        return
        
    # Aktif moda göre filtrele
    tdf = tdf[tdf["mod"] == aktif_mod].reset_index(drop=True)
    
    if tdf.empty:
        st.info("ℹ️ Henüz tahmin geçmişi yok. 'Analiz Yap' sekmesinden bir analiz başlatın.")
        return
    
    # Üst Bilgi
    m1, m2 = st.columns(2)
    m1.metric("Toplam Tahmin", len(tdf))
    sht_col = "sonuc_ht" if "sonuc_ht" in tdf.columns else "sonuc_HT"
    sonuclu = tdf[(tdf[sht_col].notna()) & (tdf[sht_col] != "") & (tdf[sht_col] != "?")]
    m2.metric("Sonuç Girilmiş", len(sonuclu))
    
    st.markdown("---")
    
    # Skor Güncelleme
    with st.expander("✏️ Tahmin Sonucu Güncelle (Maç Bittiğinde)"):
        st.caption("Aşağıdaki listeden tahmin ID'sini bulun ve biten maçın skorunu girin.")
        gc1, gc2, gc3 = st.columns([1,1,1])
        bt_id = gc1.number_input("Tahmin ID", min_value=1, key=f"bt_id_{aktif_mod}")
        bt_ht = gc2.text_input("İY Sonucu", placeholder="0-0", key=f"bt_ht_{aktif_mod}")
        bt_ft = gc3.text_input("MS Sonucu", placeholder="1-0", key=f"bt_ft_{aktif_mod}")
        bc1, bc2 = st.columns(2)
        if bc1.button("✅ Skoru Güncelle", key=f"bt_g_{aktif_mod}"):
            tahmin_skor_guncelle(bt_id, bt_ht, bt_ft)
            st.success(f"Tahmin #{bt_id} güncellendi!"); st.rerun()
        if bc2.button("🗑️ Tüm Tahmin Geçmişini Temizle", key=f"bt_sil_{aktif_mod}"):
            tahmin_tumunu_sil(); st.success("Tüm tahmin geçmişi temizlendi!"); st.rerun()
    
    st.markdown("---")
    
    # Her tahmin için expander ile detay göster
    for idx, row in tdf.iterrows():
        t_id = row["id"]
        ev = row["ev_takimi"]
        dep = row["dep_takimi"]
        tarih = row["tarih"]
        eslesen = row["eslesen_sayisi"]
        sht = row.get("sonuc_HT", row.get("sonuc_ht", "")) or ""
        sft = row.get("sonuc_FT", row.get("sonuc_ft", "")) or ""
        
        # Durum badge'i
        if sht and sft and sht != "?":
            durum = f"🎯 İY {sht} / MS {sft}"
            renk = "#2adf7a"
        else:
            durum = "⏳ Sonuç bekleniyor"
            renk = "#f0a500"
        
        header = f"**#{t_id}** | 🏠 {ev} vs {dep} ✈️ | {tarih} | Eşleşme: **{eslesen}** | <span style='color:{renk}'>{durum}</span>"
        
        with st.expander(f"📌 #{t_id} — {ev} vs {dep} ({tarih}) — {eslesen} eşleşme — {durum}"):
            # Üst bilgi kartı
            st.markdown(f"""
            <div class="match-card" style="border-left: 3px solid {renk};">
                <div style="font-size:18px; margin-bottom:6px;"><b>🏠 {ev}</b> vs <b>{dep} ✈️</b> — <span style="color:#888;">{tarih}</span></div>
                <div style="background-color: #212133; padding: 6px 12px; border-radius: 6px; border-left: 3px solid {renk};">
                    <span style="font-size: 15px; color:{renk}; font-weight:bold;">{durum}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Eşleşen maçların detayı
            try:
                raw_detay = row["eslesen_detay"]
                if isinstance(raw_detay, str):
                    detay_liste = json.loads(raw_detay) if raw_detay else []
                else:
                    detay_liste = raw_detay if raw_detay else []
            except:
                detay_liste = []
            
            if not detay_liste:
                st.info("Bu tahmin için eşleşen kayıt bulunamamıştı.")
            else:
                st.markdown(f"**{len(detay_liste)} eşleşen geçmiş maç:**")
                for d in detay_liste:
                    d_ev = d.get("ev","?"); d_dep = d.get("dep","?")
                    d_tarih = d.get("tarih","?")
                    d_sht = d.get("sht","?"); d_sft = d.get("sft","?")
                    d_tam = d.get("tam",0); d_kars = d.get("kars",0)
                    
                    # Badge'leri çiz (mod 1 veya mod 2)
                    if "detay" in d:
                        badge_html = ht_badge(d["detay"])
                    else:
                        ev_b = ht_badge(d.get("ev_detay",[])) if d.get("ev_detay") else ""
                        dep_b = ht_badge(d.get("dep_detay",[])) if d.get("dep_detay") else ""
                        badge_html = f"<div style='margin-bottom:3px'><b>Ev:</b> {ev_b}</div><div><b>Dep:</b> {dep_b}</div>"
                    
                    st.markdown(f"""
                    <div class="match-card">
                      <div style="display:flex; justify-content:space-between; margin-bottom: 6px;">
                        <div><b>🏠 {d_ev}</b> vs <b>{d_dep} ✈️</b> <span style="color:#888;font-size:12px">({d_tarih})</span></div>
                        <div>Eşleşme: <b style="color:#2adf7a">{d_tam}/{d_kars}</b></div>
                      </div>
                      <div style="background-color: #212133; padding: 5px 10px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #ffcc00;">
                          <span style="font-size: 14px;">🎯 <b>Sonuç:</b> <span style="color:#ffcc00; font-weight:bold;">İY {d_sht} / MS {d_sft}</span></span>
                      </div>
                      <div>{badge_html}</div>
                    </div>""", unsafe_allow_html=True)

# Sekme 4 renderı — her iki modda da
if "1️⃣" in secilen_mod:
    with t4:
        render_backtest_tab(1)
else:
    with t4:
        render_backtest_tab(2)
