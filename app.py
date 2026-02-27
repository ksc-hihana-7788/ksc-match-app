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
            st.error("IDまたはパスワードが違います")
    st.stop()

# --- データ保持 ---
if 'df_list' not in st.session_state:
    st.session_state.df_list, st.session_state.results = load_data()

if 'selected_no' not in st.session_state:
    st.session_state.selected_no = None

# --- 画面切り替え用関数 ---
def handle_selection():
    # 編集データの中から「選択」がTrueになった行を探す
    if "editor" in st.session_state:
        edited = st.session_state["editor"]["edited_rows"]
        for row_idx, changes in edited.items():
            if changes.get("選択") == True:
                # フィルタ後のインデックスから、元データのNoを特定
                actual_no = st.session_state.current_display_df.iloc[row_idx]["No"]
                st.session_state.selected_no = int(actual_no)
                # チェック状態をリセットして遷移
                st.session_state.df_list.loc[st.session_state.df_list['No'] == actual_no, "選択"] = False

# --- 1. 一覧画面 ---
if st.session_state.selected_no is None:
    st.title("⚽ KSC試合管理一覧")

    # 検索・フィルタ
    c1, c2 = st.columns([2, 1])
    with c1:
        search_query = st.text_input("🔍 キーワード検索", "")
    with c2:
        cat_filter = st.selectbox("📅 カテゴリー絞り込み", ["すべて", "U8", "U9", "U10", "U11", "U12"])

    # フィルタリング
    df = st.session_state.df_list.copy()
    if cat_filter != "すべて":
        df = df[df["カテゴリー"] == cat_filter]
    if search_query:
        df = df[df.apply(lambda r: search_query.lower() in r.astype(str).str.lower().values, axis=1)]
    
    st.session_state.current_display_df = df

    # データエディタ
    edited_df = st.data_editor(
        df,
        hide_index=True,
        column_config={
            "選択": st.column_config.CheckboxColumn("選択"),
            "No": st.column_config.NumberColumn(disabled=True),
            "カテゴリー": st.column_config.SelectboxColumn("カテゴリー", options=["U8", "U9", "U10", "U11", "U12"]),
            "日時": st.column_config.DateColumn("日時", format="YYYY-MM-DD"),
        },
        use_container_width=True,
        key="editor",
        on_change=handle_selection
    )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 全体の変更を保存"):
            # 反映処理
            for idx, row in edited_df.iterrows():
                st.session_state.df_list.loc[st.session_state.df_list['No'] == row['No']] = row
            save_list(st.session_state.df_list)
            st.success("スプレッドシートへ保存しました")

    with col_btn2:
        # PDF出力用（ブラウザの印刷機能呼び出し）
        st.markdown(
            '<button onclick="window.print()" style="width:100%; height:38px; border-radius:5px; border:1px solid #ccc; background-color:#f0f2f6; cursor:pointer;">📄 一覧をPDF出力 (印刷)</button>', 
            unsafe_allow_html=True
        )

# --- 2. 詳細入力画面 ---
else:
    no = st.session_state.selected_no
    match_info = st.session_state.df_list[st.session_state.df_list["No"] == no].iloc[0]
    
    st.title(f"📝 試合結果入力 (No.{no})")
    st.write(f"**{match_info['カテゴリー']}** | {match_info['日時']} | vs {match_info['対戦相手']}")

    if st.button("← 一覧に戻る"):
        st.session_state.selected_no = None
        st.rerun()

    st.divider()
    _, current_results = load_data()
    
    for i in range(1, 16):
        rk = f"res_{no}_{i}"
        sd = current_results.get(rk, {"score": "", "scorers": [""] * 10})
        with st.expander(f"第 {i} 試合 {'✅' if rk in current_results else ''}"):
            sc = st.text_input("スコア", value=sd["score"], key=f"s_{rk}")
            scorers_str = ", ".join([s for s in sd["scorers"] if s])
            sc_input = st.text_area("得点者 (カンマ区切り)", value=scorers_str, key=f"p_{rk}")
            
            if st.button("保存", key=f"b_{rk}"):
                new_s = [s.strip() for s in sc_input.split(",") if s.strip()]
                new_s += [""] * (10 - len(new_s))
                current_results[rk] = {"score": sc, "scorers": new_s[:10]}
                save_res(current_results)
                st.toast(f"第{i}試合 保存完了")
