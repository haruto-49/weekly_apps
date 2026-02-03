import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import csv

# PDF生成用ライブラリ (ReportLab)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle

# --- データの読み込み関数 ---
def load_book_data(filename):
    data = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)

    if not os.path.exists(file_path):
        return data

    def read_csv_content(encoding_type):
        temp_data = {}
        with open(file_path, newline='', encoding=encoding_type) as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3:
                    subj = row[0].strip()
                    name = row[1].strip()
                    try:
                        amount = int(row[2].strip())
                        unit_label = row[3].strip() if len(row) >= 4 else "p."
                        temp_data[name] = {"subject": subj, "amount": amount, "unit_label": unit_label}
                    except: pass
        return temp_data

    try:
        data = read_csv_content('utf-8')
    except UnicodeDecodeError:
        try:
            data = read_csv_content('cp932')
        except: return {}
    return data

# --- 計算ロジック ---
def format_range_str(start_cum, end_cum, max_amount, label):
    start_lap = (start_cum - 1) // max_amount + 1
    start_val = (start_cum - 1) % max_amount + 1
    end_val = (end_cum - 1) % max_amount + 1
    base_str = f"{label}{start_val}-{end_val}"
    if start_lap > 1: return f"{base_str} ({start_lap}周)"
    return base_str

def calculate_schedule(start_date, end_date, input_val, rounds, offset, unit_label, mode, book_max_amount, interval):
    days_total = (end_date - start_date).days + 1
    if days_total <= 0: return {}

    study_days_count = 0
    for i in range(days_total):
        curr_date = start_date + timedelta(days=i)
        if curr_date.toordinal() % interval != offset:
            study_days_count += 1
    
    if study_days_count == 0: return {}

    if mode == "期間配分":
        pace = (input_val * rounds) / study_days_count
        current_max_amount = input_val
    else:
        pace = float(input_val)
        current_max_amount = book_max_amount

    plan = {}
    accumulated_progress = 0.0
    current_start_int = 1
    
    for i in range(days_total):
        curr_date = start_date + timedelta(days=i)
        d_str = curr_date.strftime("%Y-%m-%d")
        
        if curr_date.toordinal() % interval == offset:
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

# --- PDF生成ロジック (週間予定表) ---
def generate_pdf(study_plans):
    filename = "weekly_plan.pdf"
    c = canvas.Canvas(filename, pagesize=landscape(A4))
    width, height = landscape(A4)
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont('Japanese', 'ipaexg.ttf'))
        font_name = 'Japanese'
    except: pass

    subject_order = ["英語", "数学", "国語", "理科", "社会"]
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
        row = [f"{plan['subject']}\n{plan['book']}"]
        for i in range(7):
            d = monday + timedelta(days=i)
            row.append(plan["plan"].get(d.strftime("%Y-%m-%d"), ""))
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
            if "★復習" in val:
                style.add('TEXTCOLOR', (c_idx, r_idx), (c_idx, r_idx), colors.red)

    table.setStyle(style)
    table.wrapOn(c, w, h)
    y_position = h - 40*mm - table._height
    table.drawOn(c, 10*mm, y_position)


