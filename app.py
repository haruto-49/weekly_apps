import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import requests

# PDF生成用ライブラリ (ReportLab)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle

# --- フォントの準備（スマホやクラウド環境用） ---
# 日本語フォント(IPAexGothic)を自動ダウンロードして使えるようにする
FONT_URL = "https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexg00401.zip"
FONT_FILE = "ipaexg.ttf"

def register_japanese_font():
    """日本語フォントを登録する（なければダウンロード）"""
    if not os.path.exists(FONT_FILE):
        # 簡易的にIPAフォントなどをダウンロードする処理（実運用の際はローカル配置推奨）
        # ここではGoogle Fonts等の直リンクが難しいため、
        # 動作確認用に「Notion Sans JP」や既存フォントがあればそれを使う設定にします
        pass
    
    # ⚠️注意: クラウドで動かす際はここに.ttfファイルが必要です。
    # 今回はエラー回避のため、デフォルトフォントで日本語が表示できない警告を出します。
    # 実装時は同階層に 'ipaexg.ttf' を置いてください。
    try:
        pdfmetrics.registerFont(TTFont('Japanese', FONT_FILE))
        return 'Japanese'
    except:
        return 'Helvetica' # 日本語が出ない場合のフォールバック

# --- 計算ロジック（前回と同じ） ---
def format_range_str(start_cum, end_cum, max_amount, label):
    start_lap = (start_cum - 1) // max_amount + 1
    start_val = (start_cum - 1) % max_amount + 1
    end_val = (end_cum - 1) % max_amount + 1
    
    base_str = f"{label}{start_val}-{end_val}"
    if start_lap > 1: return f"{base_str} ({start_lap}周)"
    return base_str

def calculate_schedule(start_date, end_date, input_val, rounds, offset, unit_label, mode, book_max_amount):
    days_total = (end_date - start_date).days + 1
    if days_total <= 0: return {}

    study_days_count = 0
    for i in range(days_total):
        curr_date = start_date + timedelta(days=i)
        if curr_date.toordinal() % 4 != offset:
            study_days_count += 1
    
    if study_days_count == 0: return {}

    if mode == "期間配分":
        pace = (input_val * rounds) / study_days_count
        current_max_amount = input_val
    else: # 毎日固定
        pace = float(input_val)
        current_max_amount = book_max_amount

    plan = {}
    accumulated_progress = 0.0
    current_start_int = 1
    
    for i in range(days_total):
        curr_date = start_date + timedelta(days=i)
        d_str = curr_date.strftime("%Y-%m-%d")
        
        if curr_date.toordinal() % 4 == offset:
            plan[d_str] = "★復習"
        else:
            accumulated_progress += pace
            target_end_int = int(accumulated_progress)
            
            start_round = (current_start_int - 1) // current_max_amount
            target_round = (target_end_int - 1) // current_max_amount
            
            if start_round != target_round:
                actual_end_int = (start_round + 1) * current_max_amount
            else:
                actual_end_int = target_end_int

            if actual_end_int >= current_start_int:
                display_text = format_range_str(current_start_int, actual_end_int, current_max_amount, unit_label)
                plan[d_str] = display_text
                current_start_int = actual_end_int + 1
            else:
                plan[d_str] = "予備"
    return plan

# --- PDF生成ロジック (ReportLab使用) ---
def generate_pdf(study_plans):
    filename = "study_plan.pdf"
    c = canvas.Canvas(filename, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # フォント登録（同階層にipaexg.ttfがある前提）
    # ※無い場合は日本語が文字化けします
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont('Japanese', 'ipaexg.ttf'))
        font_name = 'Japanese'
    except:
        st.warning("日本語フォント(ipaexg.ttf)が見つかりません。PDFの文字が化ける可能性があります。")

    # 科目順ソート
    subject_order = ["英語", "数学", "国語", "理科", "社会"]
    def sort_key(plan):
        subj = plan["subject"]
        if subj in subject_order: return subject_order.index(subj)
        return 99
    study_plans.sort(key=sort_key)

    # 全期間の取得
    if not study_plans: return None
    min_date = min(p["start"] for p in study_plans)
    max_date = max(p["end"] for p in study_plans)
    
    curr_monday = min_date - timedelta(days=min_date.weekday())
    
    while curr_monday <= max_date:
        draw_week_page(c, width, height, curr_monday, study_plans, font_name)
        c.showPage() # 改ページ
        curr_monday += timedelta(days=7)
        
    c.save()
    return filename

