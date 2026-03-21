import streamlit as st
import pandas as pd
import requests
import json
import random
import os
from datetime import date, datetime, timedelta
import sqlite3
import threading
import time


# Önbellek dizini oluştur
CACHE_DIR = ".cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ─────────────────────────────────────────────
#  GÖREV YÖNETİMİ (Arka Planda Devam Eden İşlemler)
# ─────────────────────────────────────────────
@st.cache_resource
def get_global_task_state():
    return {
        "running": False,
        "progress": 0.0,
        "msg": "",
        "logs": [],
        "stop_requested": False,
        "success_count": 0,
        "skipped_count": 0,
        "total_count": 0,
        "start_time": None
    }

GLOBAL_TASK_STATE = get_global_task_state()

def start_background_analysis(secilen_tarih, modes):
    if GLOBAL_TASK_STATE["running"]:
        return False
    
    # Reset state
    GLOBAL_TASK_STATE["running"] = True
    GLOBAL_TASK_STATE["progress"] = 0.0
    GLOBAL_TASK_STATE["msg"] = "Başlatılıyor..."
    GLOBAL_TASK_STATE["logs"] = []
    GLOBAL_TASK_STATE["stop_requested"] = False
    
    thread = threading.Thread(target=bulk_auto_process, args=(secilen_tarih, modes, True), daemon=True)
    thread.start()
    return True

