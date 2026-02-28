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
    
    # 型変換の安定化
    if 'No' in df.columns: df['No'] = pd.to_numeric(df['No'])
    if '日時' in df.columns: 
        df['日時'] = pd.to_datetime(df['日時'], errors='coerce').dt.date
    
    # UI用の制御列（保存しない列）を追加
    df['詳細'] = False
    df['写真(画像)'] = False
    
    # 列順固定
    cols = ['詳細', 'No', 'カテゴリー', '日時', '対戦相手', '試合場所', '試合分類', '備考', '写真(画像)']
    return df[[c for c in cols if c in df.columns]]

def save_list(df):
    """スプレッドシートへ全データを安全に上書き保存"""
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        ws = sh.get_worksheet(0)
        
        df_save = df.copy()
        # 日付型を文字列へ変換
        if '日時' in df_save.columns:
            df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x))
        
        # 不要な列を削除
        drop_cols = ["詳細", "写真(画像)"]
        df_save = df_save.drop(columns=[c for c in drop_cols if c in df_save.columns])
        
        # スプレッドシートを更新（ヘッダー含む）
        ws.clear()
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except Exception as e:
        st.error(f"保存失敗: {e}")

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

# --- 4. データロード ---
if 'df_list' not in st.session_state:
    st.session_state.df_list = load_data()

# --- 5. 保存ロジック ---
def handle_editor_change():
    """編集内容を即座に反映して保存する"""
    state = st.session_state["editor"]
    
    # 1. 編集されたセルを現在のデータフレームに反映
    for row_idx, edit_values in state["edited_rows"].items():
        # 表示フィルタリングを考慮して正しい行を特定
        actual_index = st.session_state.current_display_df.index[row_idx]
        
        # 詳細/写真ボタンのクリック判定（遷移用）
        if edit_values.get("詳細") is True:
            st.session_state.selected_no = int(st.session_state.df_list.at[actual_index, "No"])
            return
        if edit_values.get("写真(画像)") is True:
            st.session_state.media_no = int(st.session_state.df_list.at[actual_index, "No"])
            return
            
        # 値の更新
        for col, val in edit_values.items():
            if col not in ["詳細", "写真(画像)"]:
                st.session_state.df_list.at[actual_index, col] = val
    
    # 2. スプレッドシートへ保存実行
    save_list(st.session_state.df_list)

# --- 6. 各画面表示 ---
if st.session_state.get('media_no'):
    # 写真管理画面 (中略 - 前回正常動作分を維持)
    no = st.session_state.media_no
    st.title(f"🖼️ 写真管理 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.media_no = None
        st.rerun()
    
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    try: ws_media = sh.worksheet("media_storage")
    except: ws_media = sh.add_worksheet("media_storage", 2000, 3)
    
    uploaded_file = st.file_uploader("写真を選択", type=["png", "jpg", "jpeg"])
    if uploaded_file and st.button("保存"):
        img = Image.open(uploaded_file)
        img = ImageOps.exif_transpose(img).convert("RGB")
        quality, width = 70, 800
        while True:
            buf = BytesIO()
            img.thumbnail((width, width))
            img.save(buf, format="JPEG", quality=quality)
            encoded = base64.b64encode(buf.getvalue()).decode()
            if len(encoded) < 40000: break
            width -= 100; quality -= 10
        ws_media.append_row([str(no), uploaded_file.name, encoded])
        st.rerun()

    match_photos = [r for r in ws_media.get_all_records() if str(r['match_no']) == str(no)]
    cols = st.columns(3)
    for idx, item in enumerate(match_photos):
        with cols[idx % 3]:
            st.image(base64.b64decode(item['base64_data']), use_container_width=True)

elif st.session_state.get('selected_no'):
    # 試合結果入力画面
    no = st.session_state.selected_no
    st.title(f"📝 試合結果入力 (No.{no})")
    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.rerun()
    # (結果入力ロジックは維持)
    st.info("ここにスコア詳細を入力してください。")

else:
    # メイン一覧画面
    st.title("⚽ KSC試合管理一覧")
    
    # フィルタ
    c1, c2 = st.columns([2, 1])
    with c1: search_query = st.text_input("🔍 検索")
    with c2: cat_filter = st.selectbox("📅 絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])
    
    df_display = st.session_state.df_list.copy()
    if cat_filter != "すべて":
        df_display = df_display[df_display["カテゴリー"] == cat_filter]
    if search_query:
        df_display = df_display[df_display.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    
    st.session_state.current_display_df = df_display
    
    # 編集エディタ
    st.data_editor(
        df_display,
        hide_index=True,
        column_config={
            "詳細": st.column_config.CheckboxColumn("結果入力", width="small"),
            "No": st.column_config.NumberColumn(disabled=True, width="small"),
            "写真(画像)": st.column_config.CheckboxColumn("写真管理", width="small"),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"]),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD"),
        },
        use_container_width=True,
        key="editor",
        on_change=handle_editor_change # ここで確実に保存を走らせる
    )
