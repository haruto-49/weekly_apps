import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import requests
import csv # CSV操作用にインポート

# PDF生成用ライブラリ (ReportLab)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle

# --- フォントの準備 ---
FONT_FILE = "ipaexg.ttf"

# --- データの読み込み関数（ここを追加・強化） ---
def load_book_data(filename):
    """
    CSVファイルを読み込んで辞書として返す関数
    Streamlit Cloudでのパスずれや、文字コード問題を解決するロジック入り
    """
    data = {}
    
    # 1. ファイルの絶対パスを取得（重要: これがないとFile not foundになりやすい）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    # ファイルがない場合は空の辞書を返す（エラー回避）
    if not os.path.exists(file_path):
        # 開発中の確認用にWarningを出す（本番では消してもOK）
        # st.warning(f"注意: {filename} が見つかりません。手入力モードのみになります。")
        return data

    # 2. 読み込み処理（内部関数）
    def read_csv_content(encoding_type):
        temp_data = {}
        with open(file_path, newline='', encoding=encoding_type) as f:
            reader = csv.reader(f)
            for row in reader:
                # 3列以上ある行だけ読み込む (科目, 教材名, 分量, [単位])
                if len(row) >= 3:
                    subj = row[0].strip()
                    name = row[1].strip()
                    try:
                        amount = int(row[2].strip())
                        # 4列目があれば単位、なければデフォルト "p."
                        unit_label = row[3].strip() if len(row) >= 4 else "p."
                        
                        # 辞書に格納
                        temp_data[name] = {
                            "subject": subj, 
                            "amount": amount, 
                            "unit_label": unit_label
                        }
                    except:
                        pass # 数値変換エラーなどはスキップ
        return temp_data

    # 3. エンコーディング自動判定（UTF-8 -> Shift-JISの順で試す）
    try:
        data = read_csv_content('utf-8')
    except UnicodeDecodeError:
        try:
            data = read_csv_content('cp932') # Windows Excel形式
        except:
            st.error("CSVファイルの読み込みに失敗しました。")
            return {}
    except Exception:
        return {}
        
    return data

# --- 計算ロジック ---
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

# --- PDF生成ロジック ---
def generate_pdf(study_plans):
    filename = "study_plan.pdf"
    c = canvas.Canvas(filename, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont('Japanese', 'ipaexg.ttf'))
        font_name = 'Japanese'
    except:
        st.warning("日本語フォント(ipaexg.ttf)が見つかりません。PDFの文字が化ける可能性があります。")

    subject_order = ["英語", "数学", "現代文","古文","漢文","物理" ,"化学","生物","地学","地理","日本史","世界史","倫理・政経"]
    def sort_key(plan):
        subj = plan["subject"]
        if subj in subject_order: return subject_order.index(subj)
        return 99
    study_plans.sort(key=sort_key)

    if not study_plans: return None
    min_date = min(p["start"] for p in study_plans)
    max_date = max(p["end"] for p in study_plans)
    
    curr_monday = min_date - timedelta(days=min_date.weekday())
    
    while curr_monday <= max_date:
        draw_week_page(c, width, height, curr_monday, study_plans, font_name)
        c.showPage()
        curr_monday += timedelta(days=7)
        
    c.save()
    return filename

def draw_week_page(c, w, h, monday, plans, font_name):
    c.setFont(font_name, 20)
    c.drawString(20*mm, h - 20*mm, "週間学習計画表")
    
    days_of_week = ["月", "火", "水", "木", "金", "土", "日"]
    header = ["科目/教材"]
    for i in range(7):
        d = monday + timedelta(days=i)
        header.append(f"{d.strftime('%m/%d')}\n({days_of_week[i]})")
    
    data = [header]
    
    for plan in plans:
        row = []
        label = f"{plan['subject']}\n{plan['book']}"
        row.append(label)
        
        for i in range(7):
            d = monday + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            content = plan["plan"].get(d_str, "")
            row.append(content)
        data.append(row)
        
    table = Table(data, colWidths=[40*mm] + [33*mm]*7)
    
    style = TableStyle([
        ('FONT', (0,0), (-1,-1), font_name, 9),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (6,0), (6,-1), colors.blue),
        ('TEXTCOLOR', (7,0), (7,-1), colors.red),
    ])
    
    for r_idx, row in enumerate(data):
        for c_idx, val in enumerate(row):
            if "復習" in val:
                style.add('TEXTCOLOR', (c_idx, r_idx), (c_idx, r_idx), colors.red)
                style.add('FONT', (c_idx, r_idx), (c_idx, r_idx), font_name, 9)

    table.setStyle(style)
    
    # --- 位置調整の修正 ---
    # 1. まずテーブルのサイズを計算させる
    table.wrapOn(c, w, h)
    # 2. 計算されたテーブルの高さを取得
    table_height = table._height
    
    # 3. 配置するY座標を計算（用紙の上端から40mm下の位置に、テーブルの上辺を合わせる）
    # ReportLabは「左下」の座標を指定するため、「用紙高さ - 上マージン - テーブル高さ」となる
    y_position = h - 40*mm - table_height

    # 4. 計算した位置に描画
    table.drawOn(c, 10*mm, y_position)

# --- Streamlit アプリ本体 ---
def main():
    st.set_page_config(page_title="学習計画メーカー", layout="wide")
    st.title("📱 スマホ対応・学習計画表ジェネレーター")

    # セッション状態
    if "study_plans" not in st.session_state:
        st.session_state.study_plans = []

    with st.sidebar:
        st.header("① 教材の登録")
        
        # ★ここを修正: CSVからデータを読み込む
        book_db = load_book_data("books.csv")
        
        # セレクトボックス (データがない場合は手入力のみ)
        options = ["(手入力)"] + list(book_db.keys())
        book_name = st.selectbox("教材を選択", options)
        
        # デフォルト値の設定
        default_subj, default_amt, default_unit = "数学", 100, "p."
        
        if book_name in book_db:
            # CSVから読み込んだキー名を使用 (subject, amount, unit_label)
            default_subj = book_db[book_name]["subject"]
            default_amt = book_db[book_name]["amount"]
            default_unit = book_db[book_name]["unit_label"]
            
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
            s_dt = datetime.combine(start_date, datetime.min.time())
            e_dt = datetime.combine(end_date, datetime.min.time())
            
            # 手入力の場合は入力値をMAXと仮定
            book_max = book_db[book_name]["amount"] if book_name in book_db else val
            
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

    st.header("② 登録済みリスト")
    
    if st.session_state.study_plans:
        df = pd.DataFrame(st.session_state.study_plans)
        st.dataframe(df[["subject", "book", "detail"]], use_container_width=True)
        
        if st.button("リストを全クリア"):
            st.session_state.study_plans = []
            st.rerun()

        st.divider()
        
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
        # 初回表示時にCSVが読めているか確認するためのメッセージ
        if not book_db:
             st.info("👈 左のサイドバーから手入力で教材を追加してください。（books.csvが見つかりません）")
        else:
             st.info("👈 左のサイドバーから教材を選択・追加してください。")

if __name__ == "__main__":
    main()


