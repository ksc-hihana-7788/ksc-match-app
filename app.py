import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import base64
from io import BytesIO
from PIL import Image, ImageOps

# --- 1. ページ設定 ---
st.set_page_config(page_title="KSC試合管理ツール", layout="wide")

# --- 2. スプレッドシート設定 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1QmQ5uw5HI3tHmYTC29uR8jh1IeSnu4Afn7a4en7yvLc/edit#gid=0"

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
    
    try:
        data = ws_list.get_all_records()
    except Exception:
        data = []
    
    if not data:
        df = pd.DataFrame({
            "No": range(1, 101), "カテゴリー": ["U12"] * 100,
            "日時": [date.today().isoformat()] * 100, "対戦相手": [""] * 100,
            "試合場所": [""] * 100, "試合分類": [""] * 100, "備考": [""] * 100
        })
    else:
        df = pd.DataFrame(data)
    
    # 型の整理
    if 'No' in df.columns: df['No'] = pd.to_numeric(df['No'])
    if '日時' in df.columns: 
        df['日時'] = pd.to_datetime(df['日時'], errors='coerce').dt.date
    
    # UI用制御列
    df['詳細'] = False
    df['写真(画像)'] = False
    
    target_order = ['詳細', 'No', 'カテゴリー', '日時', '対戦相手', '試合場所', '試合分類', '備考', '写真(画像)']
    return df[[c for c in target_order if c in df.columns]]

def save_list(df):
    """スプレッドシートへの完全な自動保存"""
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        ws = sh.get_worksheet(0)
        
        df_save = df.copy()
        if '日時' in df_save.columns:
            df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x))
        
        # 制御列を除外して保存
        drop_cols = ["詳細", "写真(画像)"]
        df_save = df_save.drop(columns=[c for c in drop_cols if c in df_save.columns])
        
        # 確実に上書きするためにクリアしてから更新
        ws.clear()
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except Exception as e:
        st.error(f"自動保存エラー: {e}")

# --- 3. 認証処理 ---
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if not st.session_state.authenticated:
    st.title("⚽ KSCログイン")
    u, p = st.text_input("ID"), st.text_input("PASS", type="password")
    if st.button("ログイン"):
        if u == st.secrets["LOGIN_ID"] and p == st.secrets["LOGIN_PASS"]:
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("IDまたはパスワードが違います")
    st.stop()

# --- 4. セッション管理 ---
if 'df_list' not in st.session_state: 
    st.session_state.df_list = load_data()
if 'selected_no' not in st.session_state: st.session_state.selected_no = None
if 'media_no' not in st.session_state: st.session_state.media_no = None

def on_data_change():
    """データエディタの変更を即座に反映して保存"""
    changes = st.session_state["editor"]
    
    # 変更があった行の処理
    for row_idx, edit_values in changes["edited_rows"].items():
        # フィルター後の表示インデックスから、元のデータの正しい行を特定
        actual_index = st.session_state.current_display_df.index[row_idx]
        actual_no = st.session_state.df_list.at[actual_index, "No"]
        
        # 画面遷移フラグのチェック
        if edit_values.get("詳細") is True:
            st.session_state.selected_no = int(actual_no)
            return
        if edit_values.get("写真(画像)") is True:
            st.session_state.media_no = int(actual_no)
            return
            
        # 値の反映
        for col, val in edit_values.items():
            if col not in ["詳細", "写真(画像)"]:
                st.session_state.df_list.at[actual_index, col] = val
    
    # 反映が終わったら即座にスプレッドシートへ保存
    save_list(st.session_state.df_list)

# --- 5. メイン画面制御 ---
if st.session_state.media_no is not None:
    no = st.session_state.media_no
    st.title(f"🖼️ 写真管理 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.media_no = None
        st.rerun()
    
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    try:
        ws_media = sh.worksheet("media_storage")
    except:
        ws_media = sh.add_worksheet(title="media_storage", rows="2000", cols="3")
        ws_media.append_row(["match_no", "filename", "base64_data"])
    
    uploaded_file = st.file_uploader("スマホ写真を選択", type=["png", "jpg", "jpeg"])
    if uploaded_file and st.button("アップロード実行"):
        with st.spinner("圧縮中..."):
            try:
                img = Image.open(uploaded_file)
                img = ImageOps.exif_transpose(img).convert("RGB")
                quality, width = 70, 800
                while True:
                    img_temp = img.copy()
                    img_temp.thumbnail((width, width))
                    buf = BytesIO()
                    img_temp.save(buf, format="JPEG", quality=quality, optimize=True)
                    encoded = base64.b64encode(buf.getvalue()).decode()
                    if len(encoded) < 40000: break
                    width -= 100; quality -= 10
                    if quality < 5 or width < 200: break
                ws_media.append_row([str(no), uploaded_file.name, encoded])
                st.success("写真を保存しました")
                st.rerun()
            except Exception as e: st.error(f"エラー: {e}")

    match_photos = [r for r in ws_media.get_all_records() if str(r['match_no']) == str(no)]
    if match_photos:
        cols = st.columns(3)
        for idx, item in enumerate(match_photos):
            with cols[idx % 3]:
                st.image(base64.b64decode(item['base64_data']), use_container_width=True)
                if st.button("削除", key=f"del_{idx}"):
                    cell = ws_media.find(item['base64_data'])
                    ws_media.delete_rows(cell.row)
                    st.rerun()
    else: st.info("写真がありません。")

elif st.session_state.selected_no is not None:
    no = st.session_state.selected_no
    st.title(f"📝 試合結果入力 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.rerun()
    
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    try: ws_res = sh.worksheet("results")
    except:
        ws_res = sh.add_worksheet(title="results", rows="100", cols="2")
        ws_res.append_row(["key", "data"])

    res_raw = ws_res.acell("A2").value
    all_results = json.loads(res_raw) if res_raw else {}
    
    for i in range(1, 11):
        rk = f"res_{no}_{i}"
        sd = all_results.get(rk, {"score": "", "scorers": [""] * 10})
        with st.expander(f"第 {i} 試合"):
            sc = st.text_input("スコア", value=sd["score"], key=f"s_{rk}")
            sc_input = st.text_area("得点者", value=", ".join([s for s in sd["scorers"] if s]), key=f"p_{rk}")
            if st.button("保存", key=f"b_{rk}"):
                new_s = [s.strip() for s in sc_input.split(",") if s.strip()] + [""] * 10
                all_results[rk] = {"score": sc, "scorers": new_s[:10]}
                ws_res.update_acell("A2", json.dumps(all_results, ensure_ascii=False))
                st.success("保存しました")

else:
    st.title("⚽ KSC試合管理一覧")
    c1, c2 = st.columns([2, 1])
    with c1: search_query = st.text_input("🔍 検索")
    with c2: cat_filter = st.selectbox("📅 絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])
    
    df = st.session_state.df_list.copy()
    if cat_filter != "すべて": df = df[df["カテゴリー"] == cat_filter]
    if search_query: 
        df = df[df.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    
    # フィルター適用後のDFを保持（index管理のため）
    st.session_state.current_display_df = df
    
    st.data_editor(
        df, 
        hide_index=True, 
        column_config={
            "詳細": st.column_config.CheckboxColumn("結果入力", width="small"),
            "No": st.column_config.NumberColumn(disabled=True, width="small"),
            "写真(画像)": st.column_config.CheckboxColumn("写真管理", width="small"),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"], width="small"),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD")
        }, 
        use_container_width=True, 
        key="editor", 
        on_change=on_data_change
    )