def render_background_task_ui():
    if GLOBAL_TASK_STATE["running"]:
        with st.container():
            st.markdown(f"""
            <div style="background:#1e1e2e; border:1px solid #7b5ef555; border-radius:12px; padding:15px; margin-bottom:20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div style="color:#7b5ef5; font-weight:bold; font-size:16px;">⚙️ Arka Plan Analizi Devam Ediyor...</div>
                    <div style="background:#7b5ef522; color:#7b5ef5; padding:2px 10px; border-radius:10px; font-size:12px;">Aktif Görev</div>
                </div>
            """, unsafe_allow_html=True)
            
            p_val = GLOBAL_TASK_STATE["progress"]
            st.progress(p_val)
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**Durum:** {GLOBAL_TASK_STATE['msg']}")
                st.markdown(f"✅ Başarılı: `{GLOBAL_TASK_STATE['success_count']}` | ℹ️ Atlanan: `{GLOBAL_TASK_STATE['skipped_count']}` | 📂 Toplam: `{GLOBAL_TASK_STATE['total_count']}`")
            
            with col2:
                if st.button("🛑 Durdur", key="global_stop_btn", use_container_width=True):
                    GLOBAL_TASK_STATE["stop_requested"] = True
                    st.toast("Durdurma isteği gönderildi!")
            
            if GLOBAL_TASK_STATE["logs"]:
                with st.expander("Son İşlemler (Canlı Log)"):
                    st.markdown("<div style='font-size:11px; color:#aaa; font-family:monospace;'>" + "<br>".join(GLOBAL_TASK_STATE["logs"][-8:]) + "</div>", unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Polling mechanism for UI update
            time.sleep(1)
            st.rerun()
    elif GLOBAL_TASK_STATE["msg"] and "Tamamlandı" in GLOBAL_TASK_STATE["msg"]:
         with st.container():
            st.success(GLOBAL_TASK_STATE["msg"])
            if st.button("Bildirimi Kapat", key="clear_bg_msg"):
                GLOBAL_TASK_STATE["msg"] = ""
                st.rerun()




def load_cache(name):
    path = os.path.join(CACHE_DIR, f"{name}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    return None

def save_cache(name, data):
    path = os.path.join(CACHE_DIR, f"{name}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except:
        pass

def clear_local_cache(name=None):
    if name:
        path = os.path.join(CACHE_DIR, f"{name}.json")
        if os.path.exists(path):
            try: os.remove(path)
            except: pass
    else:
        if os.path.exists(CACHE_DIR):
            for f in os.listdir(CACHE_DIR):
                if f.endswith(".json"):
                    try: os.remove(os.path.join(CACHE_DIR, f))
                    except: pass

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

# ── Arka Plan Görev Durum Paneli (Her Sayfada Görünür) ──
render_background_task_ui()



# ─────────────────────────────────────────────
#  2. VERİTABANI KATMANI (SQLITE)
# ─────────────────────────────────────────────
DB_PATH = "data.db"
db_lock = threading.Lock()

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    # Tablo şemaları (Tüm kolonlar Mixed Case - UI ve Supabase uyumlu)
    schema_cols = """
        id INTEGER PRIMARY KEY, tarih TEXT, ev_takimi TEXT, dep_takimi TEXT, sonuc_HT TEXT, sonuc_FT TEXT, is_sample INTEGER,
        HT_1 TEXT, FT_1 TEXT, HT_2 TEXT, FT_2 TEXT, HT_3 TEXT, FT_3 TEXT, HT_4 TEXT, FT_4 TEXT, HT_5 TEXT, FT_5 TEXT,
        eHT_1 TEXT, eFT_1 TEXT, eHT_2 TEXT, eFT_2 TEXT, eHT_3 TEXT, eFT_3 TEXT, eHT_4 TEXT, eFT_4 TEXT, eHT_5 TEXT, eFT_5 TEXT,
        dHT_1 TEXT, dFT_1 TEXT, dHT_2 TEXT, dFT_2 TEXT, dHT_3 TEXT, dFT_3 TEXT, dHT_4 TEXT, dFT_4 TEXT, dHT_5 TEXT, dFT_5 TEXT,
        odd_1 TEXT, odd_x TEXT, odd_2 TEXT
    """
    conn.execute(f"CREATE TABLE IF NOT EXISTS mac_arsivi ({schema_cols})")
    conn.execute(f"CREATE TABLE IF NOT EXISTS mac_arsivi_detayli ({schema_cols})")
    conn.execute("""CREATE TABLE IF NOT EXISTS tahmin_gecmisi (id INTEGER PRIMARY KEY AUTOINCREMENT, tarih TEXT, ev_takimi TEXT, dep_takimi TEXT, mod INTEGER, girilen_skorlar TEXT, eslesen_idler TEXT, eslesen_detay TEXT, eslesen_sayisi INTEGER, sonuc_ht TEXT, sonuc_ft TEXT)""")
    
    # MİGRASYON: Eksik kolonları ekle (Local SQLite için)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(mac_arsivi)")
        cols = [c[1] for c in cursor.fetchall()]
        if "odd_1" not in cols:
            conn.execute("ALTER TABLE mac_arsivi ADD COLUMN odd_1 TEXT")
            conn.execute("ALTER TABLE mac_arsivi ADD COLUMN odd_x TEXT")
            conn.execute("ALTER TABLE mac_arsivi ADD COLUMN odd_2 TEXT")
            clear_local_cache() # Kolonlar eklenince eski cache geçersiz olur
        
        cursor.execute("PRAGMA table_info(mac_arsivi_detayli)")
        cols_d = [c[1] for c in cursor.fetchall()]
        if "odd_1" not in cols_d:
            conn.execute("ALTER TABLE mac_arsivi_detayli ADD COLUMN odd_1 TEXT")
            conn.execute("ALTER TABLE mac_arsivi_detayli ADD COLUMN odd_x TEXT")
            conn.execute("ALTER TABLE mac_arsivi_detayli ADD COLUMN odd_2 TEXT")
            clear_local_cache()
    except Exception as e:
        print(f"Migration Error: {e}")
    
    conn.commit()
    return conn

db_conn = init_db()

def execute_query(sql, params=(), fetch=True, commit=False):
    with db_lock:
        try:
            cur = db_conn.cursor()
            cur.execute(sql, params)
            if commit: db_conn.commit()
            if fetch: return cur.fetchall(), cur.description
            return cur.lastrowid
        except Exception as e:
            st.error(f"Veritabanı hatası: {e}")
            return None

def build_skor_dict(ev, dep):
    d = {}
    for i in range(1, 6):
        d[f"HT_{i}"] = ev.get(f"HT_{i}","") or ev.get(f"ht_{i}","") or ev.get(f"ev_ht_{i}","")
        d[f"FT_{i}"] = ev.get(f"FT_{i}","") or ev.get(f"ft_{i}","") or ev.get(f"ev_ft_{i}","")
        d[f"eHT_{i}"] = ev.get(f"HT_{i}","") or ev.get(f"ht_{i}","") or ev.get(f"ev_ht_{i}","")
        d[f"eFT_{i}"] = ev.get(f"FT_{i}","") or ev.get(f"ft_{i}","") or ev.get(f"ev_ft_{i}","")
        d[f"dHT_{i}"] = dep.get(f"HT_{i}","") or dep.get(f"ht_{i}","") or dep.get(f"dep_ht_{i}","")
        d[f"dFT_{i}"] = dep.get(f"FT_{i}","") or dep.get(f"ft_{i}","") or dep.get(f"dep_ft_{i}","")
    return d

def _clean(d):
    """Postgres unquoted columns are inherently lowercase. We lower all dict keys to match."""
    return {k.lower(): v for k, v in d.items()}

def build_skor_dict(ev_s, dep_s):
    d = {}
    for i in range(1, 6):
        # 1. Ortak Skorlar (Mod 1 için fallbackler)
        d[f"HT_{i}"] = ev_s.get(f"HT_{i}","") or ev_s.get(f"ht_{i}","")
        d[f"FT_{i}"] = ev_s.get(f"FT_{i}","") or ev_s.get(f"ft_{i}","")
        # 2. Ev Sahibi ve Deplasman (Kısa İsimler - eHT_1, dHT_1)
        d[f"eHT_{i}"] = ev_s.get(f"HT_{i}","") or ev_s.get(f"ht_{i}","")
        d[f"eFT_{i}"] = ev_s.get(f"FT_{i}","") or ev_s.get(f"ft_{i}","")
        d[f"dHT_{i}"] = dep_s.get(f"HT_{i}","") or dep_s.get(f"ht_{i}","")
        d[f"dFT_{i}"] = dep_s.get(f"FT_{i}","") or dep_s.get(f"ft_{i}","")
    return d

# DB İşlemleri - Ortak (Mod 1)
def kayit_ekle_mod1(tarih, ev, dep, sonuc_ht, sonuc_ft, ev_skorlar, dep_skorlar, is_sample=0, clear_cache=True, o1=None, ox=None, o2=None):
    d = build_skor_dict(ev_skorlar, dep_skorlar)
    cols = ["tarih","ev_takimi","dep_takimi","sonuc_HT","sonuc_FT","is_sample","odd_1","odd_x","odd_2"] + list(d.keys())
    vals = [str(tarih), ev.strip(), dep.strip(), sonuc_ht or "", sonuc_ft or "", is_sample, str(o1 or ""), str(ox or ""), str(o2 or "")] + list(d.values())
    sql = f"INSERT INTO mac_arsivi ({','.join(cols)}) VALUES ({','.join(['?']*len(vals))})"
    execute_query(sql, vals, fetch=False, commit=True)
    if clear_cache: clear_cache_mod1()

@st.cache_data(ttl=1800)
def liste_mod1():
    cached = load_cache("mod1")
    if cached: 
        df = pd.DataFrame(cached)
        for c in ["odd_1", "odd_x", "odd_2"]:
            if c not in df.columns: df[c] = ""
        return df
    with db_lock:
        df = pd.read_sql("SELECT * FROM mac_arsivi ORDER BY id DESC", db_conn)
    
    # Veritabanında (data.db) HT/FT/eHT/dHT kolonları zaten dolu
    if not df.empty: 
        for c in ["odd_1", "odd_x", "odd_2"]:
            if c not in df.columns: df[c] = ""
        save_cache("mod1", df.to_dict('records'))
    return df

def clear_cache_mod1():
    liste_mod1.clear()
    clear_local_cache("mod1")
    db_ist_mod.clear()

def sil_mod1(k_id): 
    execute_query("DELETE FROM mac_arsivi WHERE id = ?", (k_id,), commit=True)
    clear_cache_mod1()

def ornek_sil_mod1(): 
    execute_query("DELETE FROM mac_arsivi WHERE is_sample = 1", commit=True)
    clear_cache_mod1()

def tumunu_sil_mod1():
    execute_query("DELETE FROM mac_arsivi", commit=True)
    clear_cache_mod1()

def tarih_sil_mod1(tarih_str):
    execute_query("DELETE FROM mac_arsivi WHERE tarih = ?", (str(tarih_str),), commit=True)
    clear_cache_mod1()

def guncelle_skor_mod1(k_id, sht, sft, clear_cache=True):
    rows, _ = execute_query("SELECT tarih, ev_takimi, dep_takimi FROM mac_arsivi WHERE id = ?", (k_id,))
    if rows:
        mac = rows[0]
        try:
            execute_query("UPDATE tahmin_gecmisi SET sonuc_ht = ?, sonuc_ft = ? WHERE mod = 1 AND tarih = ? AND ev_takimi = ? AND dep_takimi = ?",
                          (sht, sft, mac[0], mac[1], mac[2]), fetch=False, commit=True)
        except Exception:
            pass
            
    execute_query("UPDATE mac_arsivi SET sonuc_HT = ?, sonuc_FT = ? WHERE id = ?", (sht, sft, k_id), fetch=False, commit=True)
    if clear_cache:
        clear_cache_mod1()
        clear_cache_tahmin()

# DB İşlemleri - Detaylı (Mod 2)
def kayit_ekle_mod2(tarih, ev, dep, sonuc_ht, sonuc_ft, ev_skorlar, dep_skorlar, is_sample=0, clear_cache=True, o1=None, ox=None, o2=None):
    d = build_skor_dict(ev_skorlar, dep_skorlar)
    cols = ["tarih","ev_takimi","dep_takimi","sonuc_HT","sonuc_FT","is_sample","odd_1","odd_x","odd_2"] + list(d.keys())
    vals = [str(tarih), ev.strip(), dep.strip(), sonuc_ht or "", sonuc_ft or "", is_sample, str(o1 or ""), str(ox or ""), str(o2 or "")] + list(d.values())
    sql = f"INSERT INTO mac_arsivi_detayli ({','.join(cols)}) VALUES ({','.join(['?']*len(vals))})"
    execute_query(sql, vals, fetch=False, commit=True)
    if clear_cache: clear_cache_mod2()

@st.cache_data(ttl=1800)
def liste_mod2():
    cached = load_cache("mod2")
    if cached: 
        df = pd.DataFrame(cached)
        for c in ["odd_1", "odd_x", "odd_2"]:
            if c not in df.columns: df[c] = ""
        return df
    with db_lock:
        df = pd.read_sql("SELECT * FROM mac_arsivi_detayli ORDER BY id DESC", db_conn)
        
    # UI'daki Başlıklarla Harf Uyumu İçin Dönüşüm
    rename_map = {}
    for c in df.columns:
        if "ev_ht_" in c: rename_map[c] = c.replace("ev_ht_","eHT_")
        elif "ev_ft_" in c: rename_map[c] = c.replace("ev_ft_","eFT_")
        elif "dep_ht_" in c: rename_map[c] = c.replace("dep_ht_","dHT_")
        elif "dep_ft_" in c: rename_map[c] = c.replace("dep_ft_","dFT_")
        elif c.startswith("ht_"): rename_map[c] = c.replace("ht_","HT_")
        elif c.startswith("ft_"): rename_map[c] = c.replace("ft_","FT_")
        elif c == "sonuc_ht": rename_map[c] = "sonuc_HT"
        elif c == "sonuc_ft": rename_map[c] = "sonuc_FT"
    df = df.rename(columns=rename_map)
    
    for c in ["odd_1", "odd_x", "odd_2"]:
        if c not in df.columns: df[c] = ""
        
    if not df.empty: save_cache("mod2", df.to_dict('records'))
    return df

def clear_cache_mod2():
    liste_mod2.clear()
    clear_local_cache("mod2")
    db_ist_mod.clear()

def sil_mod2(k_id): 
    execute_query("DELETE FROM mac_arsivi_detayli WHERE id = ?", (k_id,), commit=True)
    clear_cache_mod2()

def ornek_sil_mod2(): 
    execute_query("DELETE FROM mac_arsivi_detayli WHERE is_sample = 1", commit=True)
    clear_cache_mod2()

def tumunu_sil_mod2():
    execute_query("DELETE FROM mac_arsivi_detayli", commit=True)
    clear_cache_mod2()

def tarih_sil_mod2(tarih_str):
    execute_query("DELETE FROM mac_arsivi_detayli WHERE tarih = ?", (str(tarih_str),), commit=True)
    clear_cache_mod2()

def guncelle_skor_mod2(k_id, sht, sft, clear_cache=True):
    rows, _ = execute_query("SELECT tarih, ev_takimi, dep_takimi FROM mac_arsivi_detayli WHERE id = ?", (k_id,))
    if rows:
        mac = rows[0]
        try:
            execute_query("UPDATE tahmin_gecmisi SET sonuc_ht = ?, sonuc_ft = ? WHERE mod = 2 AND tarih = ? AND ev_takimi = ? AND dep_takimi = ?",
                          (sht, sft, mac[0], mac[1], mac[2]), fetch=False, commit=True)
        except Exception as e:
            st.warning(f"Tahmin geçmişi güncellenirken hata oluştu: {e}")

    execute_query("UPDATE mac_arsivi_detayli SET sonuc_HT = ?, sonuc_FT = ? WHERE id = ?",
                  (sht, sft, k_id), fetch=False, commit=True)
    if clear_cache:
        clear_cache_mod2()
        clear_cache_tahmin()

# Tahmin Geçmişi (Backtest) DB İşlemleri
def tahmin_kaydet(tarih, ev, dep, mod, girilen_skorlar, eslesen_idler, eslesen_detay, eslesen_sayisi, clear_cache=True):
    sql = """INSERT INTO tahmin_gecmisi
             (tarih, ev_takimi, dep_takimi, mod, girilen_skorlar, eslesen_idler, eslesen_detay, eslesen_sayisi)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
    vals = (str(tarih), ev.strip(), dep.strip(), mod, json.dumps(girilen_skorlar), json.dumps(eslesen_idler), json.dumps(eslesen_detay), eslesen_sayisi)
    execute_query(sql, vals, fetch=False, commit=True)
    if clear_cache: clear_cache_tahmin()

@st.cache_data(ttl=60)
def tahmin_listele():
    # 'eslesen_detay' kolonu filtreleme (max_yesil) için gereklidir.
    cols = "id,tarih,ev_takimi,dep_takimi,mod,eslesen_sayisi,sonuc_ht,sonuc_ft,eslesen_detay"
    with db_lock:
        df = pd.read_sql(f"SELECT {cols} FROM tahmin_gecmisi ORDER BY id DESC", db_conn)
    return df

@st.cache_data(ttl=300)
def tahmin_detay_cek(tahmin_id):
    rows, _ = execute_query("SELECT id,eslesen_detay,girilen_skorlar,eslesen_idler,sonuc_ht,sonuc_ft FROM tahmin_gecmisi WHERE id = ?", (tahmin_id,))
    if rows:
        r = rows[0]
        return {
            "id": r[0],
            "eslesen_detay": json.loads(r[1]) if r[1] else [],
            "girilen_skorlar": json.loads(r[2]) if r[2] else {},
            "eslesen_idler": json.loads(r[3]) if r[3] else [],
            "sonuc_ht": r[4] or "",
            "sonuc_ft": r[5] or ""
        }
    return {}

def clear_cache_tahmin():
    tahmin_listele.clear()
    tahmin_detay_cek.clear()
    clear_local_cache("tahminler")

def tahmin_tumunu_sil():
    execute_query("DELETE FROM tahmin_gecmisi", commit=True)
    clear_cache_tahmin()
    st.success("Tüm tahmin geçmişi silindi.")

def tahmin_ozel_sil(list_ids):
    if not list_ids: return
    execute_query(f"DELETE FROM tahmin_gecmisi WHERE id IN ({','.join(['?']*len(list_ids))})", list_ids, commit=True)
    clear_cache_tahmin()

def tahmin_skor_guncelle(tahmin_id, ht, ft):
    try:
        execute_query("UPDATE tahmin_gecmisi SET sonuc_ht = ?, sonuc_ft = ? WHERE id = ?", (ht, ft, int(tahmin_id)), commit=True)
        clear_cache_tahmin()
    except Exception as e:
        st.error(f"Skor güncellenirken hata: {e}")

@st.cache_data(ttl=600)
def db_ist_mod(tbl):
    try:
        rows, _ = execute_query(f"SELECT COUNT(*), MAX(tarih), MIN(tarih) FROM {tbl}")
        if rows:
            t, yn, es = rows[0]
            return {"toplam": t or 0, "yeni": yn or "-", "eski": es or "-"}
    except Exception:
        pass
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
#  API FOOTBALL ENTEGRASYONU
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_team_id(team_name):
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return None
    headers = {'x-apisports-key': api_key}
    try:
        res = requests.get(f'https://v3.football.api-sports.io/teams?search={team_name}', headers=headers, timeout=10).json()
        if res.get('response'):
            return res['response'][0]['team']['id']
    except:
        pass
    return None

def fetch_last_5_matches(team_id):
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return []
    headers = {'x-apisports-key': api_key}
    matches = []
    try:
        res = requests.get(f'https://v3.football.api-sports.io/fixtures?team={team_id}&last=10', headers=headers, timeout=10).json()
        if res.get('response'):
            for f in res['response']:
                status = str(f['fixture']['status']['short'])
                if status in ['FT', 'AET', 'PEN']:
                    ht = f['score']['halftime']
                    ft = f['score']['fulltime']
                    ht_str = f"{ht.get('home','')}-{ht.get('away','')}" if ht.get('home') is not None else ""
                    ft_str = f"{ft.get('home','')}-{ft.get('away','')}" if ft.get('home') is not None else ""
                    if ht_str and ft_str:
                        matches.append({"ht": ht_str, "ft": ft_str})
                if len(matches) == 5:
                    break
    except:
        pass
    return matches

@st.cache_data(ttl=3600)
def fetch_daily_fixtures(date_str):
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return []
    headers = {'x-apisports-key': api_key}
    try:
        res = requests.get(f'https://v3.football.api-sports.io/fixtures?date={date_str}', headers=headers, timeout=15).json()
        if res.get('response'):
            return res['response']
    except:
        pass
    return []

def get_fixture_options(fixtures, odds_dict=None):
    opts = {}
    for f in fixtures:
        f_id = f['fixture']['id']
        home = f['teams']['home']['name']
        away = f['teams']['away']['name']
        home_id = f['teams']['home']['id']
        away_id = f['teams']['away']['id']
        league = f['league']['name']
        time = f['fixture']['date'][11:16]
        
        o_str = ""
        if odds_dict and f_id in odds_dict:
            o = odds_dict[f_id]
            o_str = f" | Odds: {o['1']} - {o['x']} - {o['2']}"
            
        label = f"{time} | {home} vs {away} ({league}){o_str}"
        opts[label] = {
            "id": f_id,
            "home": home, "away": away, 
            "home_id": home_id, "away_id": away_id,
            "odds": odds_dict.get(f_id) if odds_dict else None
        }
    return opts

@st.cache_data(ttl=21600)
def fetch_daily_odds(date_str):
    """Oranları çeker. Bet365 önceliklidir, yoksa diğer büyük bürolara bakar."""
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return {}
    headers = {'x-apisports-key': api_key}
    odds_map = {}
    
    # Yaygın bookmakerlar: 8: Bet365, 6: Bwin, 11: William Hill, 1: 10Bet
    # Önce Bet365 deniyoruz (hızlı filtre ile)
    def parse_response(res, current_map):
        if res.get('response'):
            for item in res['response']:
                f_id = item['fixture']['id']
                if f_id in current_map: continue
                
                for bm in item['bookmakers']:
                    for b in bm['bets']:
                        if b['id'] == 1: # Match Winner
                            h=x=a=None
                            for v in b['values']:
                                if v['value'] == 'Home': h = v['odd']
                                elif v['value'] == 'Draw': x = v['odd']
                                elif v['value'] == 'Away': a = v['odd']
                            if h and x and a:
                                current_map[f_id] = {"1": h, "x": x, "2": a}
                                break
        return current_map

    try:
        # 1. Deneme: Bet365 (8)
        res8 = requests.get(f'https://v3.football.api-sports.io/odds?date={date_str}&bookmaker=8&bet=1', headers=headers, timeout=12).json()
        odds_map = parse_response(res8, odds_map)
        
        # 2. Deneme: Bwin (6)
        res6 = requests.get(f'https://v3.football.api-sports.io/odds?date={date_str}&bookmaker=6&bet=1', headers=headers, timeout=12).json()
        odds_map = parse_response(res6, odds_map)

        # 3. Deneme: 10Bet (1)
        res1 = requests.get(f'https://v3.football.api-sports.io/odds?date={date_str}&bookmaker=1&bet=1', headers=headers, timeout=12).json()
        odds_map = parse_response(res1, odds_map)

        # 4. Deneme: William Hill (11)
        res11 = requests.get(f'https://v3.football.api-sports.io/odds?date={date_str}&bookmaker=11&bet=1', headers=headers, timeout=12).json()
        odds_map = parse_response(res11, odds_map)
        
    except: pass
    return odds_map

def eslesme_hesapla_oran(o1, ox, o2, kayit, tolerans=0.05):
    """Oran bazlı eşleşme hesaplar."""
    try:
        db_o1 = float(kayit.get("odd_1", 0) or 0)
        db_ox = float(kayit.get("odd_x", 0) or 0)
        db_o2 = float(kayit.get("odd_2", 0) or 0)
        if not (db_o1 and db_ox and db_o2) or not (o1 and ox and o2): return {"tam": 0, "oran": 0}
        d1 = abs(float(o1)-db_o1)/float(o1); dx = abs(float(ox)-db_ox)/float(ox); d2 = abs(float(o2)-db_o2)/float(o2)
        tam = 0
        if d1 <= tolerans: tam += 1
        if dx <= tolerans: tam += 1
        if d2 <= tolerans: tam += 1
        return {"tam": tam, "oran": (tam/3)*100}
    except: return {"tam": 0, "oran": 0}

@st.cache_data(ttl=21600) # 6 saat önbellek
def fetch_h2h_matches(team_id_1, team_id_2, wanted_home_id, before_date=None):
    """İki takım arasındaki maçları çeker."""
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return []
    headers = {'x-apisports-key': api_key}
    matches = []
    try:
        h2h_param = f"{team_id_1}-{team_id_2}"
        res = requests.get(f'https://v3.football.api-sports.io/fixtures/headtohead?h2h={h2h_param}', headers=headers, timeout=12).json()
        if res.get('response'):
            # Tarihe göre azalan sırala
            fixtures = sorted(res['response'], key=lambda x: x['fixture']['timestamp'], reverse=True)
            for f in fixtures:
                f_date = str(f['fixture']['date'][:10])
                if before_date and f_date >= str(before_date):
                    continue
                
                status = str(f['fixture']['status']['short'])
                f_home_id = f['teams']['home']['id']
                
                if status in ['FT', 'AET', 'PEN'] and str(f_home_id) == str(wanted_home_id):
                    ht = f['score']['halftime']
                    ft = f['score']['fulltime']
                    ht_s = f"{ht.get('home','')}-{ht.get('away','')}" if ht.get('home') is not None else ""
                    ft_s = f"{ft.get('home','')}-{ft.get('away','')}" if ft.get('home') is not None else ""
                    if ht_s and ft_s:
                        matches.append({"ht": ht_s, "ft": ft_s})
                if len(matches) >= 5: break
    except Exception as e:
        print(f"H2H Error: {e}")
    return matches

@st.cache_data(ttl=21600) # 6 saat önbellek
def fetch_last_5_matches_by_venue(team_id, venue="home", before_date=None):
    """Takımın iç saha veya dış saha son 5 maçını çeker."""
    api_key = st.secrets.get("API_FOOTBALL_KEY")
    if not api_key: return []
    headers = {'x-apisports-key': api_key}
    matches = []
    try:
        res = requests.get(f'https://v3.football.api-sports.io/fixtures?team={team_id}&last=40', headers=headers, timeout=12).json()
        if res.get('response'):
            fixtures = sorted(res['response'], key=lambda x: x['fixture']['timestamp'], reverse=True)
            for f in fixtures:
                f_date = str(f['fixture']['date'][:10])
                if before_date and f_date >= str(before_date):
                    continue
                
                status = str(f['fixture']['status']['short'])
                f_home_id = str(f['teams']['home']['id'])
                f_away_id = str(f['teams']['away']['id'])
                
                is_home = (f_home_id == str(team_id))
                is_away = (f_away_id == str(team_id))
                
                if status in ['FT', 'AET', 'PEN']:
                    if (venue == "home" and is_home) or (venue == "away" and is_away):
                        ht = f['score']['halftime']
                        ft = f['score']['fulltime']
                        ht_s = f"{ht.get('home','')}-{ht.get('away','')}" if ht.get('home') is not None else ""
                        ft_s = f"{ft.get('home','')}-{ft.get('away','')}" if ft.get('home') is not None else ""
                        if ht_s and ft_s:
                            matches.append({"ht": ht_s, "ft": ft_s})
                if len(matches) >= 5: break
    except Exception as e:
        print(f"Venue Match Error: {e}")
    return matches

def otomatize_skor_guncelle(mode_input):
    from datetime import datetime as dt_module, timezone
    modes = mode_input if isinstance(mode_input, list) else [mode_input]
    
    total_guncellenen = 0
    for tablo_idx in modes:
        df = liste_mod1() if tablo_idx == 1 else liste_mod2()
        if df.empty: continue
        
        ht_col = "sonuc_ht" if "sonuc_ht" in df.columns else "sonuc_HT"
        ft_col = "sonuc_ft" if "sonuc_ft" in df.columns else "sonuc_FT"
        
        eksikler = df[(df[ht_col].isna()) | (df[ht_col] == "") | (df[ht_col] == "?") | 
                      (df[ft_col].isna()) | (df[ft_col] == "") | (df[ft_col] == "?")]
                      
        if eksikler.empty: continue
        
        tarihler = eksikler["tarih"].unique()
        for t in tarihler:
            gunluk_veri = fetch_daily_fixtures(str(t))
            if not gunluk_veri: continue
            
            gun_eksikleri = eksikler[eksikler["tarih"] == t]
            for _, row in gun_eksikleri.iterrows():
                ev = str(row["ev_takimi"]).lower().strip()
                dep = str(row["dep_takimi"]).lower().strip()
                row_id = int(row["id"])
                
                for f in gunluk_veri:
                    api_ev = str(f['teams']['home']['name']).lower()
                    api_dep = str(f['teams']['away']['name']).lower()
                    
                    if (ev in api_ev or api_ev in ev) and (dep in api_dep or api_dep in dep):
                        status = f['fixture']['status']['short']
                        dt_mac = dt_module.fromisoformat(f['fixture']['date'].replace('Z', '+00:00'))
                        fark_saat = (dt_module.now(timezone.utc) - dt_mac).total_seconds() / 3600
                        
                        if status in ['FT', 'AET', 'PEN'] or fark_saat >= 3:
                            skor = f['score']
                            ht_h, ht_a = skor['halftime'].get('home'), skor['halftime'].get('away')
                            ft_h, ft_a = skor['fulltime'].get('home'), skor['fulltime'].get('away')
                            if ht_h is not None and ft_h is not None:
                                yeni_ht = f"{int(ht_h)}-{int(ht_a)}"
                                yeni_ft = f"{int(ft_h)}-{int(ft_a)}"
                                # Hız için cache temizliğini toplu işlem sonuna bırakıyoruz
                                if tablo_idx == 1: guncelle_skor_mod1(row_id, yeni_ht, yeni_ft, clear_cache=False)
                                else: guncelle_skor_mod2(row_id, yeni_ht, yeni_ft, clear_cache=False)
                                total_guncellenen += 1
                        break
        # İşlem tablosuna göre cache temizle
        if tablo_idx == 1: clear_cache_mod1()
        else: clear_cache_mod2()
    
    clear_cache_tahmin()
    return total_guncellenen

def otomatize_oran_guncelle(mode_input):
    """Veritabanındaki oranı eksik olan maçların oranlarını API'den çeker."""
    modes = mode_input if isinstance(mode_input, list) else [mode_input]
    total_guncellenen = 0
    
    for tablo_idx in modes:
        df = liste_mod1() if tablo_idx == 1 else liste_mod2()
        if df.empty: continue
        
        # odd_1 kolonu yoksa veya boşsa eksik sayıyoruz
        if "odd_1" not in df.columns:
            eksikler = df
        else:
            eksikler = df[(df["odd_1"].isna()) | (df["odd_1"] == "")]
            
        if eksikler.empty: continue
        
        tarihler = eksikler["tarih"].unique()
        for t in tarihler:
            t_str = str(t)
            gunluk_oranlar = fetch_daily_odds(t_str)
            if not gunluk_oranlar: continue
            
            gunluk_fixtures = fetch_daily_fixtures(t_str)
            if not gunluk_fixtures: continue
            
            gun_eksikleri = eksikler[eksikler["tarih"] == t]
            for _, row in gun_eksikleri.iterrows():
                ev = str(row["ev_takimi"]).lower().strip()
                dep = str(row["dep_takimi"]).lower().strip()
                row_id = int(row["id"])
                
                # Takım eşleştirmesi yaparak fixture_id bulalım
                for f in gunluk_fixtures:
                    api_ev = str(f['teams']['home']['name']).lower()
                    api_dep = str(f['teams']['away']['name']).lower()
                    
                    if (ev in api_ev or api_ev in ev) and (dep in api_dep or api_dep in dep):
                        f_id = f['fixture']['id']
                        o = gunluk_oranlar.get(f_id)
                        if o:
                            o1, ox, o2 = o.get('1'), o.get('x'), o.get('2')
                            if o1:
                                sql = f"UPDATE {'mac_arsivi' if tablo_idx == 1 else 'mac_arsivi_detayli'} SET odd_1=?, odd_x=?, odd_2=? WHERE id=?"
                                execute_query(sql, (str(o1), str(ox), str(o2), row_id), fetch=False, commit=True)
                                total_guncellenen += 1
                        break
        
        if tablo_idx == 1: clear_cache_mod1()
        else: clear_cache_mod2()
        
    return total_guncellenen

def bulk_auto_process(secilen_tarih, mode_input, is_background=False):
    modes = mode_input if isinstance(mode_input, list) else [mode_input]
    date_str = secilen_tarih.strftime("%Y-%m-%d")
    gunun_maclari = fetch_daily_fixtures(date_str)
    gunun_oranlar = fetch_daily_odds(date_str)
    
    if not gunun_maclari:
        if not is_background:
            st.warning(f"{secilen_tarih} tarihinde maç bulunamadı.")
        return
    
    # Saate göre sırala
    try:
        gunun_maclari = sorted(gunun_maclari, key=lambda x: x['fixture']['timestamp'])
    except:
        pass
        
    toplam_mac = len(gunun_maclari)
    start_msg = f"📅 {secilen_tarih} tarihindeki {toplam_mac} maç saat sırasına göre taranıyor..."
    
    if not is_background:
        st.info(start_msg)
        progress_bar = st.progress(0)
        status_text_area = st.empty()
        log_text_area = st.empty()
    else:
        GLOBAL_TASK_STATE["running"] = True
        GLOBAL_TASK_STATE["progress"] = 0.0
        GLOBAL_TASK_STATE["msg"] = start_msg
        GLOBAL_TASK_STATE["logs"] = []
        GLOBAL_TASK_STATE["stop_requested"] = False
        GLOBAL_TASK_STATE["total_count"] = toplam_mac
        GLOBAL_TASK_STATE["success_count"] = 0
        GLOBAL_TASK_STATE["skipped_count"] = 0
        GLOBAL_TASK_STATE["start_time"] = datetime.now()
    
    basarili = 0
    atlanilan = 0
    logs = []
    
    import time
    df_db_1 = liste_mod1() if 1 in modes else pd.DataFrame()
    df_db_2 = liste_mod2() if 2 in modes else pd.DataFrame()
    
    # İterasyon hızlandırma: DataFrame'leri bir kez listeye çevir
    recs_1 = df_db_1.to_dict('records') if not df_db_1.empty else []
    recs_2 = df_db_2.to_dict('records') if not df_db_2.empty else []

    try:
        for i, f in enumerate(gunun_maclari):
            # Durdurma isteği kontrolü
            if GLOBAL_TASK_STATE["stop_requested"]:
                msg = "🛑 İşlem kullanıcı tarafından durduruldu."
                if not is_background: st.warning(msg)
                else: 
                    GLOBAL_TASK_STATE["logs"].append(msg)
                    GLOBAL_TASK_STATE["msg"] = msg
                break

            time_str = f['fixture']['date'][11:16]
            hid = f['teams']['home']['id']; aid = f['teams']['away']['id']
            ev_ad = f['teams']['home']['name']; dep_ad = f['teams']['away']['name']
            
            cur_status = f"**İşleniyor ({i+1}/{toplam_mac}):** 🕒 {time_str} | {ev_ad} vs {dep_ad}"
            if not is_background:
                status_text_area.markdown(cur_status)
            else:
                GLOBAL_TASK_STATE["msg"] = cur_status
                GLOBAL_TASK_STATE["progress"] = (i + 1) / toplam_mac
            
            for m_idx in modes:
                try:
                    # Maç oranlarını al
                    o = gunun_oranlar.get(f['fixture']['id'], {})
                    o1, ox, o2 = o.get('1'), o.get('x'), o.get('2')
                    
                    if m_idx == 1:
                        matches_ev = fetch_h2h_matches(hid, aid, wanted_home_id=hid, before_date=str(secilen_tarih))
                        matches_dep = fetch_h2h_matches(hid, aid, wanted_home_id=aid, before_date=str(secilen_tarih))
                        db_recs = recs_1
                    else:
                        matches_ev = fetch_last_5_matches_by_venue(hid, "home", before_date=str(secilen_tarih))
                        matches_dep = fetch_last_5_matches_by_venue(aid, "away", before_date=str(secilen_tarih))
                        db_recs = recs_2
                    
                    if len(matches_ev) == 5 and len(matches_dep) == 5:
                        e_gir = {f"HT_{j+1}": matches_ev[j]["ht"] for j in range(5)}
                        for j in range(5): e_gir[f"FT_{j+1}"] = matches_ev[j]["ft"]
                        d_gir = {f"HT_{j+1}": matches_dep[j]["ht"] for j in range(5)}
                        for j in range(5): d_gir[f"FT_{j+1}"] = matches_dep[j]["ft"]
                        
                        if all(e_gir.values()) and all(d_gir.values()):
                            if m_idx == 1:
                                kayit_ekle_mod1(secilen_tarih, ev_ad, dep_ad, "", "", e_gir, d_gir, clear_cache=False, o1=o1, ox=ox, o2=o2)
                            else:
                                kayit_ekle_mod2(secilen_tarih, ev_ad, dep_ad, "", "", e_gir, d_gir, clear_cache=False, o1=o1, ox=ox, o2=o2)
                                
                            eslesme_id_list = []
                            eslesme_detay_list = []
                            
                            # HIZLI TARAMA (Dictionary listesi üzerinden)
                            for r in db_recs:
                                res = eslesme_hesapla_mod1(e_gir, d_gir, r) if m_idx == 1 else eslesme_hesapla_mod2(e_gir, d_gir, r)
                                if res["tam"] >= 1: 
                                    eslesme_id_list.append(int(r["id"]))
                                    eslesme_detay_list.append({
                                        "id": int(r["id"]), "tarih": r["tarih"], "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                                        "sht": r.get("sonuc_HT", r.get("sonuc_ht", "?")) or "?",
                                        "sft": r.get("sonuc_FT", r.get("sonuc_ft", "?")) or "?",
                                        "tam": res["tam"], "kars": res["kars"],
                                        "oran": res["oran"], "ev_detay": res["ev_detay"], "dep_detay": res["dep_detay"]
                                    })
                            
                            birlesik_skor = {"ev": e_gir, "dep": d_gir}
                            tahmin_kaydet(secilen_tarih, ev_ad, dep_ad, m_idx, birlesik_skor, eslesme_id_list, eslesme_detay_list, len(eslesme_id_list), clear_cache=False)
                            
                            basarili += 1
                            log_msg = f"✅ [MOD {m_idx}] 🕒 {time_str} | **{ev_ad} vs {dep_ad}** ({len(eslesme_id_list)} eşleşme)"
                            logs.append(log_msg)
                            if is_background: GLOBAL_TASK_STATE["logs"].append(log_msg)
                        else:
                            atlanilan += 1
                            log_msg = f"❌ [MOD {m_idx}] 🕒 {time_str} | {ev_ad} vs {dep_ad} (Eksik skor)"
                            logs.append(log_msg)
                            if is_background: GLOBAL_TASK_STATE["logs"].append(log_msg)
                    else:
                        atlanilan += 1
                        log_msg = f"ℹ️ [MOD {m_idx}] 🕒 {time_str} | {ev_ad} vs {dep_ad} (<5 maç bulundu)"
                        logs.append(log_msg)
                        if is_background: GLOBAL_TASK_STATE["logs"].append(log_msg)
                except Exception as e:
                    atlanilan += 1
                    log_msg = f"⚠️ [MOD {m_idx}] 🕒 {time_str} | {ev_ad} vs {dep_ad} (Hata: {str(e)})"
                    logs.append(log_msg)
                    if is_background: GLOBAL_TASK_STATE["logs"].append(log_msg)
                
                if not is_background:
                    log_text_area.markdown("<br>".join(logs[-10:]), unsafe_allow_html=True)
                else:
                    GLOBAL_TASK_STATE["success_count"] = basarili
                    GLOBAL_TASK_STATE["skipped_count"] = atlanilan
                time.sleep(0.01)
            
            if not is_background:
                progress_bar.progress((i + 1) / toplam_mac)
            else:
                GLOBAL_TASK_STATE["progress"] = (i + 1) / toplam_mac

    finally:
        # SÜREÇ SONUNDA TEK SEFERLİK CACHE TEMİZLEME
        if 1 in modes: clear_cache_mod1()
        if 2 in modes: clear_cache_mod2()
        clear_cache_tahmin()
        
        final_msg = f"🚀 **İşlem Tamamlandı!** {basarili} maç başarıyla sisteme eklendi ve analiz edildi. {atlanilan} maç atlandı."
        if not is_background:
            status_text_area.markdown(final_msg)
            st.balloons()
        else:
            GLOBAL_TASK_STATE["msg"] = final_msg
            GLOBAL_TASK_STATE["running"] = False


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
        ht_db = p.get("ht_db") or "?"
        ft_db = p.get("ft_db") or "?"
        ht_in = p.get("ht_in") or "?"
        ft_in = p.get("ft_in") or "?"
        
        # Daha detaylı bilgi tooltipsiz (Görsel Karşılaştırma)
        score_info = f"{ht_db}/{ft_db}"
        if ht_in != "?" or ft_in != "?":
            # Hedef skorla beraber göster (Eğer farklıysa belirt)
            match_marker = "✓" if dur == "tam" else ("~" if dur == "kismi" else "✗")
            lbl = f"M{poz}: {score_info}"
        else:
            lbl = f"M{poz}: {score_info}"

        if dur == "tam": 
            parcalar.append(f'<span class="badge-green" title="Hedef: {ht_in}/{ft_in} • Arşiv: {ht_db}/{ft_db}">✓ {lbl}</span>')
        elif dur == "kismi": 
            parcalar.append(f'<span class="badge-partial" title="Hedef: {ht_in}/{ft_in} • Arşiv: {ht_db}/{ft_db}">~ {lbl}</span>')
        elif dur == "yok": 
            parcalar.append(f'<span class="badge-neutral" title="Hedef: {ht_in}/{ft_in} • Arşiv: {ht_db}/{ft_db}">✗ M{poz}</span>')
    return " ".join(parcalar)

def fmt_in(val):
    v = str(val).strip().lower()
    if v in ("","?","-"): return ""
    if len(v) == 2 and v.isdigit(): return f"{v[0]}-{v[1]}"
    return v.replace(" ", "-").replace(".", "-").replace(",", "-").replace("/", "-")

def render_match_card(d):
    """Tüm modlarda aynı görünen merkezi maç kartı."""
    # Renk Paleti: 3+ Tam = Yeşil (Başarı), 1+ Tam = Sarı (Orta), 0 = Gri (Başarısız)
    tam_puan = int(d.get("tam", 0))
    if tam_puan >= 3:
        tam_renk = "#2adf7a" # Yeşil
    elif tam_puan >= 1:
        tam_renk = "#f0a500" # Sarı / Turuncu
    else:
        tam_renk = "#888888" # Gri
    
    sht = str(d.get("sht", "?")).strip() or "?"
    sft = str(d.get("sft", "?")).strip() or "?"
    
    # Skoru bilinmeyenler için görsel efekt
    score_display = f"İY {sht} / MS {sft}"
    if sht == "?" or sft == "?":
        score_display = f'<span style="color:#666;">İY {sht} / MS {sft} (Bekleniyor)</span>'
    
    st.markdown(f"""
    <div class="match-card">
      <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
        <div><b>🏠 {d.get('ev','?')}</b> vs <b>{d.get('dep','?')} ✈️</b> <span style="color:#888;font-size:12px">({d.get('tarih','?')})</span></div>
        <div>Eşleşme: <b style="color:{tam_renk}">{d.get('tam',0)}/{d.get('kars',0)}</b></div>
      </div>
      <div style="background:#212133; padding:5px 10px; border-radius:6px; margin-bottom:8px; border-left:3px solid #ffcc00;">
        🎯 <b>Sonuç:</b> <span style="color:#ffcc00; font-weight:bold;">{score_display}</span>
      </div>
      <div>
        <div style="margin-bottom:2px;"><span style="color:#bbb; font-size:11px;">Ev:</span> {ht_badge(d.get('ev_detay',[]))}</div>
        <div><span style="color:#bbb; font-size:11px;">Dep:</span> {ht_badge(d.get('dep_detay',[]))}</div>
      </div>
    </div>""", unsafe_allow_html=True)

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
        # Uzun form (ev_HT_1) ve Kısa form (eHT_1) kontrolü
        col_long = f"{prefix}_{typ}_{idx}"
        first_char = "e" if prefix == "ev" else "d"
        col_short = f"{first_char}{typ}_{idx}"
        # Veritabanında (data.db) şu an eHT_1 gibi kısa isimler var.
        return kayit.get(col_short, kayit.get(col_long, kayit.get(col_long.lower(), "")))

    for i in range(1, 6):
        # Ev
        hg = nor(ev_g.get(f"HT_{i}")); fg = nor(ev_g.get(f"FT_{i}"))
        hd = nor(get_col("ev", "HT", i)); fd = nor(get_col("ev", "FT", i))
        if not hg and not fg: ev_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; ev_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            ev_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
        # Dep
        hg = nor(dep_g.get(f"HT_{i}")); fg = nor(dep_g.get(f"FT_{i}"))
        hd = nor(get_col("dep", "HT", i)); fd = nor(get_col("dep", "FT", i))
        if not hg and not fg: dep_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; dep_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            dep_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
    toplam_tam = ev_tam + dep_tam
    oran = (toplam_tam/kars*100) if kars>0 else 0
    return {"tam": toplam_tam, "kars": kars, "oran": oran, "ev_detay": ev_detay, "dep_detay": dep_detay}



def eslesme_hesapla_mod2(ev_g, dep_g, kayit):
    ev_tam=0; dep_tam=0; kars=0; ev_detay=[]; dep_detay=[]
    
    def get_col(prefix, typ, idx):
        col_long = f"{prefix}_{typ}_{idx}"
        first_char = "e" if prefix == "ev" else "d"
        col_short = f"{first_char}{typ}_{idx}"
        return kayit.get(col_short, kayit.get(col_long, kayit.get(col_long.lower(), "")))

    for i in range(1, 6):
        # Ev
        hg = nor(ev_g.get(f"HT_{i}")); fg = nor(ev_g.get(f"FT_{i}"))
        hd = nor(get_col("ev", "HT", i)); fd = nor(get_col("ev", "FT", i))
        if not hg and not fg: ev_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; ev_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            ev_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
            
        # Dep
        hg = nor(dep_g.get(f"HT_{i}")); fg = nor(dep_g.get(f"FT_{i}"))
        hd = nor(get_col("dep", "HT", i)); fd = nor(get_col("dep", "FT", i))
        if not hg and not fg: dep_detay.append({"pozisyon": i, "durum": "boş", "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
        else:
            kars+=1
            hm = (hg==hd) if hg else True; fm = (fg==fd) if fg else True
            if hm and fm: dur="tam"; dep_tam+=1
            elif hm or fm: dur="kismi"
            else: dur="yok"
            dep_detay.append({"pozisyon": i, "durum": dur, "ht_db": hd, "ft_db": fd, "ht_in": hg, "ft_in": fg})
    
    toplam_tam = ev_tam + dep_tam
    oran = (toplam_tam/kars*100) if kars>0 else 0
    return {"tam": toplam_tam, "kars": kars, "oran": oran, "ev_detay": ev_detay, "dep_detay": dep_detay}



def render_analiz_panel(sonuclar: list, key_prefix: str = "ap"):
    """
    Uzman Tahmin Algoritmalı Zengin Analiz Paneli.
    """
    if not sonuclar:
        return

    # ── Veri toplama & Bilinmeyen Analizi ─────────────────────────────────────
    gercek_iy_ms = {}; yesil_iy_ms = {}
    tamamlanan = []; bilinmeyen_count = 0

    for r in sonuclar:
        sft = str(r.get("sft", "") or "").strip(); sht = str(r.get("sht", "") or "").strip()
        if not sft or sft == "?" or "-" not in sft:
            bilinmeyen_count += 1; sft = "??"; sht = "??"

        if sft != "??":
            tamamlanan.append(r); c = f"{sht} / {sft}"; gercek_iy_ms[c] = gercek_iy_ms.get(c, 0) + 1
        
        for d_list in [r.get("ev_detay", []), r.get("dep_detay", [])]:
            for d in (d_list or []):
                if not isinstance(d, dict): continue
                ft = d.get("ft_db", ""); ht = d.get("ht_db", "")
                if ft and ft != "?" and "-" in ft and ht and ht != "?" and d.get("durum") == "tam":
                    c2 = f"{ht.strip()} / {ft.strip()}"; yesil_iy_ms[c2] = yesil_iy_ms.get(c2, 0) + 1

    n_all = len(sonuclar); n_done = len(tamamlanan); bilinmeyen_pct = round((bilinmeyen_count/n_all*100),1) if n_all>0 else 0

    # ── UZMAN TAHMİN ALGORİTMASI ──
    tahmin_puanlari = {}
    for r in tamamlanan:
        s = f"{r.get('sht','')} / {r.get('sft','')}"
        p = 10.0 + (int(r.get("tam", 0)) * 5.0) + (float(r.get("oran", 0)) / 10.0)
        tahmin_puanlari[s] = tahmin_puanlari.get(s, 0) + p

    top_expert = sorted(tahmin_puanlari.items(), key=lambda x: x[1], reverse=True)[:5]
    best_combo = top_expert[0][0] if top_expert else "? / ?"

    # ── Dağılım Hesaplama ──
    ms1=0; ms0=0; ms2=0; ms_unk=0; o25u=0; o25a=0; kgv=0; kgy=0; iy1=0; iy0=0; iy2=0; total_w=0
    for r in sonuclar:
        w = 1.0 + (int(r.get("tam",0))*0.5); total_w += w
        sft = str(r.get("sft","")).strip(); sht = str(r.get("sht","")).strip()
        if not sft or sft=="??": ms_unk += w; continue
        try:
            p = sft.split("-"); ev=int(p[0]); de=int(p[1])
            if ev>de: ms1+=w
            elif ev==de: ms0+=w
            else: ms2+=w
            if (ev+de)>2: o25u+=w
            else: o25a+=w
            if ev>0 and de>0: kgv+=w
            else: kgy+=w
            p2=sht.split("-"); ie=int(p2[0]); id_=int(p2[1])
            if ie>id_: iy1+=w
            elif ie==id_: iy0+=w
            else: iy2+=w
        except: pass

    bar_n = total_w if total_w>0 else 1.0
    def pct(v,t): return round(v/t*100,1) if t>0 else 0

    def bar_3(l1,v1,r1, l2,v2,r2, l3,v3,r3, l4,v4,r4, total):
        p1=pct(v1,total); p2=pct(v2,total); p3=pct(v3,total); p4=pct(v4,total); mx=max(v1,v2,v3)
        def box(l,v,r,p,bold,unk=False):
            bw="2px" if bold else "1px"; bg="#0d0d1a" if not unk else "#1a130d"
            return f'<div style="background:{bg}; border:{bw} solid {r}{"77" if bold else "33"}; border-radius:8px; padding:6px 4px; text-align:center; flex:1;"><div style="color:{r}; font-weight:900; font-size:14px;">{p}%</div><div style="font-size:9px; color:#888;">{l}</div></div>'
        return f'<div style="display:flex; gap:5px; margin-bottom:5px;">{box(l1,v1,r1,p1,v1==mx)}{box(l2,v2,r2,p2,v2==mx)}{box(l3,v3,r3,p3,v3==mx)}{box(l4,v4,r4,p4,False,True)}</div>'

    skor_rows = ""
    for combo, sc in top_expert:
        p = pct(sc, sum(tahmin_puanlari.values()) or 1); c = "#2adf7a"
        skor_rows += f'<div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:11px;"><b style="color:{c};">{combo}</b><span style="color:#888;">{round(sc,1)}p (%{p})</span></div>'

    top_yesil = sorted(yesil_iy_ms.items(), key=lambda x: x[1], reverse=True)[:5]
    yesil_rows = ""
    for combo, cnt in top_yesil:
        yesil_rows += f'<div style="display:flex; justify-content:space-between; margin-bottom:4px; font-size:11px;"><b style="color:#7b5ef5;">{combo}</b><span style="color:#888;">{cnt}x</span></div>'

    # ── RENDER ──
    st.markdown(f"""
    <div style="background:#080812; border:1px solid #2a2a4a; border-radius:12px; padding:15px; margin-bottom:15px;">
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
        <span style="font-size:20px;">🧠</span>
        <div><div style="color:#c9d1ff; font-weight:bold;">Uzman Analiz Motoru</div><div style="color:#555; font-size:10px;">{n_all} maç · %{bilinmeyen_pct} ??</div></div>
      </div>
      <div style="background:linear-gradient(135deg,#122a,#1e1232); border:1px solid #7b5ef544; border-radius:8px; padding:10px;">
        <div style="color:#7b5ef5; font-size:9px; font-weight:bold; margin-bottom:8px;">🏆 TAHMİN ÖNERİSİ</div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:6px;">
          <div style="text-align:center; background:#0a18; padding:5px; border-radius:5px;"><div style="color:#888; font-size:9px;">İY/MS SKOR</div><div style="color:#fff; font-size:12px; font-weight:bold;">{best_combo}</div></div>
          <div style="text-align:center; background:#0a18; padding:5px; border-radius:5px;"><div style="color:#888; font-size:9px;">MS</div><div style="color:#2adf7a; font-size:12px; font-weight:bold;">{"1" if ms1>ms0 and ms1>ms2 else ("X" if ms0>ms2 else "2")}</div></div>
          <div style="text-align:center; background:#0a18; padding:5px; border-radius:5px;"><div style="color:#888; font-size:9px;">ALT/ÜST</div><div style="color:#7b9eff; font-size:12px; font-weight:bold;">{"ÜST" if o25u>o25a else "ALT"}</div></div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)
    cl, cr = st.columns(2)
    with cl:
        st.markdown(f'<div style="background:#080812; border:1px solid #2a4a; border-radius:10px; padding:10px; margin-bottom:10px;"><div style="color:#c9d1ff; font-size:10px; font-weight:bold; margin-bottom:8px;">⚽ MS DAĞILIMI (+ ??)</div>{bar_3("1",ms1,"#2adf7a","X",ms0,"#f0a500","2",ms2,"#ff6b6b","??",ms_unk,"#444",bar_n)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="background:#080812; border:1px solid #2a4a; border-radius:10px; padding:10px; margin-bottom:10px;"><div style="color:#c9d1ff; font-size:10px; font-weight:bold; margin-bottom:8px;">⏱️ İY DAĞILIMI</div>{bar_3("1",iy1,"#2adf7a","X",iy0,"#f0a500","2",iy2,"#ff6b6b","??",ms_unk,"#444",bar_n)}</div>', unsafe_allow_html=True)
    with cr:
        if skor_rows: st.markdown(f'<div style="background:#080812; border:1px solid #2a4a; border-radius:10px; padding:10px; margin-bottom:10px;"><div style="color:#c9d1ff; font-size:10px; font-weight:bold; margin-bottom:8px;">🚀 SKOR RANKING</div>{skor_rows}</div>', unsafe_allow_html=True)
        if yesil_rows: st.markdown(f'<div style="background:#080812; border:1px solid #2a4a; border-radius:10px; padding:10px;"><div style="color:#c9d1ff; font-size:10px; font-weight:bold; margin-bottom:8px;">🟢 YEŞİL PATTERN</div>{yesil_rows}</div>', unsafe_allow_html=True)
        if not (skor_rows or yesil_rows): st.info("Veri yok.")


@st.cache_data(ttl=3600)
def analiz_ve_komple_oneri(sonuclar_json):
    """Geriye dönük uyumluluk için tutuldu — render_analiz_panel kullanın."""
    import json
    sonuclar = json.loads(sonuclar_json)
    gercek_combs = {}; yesil_combs = {}; olmayan_combs = {}; genel_combs = {}
    for r in sonuclar:
        if isinstance(r, dict) and r.get("sft") and r.get("sft") != "?" and "-" in str(r.get("sft")):
            ms = str(r.get("sft")).strip(); iy = str(r.get("sht", "?")).strip()
            if iy != "?":
                c = f"{iy} / {ms}"; gercek_combs[c] = gercek_combs.get(c, 0) + 1
                genel_combs[c] = genel_combs.get(c, 0) + 1
        for d_list in [r.get("ev_detay", []), r.get("dep_detay", [])]:
            for d in d_list:
                if not isinstance(d, dict): continue
                ft = d.get("ft_db"); ht = d.get("ht_db")
                if ft and ft != "?" and "-" in ft and ht and ht != "?":
                    c = f"{ht.strip()} / {ft.strip()}"; genel_combs[c] = genel_combs.get(c, 0) + 1
                    if d.get("durum") == "tam": yesil_combs[c] = yesil_combs.get(c, 0) + 1
                    elif d.get("durum") in ["kismi","yok"]: olmayan_combs[c] = olmayan_combs.get(c, 0) + 1
    def get_top(d):
        if not d: return None, 0
        k = max(d, key=d.get); return k, d[k]
    def hesapla_oneri(cs):
        if not cs or "/" not in cs: return ""
        try:
            p = cs.split("/")[-1].strip().split("-"); ev=int(p[0]); de=int(p[1]); t=ev+de
            r=[]
            r.append("MS 1" if ev>de else ("MS 0" if ev==de else "MS 2"))
            r.append("2.5 Üst" if t>=2.5 else "2.5 Alt")
            r.append("KG Var" if ev>0 and de>0 else "KG Yok")
            return " | ".join(r)
        except: return ""
    g_c,g_t = get_top(gercek_combs); y_c,y_t = get_top(yesil_combs)
    on_c,on_t = get_top(olmayan_combs); gen_c,gen_t = get_top(genel_combs)
    return {
        "gercek": (g_c, hesapla_oneri(g_c), g_t),
        "yesil": (y_c, hesapla_oneri(y_c), y_t),
        "yesil_olmayan": (on_c, hesapla_oneri(on_c), on_t),
        "genel": (gen_c, hesapla_oneri(gen_c), gen_t)
    }


@st.dialog("📊 Maç Detayı", width="large")
def goster_tahmin_detayi(sel_id, ev, dep, tarih, aktif_mod):
    # CSS: Diyaloğu genişlet
    st.markdown("""
        <style>
        div[role="dialog"] { max-width: 95vw !important; width: 95vw !important; }
        [data-testid="column"] { min-width: 300px !important; }
        </style>
    """, unsafe_allow_html=True)
    
    detay_verisi = tahmin_detay_cek(sel_id)
    s_ht = detay_verisi.get("sonuc_ht","")
    s_ft = detay_verisi.get("sonuc_ft","")
    
    g_skorlar = {}
    try:
        raw = detay_verisi.get("girilen_skorlar", {})
        g_skorlar = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    except: pass

    ev_gir = g_skorlar.get("ev", {})
    dep_gir = g_skorlar.get("dep", {})
    detay_liste = []
    
    if ev_gir or dep_gir:
        with st.spinner("🔄 Arşiv taranıyor..."):
            db_df = liste_mod1() if aktif_mod == 1 else liste_mod2()
            if not db_df.empty:
                a_t = str(tarih).strip()
                a_e = str(ev).strip().lower()
                rdf = db_df[db_df['tarih'] < a_t].copy()
                records = rdf.to_dict('records')
                for r in records:
                    if str(r.get("tarih","")) == a_t and str(r.get("ev_takimi","")).lower() == a_e:
                        continue
                    res = eslesme_hesapla_mod1(ev_gir, dep_gir, r) if aktif_mod == 1 else eslesme_hesapla_mod2(ev_gir, dep_gir, r)
                    if res["tam"] >= 1:
                        sht = str(r.get("sonuc_ht", r.get("sonuc_HT", "?")) or "?")
                        sft = str(r.get("sonuc_ft", r.get("sonuc_FT", "?")) or "?")
                        detay_liste.append({
                            "id": int(r["id"]), "tarih": r["tarih"], "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                            "sht": sht, "sft": sft, "tam": res["tam"], "kars": res["kars"],
                            "oran": res["oran"], "ev_detay": res["ev_detay"], "dep_detay": res["dep_detay"]
                        })

    if not detay_liste:
        st.info("Eşleşen kayıt bulunamadı.")
        return

    # --- 🔵 FİLTRELEME VE ANALİZ BAŞLIYOR ---
    max_tam = max((int(d.get("tam", 0)) for d in detay_liste), default=0)
    secenekler = {"Filtresiz (Tümü)": -1}
    for e in range(1, max_tam + 1):
        kac = sum(1 for d in detay_liste if int(d.get("tam", 0)) >= e)
        if kac > 0: secenekler[f"En Az {e} Yeşil Adeti ({kac} maç)"] = e

    f_col1, f_col2 = st.columns([2, 4])
    sel_label = f_col1.selectbox("🎯 Yeşil Filtresi (Min)", list(secenekler.keys()), key=f"detay_f_{sel_id}")
    min_y = secenekler[sel_label]
    f_res = detay_liste if min_y == -1 else [d for d in detay_liste if int(d.get("tam",0)) >= min_y]
    f_col2.info(f"💡 Şu an **{len(f_res)}** maç analiz ediliyor.")

    # --- 🟢 BAŞARI TAKİBİ (Sadece filtrelenmiş maçlar üzerinden) ---
    ev_success = set()
    dep_success = set()
    for item in f_res:
        for idx, d in enumerate(item.get("ev_detay", [])):
            if d.get("durum") == "tam": ev_success.add(idx + 1)
        for idx, d in enumerate(item.get("dep_detay", [])):
            if d.get("durum") == "tam": dep_success.add(idx + 1)

    # 🟢 ÜST ÖZET ALANI
    score_badge_html = ""
    if s_ht and s_ft and s_ht not in ["","?"]:
        score_badge_html = f'<div style="background:#2adf7a18; border:1px solid #2adf7a55; padding:8px 16px; border-radius:8px; display:inline-block; margin-top:10px;"><span style="color:#2adf7a; font-weight:bold; font-size:14px;">🎯 MAÇ SONUCU: İY {s_ht} / MS {s_ft}</span></div>'

    def get_td_style(is_success, is_bottom=False):
        base = "padding:8px; text-align:center;"
        if not is_bottom: base += " border-bottom:1px solid #2d2d4a;"
        if is_success: return base + " background: #2adf7a33; color: #2adf7a; font-weight: bold;"
        return base

    ev_tds = "".join([f'<td style="{get_td_style(i+1 in ev_success)}">{ev_gir.get(f"HT_{i+1}","?")}/{ev_gir.get(f"FT_{i+1}","?")}</td>' for i in range(5)])
    dep_tds = "".join([f'<td style="{get_td_style(i+1 in dep_success, True)}">{dep_gir.get(f"HT_{i+1}","?")}/{dep_gir.get(f"FT_{i+1}","?")}</td>' for i in range(5)])
    header_row = "".join([f'<th style="padding:6px; text-align:center; border-bottom:1px solid #2d2d4a;">Maç {i+1}</th>' for i in range(5)])

    st.markdown(f"""
<div style="background:#0a0a18; border:1px solid #1a1a2e; padding:15px; border-radius:12px; margin-bottom:10px;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<h3 style="margin:0; color:#fff;">🏠 {ev} <span style="color:#666;">vs</span> ✈️ {dep}</h3>
<span style='color:#666; font-size:12px;'>📅 {tarih}</span>
</div>
{score_badge_html}
<div style="margin-top:15px; border-top:1px solid #2d2d4a; padding-top:12px;">
<div style="color:#c9d1ff; font-size:12px; font-weight:bold; margin-bottom:10px; display:flex; align-items:center; gap:8px;">
<span style="background:linear-gradient(45deg, #2adf7a, #3b3bff); padding:4px; border-radius:4px;">🔍</span> ARANAN 5v5 SKORLAR (Filtredeki Başarılar <span style="color:#2adf7a;">Yeşil</span>)
</div>
<div style="overflow-x:auto;">
<table style="width:100%; border-collapse:collapse; font-size:11px; color:#eee; background:#151525; border-radius:8px; overflow:hidden;">
<tr style="background:#1e1e30; color:#888;">
<th style="padding:6px; text-align:left; border-bottom:1px solid #2d2d4a;">Kategori</th>
{header_row}
</tr>
<tr>
<td style="padding:8px; font-weight:bold; color:#3b3bff; border-bottom:1px solid #2d2d4a;">🏠 Ev</td>
{ev_tds}
</tr>
<tr>
<td style="padding:8px; font-weight:bold; color:#7b5ef5;">✈️ Dep</td>
{dep_tds}
</tr>
</table>
</div>
</div>
</div>
""", unsafe_allow_html=True)
    # Sıralama
    f_res = sorted(f_res, key=lambda x: (int(x.get("tam", 0)), float(x.get("oran", 0))), reverse=True)
    
    # ŞİMDİ RENDER (Filtrelenmiş Liste ile)
    render_analiz_panel(f_res, key_prefix=f"modal_{sel_id}")

    for d in f_res:
        render_match_card(d)

# ─── Çift Mod Karşılaştırma Dialog ───
@st.dialog("🔀 Çift Mod Karşılaştırma", width="large")
def goster_cift_mod_detayi(ev, dep, tarih, id_mod1, id_mod2):
    # CSS ile diyaloğu tam ekran yapma denemesi (Yan yana görünüm için kritik)
    st.markdown("""
        <style>
        div[role="dialog"] {
            max-width: 98vw !important;
            width: 98vw !important;
        }
        /* Kolonların çok daralmasını engelle */
        [data-testid="column"] {
            min-width: 320px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Ana maçın sonucunu çek (Bitmiş maçsa göstermek için)
    ana_detay = tahmin_detay_cek(id_mod1)
    s_ht = ana_detay.get("sonuc_ht","")
    s_ft = ana_detay.get("sonuc_ft","")
    score_badge_html = ""
    if s_ht and s_ft and s_ht not in ["","?"]:
        score_badge_html = f'<div style="background:#2adf7a18; border:1px solid #2adf7a55; padding:8px 16px; border-radius:8px; display:inline-block; margin-bottom:10px;"><span style="color:#2adf7a; font-weight:bold; font-size:14px;">🎯 MAÇ SONUCU: İY {s_ht} / MS {s_ft}</span></div>'

    st.markdown(f"### 🏠 {ev} **vs** ✈️ {dep}  <span style='color:#888; font-size:14px;'>({tarih})</span>", unsafe_allow_html=True)
    if score_badge_html: st.markdown(score_badge_html, unsafe_allow_html=True)
    st.markdown("---")

    def hesapla_anlik(tahmin_id, aktif_mod):
        """Verilen tahmin ID ve mod için anlık eşleşme listesi döner."""
        detay_verisi = tahmin_detay_cek(tahmin_id)
        g_s = {}
        try:
            raw = detay_verisi.get("girilen_skorlar", {})
            g_s = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except:
            pass
        ev_gir = g_s.get("ev", {})
        dep_gir = g_s.get("dep", {})
        detay = []
        if ev_gir or dep_gir:
            db_df = liste_mod1() if aktif_mod == 1 else liste_mod2()
            if not db_df.empty:
                a_t = str(tarih).strip()
                a_e = str(ev).strip().lower()
                a_d = str(dep).strip().lower()
                for _, r in db_df.iterrows():
                    r_t = str(r.get("tarih", "")).strip()
                    r_e = str(r.get("ev_takimi", "")).strip().lower()
                    r_d = str(r.get("dep_takimi", "")).strip().lower()
                    if r_t == a_t and r_e == a_e and r_d == a_d:
                        continue
                    if r_t >= a_t:
                        continue
                    res = eslesme_hesapla_mod1(ev_gir, dep_gir, r) if aktif_mod == 1 else eslesme_hesapla_mod2(ev_gir, dep_gir, r)
                    if res["tam"] >= 1:
                        sht = str(r.get("sonuc_HT", r.get("sonuc_ht", "?")) or "?")
                        sft = str(r.get("sonuc_FT", r.get("sonuc_ft", "?")) or "?")
                        detay.append({
                            "id": int(r["id"]), "tarih": r["tarih"],
                            "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                            "sht": sht, "sft": sft,
                            "tam": res["tam"], "kars": res["kars"],
                            "oran": res["oran"],
                            "ev_detay": res["ev_detay"], "dep_detay": res["dep_detay"]
                        })
        detay_sirali = sorted(detay, key=lambda x: (int(x.get("tam",0)), float(x.get("oran",0))), reverse=True)
        return g_s, detay_sirali

    with st.spinner("🔄 Her iki mod için tüm arşiv taranıyor..."):
        g_s1, liste1 = hesapla_anlik(id_mod1, 1)
        g_s2, liste2 = hesapla_anlik(id_mod2, 2)

    # ── GLOBAL FİLTRELEME (En Az Puan) ──
    all_combined = list(liste1 + liste2)
    max_global = max([int(d.get("tam",0)) for d in all_combined] + [0])
    secenekler_g = {"Filtresiz (Tümü)": -1}
    for e in range(1, max_global + 1):
        kac = sum(1 for d in all_combined if int(d.get("tam",0)) >= e)
        if kac > 0: secenekler_g[f"En Az {e} Yeşil Puan ({kac} maç)"] = e
    
    sf1, sf2 = st.columns([1, 2])
    g_sel = sf1.selectbox("🎯 GLOBAL FİLTRE (Min)", list(secenekler_g.keys()), key=f"cift_global_{id_mod1}")
    val_g = secenekler_g[g_sel]
    sf2.info(f"💡 Seçilen puan ve üzerindeki tüm maçlar birleştirilerek analiz yapılır.")

    if val_g == -1:
        f_liste1 = liste1
        f_liste2 = liste2
    else:
        f_liste1 = [d for d in liste1 if int(d.get("tam",0)) >= val_g]
        f_liste2 = [d for d in liste2 if int(d.get("tam",0)) >= val_g]

    # Hibrit (Birleşik) Analiz - Filtrelenmiş birleşim
    birlesik_liste = {d["id"]: d for d in (f_liste1 + f_liste2)}.values()
    if birlesik_liste:
        st.markdown("""<div style="margin-bottom:20px; border:2px solid #ffcc0044; border-radius:16px; padding:2px;">
            <div style="background:linear-gradient(90deg, #ffcc0022, transparent); text-align:center; padding:8px; color:#ffcc00; font-weight:bold; font-size:13px; border-radius:14px 14px 0 0; border-bottom:1px solid #ffcc0033;">
                🔥 HİBRİT (MOD 1 + MOD 2) BİRLEŞİK ANALİZ
            </div>""", unsafe_allow_html=True)
        render_analiz_panel(list(birlesik_liste), key_prefix=f"hybrid_{id_mod1}_{id_mod2}")
        st.markdown("</div>", unsafe_allow_html=True)

    # Üst özet metrikler (Filtrelenmiş)
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Mod 1 (Filtreli)", len(f_liste1))
    mc2.metric("Mod 2 (Filtreli)", len(f_liste2))
    mc3.metric("Hibrit Toplam", len(birlesik_liste))

    def oneri_kutusu(liste, renk, k_pre):
        if not liste:
            st.warning("Veri yok.")
            return
        render_analiz_panel(liste, key_prefix=f"cift_box_{k_pre}_{id_mod1}")

    def render_kolon(g_s, f_liste, mod_label, renk, k_pre):
        e_s = g_s.get("ev", {}); d_s = g_s.get("dep", {})
        
        # 🟢 BAŞARI TAKİBİ (Filtreli liste üzerinden)
        ev_success = set(); dep_success = set()
        for item in f_liste:
            for idx, d_item in enumerate(item.get("ev_detay", [])):
                if d_item.get("durum") == "tam": ev_success.add(idx + 1)
            for idx, d_item in enumerate(item.get("dep_detay", [])):
                if d_item.get("durum") == "tam": dep_success.add(idx + 1)

        # 📊 Özet Tablo Oluştur
        def get_td_style(is_success, is_bottom=False):
            base = "padding:6px; text-align:center;"
            if not is_bottom: base += " border-bottom:1px solid #2d2d4a55;"
            if is_success: return base + " background: #2adf7a22; color: #2adf7a; font-weight: bold;"
            return base

        ev_tds = "".join([f'<td style="{get_td_style(i+1 in ev_success)}">{e_s.get(f"HT_{i+1}","?")}/{e_s.get(f"FT_{i+1}","?")}</td>' for i in range(5)])
        dep_tds = "".join([f'<td style="{get_td_style(i+1 in dep_success, True)}">{d_s.get(f"HT_{i+1}","?")}/{d_s.get(f"FT_{i+1}","?")}</td>' for i in range(5)])
        header_r = "".join([f'<th style="padding:4px; text-align:center; border-bottom:1px solid #2d2d4a55;">M{i+1}</th>' for i in range(5)])

        st.markdown(f"""
        <div style="background:#141422; border:1px solid {renk}44; border-radius:12px; padding:12px; margin-bottom:14px;">
          <div style="color:{renk}; font-weight:bold; font-size:16px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
             <span>{mod_label}</span>
             <span style="font-size:10px; color:#666;">Filtreli: {len(f_liste)} Maç</span>
          </div>
          
          <div style="background:#0a0a18; padding:10px; border-radius:8px; border:1px solid #1a1a2e; margin-bottom:10px;">
            <div style="color:#c9d1ff; font-size:11px; font-weight:bold; margin-bottom:8px;">🔍 ARANAN 5v5 SKORLAR</div>
            <div style="overflow-x:auto;">
              <table style="width:100%; border-collapse:collapse; font-size:10px; color:#eee; background:#151525; border-radius:6px; overflow:hidden;">
                <tr style="background:#1e1e30; color:#888;">
                  <th style="padding:4px; text-align:left; border-bottom:1px solid #2d2d4a55;">Kat</th>
                  {header_r}
                </tr>
                <tr>
                  <td style="padding:6px; font-weight:bold; color:#3b3bff; border-bottom:1px solid #2d2d4a55;">Ev</td>
                  {ev_tds}
                </tr>
                <tr>
                  <td style="padding:6px; font-weight:bold; color:#7b5ef5;">Dep</td>
                  {dep_tds}
                </tr>
              </table>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)
        
        oneri_kutusu(f_liste, renk, k_pre)
        st.caption(f"**{len(f_liste)}** eşleşen maç listeleniyor")
        for d in f_liste:
            render_match_card(d)

    col1, col2 = st.columns(2)
    with col1:
        render_kolon(g_s1, f_liste1, "1️⃣ Mod 1 — Ortak 5 Maç", "#3b3bff", "m1")
    with col2:
        render_kolon(g_s2, f_liste2, "2️⃣ Mod 2 — Ev/Dep Ayrı", "#7b5ef5", "m2")

# ─── Tahmin Geçmişi Render Fonksiyonu ───
def render_backtest_tab(aktif_mod):
    """Her iki modun 4. sekmesinde (t4) çağrılır."""
    st.markdown("## 📈 Tahmin Geçmişi / Backtest")
    st.caption("Analiz Yap sekmesinde yapılan her tahmin burada saklanır. Maç bitince skoru güncelleyerek backtest yapabilirsiniz.")
    
    tdf = tahmin_listele()


    # Supabase tablosu henüz boşsa columns dönmez
    if tdf.empty or "mod" not in tdf.columns:
        st.info("ℹ️ Henüz tahmin geçmişi yok. 'Analiz Yap' sekmesinden bir analiz başlatın.")
        return
        
    # Aktif moda göre filtrele (int veya string olabilir)
    tdf["mod"] = pd.to_numeric(tdf["mod"], errors="coerce")
    tdf = tdf[tdf["mod"] == int(aktif_mod)].reset_index(drop=True)
    
    if tdf.empty:
        st.info(f"ℹ️ Mod {aktif_mod} için henüz tahmin kaydı yok. 'Analiz Yap' sekmesinden bir analiz başlatın.")
        return

    st.markdown("---")
    
    # Skor Güncelleme & Temizleme (En üstte dursun)
    with st.expander("✏️ Tahmin Sonuçları Yönetimi (Güncelle / Sil)"):
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

    st.markdown("#### 🎛️ Gelişmiş Filtreleme & Arşiv Taraması")
    
    with st.container():
        f_row = st.columns([2, 4])
        
        # 1. Tarih Filtresi (İsteğe Bağlı)
        use_date = f_row[0].checkbox("📅 Tarih Bazlı Filtre", value=True, key=f"use_t_{aktif_mod}")
        sel_date_str = "Tüm Zamanlar"
        if use_date:
            filter_date = f_row[0].date_input("Analiz Tarihi", value=date.today(), key=f"t_sec_{aktif_mod}", label_visibility="collapsed")
            sel_date_str = filter_date.strftime("%Y-%m-%d")
            tdf = tdf[tdf["tarih"].astype(str) == sel_date_str]
        
        # 2. Takım Arama
        search_query = f_row[1].text_input("🔍 Takım Ara", placeholder="Takım ismine göre...", key=f"ara_{aktif_mod}")
        if search_query and not tdf.empty:
            tdf = tdf[tdf["ev_takimi"].str.contains(search_query, case=False, na=False) | 
                      tdf["dep_takimi"].str.contains(search_query, case=False, na=False)]

    # --- PERFORMANS AYARI: Ağır hesaplamaları sadece filtrelenmiş (azaltılmış) veri üzerinde yapalım ---
    if not tdf.empty:
        # Yeşil badge (Tam) hesaplamasını sadece gösterilecek maçlar için yap (Hız kazandırır)
        def hesapla_max_yesil_lite(detay_str):
            try:
                if not detay_str: return 0
                detay = json.loads(detay_str) if isinstance(detay_str, str) else detay_str
                return max((int(r.get("tam", 0)) for r in detay), default=0)
            except: return 0
            
        tdf["max_yesil"] = tdf["eslesen_detay"].apply(hesapla_max_yesil_lite)

        # 🟢 Gelişmiş Filtreleme (Puan ve Adet Ayrıştırıldı)
        st.markdown("---")
        q_row = st.columns([2, 2, 2])
        
        # Filtre Tipi (Puan mı Arşiv Sayısı mı yoksa Kombine mi?)
        filter_type = q_row[0].selectbox("🔍 Filtre Kriteri", ["📊 Yeşil Adeti (Max Puan)", "📂 Eşleşme Sayısı (Toplam Adet)", "🎯 Puan x Adet (Altın Kural)"], key=f"filter_type_{aktif_mod}")
        
        if filter_type != "🎯 Puan x Adet (Altın Kural)":
            # Filtre Kuralı (Normal Mod)
            q_rule = q_row[1].selectbox("⚙️ Kural", ["Herhangi", "Sadece (Tam)", "En Az", "En Fazla"], key=f"q_rule_{aktif_mod}", index=2) # Varsayılan 'En Az'
            q_val = q_row[2].number_input("Değer", min_value=0, max_value=500, value=2 if "📊" in filter_type else 5, key=f"q_val_{aktif_mod}")
            
            if q_rule != "Herhangi":
                # 'Yeşil Adeti' -> max_yesil (puan)
                # 'Eşleşme Sayısı' -> eslesen_sayisi (adet)
                target_col = "max_yesil" if "📊" in filter_type else "eslesen_sayisi"
                if q_rule == "Sadece (Tam)": tdf = tdf[tdf[target_col] == q_val]
                elif q_rule == "En Az": tdf = tdf[tdf[target_col] >= q_val]
                elif q_rule == "En Fazla": tdf = tdf[tdf[target_col] <= q_val]
        else:
            # ALTIN KURAL: Belirli bir yeşil adeti (puan) geçen X adet maç olsun
            q_score = q_row[1].number_input("Min. Yeşil Adeti", min_value=1, max_value=10, value=2, key=f"gs_score_{aktif_mod}")
            q_count = q_row[2].number_input("Min. Maç Sayısı (Adet)", min_value=1, max_value=100, value=5, key=f"gs_count_{aktif_mod}")
            
            def check_gold_rule(detay_str, target_p, target_c):
                try:
                    detay = json.loads(detay_str) if isinstance(detay_str, str) else detay_str
                    count = sum(1 for r in detay if int(r.get("tam", 0)) >= target_p)
                    return count >= target_c
                except: return False
            
            tdf["gold_rule_met"] = tdf["eslesen_detay"].apply(lambda x: check_gold_rule(x, q_score, q_count))
            tdf = tdf[tdf["gold_rule_met"]]
        
        st.info(f"🔍 **{len(tdf)}** analiz kriterlere uyuyor.")

    tdf = tdf.sort_values(by="id", ascending=False).reset_index(drop=True)

    if tdf.empty:
        st.info(f"ℹ️ {sel_date_str} tarihinde henüz tahmin kaydı bulunmuyor.")
        return

    # Üst Bilgi
    m1, m2 = st.columns(2)
    m1.metric("Gösterilen Tahmin Sayısı", len(tdf))
    sht_col = "sonuc_ht" if "sonuc_ht" in tdf.columns else "sonuc_HT"
    sonuclu = tdf[(tdf[sht_col].notna()) & (tdf[sht_col] != "") & (tdf[sht_col] != "?")]
    m2.metric("Sonuç Girilmiş", len(sonuclu))
    st.markdown("---")

    # Tarih bazlı görünümde tüm maçları göster (limit yok)
    tdf_view = tdf
    
    # Canlı veritabanı skor sözlüğü (eslesen maçlardaki skorları anlık yansıtmak için)
    db_df = liste_mod1() if aktif_mod == 1 else liste_mod2()
    db_scores = {}
    if not db_df.empty:
        for _, r in db_df.iterrows():
            sv_ht = str(r.get("sonuc_HT", r.get("sonuc_ht", "")))
            sv_ft = str(r.get("sonuc_FT", r.get("sonuc_ft", "")))
            db_scores[int(r["id"])] = {"ht": sv_ht, "ft": sv_ft}
    
    # ── Kompakt Maç Listesi ──
    secili_key = f"secili_tahmin_{aktif_mod}"
    if secili_key not in st.session_state:
        st.session_state[secili_key] = None

    for idx, row in tdf_view.iterrows():
        t_id = int(row["id"])
        ev = row["ev_takimi"]
        dep = row["dep_takimi"]
        tarih = row["tarih"]
        eslesen = row["eslesen_sayisi"]
        sht = row.get("sonuc_ht", "") or ""
        sft = row.get("sonuc_ft", "") or ""

        if sht and sft and sht not in ["", "?"]:
            durum_ikon = "🎯"
            durum_renk = "#2adf7a"
            durum_text = f"İY {sht} / MS {sft}"
        else:
            durum_ikon = "⏳"
            durum_renk = "#f0a500"
            durum_text = "Bekleniyor"

        secili = (st.session_state[secili_key] == t_id)
        kart_border = f"3px solid {durum_renk}" if secili else f"1px solid #2d2d4a"
        kart_bg = "#1e1e35" if secili else "#1a1a2e"

        col_info, col_btn = st.columns([6, 1])
        with col_info:
            st.markdown(f"""
            <div style="background:{kart_bg}; border:{kart_border}; border-radius:8px; padding:10px 14px; margin-bottom:6px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <span style="font-weight:bold; font-size:14px;">🏠 {ev} <span style="color:#777">vs</span> ✈️ {dep}</span>
                  <span style="color:#555; font-size:12px; margin-left:8px;">{tarih}</span>
                </div>
                <div style="display:flex; gap:10px; align-items:center;">
                  <span style="background:#1a2e24; color:#2adf7a; padding:2px 8px; border-radius:10px; font-size:12px; font-weight:bold;">{eslesen} eşleşme</span>
                  <span style="background:#1e3a1e; color:#7bff7b; padding:2px 8px; border-radius:10px; font-size:11px; margin-left:5px;">⭐ En İyi: {row.get('max_yesil', 0)} Yeşil</span>
                  <span style="color:{durum_renk}; font-size:13px;">{durum_ikon} {durum_text}</span>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        with col_btn:
            if st.button("📂 Detay", key=f"detay_btn_{aktif_mod}_{t_id}", use_container_width=True):
                goster_tahmin_detayi(t_id, ev, dep, tarih, aktif_mod)






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
            "2️⃣ Ev / Dep Ayrı 5 Maç (Detaylı)",
            "3️⃣ Oran Eşleşme Analizi",
            "🔀 Çift Mod Karşılaştırma"
        ],
        help="Mod 1 ve 2 skor bazlıdır. Mod 3 oran bazlı geçmiş maçları bulur. Çift Mod: her iki modda analiz edilmiş maçları karşılaştırır."
    )
    st.markdown("---")
    
    if "1️⃣" in secilen_mod:
        istat = db_ist_mod("mac_arsivi")
        st.markdown("### 📊 Aktif DB Durumu")
        st.metric("Kayıt Sayısı", f"{istat['toplam']:,}")
        st.caption(f"En yeni: {istat['yeni']} \nEn eski: {istat['eski']}")
    elif "2️⃣" in secilen_mod:
        istat = db_ist_mod("mac_arsivi_detayli")
        st.markdown("### 📊 Aktif DB Durumu")
        st.metric("Kayıt Sayısı", f"{istat['toplam']:,}")
        st.caption(f"En yeni: {istat['yeni']} \nEn eski: {istat['eski']}")
    else:
        i1 = db_ist_mod("mac_arsivi")
        i2 = db_ist_mod("mac_arsivi_detayli")
        st.markdown("### 📊 DB Durumu")
        st.metric("Mod 1 Kayıt", f"{i1['toplam']:,}")
        st.metric("Mod 2 Kayıt", f"{i2['toplam']:,}")

# ─── Mod 1 (Ortak 5 Maç) Çizimi ───
if "1️⃣" in secilen_mod:
    st.markdown("<h1>⚽ Ortak Skor Eşleşme Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>Ev sahibi ve deplasman takımlarının <b>son 5 maçını ayrı ayrı</b> girerek analiz yapın.</p><hr>", unsafe_allow_html=True)
    
    # Navigasyon Seçenekleri
    tab_labels = ["🔍 Analiz Yap", "⚡ Otomatik Kayıt Ekle", "📋 Tüm Veriler", "📈 Tahmin Geçmişi"]
    if "active_tab_1" not in st.session_state:
        st.session_state.active_tab_1 = tab_labels[0]
    
    sel_tab1 = st.radio("Navigasyon", tab_labels, index=tab_labels.index(st.session_state.active_tab_1), 
                         horizontal=True, label_visibility="collapsed", key="nav_1")
    st.session_state.active_tab_1 = sel_tab1
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.session_state.active_tab_1 == "🔍 Analiz Yap":
        st.markdown("### 🔍 Analiz Yap + Otomatik Kayıt")
        st.caption("Günün maçlarından seçim yaparak takımları ve verileri otomatik getirebilirsin.")
        
        # Günün İddaa Bülteni Paneli
        st.markdown("#### 📅 Maç Seçimi (İddaa Bülteni)")
        b_col1, b_col2 = st.columns([1, 3])
        secilen_tarih = b_col1.date_input("Bülten Tarihi", value=date.today(), key="bulten_tarih1")
        
        gunun_maclari = fetch_daily_fixtures(secilen_tarih.strftime("%Y-%m-%d"))
        gunun_oranlar = fetch_daily_odds(secilen_tarih.strftime("%Y-%m-%d"))
        mac_opsiyonlar = get_fixture_options(gunun_maclari, gunun_oranlar)
        
        secilen_mac_label = b_col2.selectbox(
            "Günün Maçlarından Seç (Verileri Seçince Otomatik Çeker)", 
            ["Lütfen Bir Maç Seçin..."] + list(mac_opsiyonlar.keys())
        )

        ac1, ac2, ac3 = st.columns([2, 2, 1])
        # Manuel girdi veya Mac secimi ile doldur
        default_ev = ""
        default_dep = ""
        
        if secilen_mac_label != "Lütfen Bir Maç Seçin...":
            detay = mac_opsiyonlar[secilen_mac_label]
            default_ev = detay["home"]
            default_dep = detay["away"]

        a_ev = ac1.text_input("🏠 Ev Sahibi Takım", value=default_ev, placeholder="Örn: Galatasaray", key="a1_ev")
        a_dep = ac2.text_input("✈️ Deplasman Takımı", value=default_dep, placeholder="Örn: Fenerbahçe", key="a1_dep")
        a_tar = ac3.date_input("📅 Tarih", value=secilen_tarih, key="a1_tar")
        
        btn_api1, _ = st.columns([1, 2])
        if btn_api1.button("⚡ Aralarındaki Geçmiş Maçları Çek (API)", key="api_btn_1", use_container_width=True):
            with st.spinner("Takımların aralarındaki geçmiş maçlar çekiliyor..."):
                # Önce Takım ID'lerini bulalım
                hid = None
                aid = None
                
                if secilen_mac_label != "Lütfen Bir Maç Seçin...":
                    if a_ev == default_ev: hid = mac_opsiyonlar[secilen_mac_label]["home_id"]
                    if a_dep == default_dep: aid = mac_opsiyonlar[secilen_mac_label]["away_id"]
                
                if not hid and a_ev: hid = get_team_id(a_ev)
                if not aid and a_dep: aid = get_team_id(a_dep)
                
                if hid and aid:
                    # Ev Sahibi için (Galatasaray'ın Fenerbahçe'ye karşı EV SAHİBİ olduğu maçlar)
                    matches_ev = fetch_h2h_matches(hid, aid, wanted_home_id=hid, before_date=str(a_tar))
                    for i, m in enumerate(matches_ev):
                        st.session_state[f"a1_eviy{i+1}"] = m["ht"]
                        st.session_state[f"a1_evms{i+1}"] = m["ft"]
                    if not matches_ev: st.warning(f"Ev sahibi takımın kendi evinde oynadığı aralarındaki maç bulunamadı.")
                        
                    # Deplasman için (Fenerbahçe'nin Galatasaray'a karşı EV SAHİBİ olduğu -kendi evinde oynadığı- maçlar)
                    matches_dep = fetch_h2h_matches(hid, aid, wanted_home_id=aid, before_date=str(a_tar))
                    for i, m in enumerate(matches_dep):
                        st.session_state[f"a1_depiy{i+1}"] = m["ht"]
                        st.session_state[f"a1_depms{i+1}"] = m["ft"]
                    if not matches_dep: st.warning(f"Deplasman takımının kendi evinde oynadığı aralarındaki maç bulunamadı.")
                else: 
                    st.warning("Veri çekebilmek için iki takımın da girilmesi (veya listeden seçilmesi) ve bulunabilmesi gerekmektedir.")
            st.rerun()

        st.markdown("---")
        st.markdown("#### 🏠 Ev Sahibi Son 5 Maç")
        ev_gir1 = input_skor_ui("a1_ev")
        st.markdown("<br>#### ✈️ Deplasman Son 5 Maç", unsafe_allow_html=True)
        dep_gir1 = input_skor_ui("a1_dep")
        
        st.markdown("---")
        c1, c2 = st.columns([2,1])
        min_e = c1.slider("Min Tam Eşleşme (Max 10)", 1, 10, 1)
        basla = c2.button("🔍 Analizi Başlat", type="primary", use_container_width=True)
            
        if basla:
            o1, ox, o2 = None, None, None
            if secilen_mac_label != "Lütfen Bir Maç Seçin...":
                odds = mac_opsiyonlar[secilen_mac_label].get("odds")
                if odds: o1, ox, o2 = odds.get("1"), odds.get("x"), odds.get("2")

            if a_ev.strip() and a_dep.strip():
                kayit_ekle_mod1(a_tar, a_ev, a_dep, "", "", ev_gir1, dep_gir1, o1=o1, ox=ox, o2=o2)
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
                st.session_state["mod1_sonuclar"] = None
            else:
                st.session_state["mod1_sonuclar"] = sonuclar
                st.success(f"✅ {len(sonuclar)} adet eşleşme bulundu! Aşağıdan filtreleyebilirsiniz.")

        # ── Kalıcı ve Dinamik Sonuç Alanı ──
        if st.session_state.get("mod1_sonuclar"):
            all_res = st.session_state["mod1_sonuclar"]
            
            # Filtreleme UI (En Az Puan)
            f_col1, f_col2 = st.columns([2, 4])
            max_t = max((int(d.get("tam",0)) for d in all_res), default=0)
            secenekler = {"Filtresiz (Tümü)": -1}
            for e in range(1, max_t+1):
                kac = sum(1 for d in all_res if int(d.get("tam",0)) >= e)
                if kac > 0: secenekler[f"En Az {e} Yeşil Puan ({kac} maç)"] = e
            
            sel_f = f_col1.selectbox("🎯 Hassas Filtre (Min)", list(secenekler.keys()), key="mod1_f_live")
            val_f = secenekler[sel_f]
            if val_f == -1:
                f_res = all_res
            else:
                f_res = [d for d in all_res if int(d.get("tam",0)) >= val_f]
            f_col2.info(f"💡 Sadece **{len(f_res)}** maç ({'Minimum ' + str(val_f) if val_f!=-1 else 'Tüm'} Puanlılar) analiz ediliyor.")

            st.markdown("---")
            # ── Zengin Analiz Paneli (Dinamiğe Bağlı) ──
            render_analiz_panel(f_res, key_prefix="mod1_yap_live")

            # Maç Listesi
            sdf = pd.DataFrame(f_res).sort_values(["tam", "oran"], ascending=False)
            for t_val in sorted(sdf["tam"].unique(), reverse=True):
                g = sdf[sdf["tam"]==t_val]
                st.markdown(f"#### 🟢 {t_val} Yeşil Eşleşme ({len(g)} Maç)")
                for _, row in g.iterrows():
                    render_match_card(row)
    elif st.session_state.active_tab_1 == "⚡ Otomatik Kayıt Ekle":
        st.markdown("### ⚡ Günlük Otomatik Maç Tarama ve Kayıt (Bülten Sırasına Göre)")
        st.markdown("Seçilen tarihteki iddaa bülteninde bulunan tüm maçları saat sırasına göre tek tek tarar. Yeterli geçmiş verisi olan maçları otomatik olarak tüm verilere kaydeder ve geçmiş veritabanıyla analiz ederek Tahmin Geçmişine düşürür.")
        
        c1, c2 = st.columns([1, 2])
        oto_tar = c1.date_input("📅 Bülten Tarihi", value=date.today(), key="oto1_tar")
        oto_mod = c2.multiselect("⚙️ İşlenecek Modlar", ["1️⃣ Ortak 5 Maç (Mod 1)", "2️⃣ Ev/Dep Ayrı (Mod 2)"], default=["1️⃣ Ortak 5 Maç (Mod 1)"], key="oto1_modlar")
        
        if st.button("🚀 Seçilen Tarihteki Maçları Çek ve Ekle", type="primary", use_container_width=True):
            secilenler = []
            if "1️⃣ Ortak 5 Maç (Mod 1)" in oto_mod: secilenler.append(1)
            if "2️⃣ Ev/Dep Ayrı (Mod 2)" in oto_mod: secilenler.append(2)
            
            if not secilenler:
                st.warning("Lütfen en az bir mod seçin.")
            else:
                if start_background_analysis(oto_tar, secilenler):
                    st.toast("Arka plan analizi başlatıldı!")
                    st.rerun()
                else:
                    st.error("Zaten çalışan bir analiz var!")


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

    elif st.session_state.active_tab_1 == "📋 Tüm Veriler":
        # Üst Panel (Yenile / Sil)
        b1, b2, b3 = st.columns([1, 2, 3])
        if b1.button("🔄 Tabloyu Yenile", key="y1", use_container_width=True): st.rerun()
        if b2.button("🗑️ SADECE Örnek Verileri Sil", type="primary", key="sd1", use_container_width=True):
            ornek_sil_mod1()
            st.success("Test amacıyla yüklenen tüm sahte / örnek kayıtlar başarıyla silindi!")
            st.rerun()
        if b3.button("⚡ Eksik Skorları Çek (API)", key="oto1", use_container_width=True):
            with st.spinner("Skoru boş olan maçlar taranıyor, API puanları otomatik çekiliyor..."):
                gn = otomatize_skor_guncelle([1, 2])
                st.success(f"✓ Her iki veritabanı da tarandı ve toplam {gn} adet maçın skoru API'den güncellendi!")
                st.rerun()

        if b1.button("📉 Eksik Oranları Tamamla (API)", key="oto_oran1", use_container_width=True):
            with st.spinner("Oranı eksik olan maçlar taranıyor, API oranları otomatik çekiliyor..."):
                gn = otomatize_oran_guncelle([1, 2])
                st.success(f"✓ Toplam {gn} adet maçın oran bilgisi API'den çekilerek veritabanına eklendi!")
                st.rerun()
            
        with st.expander("⚠️ Tehlikeli İşlemler (Silme Seçenekleri)"):
            st.markdown("#### 📅 Tarih Bazlı Silme")
            d_col1, d_col2 = st.columns([2, 1])
            sil_tar1 = d_col1.date_input("Silinecek Tarihi Seçin", value=date.today(), key="sil_tar1")
            if d_col2.button("🗑️ Tarihe Göre Sil", type="primary", key="btn_sil_tar1", use_container_width=True):
                tarih_sil_mod1(sil_tar1)
                st.success(f"✅ {sil_tar1} tarihindeki tüm Mod 1 kayıtları silindi!")
                st.rerun()

            st.markdown("---")
            st.warning("BÜTÜN veritabanını ve bunlara bağlı Tahmin Geçmişini kalıcı olarak siler.")
            if st.button("💀 TÜM VERİLERİ VE TAHMİN GEÇMİŞİNİ KALICI OLARAK SİL", type="primary", key="nuke1", use_container_width=True):
                tumunu_sil_mod1()
                tahmin_tumunu_sil()
                st.success("✅ Sistem başarıyla sıfırlandı! Tüm veriler ve tahmin geçmişi kalıcı olarak silindi.")
                st.rerun()
                
        df1 = liste_mod1()
        search_v1 = st.text_input("🔍 Arşivde Ara (Takım)", placeholder="Takım ismi yazın...", key="s_v1")
        if search_v1 and not df1.empty:
            df1 = df1[df1["ev_takimi"].str.contains(search_v1, case=False, na=False) | 
                     df1["dep_takimi"].str.contains(search_v1, case=False, na=False)]
        
        if not df1.empty:
            ht_col = "sonuc_ht" if "sonuc_ht" in df1.columns else "sonuc_HT"
            ft_col = "sonuc_ft" if "sonuc_ft" in df1.columns else "sonuc_FT"
            
            # Orijinal Tablo Tasarımı (Tüm Kolonlar Görünür)
            st.info("💡 Tablodaki **İY** veya **MS** hücrelerine çift tıklayarak skoru doğrudan girebilirsiniz.")
            
            # Veritabanındaki tüm HT/FT, eHT/eFT, dHT/dFT kolonlarını göstermek için DF'i temizle
            drop_system = ["olusturulma", "is_sample"]
            vdf1 = df1.drop(columns=[c for c in drop_system if c in df1.columns], errors="ignore")
            
            # Kolon Konfigürasyonu
            c_config = {
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "tarih": st.column_config.TextColumn("Tarih", disabled=True),
                "ev_takimi": st.column_config.TextColumn("Ev Sahibi", disabled=True),
                "dep_takimi": st.column_config.TextColumn("Deplasman", disabled=True),
                "sonuc_HT": st.column_config.TextColumn("İY", help="İlk Yarı Skoru"),
                "sonuc_FT": st.column_config.TextColumn("MS", help="Maç Sonucu"),
                "sonuc_ht": st.column_config.TextColumn("İY", help="İlk Yarı Skoru"), # Fallback
                "sonuc_ft": st.column_config.TextColumn("MS", help="Maç Sonucu"), # Fallback
            }
            # Geri kalan skor kolonlarını isme göre etiketle
            for c in vdf1.columns:
                if c not in c_config:
                    c_config[c] = st.column_config.TextColumn(c.replace("_", " "), width="small")

            edited_df1 = st.data_editor(
                vdf1,
                column_config=c_config,
                disabled=["id", "tarih", "ev_takimi", "dep_takimi"],
                use_container_width=True,
                hide_index=True,
                key="ed_v1"
            )
            
            # Eğer hücre düzenlendiyse Kaydet butonu göster
            if "ed_v1" in st.session_state and st.session_state.ed_v1["edited_rows"]:
                st.markdown("---")
                if st.button("💾 Değişiklikleri Veritabanına Kaydet", key="save_v1", type="primary", use_container_width=True):
                    edits = st.session_state.ed_v1["edited_rows"]
                    with st.status("Veriler güncelleniyor...", expanded=False) as status:
                        for idx_str, changes in edits.items():
                            idx = int(idx_str)
                            row_id = df1.iloc[idx]["id"]
                            new_ht = changes.get(ht_col, df1.iloc[idx][ht_col])
                            new_ft = changes.get(ft_col, df1.iloc[idx][ft_col])
                            guncelle_skor_mod1(row_id, new_ht, new_ft)
                        status.update(label="✅ Tüm değişiklikler kaydedildi!", state="complete")
                    st.success("Başarıyla güncellendi!")
                    st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            st.empty() # Eski güncelleme paneli kaldırıldı

        with c2:
            with st.expander("🗑️ Spesifik Kayıt Sil"):
                sid = st.number_input("Silinecek ID", min_value=1)
                if st.button("Kaydı Uçur", key="ds1"):
                    sil_mod1(sid); st.success(f"#{sid} silindi!"); st.rerun()

    elif st.session_state.active_tab_1 == "📈 Tahmin Geçmişi":
        render_backtest_tab(1)

# ─── Mod 2 (Ev & Dep Ayrı 5 Maç) Çizimi ───
elif "2️⃣" in secilen_mod:
    st.markdown("<h1>⚽ Detaylı Skor Eşleşme Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>Ev sahibi için ayrı son 5 maç, deplasman için ayrı son 5 maç girilir. Geçmişte <b>iki takımın da aynı durumla sahaya çıktığı</b> maçlar aranır.</p><hr>", unsafe_allow_html=True)
    
    # Navigasyon Seçenekleri
    tab_labels_2 = ["🔍 Analiz Yap", "⚡ Otomatik Kayıt Ekle", "📋 Tüm Veriler", "📈 Tahmin Geçmişi"]
    if "active_tab_2" not in st.session_state:
        st.session_state.active_tab_2 = tab_labels_2[0]
    
    sel_tab2 = st.radio("Navigasyon", tab_labels_2, index=tab_labels_2.index(st.session_state.active_tab_2), 
                         horizontal=True, label_visibility="collapsed", key="nav_2")
    st.session_state.active_tab_2 = sel_tab2
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.session_state.active_tab_2 == "🔍 Analiz Yap":
        st.markdown("### 🔍 Detaylı Analiz + Otomatik Kayıt")
        st.caption("Günün maçlarından seçim yaparak takımları ve verileri otomatik getirebilirsin.")
        
        # Günün İddaa Bülteni Paneli
        st.markdown("#### 📅 Maç Seçimi (İddaa Bülteni)")
        b_col1_2, b_col2_2 = st.columns([1, 3])
        secilen_tarih2 = b_col1_2.date_input("Bülten Tarihi", value=date.today(), key="bulten_tarih2")
        
        gunun_maclari2 = fetch_daily_fixtures(secilen_tarih2.strftime("%Y-%m-%d"))
        gunun_oranlar2 = fetch_daily_odds(secilen_tarih2.strftime("%Y-%m-%d"))
        mac_opsiyonlar2 = get_fixture_options(gunun_maclari2, gunun_oranlar2)
        
        secilen_mac_label2 = b_col2_2.selectbox(
            "Günün Maçlarından Seç (Verileri Seçince Otomatik Çeker)", 
            ["Lütfen Bir Maç Seçin..."] + list(mac_opsiyonlar2.keys()),
            key="secilen_mac_label2"
        )

        ac1, ac2, ac3 = st.columns([2, 2, 1])
        default_ev2 = ""
        default_dep2 = ""
        
        if secilen_mac_label2 != "Lütfen Bir Maç Seçin...":
            detay2 = mac_opsiyonlar2[secilen_mac_label2]
            default_ev2 = detay2["home"]
            default_dep2 = detay2["away"]

        a_ev2 = ac1.text_input("🏠 Ev Sahibi Takım", value=default_ev2, placeholder="Örn: Galatasaray", key="a2_ev_takim")
        a_dep2 = ac2.text_input("✈️ Deplasman Takımı", value=default_dep2, placeholder="Örn: Fenerbahçe", key="a2_dep_takim")
        a_tar2 = ac3.date_input("📅 Tarih", value=secilen_tarih2, key="a2_tar")
        
        btn_api2, _ = st.columns([1, 2])
        if btn_api2.button("⚡ Ev Sahibinin İÇ SAHA, Deplasmanın DIŞ SAHA Geçmişini Çek (API)", key="api_btn_a2", use_container_width=True):
            with st.spinner("Takımların iç/dış saha verileri detaylı çekiliyor..."):
                # Ev Sahibi (İç Saha)
                hid = None
                if secilen_mac_label2 != "Lütfen Bir Maç Seçin..." and a_ev2 == default_ev2:
                    hid = mac_opsiyonlar2[secilen_mac_label2]["home_id"]
                elif a_ev2:
                    hid = get_team_id(a_ev2)
                
                if hid:
                    matches = fetch_last_5_matches_by_venue(hid, "home", before_date=str(a_tar2))
                    for i, m in enumerate(matches):
                        st.session_state[f"a2_eviy{i+1}"] = m["ht"]
                        st.session_state[f"a2_evms{i+1}"] = m["ft"]
                    if not matches: st.warning(f"{a_ev2} iç saha maçı bulunamadı.")
                else: st.warning(f"{a_ev2} bulunamadı.")
                
                # Deplasman (Dış Saha)
                aid = None
                if secilen_mac_label2 != "Lütfen Bir Maç Seçin..." and a_dep2 == default_dep2:
                    aid = mac_opsiyonlar2[secilen_mac_label2]["away_id"]
                elif a_dep2:
                    aid = get_team_id(a_dep2)
                
                if aid:
                    matches = fetch_last_5_matches_by_venue(aid, "away", before_date=str(a_tar2))
                    for i, m in enumerate(matches):
                        st.session_state[f"a2_depiy{i+1}"] = m["ht"]
                        st.session_state[f"a2_depms{i+1}"] = m["ft"]
                    if not matches: st.warning(f"{a_dep2} dış saha maçı bulunamadı.")
                else: st.warning(f"{a_dep2} bulunamadı.")
            st.rerun()

        st.markdown("---")
        st.markdown("#### 🏠 Ev Sahibi Geçmişi")
        e_gir = input_skor_ui("a2_ev")
        st.markdown("<br>#### ✈️ Deplasman Geçmişi", unsafe_allow_html=True)
        d_gir = input_skor_ui("a2_dep")
        
        st.markdown("---")
        c1, c2 = st.columns([2,1])
        min_e = c1.slider("Min Toplam Tam Eşleşme (Max. 10)", 1, 10, 1)
        basla2 = c2.button("🔍 Detaylı Analizi Başlat", type="primary", use_container_width=True)
            
        if basla2:
            o1, ox, o2 = None, None, None
            if secilen_mac_label2 != "Lütfen Bir Maç Seçin...":
                odds = mac_opsiyonlar2[secilen_mac_label2].get("odds")
                if odds: o1, ox, o2 = odds.get("1"), odds.get("x"), odds.get("2")

            # Önce veritabanına kaydet
            if a_ev2.strip() and a_dep2.strip():
                kayit_ekle_mod2(a_tar2, a_ev2, a_dep2, "", "", e_gir, d_gir, o1=o1, ox=ox, o2=o2)
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
                st.session_state["mod2_sonuclar"] = None
            else:
                st.session_state["mod2_sonuclar"] = sonuclar
                st.success(f"✅ {len(sonuclar)} adet eşleşme bulundu! Aşağıdan filtreleyebilirsiniz.")

        # ── Kalıcı ve Dinamik Sonuç Alanı ──
        if st.session_state.get("mod2_sonuclar"):
            all_res2 = st.session_state["mod2_sonuclar"]
            
            # Filtreleme UI (En Az Puan)
            f_col1, f_col2 = st.columns([2, 4])
            max_t2 = max((int(d.get("tam",0)) for d in all_res2), default=0)
            secenekler2 = {"Filtresiz (Tümü)": -1}
            for e in range(1, max_t2+1):
                kac = sum(1 for d in all_res2 if int(d.get("tam",0)) >= e)
                if kac > 0: secenekler2[f"En Az {e} Yeşil Puan ({kac} maç)"] = e
            
            sel_f2 = f_col1.selectbox("🎯 Hassas Filtre (Min)", list(secenekler2.keys()), key="mod2_f_live")
            val_f2 = secenekler2[sel_f2]
            if val_f2 == -1:
                f_res2 = all_res2
            else:
                f_res2 = [d for d in all_res2 if int(d.get("tam",0)) >= val_f2]
            f_col2.info(f"💡 Sadece **{len(f_res2)}** maç ({'Minimum ' + str(val_f2) if val_f2!=-1 else 'Tüm'} Puanlılar) analiz ediliyor.")

            st.markdown("---")
            # ── Zengin Analiz Paneli (Dinamiğe Bağlı) ──
            render_analiz_panel(f_res2, key_prefix="mod2_yap_live")

            # Maç Listesi
            sdf2 = pd.DataFrame(f_res2).sort_values(["tam", "oran"], ascending=False)
            for t_val in sorted(sdf2["tam"].unique(), reverse=True):
                g = sdf2[sdf2["tam"]==t_val]
                st.markdown(f"#### 🟢 {t_val} Yeşil Eşleşme ({len(g)} Maç)")
                for _, row in g.iterrows():
                    render_match_card(row)

    elif st.session_state.active_tab_2 == "⚡ Otomatik Kayıt Ekle":
        st.markdown("### ⚡ Günlük Otomatik Maç Tarama ve Kayıt (İç Saha / Dış Saha)")
        st.markdown("Seçilen tarihteki iddaa bülteninde bulunan tüm maçları saat sırasına göre tek tek tarar. Yeterli geçmiş verisi olan maçları otomatik olarak tüm verilere kaydeder ve geçmiş veritabanıyla analiz ederek Tahmin Geçmişine düşürür.")
        
        c1, c2 = st.columns([1, 2])
        oto_tar2 = c1.date_input("📅 Bülten Tarihi", value=date.today(), key="oto2_tar")
        oto_mod2 = c2.multiselect("⚙️ İşlenecek Modlar", ["1️⃣ Ortak 5 Maç (Mod 1)", "2️⃣ Ev/Dep Ayrı (Mod 2)"], default=["2️⃣ Ev/Dep Ayrı (Mod 2)"], key="oto2_modlar")
        
        if st.button("🚀 Seçilen Tarihteki Maçları Çek ve Ekle", type="primary", use_container_width=True):
            secilenler = []
            if "1️⃣ Ortak 5 Maç (Mod 1)" in oto_mod2: secilenler.append(1)
            if "2️⃣ Ev/Dep Ayrı (Mod 2)" in oto_mod2: secilenler.append(2)
            
            if not secilenler:
                st.warning("Lütfen en az bir mod seçin.")
            else:
                if start_background_analysis(oto_tar2, secilenler):
                    st.toast("Arka plan analizi başlatıldı!")
                    st.rerun()
                else:
                    st.error("Zaten çalışan bir analiz var!")


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

    elif st.session_state.active_tab_2 == "📋 Tüm Veriler":
        # Üst Panel (Yenile / Sil)
        b1, b2, b3 = st.columns([1, 2, 3])
        if b1.button("🔄 Tabloyu Yenile", key="y2", use_container_width=True): st.rerun()
        if b2.button("🗑️ SADECE Örnek Verileri Sil", type="primary", key="sd2", use_container_width=True):
            ornek_sil_mod2()
            st.success("Test amacıyla yüklenen (Detaylı Mod) tüm sahte önek kayıtlar başarıyla silindi!")
            st.rerun()
        if b3.button("⚡ Eksik Skorları Çek (API)", key="oto2", use_container_width=True):
            with st.spinner("Skoru boş olan maçlar taranıyor, API puanları otomatik çekiliyor..."):
                gn = otomatize_skor_guncelle([1, 2])
                st.success(f"✓ Her iki veritabanı da tarandı ve toplam {gn} adet maçın skoru API'den güncellendi!")
                st.rerun()

        if b1.button("📉 Eksik Oranları Tamamla (API)", key="oto_oran2", use_container_width=True):
            with st.spinner("Oranı eksik olan maçlar taranıyor, API oranları otomatik çekiliyor..."):
                gn = otomatize_oran_guncelle([1, 2])
                st.success(f"✓ Toplam {gn} adet maçın oran bilgisi API'den çekilerek veritabanına eklendi!")
                st.rerun()
            
        with st.expander("⚠️ Tehlikeli İşlemler (Silme Seçenekleri)"):
            st.markdown("#### 📅 Tarih Bazlı Silme")
            d2_col1, d2_col2 = st.columns([2, 1])
            sil_tar2 = d2_col1.date_input("Silinecek Tarihi Seçin", value=date.today(), key="sil_tar2")
            if d2_col2.button("🗑️ Tarihe Göre Sil", type="primary", key="btn_sil_tar2", use_container_width=True):
                tarih_sil_mod2(sil_tar2)
                st.success(f"✅ {sil_tar2} tarihindeki tüm Mod 2 kayıtları silindi!")
                st.rerun()

            st.markdown("---")
            st.warning("BÜTÜN detaylı veritabanını ve bunlara bağlı Tahmin Geçmişini kalıcı olarak siler.")
            if st.button("💀 TÜM DETAYLI VERİLERİ VE TAHMİN GEÇMİŞİNİ KALICI OLARAK SİL", type="primary", key="nuke2", use_container_width=True):
                tumunu_sil_mod2()
                tahmin_tumunu_sil()
                st.success("✅ Sistem başarıyla sıfırlandı! Tüm detaylı mod verileri ve tahmin geçmişi kalıcı olarak silindi.")
                st.rerun()
                
        df2 = liste_mod2()
        search_v2 = st.text_input("🔍 Arşivde Ara (Takım)", placeholder="Takım ismi yazın...", key="s_v2")
        if search_v2 and not df2.empty:
            df2 = df2[df2["ev_takimi"].str.contains(search_v2, case=False, na=False) | 
                     df2["dep_takimi"].str.contains(search_v2, case=False, na=False)]
        
        if not df2.empty:
            ht_col = "sonuc_ht" if "sonuc_ht" in df2.columns else "sonuc_HT"
            ft_col = "sonuc_ft" if "sonuc_ft" in df2.columns else "sonuc_FT"
            
            st.info("💡 Tablodaki **İY** veya **MS** hücrelerine çift tıklayarak skoru doğrudan girebilirsiniz.")
            edited_df2 = st.data_editor(
                df2.drop(columns=["olusturulma"], errors="ignore"),
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "tarih": st.column_config.TextColumn("Tarih", disabled=True),
                    "ev_takimi": st.column_config.TextColumn("Ev Sahibi", disabled=True),
                    "dep_takimi": st.column_config.TextColumn("Deplasman", disabled=True),
                    ht_col: st.column_config.TextColumn("İY"),
                    ft_col: st.column_config.TextColumn("MS"),
                    "is_sample": None
                },
                disabled=["id", "tarih", "ev_takimi", "dep_takimi", "is_sample"],
                use_container_width=True,
                hide_index=True,
                key="ed_v2"
            )
            
            if "ed_v2" in st.session_state and st.session_state.ed_v2["edited_rows"]:
                st.markdown("---")
                if st.button("💾 Değişiklikleri Veritabanına Kaydet", key="save_v2", type="primary", use_container_width=True):
                    with st.status("Veriler güncelleniyor...", expanded=False) as status:
                        for idx_str, changes in st.session_state.ed_v2["edited_rows"].items():
                            idx = int(idx_str)
                            row_id = df2.iloc[idx]["id"]
                            new_ht = changes.get(ht_col, df2.iloc[idx][ht_col])
                            new_ft = changes.get(ft_col, df2.iloc[idx][ft_col])
                            guncelle_skor_mod2(row_id, new_ht, new_ft)
                        status.update(label="✅ Tüm değişiklikler kaydedildi!", state="complete")
                    st.success("Başarıyla güncellendi!")
                    st.rerun()
        
        c1, c2 = st.columns(2)
        with c1:
            st.empty()

    elif st.session_state.active_tab_2 == "📈 Tahmin Geçmişi":
        render_backtest_tab(2)

# ─── Mod 3 (Oran Eşleşme Analizi) ───
elif "3️⃣" in secilen_mod:
    st.markdown("<h1>⚽ Oran Eşleşme Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>API'den güncel maç oranlarını çekerek benzer oranlı geçmiş maçları analiz edin. <i>(Veritabanında oran verisi olan maçlar arasında arama yapılır)</i></p><hr>", unsafe_allow_html=True)
    
    # Oran Analizi için basit bir sekme yapısı
    tab1, tab2 = st.tabs(["🔍 Oran Analizi Yap", "📋 Oranlı Maç Arşivi"])
    
    with tab1:
        st.markdown("### 🔍 Oran Bazlı Geçmiş Taraması")
        c1, c2 = st.columns([1, 2])
        analiz_tar = c1.date_input("📅 Bülten Tarihi", value=date.today(), key="oran_tar")
        
        with st.spinner("Günün maçları ve oranlar çekiliyor..."):
            gunluk_maclar = fetch_daily_fixtures(analiz_tar.strftime("%Y-%m-%d"))
            # Bet365 oranlarını çekiyoruz (Sıklıkla standart kabul edilir)
            gunluk_oranlar = fetch_daily_odds(analiz_tar.strftime("%Y-%m-%d"))
            mac_opsiyonlar = get_fixture_options(gunluk_maclar, gunluk_oranlar)
            
        secilen_mac_lbl = st.selectbox("Analiz Edilecek Maçı Seçin (Oranlı)", ["Lütfen Seçin..."] + list(mac_opsiyonlar.keys()), key="oran_mac_sel")
        
        sub_c1, sub_c2 = st.columns([2, 1])
        tolerans = sub_c1.slider("Oran Toleransı (%)", 1, 30, 10, help="Oranların ne kadar yakın olması gerektiğini belirler. Örn: %10 toleransta 2.00 oran için 1.80-2.20 arası aranır.") / 100
        
        o1 = ox = o2 = None
        if secilen_mac_lbl != "Lütfen Seçin...":
            m_detay = mac_opsiyonlar[secilen_mac_lbl]
            o = m_detay.get("odds")
            
            if not o:
                st.warning("⚠️ Bu maç için API'den oran çekilemedi. Lütfen manuel girin veya başka bir maç seçin.")
                oc1, oc2, oc3 = st.columns(3)
                o1 = oc1.text_input("1 (Ev)", key="man_o1")
                ox = oc2.text_input("X (Ber)", key="man_ox")
                o2 = oc3.text_input("2 (Dep)", key="man_o2")
            else:
                st.success(f"✅ Seçilen Maç Oranları (Bet365): **1:** {o['1']} | **X:** {o['x']} | **2:** {o['2']}")
                o1, ox, o2 = o['1'], o['x'], o['2']
            
            if st.button("🔍 Benzer Oranlı Maçları Getir", type="primary", use_container_width=True):
                if not (o1 and ox and o2):
                    st.error("Lütfen oranları kontrol edin.")
                else:
                    # Mod 1 ve Mod 2 verilerini birleştirip oranlarına bakıyoruz
                    df1 = liste_mod1(); df2 = liste_mod2()
                    df_all = pd.concat([df1, df2]).drop_duplicates(subset=["id"]).reset_index(drop=True)
                    
                    sonuclar = []
                    for _, r in df_all.iterrows():
                        res = eslesme_hesapla_oran(o1, ox, o2, r, tolerans)
                        if res["tam"] >= 2: # En az 2 oran tolerans içinde olmalı
                            sht = r.get("sonuc_HT", r.get("sonuc_ht", "?")) or "?"
                            sft = r.get("sonuc_FT", r.get("sonuc_ft", "?")) or "?"
                            sonuclar.append({
                                "id": r["id"], "tarih": r["tarih"], "ev": r["ev_takimi"], "dep": r["dep_takimi"],
                                "sht": sht, "sft": sft, "tam": res["tam"], "oran": res["oran"],
                                "db_o1": r.get("odd_1","-"), "db_ox": r.get("odd_x","-"), "db_o2": r.get("odd_2","-")
                            })
                    
                    if not sonuclar:
                        st.warning("Kayıtlı maçlar arasında bu oranlara (%) tolerans dahilinde benzer maç bulunamadı.")
                    else:
                        st.success(f"🎯 Toplam **{len(sonuclar)}** adet benzer oranlı maç bulundu.")
                        render_analiz_panel(sonuclar, key_prefix="oran_res")
                        
                        st.markdown("#### 📋 Eşleşen Maç Detayları")
                        for rs in sorted(sonuclar, key=lambda x: x["tam"], reverse=True):
                            st.markdown(f"""
                            <div class="match-card">
                              <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                                <div><b>{rs['ev']} vs {rs['dep']}</b> <span style="color:#666; font-size:12px;">({rs['tarih']})</span></div>
                                <div style="background:{'#2adf7a33' if rs['tam']==3 else '#f0a50033'}; color:{'#2adf7a' if rs['tam']==3 else '#f0a500'}; padding:2px 8px; border-radius:10px; font-size:11px;">{rs['tam']}/3 Oran Eşleşti</div>
                              </div>
                              <div style="font-size:12px; color:#aaa; margin-bottom:5px;">
                                DB Oranlar: <b style="color:#fff;">{rs['db_o1']} - {rs['db_ox']} - {rs['db_o2']}</b>
                              </div>
                              <div style="background:#212133; padding:6px 10px; border-radius:6px; border-left:3px solid #ffcc00;">
                                🎯 <b>Biten Sonuç: İY {rs['sht']} / MS {rs['sft']}</b>
                              </div>
                            </div>
                            """, unsafe_allow_html=True)

    with tab2:
        st.markdown("### 📋 Veritabanındaki Oranlı Maçlar")
        df1 = liste_mod1(); df2 = liste_mod2()
        df_joined = pd.concat([df1, df2]).drop_duplicates(subset=["id"]).reset_index(drop=True)
        
        # Sadece oranı olanları filtreleyelim
        if not df_joined.empty:
            if "odd_1" not in df_joined.columns:
                df_joined["odd_1"] = ""
                df_joined["odd_x"] = ""
                df_joined["odd_2"] = ""

            df_with_odds = df_joined[df_joined["odd_1"].notna() & (df_joined["odd_1"] != "")].copy()
            if df_with_odds.empty:
                st.info("Henüz veritabanında oran bilgisi kaydedilmiş maç bulunmuyor.")
                st.caption("Not: Otomatik kayıt sırasında veya manuel eklemede oran bilgisi eklenmiş maçlar burada görünür.")
            else:
                st.dataframe(
                    df_with_odds[["id","tarih","ev_takimi","dep_takimi","sonuc_HT","sonuc_FT","odd_1","odd_x","odd_2"]],
                    column_config={
                        "odd_1": "1 Oran", "odd_x": "X Oran", "odd_2": "2 Oran",
                        "sonuc_HT": "İY", "sonuc_FT": "MS"
                    },
                    use_container_width=True, hide_index=True
                )
        else:
            st.info("Arşiv henüz boş.")

# ─── Çift Mod Karşılaştırma Sayfası ───
elif "🔀" in secilen_mod:
    st.markdown("<h1>🔀 Çift Mod Karşılaştırma</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#9999bb;'>Her iki modda da analiz edilmiş müsabakalar listelenir. <b>Bir müsabakaya tıkladığınızda Mod 1 ve Mod 2 eşleşmeleri yan yana tam ekran gösterilir.</b></p><hr>", unsafe_allow_html=True)

    tdf_all = tahmin_listele()
    if tdf_all.empty or "mod" not in tdf_all.columns:
        st.info("ℹ️ Henüz tahmin geçmişi yok.")
    else:
        tdf_all["mod"] = pd.to_numeric(tdf_all["mod"], errors="coerce")

        # ── GELİŞMİŞ FİLTRELEME PANELİ (Çift Mod - HIZLI) ──
        st.markdown("#### 🎛️ Arşiv Taraması (Optimize)")
        c1, c2 = st.columns([2, 4])
        
        # 1. Tarih Filtresi (İsteğe Bağlı)
        use_t_cift = c1.checkbox("📅 Tarih Filtresi", value=True, key="use_t_cift")
        cift_tarih_str = "Tümü"
        if use_t_cift:
            cift_tarih = c1.date_input("Analiz Tarihi", value=date.today(), key="cift_t_val", label_visibility="collapsed")
            cift_tarih_str = cift_tarih.strftime("%Y-%m-%d")
        
        cift_ara = c2.text_input("🔍 Takım Ara", placeholder="Hızlı takım arama...", key="cift_ara")

        mod1_df = tdf_all[tdf_all["mod"] == 1].copy()
        mod2_df = tdf_all[tdf_all["mod"] == 2].copy()

        # Her iki modda analiz edilmiş maçları bul (tarih+ev+dep eşleşmesi)
        merge_keys = ["tarih", "ev_takimi", "dep_takimi"]
        m1 = mod1_df[merge_keys + ["id", "eslesen_sayisi"]].rename(columns={"id": "id_mod1", "eslesen_sayisi": "eslesme_m1"})
        m2 = mod2_df[merge_keys + ["id", "eslesen_sayisi"]].rename(columns={"id": "id_mod2", "eslesen_sayisi": "eslesme_m2"})
        cift_df = m1.merge(m2, on=merge_keys).drop_duplicates(subset=["tarih", "ev_takimi", "dep_takimi"])

        # ── HIZLI FİLTRELEME ──
        if not cift_df.empty:
            if use_t_cift:
                cift_df = cift_df[cift_df["tarih"].astype(str) == cift_tarih_str]
            if cift_ara:
                cift_df = cift_df[cift_df["ev_takimi"].str.contains(cift_ara, case=False, na=False) |
                                  cift_df["dep_takimi"].str.contains(cift_ara, case=False, na=False)]

            # --- Sadece Gerektiğinde Detayları Çek (Performans İçin) ---
            if not cift_df.empty:
                st.markdown("---")
                q1, q2, q3 = st.columns([2, 2, 2])
                
                # 🟢 Yeşil Eşleşme Filtresi (Hassas)
                q_kural = q1.selectbox("🎯 Hassas Yeşil Filtresi", ["Herhangi", "Sadece (Tam)", "En Az", "En Fazla"], key="cift_q_k")
                q_adet = q1.number_input("Yeşil Sayısı", min_value=0, max_value=10, value=2 if q_kural != "Herhangi" else 0, key="cift_q_a")
                q_hedef = q2.selectbox("📍 Hedef Mod", ["İkisi De", "Mod 1", "Mod 2"], key="cift_q_target")

                if q_kural != "Herhangi":
                    def get_yesil_lite(id_val, mode):
                        try:
                            row = tdf_all[(tdf_all["id"] == id_val) & (tdf_all["mod"] == mode)]
                            if row.empty: return 0
                            detay = row.iloc[0]["eslesen_detay"]
                            if not detay: return 0
                            if isinstance(detay, str): detay = json.loads(detay)
                            return max((int(r.get("tam", 0)) for r in detay), default=0)
                        except: return 0

                    cift_df["yesil_m1"] = cift_df["id_mod1"].apply(get_yesil_lite, args=(1,))
                    cift_df["yesil_m2"] = cift_df["id_mod2"].apply(get_yesil_lite, args=(2,))
                    
                    def uygula_q(val, target):
                        v_int = int(val); t_int = int(target)
                        if q_kural == "Sadece (Tam)": return v_int == t_int
                        if q_kural == "En Az": return v_int >= t_int
                        if q_kural == "En Fazla": return v_int <= t_int
                        return True
                    
                    if q_hedef == "Mod 1":
                        cift_df = cift_df[cift_df["yesil_m1"].apply(uygula_q, args=(q_adet,))]
                    elif q_hedef == "Mod 2":
                        cift_df = cift_df[cift_df["yesil_m2"].apply(uygula_q, args=(q_adet,))]
                    else:
                        cift_df = cift_df[cift_df["yesil_m1"].apply(uygula_q, args=(q_adet,)) & 
                                          cift_df["yesil_m2"].apply(uygula_q, args=(q_adet,))]
                
                q3.info(f"🔍 {len(cift_df)} kriterlere uygun Çift Eşleşme.")

        cift_df = cift_df.sort_values("id_mod1", ascending=False).reset_index(drop=True)

        if cift_df.empty:
            st.info(f"ℹ️ {cift_tarih_str} tarihinde her iki modda da analiz edilmiş müsabaka bulunamadı.")
            st.caption("Bir müsabakanın burada görünmesi için hem Mod 1 hem Mod 2 Analiz Yap sekmesinden analiz edilmiş olması gerekmektedir.")
        else:
            # Render öncesi yeşil badge statülerini de ekleyelim (Eğer filtreden gelmediyse)
            def get_yesil_lite_raw(id_val, mode):
                try:
                    row = tdf_all[(tdf_all["id"] == id_val) & (tdf_all["mod"] == mode)]
                    if row.empty: return 0
                    detay = row.iloc[0]["eslesen_detay"]
                    if not detay: return 0
                    if isinstance(detay, str): detay = json.loads(detay)
                    return max((int(r.get("tam", 0)) for r in detay), default=0)
                except: return 0

            st.markdown(f"#### 🎯 {cift_tarih_str} Tarihinde Her İki Modda Analiz Edilenler: **{len(cift_df)} Maç**")
            st.markdown("---")

            for _, row in cift_df.iterrows():
                c_ev = row["ev_takimi"]; c_dep = row["dep_takimi"]; c_tarih = row["tarih"]
                c_m1 = int(row["eslesme_m1"]); c_m2 = int(row["eslesme_m2"])
                c_id1 = int(row["id_mod1"]); c_id2 = int(row["id_mod2"])
                c_sht = row.get("sht", "") or ""; c_sft = row.get("sft", "") or ""
                
                # Kartta görünecek kalite statüsü
                y_m1 = row["yesil_m1"] if "yesil_m1" in row else get_yesil_lite_raw(c_id1, 1)
                y_m2 = row["yesil_m2"] if "yesil_m2" in row else get_yesil_lite_raw(c_id2, 2)

                if c_sht and c_sft and c_sht not in ["", "?"]:
                    durum_ikon = "🎯"; durum_renk = "#2adf7a"
                    durum_text = f"İY {c_sht} / MS {c_sft}"
                else:
                    durum_ikon = "⏳"; durum_renk = "#f0a500"
                    durum_text = "Bekleniyor"

                col_info, col_btn = st.columns([6, 1])
                with col_info:
                    st.markdown(f"""
                    <div style="background:#1a1a2e; border:1px solid #2d2d4a; border-radius:10px; padding:12px 16px; margin-bottom:8px;">
                      <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                          <span style="font-weight:bold; font-size:15px;">🏠 {c_ev} <span style="color:#555">vs</span> ✈️ {c_dep}</span>
                          <span style="color:#555; font-size:12px; margin-left:8px;">({c_tarih})</span>
                        </div>
                        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                          <span style="background:#1a2035; border:1px solid #3b3bff55; color:#7b9eff; padding:2px 10px; border-radius:10px; font-size:11px; font-weight:bold;">🔵 M1: {c_m1} eşt. (⭐ {y_m1}Y)</span>
                          <span style="background:#1e1a35; border:1px solid #7b5ef555; color:#b09eff; padding:2px 10px; border-radius:10px; font-size:11px; font-weight:bold;">🟣 M2: {c_m2} eşt. (⭐ {y_m2}Y)</span>
                          <span style="color:{durum_renk}; font-size:13px;">{durum_ikon} {durum_text}</span>
                        </div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_btn:
                    if st.button("🔀 Karşılaştır", key=f"cift_btn_{c_id1}_{c_id2}", use_container_width=True, type="primary"):
                        goster_cift_mod_detayi(c_ev, c_dep, c_tarih, c_id1, c_id2)
