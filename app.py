import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import traceback

# --- ページ設定 ---
st.set_page_config(page_title="KSC試合管理ツール", layout="centered")

# --- 💡 スプレッドシートのURL ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1QmQ5uw5HI3tHmYTC29uR8jh1IeSnu4Afn7a4en7yvLc/edit?gid=0#gid=0"

# --- 💡 Googleスプレッドシート接続設定（Secretsから読み込む） ---
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # StreamlitのSecrets（秘密の箱）から認証情報を一括で読み込む
        creds_dict = json.loads(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"認証情報の読み込みに失敗しました。Secretsの設定を確認してください。: {e}")
        st.stop()

# --- データの読み書き関数 ---
def load_data_from_gs():
    client = get_gspread_client()
    try:
        sh = client.open_by_url(SPREADSHEET_URL)
        ws_list = sh.get_worksheet(0)
        data = ws_list.get_all_records()
        
        if not data:
            df = pd.DataFrame({
                "選択": [False] * 100, 
                "No": range(1, 101), 
                "日時": ["2026-02-26"] * 100,
                "対戦相手": [""] * 100, 
                "試合場所": [""] * 100, 
                "試合分類": [""] * 100, 
                "備考": [""] * 100
            })
            data_to_update = [df.columns.values.tolist()] + df.values.tolist()
            ws_list.update(data_to_update)
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
    except Exception as e:
        st.error(f"スプレッドシートの操作に失敗しました。: {e}")
        st.stop()

def save_list_to_gs(df):
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        ws = sh.get_worksheet(0)
        df_save = df.copy()
        df_save['日時'] = df_save['日時'].apply(lambda x: x.isoformat() if hasattr(x, 'isoformat') else x)
        data_to_update = [df_save.columns.values.tolist()] + df_save.values.tolist()
        ws.update(data_to_update)
    except Exception as e:
        st.error(f"一覧の保存に失敗しました: {e}")

def save_res_to_gs(results):
    try:
        client = get_gspread_client()
        sh = client.open_by_url(SPREADSHEET_URL)
        ws = sh.get_worksheet(1)
        ws.update_acell("A2", json.dumps(results, ensure_ascii=False))
    except Exception as e:
        st.error(f"詳細結果の保存に失敗しました: {e}")

# --- 認証機能 ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def login():
    st.title("KSC試合管理ツール ログイン")
    user_id = st.text_input("ログインID")
    password = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        if user_id == "KSC" and password == "kuma2019":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("IDまたはパスワードが違います")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- 初期ロード ---
if 'df_list' not in st.session_state:
    st.session_state.df_list, st.session_state.match_results = load_data_from_gs()

def on_table_change():
    if "main_table_editor" in st.session_state:
        edits = st.session_state["main_table_editor"]
        for row_idx, edit_values in edits.get("edited_rows", {}).items():
            for col_name, val in edit_values.items():
                st.session_state.df_list.at[row_idx, col_name] = val
        save_list_to_gs(st.session_state.df_list)

# --- 画面制御 ---
if 'selected_match_no' not in st.session_state:
    st.session_state.selected_match_no = None

if st.session_state.selected_match_no is None:
    st.title("KSC試合管理ツール (Cloud)")
    st.info("💡 スプレッドシートへリアルタイム保存中")
    
    edited_df = st.data_editor(
        st.session_state.df_list,
        hide_index=True,
        column_config={
            "選択": st.column_config.CheckboxColumn("選択", default=False), 
            "No": st.column_config.NumberColumn(disabled=True)
        },
        use_container_width=True,
        key="main_table_editor",
        on_change=on_table_change
    )

    selected_rows = edited_df[edited_df["選択"] == True]
    if not selected_rows.empty:
        no = int(selected_rows.iloc[0]["No"])
        st.session_state.df_list.at[no - 1, "選択"] = False
        save_list_to_gs(st.session_state.df_list)
        st.session_state.selected_match_no = no
        st.rerun()
else:
    _, latest_res = load_data_from_gs()
    match_no = st.session_state.selected_match_no
    
    st.title(f"試合結果入力 No.{match_no}")
    if st.button("← 一覧に戻る"):
        st.session_state.selected_match_no = None
        st.rerun()

    for i in range(1, 16):
        rk = f"res_{match_no}_{i}"
        sd = latest_res.get(rk, {"score": "", "scorers": [""] * 10})
        with st.expander(f"第 {i} 試合 {'(保存済)' if rk in latest_res else ''}"):
            score = st.text_input("スコア", value=sd["score"], key=f"s_{rk}")
            scorers = [st.text_input(f"得点者{j+1}", value=sd["scorers"][j], key=f"p_{rk}_{j}") for j in range(10)]
            if st.button("保存", key=f"b_{rk}"):
                _, res_upd = load_data_from_gs()
                res_upd[rk] = {"score": score, "scorers": scorers}
                save_res_to_gs(res_upd)
                st.success(f"第 {i} 試合の結果を保存しました")
                st.rerun()
