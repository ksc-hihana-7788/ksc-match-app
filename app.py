import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- ページ設定 ---
st.set_page_config(page_title="KSC試合管理ツール", layout="wide")

# --- スプレッドシート設定 ---
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
            "選択": [False] * 100,
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
    
    # 日時を日付型に変換
    df['日時'] = pd.to_datetime(df['日時']).dt.date
    return df

def save_list(df):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws = sh.get_worksheet(0)
    df_save = df.copy()
    # 保存用に日付を文字列に戻す
    df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x))
    ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())

# --- 認証 ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("KSC試合管理 ログイン")
    u = st.text_input("ID")
    p = st.text_input("PASS", type="password")
    if st.button("ログイン"):
        if u == "KSC" and p == "kuma2019":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("IDまたはパスワードが違います")
    st.stop()

# --- データ初期ロード ---
if 'df_list' not in st.session_state:
    st.session_state.df_list = load_data()

if 'selected_no' not in st.session_state:
    st.session_state.selected_no = None

# --- エラー防止のための改善されたハンドラ ---
def on_data_change():
    # エディタの変更内容を取得
    changes = st.session_state["editor"]
    
    # 1. 編集された行の反映
    for row_idx, edit_values in changes["edited_rows"].items():
        # 表示中のデータ(current_display_df)から、該当行の「No」を特定する
        # これにより絞り込み中でも正しい行を更新できる
        actual_no = st.session_state.current_display_df.iloc[row_idx]["No"]
        
        # 詳細画面への遷移（選択にチェックが入った場合）
        if edit_values.get("選択") == True:
            st.session_state.selected_no = int(actual_no)
            # 遷移するので、元データのチェックは外しておく
            st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, "選択"] = False
        
        # それ以外の項目の更新
        for col, val in edit_values.items():
            if col != "選択":
                st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, col] = val
    
    # 保存実行
    save_list(st.session_state.df_list)
    st.toast("スプレッドシートを更新しました ☁️")

# --- 1. 一覧画面 ---
if st.session_state.selected_no is None:
    st.title("⚽ KSC試合管理一覧")

    # 検索・フィルタ
    c1, c2 = st.columns([2, 1])
    with c1:
        search_query = st.text_input("🔍 キーワード検索", "")
    with c2:
        cat_filter = st.selectbox("📅 カテゴリー絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])

    # 表示用データの抽出
    df = st.session_state.df_list.copy()
    if cat_filter != "すべて":
        df = df[df["カテゴリー"] == cat_filter]
    if search_query:
        df = df[df.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    
    # ハンドラが参照できるようにセッションに保存
    st.session_state.current_display_df = df

    # データエディタ
    st.data_editor(
        df,
        hide_index=True,
        column_config={
            "選択": st.column_config.CheckboxColumn("詳細"),
            "No": st.column_config.NumberColumn(disabled=True),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"]),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD"),
        },
        use_container_width=True,
        key="editor",
        on_change=on_data_change
    )

    st.divider()
    st.markdown(
        '<button onclick="window.print()" style="width:100%; height:40px; border-radius:8px; border:1px solid #ddd; background-color:#ffffff; cursor:pointer; font-weight:bold;">📄 一覧をPDF出力 / 印刷</button>', 
        unsafe_allow_html=True
    )

# --- 2. 詳細入力画面 ---
else:
    # (詳細画面のコードは以前のものを維持)
    no = st.session_state.selected_no
    match_info = st.session_state.df_list[st.session_state.df_list["No"] == no].iloc[0]
    
    st.title(f"📝 試合結果入力 (No.{no})")
    st.info(f"**{match_info['カテゴリー']}** | {match_info['日時']} | vs {match_info['対戦相手']}")

    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.rerun()

    st.divider()
    # 簡易的に結果をスプレッドシートの別シートから読み書きする部分は維持
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    try:
        ws_res = sh.get_worksheet(1)
    except:
        ws_res = sh.add_worksheet(title="results", rows="100", cols="2")
    
    res_raw = ws_res.acell("A2").value
    all_results = json.loads(res_raw) if res_raw else {}
    
    for i in range(1, 16):
        rk = f"res_{no}_{i}"
        sd = all_results.get(rk, {"score": "", "scorers": [""] * 10})
        with st.expander(f"第 {i} 試合 {'✅ 保存済' if rk in all_results else ''}"):
            sc = st.text_input("スコア", value=sd["score"], key=f"s_{rk}")
            scorers_str = ", ".join([s for s in sd["scorers"] if s])
            sc_input = st.text_area("得点者 (カンマ区切り)", value=scorers_str, key=f"p_{rk}")
            
            if st.button("保存", key=f"b_{rk}"):
                new_s = [s.strip() for s in sc_input.split(",") if s.strip()]
                new_s += [""] * (10 - len(new_s))
                all_results[rk] = {"score": sc, "scorers": new_s[:10]}
                ws_res.update_acell("A
