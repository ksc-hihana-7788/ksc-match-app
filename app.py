import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import base64
from io import BytesIO
from PIL import Image # 画像圧縮用

# --- 1. ページ設定 ---
st.set_page_config(page_title="KSC試合管理ツール", layout="wide")

# --- 2. スプレッドシート設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1QmQ5uw5HI3tHmYTC29uR8jh1IeSnu4Afn7a4en7yvLc/edit?gid=0#gid=0"

def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_info = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        st.stop()

def load_data():
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws_list = sh.get_worksheet(0)
    data = ws_list.get_all_records()
    
    if not data:
        df = pd.DataFrame({
            "詳細": [False] * 100, "No": range(1, 101), "カテゴリー": ["U12"] * 100,
            "日時": [date.today().isoformat()] * 100, "対戦相手": [""] * 100,
            "試合場所": [""] * 100, "試合分類": [""] * 100, "備考": [""] * 100, "動画＆画像": [False] * 100
        })
    else:
        df = pd.DataFrame(data)
    
    if "選択" in df.columns: df = df.drop(columns=["選択"])
    df['詳細'] = False
    df['動画＆画像'] = False
    if '日時' in df.columns: df['日時'] = pd.to_datetime(df['日時']).dt.date
    
    target_order = ['詳細', 'No', 'カテゴリー', '日時', '対戦相手', '試合場所', '試合分類', '備考', '動画＆画像']
    actual_cols = [col for col in target_order if col in df.columns]
    return df[actual_cols]

def save_list(df):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws = sh.get_worksheet(0)
    df_save = df.copy()
    if '日時' in df_save.columns:
        df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x))
    drop_cols = [c for c in ["詳細", "動画＆画像"] if c in df_save.columns]
    df_save = df_save.drop(columns=drop_cols)
    ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())

# --- 3. 認証処理 ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("KSC試合管理 ログイン")
    u, p = st.text_input("ID"), st.text_input("PASS", type="password")
    if st.button("ログイン"):
        if u == st.secrets["LOGIN_ID"] and p == st.secrets["LOGIN_PASS"]:
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("IDまたはパスワードが違います")
    st.stop()

# --- 4. セッション管理 ---
if 'df_list' not in st.session_state: st.session_state.df_list = load_data()
if 'selected_no' not in st.session_state: st.session_state.selected_no = None
if 'media_no' not in st.session_state: st.session_state.media_no = None

def on_data_change():
    changes = st.session_state["editor"]
    for row_idx, edit_values in changes["edited_rows"].items():
        actual_no = st.session_state.current_display_df.iloc[row_idx]["No"]
        if edit_values.get("詳細") == True:
            st.session_state.selected_no = int(actual_no)
            st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, "詳細"] = False
            return 
        if edit_values.get("動画＆画像") == True:
            st.session_state.media_no = int(actual_no)
            st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, "動画＆画像"] = False
            return
        for col, val in edit_values.items():
            if col not in ["詳細", "動画＆画像"]:
                st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, col] = val
    save_list(st.session_state.df_list)

# --- 5. メイン画面制御 ---
# A. 動画＆画像画面
if st.session_state.media_no is not None:
    no = st.session_state.media_no
    st.title(f"📁 メディア管理 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.media_no = None
        st.rerun()
    
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    try: ws_res = sh.get_worksheet(1)
    except: ws_res = sh.add_worksheet(title="results", rows="100", cols="2")
    
    res_raw = ws_res.acell("B2").value
    all_media = json.loads(res_raw) if res_raw else {}
    match_media = all_media.get(str(no), [])

    uploaded_file = st.file_uploader("画像/動画を選択 (画像は自動圧縮されます)", type=["png", "jpg", "jpeg", "mp4"])
    if uploaded_file:
        if st.button("アップロード実行"):
            with st.spinner("処理中..."):
                file_type = uploaded_file.type
                if "image" in file_type:
                    img = Image.open(uploaded_file)
                    img = img.convert("RGB")
                    img.thumbnail((800, 800)) # サイズ縮小
                    buf = BytesIO()
                    img.save(buf, format="JPEG", quality=60) # 圧縮
                    encoded = base64.b64encode(buf.getvalue()).decode()
                else:
                    encoded = base64.b64encode(uploaded_file.read()).decode()
                
                match_media.append({"name": uploaded_file.name, "type": file_type, "data": encoded})
                all_media[str(no)] = match_media
                try:
                    ws_res.update_acell("B2", json.dumps(all_media))
                    st.success("成功！")
                    st.rerun()
                except Exception:
                    st.error("エラー：ファイルが大きすぎてスプレッドシートの制限を超えました。より小さいファイルを選択してください。")

    st.subheader("保存済みメディア")
    if match_media:
        cols = st.columns(3)
        for idx, item in enumerate(match_media):
            with cols[idx % 3]:
                st.caption(item['name'])
                data = base64.b64decode(item['data'])
                if "image" in item['type']: st.image(data)
                else: st.video(data)
                if st.button("削除", key=f"del_{idx}"):
                    match_media.pop(idx)
                    all_media[str(no)] = match_media
                    ws_res.update_acell("B2", json.dumps(all_media))
                    st.rerun()

# B. 詳細入力画面 (既存維持)
elif st.session_state.selected_no is not None:
    no = st.session_state.selected_no
    st.title(f"📝 試合結果入力 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.session_state.df_list = load_data()
        st.rerun()
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws_res = sh.get_worksheet(1)
    res_raw = ws_res.acell("A2").value
    all_results = json.loads(res_raw) if res_raw else {}
    for i in range(1, 11): # 10試合分に整理
        rk = f"res_{no}_{i}"
        sd = all_results.get(rk, {"score": "", "scorers": [""] * 10})
        with st.expander(f"第 {i} 試合"):
            sc = st.text_input("スコア", value=sd["score"], key=f"s_{rk}")
            sc_input = st.text_area("得点者", value=", ".join([s for s in sd["scorers"] if s]), key=f"p_{rk}")
            if st.button("保存", key=f"b_{rk}"):
                new_s = [s.strip() for s in sc_input.split(",") if s.strip()] + [""] * 10
                all_results[rk] = {"score": sc, "scorers": new_s[:10]}
                ws_res.update_acell("A2", json.dumps(all_results, ensure_ascii=False))
                st.rerun()

# C. 一覧画面 (既存維持)
else:
    st.title("⚽ KSC試合管理一覧")
    c1, c2 = st.columns([2, 1])
    with c1: search_query = st.text_input("🔍 検索")
    with c2: cat_filter = st.selectbox("📅 絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])
    df = st.session_state.df_list.copy()
    if cat_filter != "すべて": df = df[df["カテゴリー"] == cat_filter]
    if search_query: df = df[df.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    st.session_state.current_display_df = df
    st.data_editor(df, hide_index=True, column_config={
        "詳細": st.column_config.CheckboxColumn("結果", width="small"),
        "No": st.column_config.NumberColumn(disabled=True, width="small"),
        "動画＆画像": st.column_config.CheckboxColumn("メディア", width="small"),
        "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"], width="small"),
    }, use_container_width=True, key="editor", on_change=on_data_change)