# --- ★新機能: 年間ロードマップ生成ロジック ---
def generate_roadmap_pdf(study_plans):
    filename = "roadmap.pdf"
    c = canvas.Canvas(filename, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    # フォント設定
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont('Japanese', 'ipaexg.ttf'))
        font_name = 'Japanese'
    except: pass

    # 1. 期間の決定 (全データの最小開始日〜最大終了日)
    if not study_plans: return None
    min_date = min(p["start"] for p in study_plans)
    max_date = max(p["end"] for p in study_plans)
    
    # 開始をその月の1日に、終了をその月の末日に調整
    start_view = min_date.replace(day=1)
    # 月末日の計算ロジック
    next_month = max_date.replace(day=28) + timedelta(days=4)
    end_view = next_month - timedelta(days=next_month.day)
    
    total_days = (end_view - start_view).days + 1
    
    # 2. 描画エリアの設定
    margin_x = 20*mm
    margin_y = 20*mm
    chart_width = width - 2 * margin_x
    chart_height = height - 40*mm # タイトル分を確保
    
    # 3. 科目ごとのデータ整理と色設定
    subjects = {} # {科目名: [plan1, plan2...]}
    subj_colors = {
        "英語": colors.mistyrose, "数学": colors.aliceblue, "国語": colors.lavenderblush,
        "理科": colors.honeydew, "社会": colors.lemonchiffon, "情報": colors.whitesmoke
    }
    default_color = colors.lightgrey

    for p in study_plans:
        s = p["subject"]
        if s not in subjects: subjects[s] = []
        subjects[s].append(p)
    
    # 表示順序
    subj_order = ["英語", "数学", "国語", "理科", "社会"]
    sorted_subjs = sorted(subjects.keys(), key=lambda x: subj_order.index(x) if x in subj_order else 99)

    # 4. 描画開始
    c.setFont(font_name, 18)
    c.drawString(margin_x, height - 20*mm, "年間学習ロードマップ")
    
    # 軸の描画 (月ごとの縦線)
    c.setFont(font_name, 9)
    c.setLineWidth(0.3)
    c.setStrokeColor(colors.grey)
    
    # 日付 -> X座標変換関数
    def get_x(dt):
        delta = (dt - start_view).days
        return margin_x + (delta / total_days) * chart_width

    # 月のメモリを描画
    curr = start_view
    while curr <= end_view:
        x = get_x(curr)
        c.line(x, height - 30*mm, x, margin_y)
        c.drawString(x + 2*mm, height - 28*mm, curr.strftime("%Y/%m"))
        # 翌月へ
        if curr.month == 12:
            curr = curr.replace(year=curr.year+1, month=1, day=1)
        else:
            curr = curr.replace(month=curr.month+1, day=1)

    # 5. ガントチャートのバーを描画
    current_y = height - 35*mm
    lane_height = 8*mm # バーの高さ
    lane_gap = 4*mm    # バーの間隔
    subj_gap = 10*mm   # 科目間の間隔

    for subj in sorted_subjs:
        # 科目ラベル
        c.setFont(font_name, 11)
        c.setFillColor(colors.black)
        c.drawString(margin_x - 15*mm, current_y - 8*mm, subj) # 左側に科目名
        
        # この科目の教材リスト
        plans = subjects[subj]
        plans.sort(key=lambda x: x["start"]) # 開始日順にソート
        
        # 段組み計算 (重なり回避)
        # lanes = [ [end_date_of_last_item_in_lane0], [end_date_of_lane1]... ]
        lanes = [] 
        
        for p in plans:
            p_start = p["start"]
            p_end = p["end"]
            
            # 入れるレーンを探す
            placed = False
            lane_idx = 0
            for i, last_end in enumerate(lanes):
                if last_end < p_start: # このレーンの最後より後に始まるなら置ける
                    lanes[i] = p_end
                    lane_idx = i
                    placed = True
                    break
            
            if not placed:
                lanes.append(p_end)
                lane_idx = len(lanes) - 1
            
            # 座標計算
            x_start = get_x(p_start)
            x_end = get_x(p_end)
            bar_width = x_end - x_start
            if bar_width < 1*mm: bar_width = 1*mm # 最低幅
            
            # バーのY座標 (科目の基準Yから、レーン分だけ下げる)
            bar_y = current_y - (lane_idx + 1) * (lane_height + lane_gap)
            
            # 描画
            col = subj_colors.get(subj, default_color)
            c.setFillColor(col)
            c.rect(x_start, bar_y, bar_width, lane_height, stroke=1, fill=1)
            
            # 文字描画 (バーの中に収める、またははみ出すならクリップ)
            c.setFillColor(colors.black)
            c.setFont(font_name, 8)
            # バーの中央に文字
            text = p["book"]
            c.drawString(x_start + 1*mm, bar_y + 2*mm, text)

        # 次の科目のためにY座標を更新
        # この科目で使ったレーン数分だけ下げる
        used_height = len(lanes) * (lane_height + lane_gap)
        current_y -= (used_height + subj_gap)
        
        # ページ下端を超えたら改ページ (簡易実装)
        if current_y < margin_y + 20*mm:
             c.showPage()
             current_y = height - 30*mm
             # 改ページ後の再設定
             c.setFont(font_name, 18)
             # 再度軸描画などは省略(必要ならここに関数化して呼ぶ)

    c.save()
    return filename


