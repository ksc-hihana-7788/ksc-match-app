import streamlit as st
import pandas as pd
from datetime import date, datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- ページ設定 ---
st.set_page_config(page_title="KSC試合管理ツール", layout="wide")

# --- スプレッドシートのURL ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1QmQ5uw5HI3tHmYTC29uR8jh1IeSnu4Afn7a4en7yvLc/edit?gid=0#gid=0"

# --- 接続設定 ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_info = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"認証エラー: {e}")
        st.stop()

# --- データ読み書き ---
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
        ws_list.update([df.columns.values.tolist()] + df.values.tolist())
    else:
        df = pd.DataFrame(data)
    
    try:
        ws_res = sh.get_worksheet(1)
    except:
        ws_res = sh.add_worksheet(title="results", rows="100", cols="2")
        ws_res.update_acell("A1", "json_data")
        
    res_raw = ws_res.acell("A2").value
    results = json.loads(res_raw) if res_raw else {}
    return df, results

def save_list(df):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws = sh.get_worksheet(0)
    df_save = df.copy()
    # 日付オブジェクトを文字列に変換
    df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else x)
    ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())

def save_res(results):
    client = get_gspread_client()
    sh = client.open_by_url(SPREADSHEET_URL)
    ws = sh.get_worksheet(1)
    ws.update_acell("A2", json.dumps(results, ensure_ascii=False))

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
            st.error("不整合")
    st.stop()

# --- メイン処理 ---
if 'df_list' not in st.session_state:
    st.session_state.df_list, st.session_state.results = load_data()

# 詳細画面への遷移管理
if 'selected_no' not in st.session_state:
    st.session_state.selected_no = None

# --- 一覧画面 ---
if st.session_state.selected_no is None:
    st.title("⚽ KSC試合管理一覧")

    # --- 検索・フィルタエリア ---
    col1, col2 = st.columns([2, 1])
    with col1:
        search_query = st.text_input("🔍 キーワード検索 (相手、場所、備考など)", "")
    with col2:
        category_filter = st.selectbox("📅 カテゴリー絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])

    # フィルタリング処理
    display_df = st.session_state.df_list.copy()
    if category_filter != "すべて":
        display_df = display_df[display_df["カテゴリー"] == category_filter]
    if search_query:
        display_df = display_df[display_df.apply(lambda row: search_query.lower() in row.astype(str).str.lower().values, axis=1)]

    # データエディタ表示
    st.info("💡 カテゴリーや日時はセルをクリックして変更できます")
    edited_df = st.data_editor(
        display_df,
        hide_index=True,
        column_config={
            "選択": st.column_config.CheckboxColumn("選択"),
            "No": st.column_config.NumberColumn(disabled=True),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"], required=True),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD", required=True),
        },
        use_container_width=True,
        key="editor"
    )

    # 保存ボタン（変更があった場合のみ表示）
    if st.button("変更をスプレッドシートに保存"):
        # 編集されたデータを元のリストに反映
        for idx, row in edited_df.iterrows():
            st.session_state.df_list.loc[st.session_state.df_list['No'] == row['No']] = row
        save_list(st.session_state.df_list)
        st.success("保存完了しました")

    # 選択チェックが入ったか確認
    selected_rows = edited_df[edited_df["選択"] == True]
    if not selected_rows.empty:
        st.session_state.selected_no = int(selected_rows.iloc[0]["No"])
        # チェックを外した状態で保持（戻った時にループしないよう）
        st.session_state.df_list.loc[st.session_state.df_list['No'] == st.session_state.selected_no, "選択"] = False
        st.rerun()

# --- 詳細入力画面 ---
else:
    no = st.session_state.selected_no
    match_info = st.session_state.df_list[st.session_state.df_list["No"] == no].iloc[0]
    
    st.title(f"📝 試合結果入力 (No.{no})")
    st.subheader(f"{match_info['カテゴリー']} | {match_info['日時']} | vs {match_info['対戦相手']}")

    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.rerun()

    # 結果入力フォーム
    st.divider()
    _, current_results = load_data() # 最新データ取得
    
    for i in range(1, 16):
        rk = f"res_{no}_{i}"
        sd = current_results.get(rk, {"score": "", "scorers": [""] * 10})
        
        with st.expander(f"第 {i} 試合 {'✅ 保存済' if rk in current_results else ''}"):
            c1, c2 = st.columns([1, 3])
            with c1:
                score = st.text_input("スコア", value=sd["score"], key=f"s_{rk}", placeholder="2-1")
            with c2:
                scorers_str = ", ".join([s for s in sd["scorers"] if s])
                scorers_input = st.text_area("得点者 (カンマ区切り)", value=scorers_str, key=f"p_{rk}", help="選手名をカンマ(,)で区切って入力")
            
            if st.button("この試合を保存", key=f"b_{rk}"):
                # 文字列をリストに戻す
                new_scorers = [s.strip() for s in scorers_input.split(",") if s.strip()]
                new_scorers += [""] * (10 - len(new_scorers))
                
                _, res_upd = load_data()
                res_upd[rk] = {"score": score, "scorers": new_scorers[:10]}
                save_res(res_upd)
                st.toast(f"第{i}試合を保存しました")
