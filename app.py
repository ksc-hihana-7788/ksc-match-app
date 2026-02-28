import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

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
            "詳細": [False] * 100,
            "No": range(1, 101),
            "カテゴリー": ["U12"] * 100,
            "日時": [date.today().isoformat()] * 100,
            "対戦相手": [""] * 100,
            "試合場所": [""] * 100,
            "試合分類": [""] * 100,
            "備考": [""] * 100
        })
    else:
        df = pd.DataFrame(data)
    
    # 全ての「詳細」チェックボックスを強制的にFalseで初期化（バグ防止）
    df['詳細'] = False
    # 日時を日付型に変換
    df['日時'] = pd.to_datetime(df['日時']).dt.date
    
    # --- ★重要：列の並び順を左から「詳細」にする ---
    cols = ['詳細', 'No', 'カテゴリー', '日時', '対戦相手', '試合場所', '試合分類', '備考']
    # 存在する列だけで並び替え（エラー防止）
    df = df[[c for c in cols if c in df.columns]]
    
    return df

def save_list(df):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws = sh.get_worksheet(0)
    df_save = df.copy()
    # 保存用に日付を文字列に戻す
    df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x))
    # スプレッドシートへ書き込み（「詳細」列は保存不要なら落としても良いが、管理上含めて保存）
    ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())

# --- 3. 認証処理 ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("KSC試合管理 ログイン")
    u = st.text_input("ID")
    p = st.text_input("PASS", type="password")
    if st.button("ログイン"):
        if u == st.secrets["LOGIN_ID"] and p == st.secrets["LOGIN_PASS"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("IDまたはパスワードが違います")
    st.stop()

# --- 4. データ管理ロジック ---
if 'df_list' not in st.session_state:
    st.session_state.df_list = load_data()

if 'selected_no' not in st.session_state:
    st.session_state.selected_no = None

def on_data_change():
    changes = st.session_state["editor"]
    
    # 編集内容の反映
    for row_idx, edit_values in changes["edited_rows"].items():
        actual_no = st.session_state.current_display_df.iloc[row_idx]["No"]
        
        # 「詳細」にチェックが入った場合
        if edit_values.get("詳細") == True:
            st.session_state.selected_no = int(actual_no)
            # 画面遷移前にチェックを解除
            st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, "詳細"] = False
            return 
        
        # その他のデータの更新
        for col, val in edit_values.items():
            if col != "詳細":
                st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, col] = val
    
    save_list(st.session_state.df_list)
    st.toast("スプレッドシートを更新しました ☁️")

# --- 5. 一覧画面 ---
if st.session_state.selected_no is None:
    st.title("⚽ KSC試合管理一覧")

    # 検索・フィルタ
    c1, c2 = st.columns([2, 1])
    with c1:
        search_query = st.text_input("🔍 キーワード検索", "")
    with c2:
        cat_filter = st.selectbox("📅 カテゴリー絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])

    # 表示データの抽出
    df = st.session_state.df_list.copy()
    if cat_filter != "すべて":
        df = df[df["カテゴリー"] == cat_filter]
    if search_query:
        df = df[df.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    
    st.session_state.current_display_df = df

    # データエディタ（詳細を左側に配置した設定）
    st.data_editor(
        df,
        hide_index=True,
        column_config={
            "詳細": st.column_config.CheckboxColumn("入力", default=False),
            "No": st.column_config.NumberColumn(disabled=True, width="small"),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"], width="small"),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD", width="medium"),
            "対戦相手": st.column_config.TextColumn("対戦相手", width="medium"),