# --- Streamlit アプリ本体 ---
def main():
    st.set_page_config(page_title="学習計画メーカー", layout="wide")
    st.title("📱 学習計画表ジェネレーター")

    if "study_plans" not in st.session_state:
        st.session_state.study_plans = []

    # --- サイドバー ---
    with st.sidebar:
        st.header("① 教材の登録")
        book_db = load_book_data("books.csv")
        options = ["(手入力)"] + list(book_db.keys())
        book_name = st.selectbox("教材を選択", options)
        
        default_subj, default_amt, default_unit = "数学", 100, "p."
        if book_name in book_db:
            default_subj = book_db[book_name]["subject"]
            default_amt = book_db[book_name]["amount"]
            default_unit = book_db[book_name]["unit_label"]
            
        subj = st.text_input("科目", value=default_subj)
        book_real_name = st.text_input("教材名", value="" if book_name == "(手入力)" else book_name)
        mode = st.radio("計算モード", ["期間配分", "毎日固定"])
        
        col1, col2 = st.columns(2)
        with col1:
            val = st.number_input("数値(総量or日量)", value=default_amt)
        with col2:
            unit = st.text_input("単位", value=default_unit)
            
        review_interval = st.number_input("復習の頻度（何日に1回）", value=4, min_value=1)
        rounds = st.number_input("周数", value=1, min_value=1)
        start_date = st.date_input("開始日", datetime.now())
        end_date = st.date_input("終了日", datetime.now() + timedelta(days=14))
        
        if st.button("リストに追加", type="primary"):
            s_dt = datetime.combine(start_date, datetime.min.time())
            e_dt = datetime.combine(end_date, datetime.min.time())
            book_max = book_db[book_name]["amount"] if book_name in book_db else val
            
            offset = len(st.session_state.study_plans) % review_interval
            
            plan_map = calculate_schedule(s_dt, e_dt, val, rounds, offset, unit, mode, book_max, review_interval)
            
            st.session_state.study_plans.append({
                "subject": subj, "book": book_real_name, "start": s_dt, "end": e_dt,
                "plan": plan_map, "detail": f"{mode}: {val}{unit} (復習:{review_interval}日毎)"
            })
            st.success("追加しました！")

    # --- リスト表示 ---
    st.header("② 登録済みリスト")
    if st.session_state.study_plans:
        col_h1, col_h2, col_h3, col_h4 = st.columns([2, 4, 3, 1])
        col_h1.markdown("**科目**")
        col_h2.markdown("**教材名**")
        col_h3.markdown("**詳細**")
        col_h4.markdown("**削除**")
        st.divider()

        for i, plan in enumerate(st.session_state.study_plans):
            col1, col2, col3, col4 = st.columns([2, 4, 3, 1])
            col1.text(plan["subject"])
            col2.text(plan["book"])
            col3.text(plan["detail"])
            if col4.button("🗑️", key=f"del_{i}"):
                del st.session_state.study_plans[i]
                st.rerun()

        st.divider()
        if st.button("リストを全クリア", type="secondary"):
            st.session_state.study_plans = []
            st.rerun()

        # --- 出力ボタン ---
        st.header("③ 出力")
        
        col_pdf1, col_pdf2 = st.columns(2)
        
        with col_pdf1:
            st.subheader("週間計画表 (ミクロ)")
            if st.button("週間PDFを作成"):
                pdf_file = generate_pdf(st.session_state.study_plans)
                if pdf_file:
                    with open(pdf_file, "rb") as f:
                        st.download_button(label="📥 週間PDF DL", data=f, file_name="weekly_plan.pdf", mime="application/pdf")
        
        with col_pdf2:
            st.subheader("年間ロードマップ (マクロ)")
            # ★ここが新機能
            if st.button("ロードマップPDFを作成"):
                roadmap_file = generate_roadmap_pdf(st.session_state.study_plans)
                if roadmap_file:
                    with open(roadmap_file, "rb") as f:
                        st.download_button(label="📥 ロードマップDL", data=f, file_name="roadmap.pdf", mime="application/pdf")

    else:
        st.info("👈 左のサイドバーから教材を追加してください。")

if __name__ == "__main__":
    main()