def draw_week_page(c, w, h, monday, plans, font_name):
    # タイトル
    c.setFont(font_name, 20)
    c.drawString(20*mm, h - 20*mm, "週間学習計画表")
    
    # テーブルデータの作成
    # ヘッダー行
    days_of_week = ["月", "火", "水", "木", "金", "土", "日"]
    header = ["科目/教材"]
    for i in range(7):
        d = monday + timedelta(days=i)
        header.append(f"{d.strftime('%m/%d')}\n({days_of_week[i]})")
    
    data = [header]
    
    # データ行
    for plan in plans:
        row = []
        # 1列目: 科目と教材名
        label = f"{plan['subject']}\n{plan['book']}"
        row.append(label)
        
        # 2~8列目: 各日の内容
        for i in range(7):
            d = monday + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            content = plan["plan"].get(d_str, "")
            row.append(content)
        data.append(row)
        
    # テーブルスタイルの設定
    table = Table(data, colWidths=[40*mm] + [33*mm]*7)
    
    style = TableStyle([
        ('FONT', (0,0), (-1,-1), font_name, 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), # ヘッダー背景
        ('TEXTCOLOR', (6,0), (6,-1), colors.blue), # 土曜
        ('TEXTCOLOR', (7,0), (7,-1), colors.red),  # 日曜
    ])
    
    # 「復習」の文字を赤くする処理はReportLabのTableだと少し複雑になるため、
    # ここでは簡易的にセルごとの設定を行うループを追加
    for r_idx, row in enumerate(data):
        for c_idx, val in enumerate(row):
            if "復習" in val:
                style.add('TEXTCOLOR', (c_idx, r_idx), (c_idx, r_idx), colors.red)
                style.add('FONT', (c_idx, r_idx), (c_idx, r_idx), font_name, 9) # 太字にしたいがTTF次第

    table.setStyle(style)
    
    # 描画位置
    table.wrapOn(c, w, h)
    table.drawOn(c, 10*mm, h - 180*mm) # 位置調整

# --- Streamlit アプリ本体 ---
def main():
    st.set_page_config(page_title="学習計画メーカー", layout="wide")
    st.title("📱 スマホ対応・学習計画表ジェネレーター")

    # セッション状態（リストの保持）
    if "study_plans" not in st.session_state:
        st.session_state.study_plans = []

    # サイドバー：入力フォーム
    with st.sidebar:
        st.header("① 教材の登録")
        
        # CSVの代わりの簡易データ（実運用ではファイルアップロードも可能）
        book_db = {
            "青チャート": {"subj": "数学", "amt": 500, "unit": "No."},
            "ターゲット1900": {"subj": "英語", "amt": 1900, "unit": "No."},
            "現代文キーワード": {"subj": "国語", "amt": 160, "unit": "p."},
            "物理のエッセンス": {"subj": "理科", "amt": 100, "unit": "p."},
            "日本史B用語集": {"subj": "社会", "amt": 300, "unit": "p."}
        }
        
        book_name = st.selectbox("教材を選択", ["(手入力)"] + list(book_db.keys()))
        
        # 自動入力
        default_subj, default_amt, default_unit = "数学", 100, "p."
        if book_name in book_db:
            default_subj = book_db[book_name]["subj"]
            default_amt = book_db[book_name]["amt"]
            default_unit = book_db[book_name]["unit"]
            
        subj = st.text_input("科目", value=default_subj)
        if book_name == "(手入力)":
            book_real_name = st.text_input("教材名を入力")
        else:
            book_real_name = st.text_input("教材名", value=book_name)

        mode = st.radio("計算モード", ["期間配分", "毎日固定"])
        
        col1, col2 = st.columns(2)
        with col1:
            val = st.number_input("数値(総量or日量)", value=default_amt)
        with col2:
            unit = st.text_input("単位", value=default_unit)
            
        rounds = st.number_input("周数", value=1, min_value=1)
        
        start_date = st.date_input("開始日", datetime.now())
        end_date = st.date_input("終了日", datetime.now() + timedelta(days=14))
        
        if st.button("リストに追加", type="primary"):
            # 計算実行
            s_dt = datetime.combine(start_date, datetime.min.time())
            e_dt = datetime.combine(end_date, datetime.min.time())
            
            # 手入力の場合は入力値をMAXと仮定
            book_max = book_db[book_name]["amt"] if book_name in book_db else val
            
            offset = len(st.session_state.study_plans) % 4
            
            plan_map = calculate_schedule(s_dt, e_dt, val, rounds, offset, unit, mode, book_max)
            
            st.session_state.study_plans.append({
                "subject": subj,
                "book": book_real_name,
                "start": s_dt,
                "end": e_dt,
                "plan": plan_map,
                "detail": f"{mode}: {val}{unit} ({rounds}周)"
            })
            st.success("追加しました！")

    # メイン画面：リスト表示
    st.header("② 登録済みリスト")
    
    if st.session_state.study_plans:
        # データフレームで見やすく表示
        df = pd.DataFrame(st.session_state.study_plans)
        st.dataframe(df[["subject", "book", "detail"]], use_container_width=True)
        
        # 削除ボタン
        if st.button("リストを全クリア"):
            st.session_state.study_plans = []
            st.rerun()

        st.divider()
        
        # PDF生成ボタン
        st.header("③ 出力")
        if st.button("PDFを作成する"):
            pdf_file = generate_pdf(st.session_state.study_plans)
            if pdf_file:
                with open(pdf_file, "rb") as f:
                    st.download_button(
                        label="📄 PDFをダウンロード",
                        data=f,
                        file_name="weekly_plan.pdf",
                        mime="application/pdf"
                    )
    else:
        st.info("左のサイドバーから教材を追加してください")

if __name__ == "__main__":
    main()