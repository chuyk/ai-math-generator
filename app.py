import streamlit as st
import json
import os
import re
import platform
import urllib.request
import random
from google import genai
from google.genai import types
import pypandoc

# 【全域套件強制宣告】：保證 exec() 執行時絕對不會出現 NameError
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Wedge, Circle, Rectangle, Polygon, RegularPolygon
import mpl_toolkits.mplot3d
from matplotlib import font_manager

# =======================================================
# 系統初始化 1：Pandoc 轉檔引擎 (支援本機與雲端)
# =======================================================
try:
    pypandoc.get_pandoc_version()
except OSError:
    with st.spinner("系統初始化中：正在植入核心轉檔引擎 (Pandoc)，請稍候..."):
        pypandoc.download_pandoc()

# =======================================================
# 狀態管理 (Session State - 雲端安全隔離機制)
# =======================================================
if "api_key" not in st.session_state:
    st.session_state.api_key = "" 
if "current_question" not in st.session_state:
    st.session_state.current_question = ""
if "current_code" not in st.session_state:
    st.session_state.current_code = ""
if "has_image" not in st.session_state:
    st.session_state.has_image = False

# =======================================================
# 網頁介面與 CSS 設定
# =======================================================
st.set_page_config(page_title="AI 數學題庫產生器", layout="wide")

st.markdown("""
<style>
.mobile-warning { 
    display: none; 
    background-color: #fff3cd; 
    padding: 15px; 
    border-radius: 8px; 
    border-left: 6px solid #dc3545; 
    color: #856404; 
    margin-bottom: 20px; 
    font-weight: bold;
}
@media (max-width: 768px) { 
    .mobile-warning { display: block; } 
}
</style>
<div class="mobile-warning">
    📱 系統偵測到您可能正使用行動裝置。<br>本系統包含複雜公式渲染、AI 繪圖與 Word 轉檔排版功能，強烈建議使用「電腦瀏覽器」以獲得最佳操作體驗！
</div>
""", unsafe_allow_html=True)

st.title("🤖 AI 數學題庫產生器 (阿凱老師專屬版)")
st.write("支援幾何繪圖、立體圖、不等式、素養題與動態難度，並透過 Pandoc 完美匯出 Word！")

# =======================================================
# 全域變數初始化 (供函數圖形開關使用)
# =======================================================
show_intersection = True
show_equation = True

# =======================================================
# 側邊欄：設定與參數
# =======================================================
with st.sidebar:
    st.header("⚙️ 系統設定")
    # ✅ 修改1：加上 Google API Key 超連結
    user_input_key = st.text_input("🔑 請輸入 [Google AI API Key](https://aistudio.google.com/app/api-keys)", type="password", value=st.session_state.api_key)
    
    # 雙驗證碼防護機制
    verify_code = st.text_input("🔒 請輸入系統驗證碼", type="password")
    
    if user_input_key != st.session_state.api_key:
        st.session_state.api_key = user_input_key
    
    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
        st.rerun()
        
    st.markdown("*(您的 API Key 僅於本次連線暫存，關閉網頁即自動銷毀，絕對安全)*")
    st.markdown("---")
    
    # 新增 AI 模型選擇區塊
    st.header("🤖 AI 模型設定")
    model_mapping = {
        "Gemini 3.1 Flash-Lite": "gemini-3.1-flash-lite-preview",
        "Gemma 4 31B": "gemma-4-31b-it",
        "Gemma 4 26B A4B": "gemma-4-26b-a4b-it"
    }
    selected_model_display = st.selectbox("選擇 AI 模型", options=list(model_mapping.keys()), index=0)
    selected_model = model_mapping[selected_model_display]
    
    st.markdown("---")
    st.header("🎚️ 題目參數設定")
    difficulty = st.select_slider("難度級別", options=["基礎概念", "標準段考", "進階挑戰"], value="標準段考")
    
    transparent_bg = st.checkbox("🖼️ 圖片自動去背 (透明背景)", value=False)
    
    # SVG/PNG 格式選擇
    img_format = st.radio("💾 Word 考卷配圖格式", [".png (一般圖檔)", ".svg (可編修向量圖)"])
    
    st.markdown("---")
    st.caption("👨‍🏫 宜蘭縣中華國中教師 / 阿凱老師製作")

# =======================================================
# 主畫面：選擇題型與生成邏輯
# =======================================================
st.markdown("### 📝 第一步：選擇題型")
question_type = st.radio(
    "請選擇您要生成的題目大類：",
    [
        "一般幾何 (平面/複合圖形)", 
        "直角坐標系與函數圖形",
        "立體圖形三視圖 (積木堆疊)", 
        "立體圖形展開圖 (圓柱/圓錐/角柱)", 
        "統計圖表 (折線圖/圓餅圖/長條圖/直方圖)", 
        "一元一次不等式圖解 (數線)", 
        "純文字計算題 (無插圖)",
        "會考非選素養題 (情境+兩小題)"
    ]
)

topic = ""
if question_type == "一般幾何 (平面/複合圖形)":
    topic = st.text_input("💡 請輸入出題單元 (可用括號排除概念，如：圓周角(不要用到圓內角))：", value="直角三角形斜邊上的高")
elif question_type == "直角坐標系與函數圖形":
    topic = st.text_input("💡 請輸入函數或方程式主題：", value="二元一次聯立方程式的圖形")
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        show_intersection = st.checkbox("📍 標示交點坐標", value=True)
    with col_opt2:
        show_equation = st.checkbox("📝 顯示直線方程式 (圖例)", value=True)
    st.info("💡 系統將自動繪製標準直角坐標系 (含十字箭頭、原點、x/y軸刻度標示)。")
elif question_type == "立體圖形三視圖 (積木堆疊)":
    st.info("💡 系統已全面改用 Python 幾何引擎！強迫 AI 照抄精算後的四個 3D 視圖選項，100% 符合數學課本規範。")
elif question_type == "立體圖形展開圖 (圓柱/圓錐/角柱)":
    topic = st.text_input("💡 請輸入要測驗的展開圖圖形：", value="五角柱的展開圖與表面積")
elif question_type == "統計圖表 (折線圖/圓餅圖/長條圖/直方圖)":
    topic = st.text_input("💡 請輸入圖表主題與資料情境：", value="某班學生數學成績直方圖")
elif question_type == "一元一次不等式圖解 (數線)":
    topic = st.text_input("💡 請輸入不等式主題：", value="解一元一次不等式並在數線上圖示(封閉區間)")
elif question_type == "純文字計算題 (無插圖)":
    topic = st.text_input("💡 請輸入代數或計算主題：", value="一元一次方程式的應用")
elif question_type == "會考非選素養題 (情境+兩小題)":
    topic = st.text_input("💡 請輸入生活情境主題：", value="線性函數與電信資費方案比較")

st.markdown("### 🚀 第二步：生成或修改考題")

col_gen, col_reroll = st.columns([1, 4])

def run_ai_generation(is_reroll=False):
    # 雙驗證碼通關邏輯
    if verify_code not in ["kai", "kaishow"]:
        st.error("🔒 系統驗證碼錯誤！請在左側輸入正確的驗證碼以解鎖出題功能。")
        return

    if not st.session_state.api_key:
        st.warning("請先在左側輸入您的 Google API Key 喔！")
        return

    client = genai.Client(api_key=st.session_state.api_key)
    
    base_rules = """
    【⚠️ 極度重要：JSON、LaTeX 與 Python 繪圖複合規範】
    1. JSON 跳脫：所有的 LaTeX 語法反斜線「必須雙重跳脫」！例如：\\\\triangle。
    2. LaTeX 包覆：所有的數學符號、方程式，絕對必須用 $ 符號包覆起來，否則網頁無法渲染！
    3. 【考卷印刷視覺規範】：所有的繪圖絕對禁止使用灰色或彩色填滿！一律「純白底、純黑線」。
    4. 【⚠️ Markdown 刪除線防呆】：若要表示分數或數字範圍，【絕對使用全形波浪號「～」或連字號「-」】。
    5. 【⚠️ 程式繪圖防呆】：請務必自行宣告畫布 (例如 fig, ax = plt.subplots())。但絕對不要在結尾寫 plt.savefig() 或 plt.show()，系統會自動接管存檔動作。
    6. 【⚠️ 線段標示規範】：題目文字或解析中若提到幾何「線段」，絕對必須使用 LaTeX 的 `\\\\overline{AB}` 來標示頂部橫線！
    """

    if is_reroll and question_type != "立體圖形三視圖 (積木堆疊)":
        if not st.session_state.current_question:
            st.warning("請先生成一道題目，才能使用換數字功能！")
            return
        prompt = f"""
        你是一位國中數學老師。請你完全保留原本的題型架構與幾何形狀，但是換成另一組合理的整數數字。
        重新計算正確答案，並修改對應的 Python 程式碼座標。
        舊題目：{st.session_state.current_question}
        舊程式碼：{st.session_state.current_code}
        {base_rules}
        請回傳包含 "question_text" 與 "python_code" 的 JSON。
        """
    else:
        if question_type == "一般幾何 (平面/複合圖形)":
            prompt = f"""
            請根據主題：【{topic}】，生成一道【{difficulty}】難度的幾何題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與解析。
            2. "python_code": 
               - 必須自行宣告 fig, ax = plt.subplots()
               - 使用 ax.set_aspect('equal') 與 ax.axis('off')。
               - 【⚠️ 直角記號絕對防呆】：必須照抄以下向量邏輯：
                 u = (A - D) / np.linalg.norm(A - D); v = (C - D) / np.linalg.norm(C - D)
                 p1 = D + 0.5 * u; p2 = p1 + 0.5 * v; p3 = D + 0.5 * v
                 ax.plot([p1[0], p2[0], p3[0]], [p1[1], p2[1], p3[1]], 'k-', lw=1.5)
               - 【⚠️ 標籤字體 18pt 防呆】：圖形中所有頂點的英文字母標示 (使用 ax.text 時)，必須強制加上參數 fontsize=18，且【嚴格規定】必須加上座標偏移量 (如 x+0.2, y-0.2) 或 ha/va 對齊，將字母往外推開，絕對不能與幾何線條或直角記號重疊！
               - ax.relim(); ax.autoscale_view(); ax.margins(0.15)
            """
        elif question_type == "直角坐標系與函數圖形":
            intersection_rule = "- 若需標示交點，可使用 `ax.plot(x, y, 'ko')` 畫出實心黑點，並用 `ax.text(x+0.2, y-0.2, ' P(a,b)', fontsize=14)` 標示坐標 (稍作偏移避免重疊)。" if show_intersection else "- 【⚠️ 絕對禁令】：絕對不要在圖上標示交點的坐標文字、實心點或名稱。"
            equation_rule = "- 若要標示直線名稱，請使用 `ax.plot(..., label='L1: 方程式')` 並在最後呼叫 `ax.legend(loc='lower right')` 顯示圖例。" if show_equation else "- 【⚠️ 絕對禁令】：絕對不要顯示圖例 (legend)，也不要在圖上標示方程式文字。"
            
            prompt = f"""
            請根據主題：【{topic}】，生成一道【{difficulty}】難度的測驗題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與解析。聯立方程式請使用標準 LaTeX 語法。
            2. "python_code": 
               - 必須自行宣告 fig, ax = plt.subplots()
               - 【⚠️ 絕對防呆】：你不准自己畫坐標軸！必須直接呼叫底層防呆函數 `draw_coordinate_system(ax, x_min, x_max, y_min, y_max)`。
               - 請根據你設計的函數圖形範圍，給定合理的 x_min, x_max, y_min, y_max (例如 -5 到 5)。
               - 畫函數直線時，請使用 `ax.plot()`，例如：`ax.plot(x, y, 'k-', lw=1.5)`。
               {intersection_rule}
               {equation_rule}
               - 絕對不可使用 ax.axis('off')，否則坐標軸會消失！
            """
        elif question_type == "立體圖形三視圖 (積木堆疊)":
            target_view = random.choice(["前視圖", "上視圖", "右視圖"])
            
            heights_arr = np.zeros((3, 3), dtype=int)
            for _y in range(3):
                for _x in range(3):
                    heights_arr[_y, _x] = random.randint(0, 3)
            heights_arr[1, 1] = random.randint(1, 3)
            heights_arr[0, random.randint(0, 2)] = random.randint(1, 2)
            
            def get_view_string(matrix, v_type):
                res = []
                if v_type == "上視圖":
                    for _y in [2, 1, 0]:
                        res.append("".join(["⬛" if matrix[_y, _x] > 0 else "⬜" for _x in range(3)]))
                elif v_type == "前視圖":
                    h = [max(matrix[:, _x]) for _x in range(3)]
                    for _z in [2, 1, 0]:
                        res.append("".join(["⬛" if h[_x] > _z else "⬜" for _x in range(3)]))
                elif v_type == "右視圖":
                    h = [max(matrix[_y, :]) for _y in range(3)]
                    for _z in [2, 1, 0]:
                        res.append("".join(["⬛" if h[_y] > _z else "⬜" for _y in range(3)]))
                return "<br>".join(res)
            
            correct_ans_str = get_view_string(heights_arr, target_view)
            
            options_list = [correct_ans_str]
            attempts = 0
            while len(options_list) < 4 and attempts < 100:
                attempts += 1
                mod_m = heights_arr.copy()
                action = random.choice(['rot', 'flip', 'mod'])
                if action == 'rot':
                    mod_m = np.rot90(mod_m, k=random.randint(1, 3))
                elif action == 'flip':
                    mod_m = np.fliplr(mod_m) if random.choice([True, False]) else np.flipud(mod_m)
                else:
                    mod_m[random.randint(0, 2), random.randint(0, 2)] = random.randint(0, 3)
                
                dist_str = get_view_string(mod_m, target_view)
                if dist_str not in options_list and "⬛" in dist_str:
                    options_list.append(dist_str)
                    
            while len(options_list) < 4:
                options_list.append("<br>⬜⬜⬜<br>⬜⬛⬜<br>⬜⬜⬜")

            random.shuffle(options_list)
            correct_idx = options_list.index(correct_ans_str)
            ans_letter = chr(65 + correct_idx)
            h_matrix_str = repr(heights_arr.tolist())

            prompt = f"""
            你是一位專業的國中數學老師。請生成一道【{difficulty}】難度的「立體積木三視圖」選擇題。
            {base_rules}
            
            【⚠️ 絕對防呆指示：請完全照抄我為你算好的選項，不准自己發揮！】
            - 測驗目標：【{target_view}】
            - 題目必須是：「如圖為正方體堆疊的立體圖形，請判斷其【{target_view}】為何？」
            - 【重要】請將以下四個選項「一字不漏」地放進你的 JSON 選項中：
              (A)<br><br>{options_list[0]}<br><br>
              (B)<br><br>{options_list[1]}<br><br>
              (C)<br><br>{options_list[2]}<br><br>
              (D)<br><br>{options_list[3]}
            - 【重要】解析請明確指出正確答案為 ({ans_letter})。

            請回傳 JSON：
            1. "question_text": 包含上述題目、四個選項與解析。
            2. "python_code": 
               - 【絕對照抄】以下陣列與繪圖程式碼 (此座標已完美對應前視與右視方向)：
                 fig, ax = plt.subplots(subplot_kw={{'projection': '3d'}})
                 heights = np.array({h_matrix_str})
                 cubes = np.zeros((3, 3, 3), dtype=bool)
                 for y in range(3):
                     for x in range(3):
                         for z in range(heights[y, x]):
                             cubes[x, y, z] = True
                 ax.voxels(cubes, facecolors='white', edgecolors='black', shade=False)
                 ax.view_init(elev=30, azim=-45)
                 ax.set_box_aspect((1, 1, 1))
                 ax.axis('off')
            """
            
        elif question_type == "立體圖形展開圖 (圓柱/圓錐/角柱)":
            prompt = f"""
            你是一位專業的國中數學老師。請根據主題：【{topic}】，生成一道【{difficulty}】難度的「立體圖形展開圖」幾何題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與解析。
            2. "python_code": 繪製該圖形的展開圖。必須自行宣告 fig, ax = plt.subplots()。
               - 【⚠️ 絕對禁令】：不准自行計算座標或使用 add_patch！必須直接呼叫底層已建好的防呆函數：
               - 若為角柱，請呼叫 `draw_prism(ax, N, a, h)` (N為邊數, a為底邊長, h為柱高)
               - 若為圓錐，請呼叫 `draw_cone(ax, L, r)` (L為扇形半徑/母線長, r為底圓半徑)
               - 程式碼範例：
                 fig, ax = plt.subplots()
                 draw_cone(ax, L=10, r=3)
            """
        elif question_type == "統計圖表 (折線圖/圓餅圖/長條圖/直方圖)":
            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的統計圖表題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、選項與解析。
            2. "python_code": 必須自行宣告 fig, ax = plt.subplots()。
               - 【⚠️ 語言禁令】：所有的圖表標題 (title)、X 軸與 Y 軸標籤、圖例，『絕對強制』使用繁體中文，嚴禁出現任何英文！
               - 【⚠️ 字體大小防呆】：所有的標題、x 軸標籤，請加上 `fontsize=16` 參數。
               - 【⚠️ Y軸直排絕對防呆】：你不准自己設定 Y 軸標籤或自己加換行符號！請一律呼叫底層專屬函數 `set_vertical_ylabel(ax, '你的標籤字串')` (例如：`set_vertical_ylabel(ax, '次數(人)')`)，底層程式會完美幫你直排並處理括號，絕對不要自己寫 ax.set_ylabel！
               - 直方圖長條必須緊密相連 (width=組距)。
            """
        elif question_type == "一元一次不等式圖解 (數線)":
            force_closed = "封閉" in topic or "範圍" in topic or "雙邊" in topic
            closed_rule = "- 【⚠️ 封閉區間絕對強制令】：使用者已指定封閉區間！你【絕對強制】必須設計一道「連立不等式」或「雙邊連續不等式」(例如 $-5 \le 2x - 3 < 7$)，解答必須是介於兩個數字之間的範圍 (例如 $-1 \le x < 5$)，絕對不准出單向不等式！" if force_closed else "- 題型必須涵蓋「單向不等式」(如 $x > 3$) 與「封閉範圍不等式」(如 $-2 < x \\le 4$)，請隨機出題，增加變化性！"

            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的測驗題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 
               - 題目明確問：「求此不等式的解為何？」
               {closed_rule}
               - 【⚠️ 動態選項防呆】：你必須先隨機產生方程式並算出真實解答，再根據解答生成 (A)(B)(C)(D) 選項。選項必須是純文字數學範圍（例如真實解答是 x > -2，選項可能為 (A) x > 2 (B) x > -2 (C) x < 2 (D) x < -2）。絕對不要只輸出死板不變的選項。
            2. "python_code": 
               - 【⚠️ 絕對禁令】：你不准自己寫 plot 或 add_patch 等任何繪圖指令！
               - 你只能「完全照抄」以下兩行程式碼，並將正確解答的參數填入函數中：
               ```python
               fig, ax = plt.subplots(figsize=(8, 3))
               # 參數：ax, 圖形種類("向右射線"/"向左射線"/"封閉區間"), 起點數值, 起點是否實心(True/False), 終點數值(若無則填None), 終點是否實心(預設False)
               draw_number_line(ax, "封閉區間", -2, False, 4, True) # 此為封閉區間範例寫法
               ```
            """
        elif question_type == "純文字計算題 (無插圖)":
            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的計算題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與詳解。
            2. "python_code": 回傳空字串 ""。
            """
        # ✅ 修改3：注入完整的會考非選題 Prompt 模板
        elif question_type == "會考非選素養題 (情境+兩小題)":
            prompt = f"""
            你是專業的台灣國中教育會考數學科出題老師。請根據指定的核心數學概念：【{topic}】，設計一道符合教育會考風格的非選擇題。
            
            {base_rules}
            
            【出題核心特徵與規範】
            1. 情境設計原則
               - 完整生活場景鋪陳：5行以上的文字描述，建立完整故事背景。
               - 時事元素融入：結合當前熱門話題、科技趨勢或社會現象。
               - 自然融入數學：數學問題從情境中自然浮現，不突兀。
               - 素養導向：連結真實生活應用，有實際操作意義。
               - 語句自然流暢：像在講述一個小故事或描述一個現象，避免制式化表達。
               
            2. 題目結構 (固定兩小題設計)
               - 第一小題：考核心概念理解或基本應用。需要思考但不會過於複雜，避免過於直接的問法(如直接問邊長)。答案必須是整數，避免複雜小數計算。
               - 第二小題：具有挑戰性的應用題。需要3-4個步驟的思考或計算，結合多個數學概念或實際應用情境，但不會超出國中課程範圍。
               
            3. 解題自由度設計
               - 絕對不預設變數：不寫「設x為...」「設y為...」。
               - 不直接提示解法：不說「請列不等式」「請用畢氏定理」。
               - 開放多元解法與間接問法：問「關係如何」「最多幾個」「面積為多少」，而非「列出算式」。
               - 自主判斷：讓學生自己決定用什麼數學方法。
               
            4. 難度控制標準
               - 第一題適中挑戰：需要理解概念＋簡單推理，不能太直接，答案為整數。
               - 第二題高層次：需要多步驟思考，涉及複合概念應用，考驗綜合能力。
               - 避免過簡或超綱：不使用高中才學的概念(如餘弦定理)。
               
            【語言風格要求】
               - 台灣在地化：使用台灣學生熟悉的用語和表達方式。
               - 生活化表達：自然流暢，長短句交錯。

            請嚴格回傳 JSON 格式：
            1. "question_text": 內容必須包含以下 Markdown 標題段落：
               ### 題目情境與問題
               (請在此撰寫豐富生動的5行以上情境描述與兩小題)
               ### 自我檢核清單
               (請依據上述規範，列出打勾的檢核清單)
               ### 簡要解答與評分指引
            2. "python_code": 回傳空字串 ""。
            """

    with st.spinner("AI 正在雲端運算與製圖中... (這可能需要 5-10 秒)"):
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
            )
            
            triple_backticks = chr(96) * 3
            regex_pattern = triple_backticks + r"(?:json)?\s*(\{.*?\})\s*" + triple_backticks
            match = re.search(regex_pattern, response.text, re.DOTALL | re.IGNORECASE)
            
            if match:
                clean_json_str = match.group(1)
            else:
                raw_text = response.text.strip()
                start_idx = raw_text.find('{')
                end_idx = raw_text.rfind('}')
                clean_json_str = raw_text[start_idx : end_idx+1] if start_idx != -1 else raw_text
                
            data = json.loads(clean_json_str)
            
            st.session_state.current_question = data['question_text']
            raw_code = data.get('python_code', '').strip()
            
            if raw_code:
                injected_imports = """import matplotlib.pyplot as plt\nimport numpy as np\nfrom matplotlib.patches import Wedge, Circle, Rectangle, Polygon, RegularPolygon\nimport mpl_toolkits.mplot3d\nimport platform\nimport os\nfrom matplotlib import font_manager\nimport urllib.request\nimport re\n"""
                
                font_setup = """
plt.rcParams.update({'font.size': 16})
plt.rcParams['axes.unicode_minus'] = False

def setup_chinese_font():
    font_url = 'https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansTC/NotoSansTC-Regular.ttf'
    font_path = 'NotoSansTC-Regular.ttf'
    
    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(font_url, font_path)
        except:
            pass

    if os.path.exists(font_path):
        font_manager.fontManager.addfont(font_path)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=font_path).get_name()
        return

    sys_os = platform.system()
    search_dirs = ['C:/Windows/Fonts'] if sys_os == 'Windows' else ['/System/Library/Fonts', '/Library/Fonts']
    target_files = ['msjh.ttc', 'msjh.ttf', 'pingfang.ttc']
    
    for d in search_dirs:
        if not os.path.exists(d): continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower() in target_files:
                    try:
                        f_path = os.path.join(root, f)
                        font_manager.fontManager.addfont(f_path)
                        plt.rcParams['font.family'] = font_manager.FontProperties(fname=f_path).get_name()
                        return
                    except:
                        pass
                        
setup_chinese_font()

def set_vertical_ylabel(ax, text):
    res = []
    temp = ""
    in_paren = False
    for char in text:
        if char in '({（':
            in_paren = True
            temp += char
        elif char in ')}）':
            in_paren = False
            temp += char
            res.append(temp)
            temp = ""
        elif in_paren:
            temp += char
        else:
            res.append(char)
    if temp: res.append(temp)
    ax.set_ylabel('\\n'.join(res), rotation=0, labelpad=20, va='center', fontsize=16)

def draw_coordinate_system(ax, x_min=-5, x_max=5, y_min=-5, y_max=5):
    ax.spines['top'].set_color('none')
    ax.spines['right'].set_color('none')
    ax.spines['left'].set_position(('data', 0))
    ax.spines['bottom'].set_position(('data', 0))
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
    
    x_ticks = np.arange(x_min, x_max+1, 1)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(['' if x == 0 else str(x) for x in x_ticks])
    
    y_ticks = np.arange(y_min, y_max+1, 1)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(['' if y == 0 else str(y) for y in y_ticks])
    
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    
    ax.text(x_max + 0.2, -0.3, '$x$', fontsize=14, style='italic')
    ax.text(-0.4, y_max + 0.2, '$y$', fontsize=14, style='italic')
    ax.text(-0.4, -0.4, '$O$', fontsize=14, style='italic')
    
    ax.plot(x_max, 0, marker='>', color='black', clip_on=False, markersize=8, zorder=10)
    ax.plot(0, y_max, marker='^', color='black', clip_on=False, markersize=8, zorder=10)
    
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_aspect('equal')

def draw_prism(ax, N, a, h):
    for i in range(N): 
        ax.add_patch(Rectangle((i*a, 0), a, h, fc='white', ec='black', lw=1.5))
    R = a / (2 * np.sin(np.pi/N))
    apothem = a / (2 * np.tan(np.pi/N))
    ax.add_patch(RegularPolygon((a/2, -apothem), numVertices=N, radius=R, orientation=np.pi/N, fc='white', ec='black', lw=1.5))
    ax.add_patch(RegularPolygon((a/2, h + apothem), numVertices=N, radius=R, orientation=(np.pi/N if N%2==0 else np.pi/N + np.pi), fc='white', ec='black', lw=1.5))
    
    ax.plot([-R, N*a + R], [-apothem - R, h + apothem + R], alpha=0)
    ax.set_aspect('equal')
    ax.axis('off')

def draw_cone(ax, L, r):
    theta = 360 * (r / L)
    ax.add_patch(Wedge((0, L), L, 270 - theta/2, 270 + theta/2, fc='white', ec='black', lw=1.5))
    ax.add_patch(Circle((0, -r), r, fc='white', ec='black', lw=1.5))
    
    ax.plot([-L, L], [-2*r, L], alpha=0)
    ax.set_aspect('equal')
    ax.axis('off')

def draw_voxels(ax, heights):
    heights = np.array(heights)
    cubes = np.zeros((3, 3, 3), dtype=bool)
    for y in range(3):
        for x in range(3):
            for z in range(heights[y, x]):
                cubes[x, y, z] = True
    ax.voxels(cubes, facecolors='#FFFFFF', edgecolors='black', shade=False)
    ax.set(xlim=(0, 3), ylim=(0, 3), zlim=(0, 3))
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=30, azim=-45)
    ax.axis('off')

def draw_right_angle(ax, A, D, C, size=0.5):
    A, D, C = np.array(A), np.array(D), np.array(C)
    u = (A - D) / np.linalg.norm(A - D)
    v = (C - D) / np.linalg.norm(C - D)
    p1 = D + size * u; p2 = p1 + size * v; p3 = D + size * v
    ax.plot([p1[0], p2[0], p3[0]], [p1[1], p2[1], p3[1]], 'k-', lw=1.5)

def draw_number_line(ax, line_type, start_val, start_solid, end_val=None, end_solid=False):
    ax.clear()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_position('zero')
    ax.get_yaxis().set_visible(False)
    
    y_h = 0.5
    
    if line_type == "封閉區間":
        if start_val <= end_val:
            s, e = start_val, end_val
            s_inc, e_inc = start_solid, end_solid
        else:
            s, e = end_val, start_val
            s_inc, e_inc = end_solid, start_solid
            
        s_fc = 'black' if s_inc else 'white'
        e_fc = 'black' if e_inc else 'white'
        
        ax.set_xlim(s - 3, e + 3)
        ax.set_xticks(np.arange(int(s - 3), int(e + 4), 1))
        
        ax.plot([s, s], [0, y_h], 'k-', lw=1.5)
        ax.plot([e, e], [0, y_h], 'k-', lw=1.5)
        ax.plot([s, e], [y_h, y_h], 'k-', lw=1.5)
        ax.plot(s, 0, marker='o', markersize=8, markerfacecolor=s_fc, markeredgecolor='black', zorder=5)
        ax.plot(e, 0, marker='o', markersize=8, markerfacecolor=e_fc, markeredgecolor='black', zorder=5)
        
    elif line_type == "向右射線":
        s = start_val
        s_fc = 'black' if start_solid else 'white'
        
        ax.set_xlim(s - 3, s + 6)
        ax.set_xticks(np.arange(int(s - 3), int(s + 7), 1))
        
        ax.plot([s, s], [0, y_h], 'k-', lw=1.5)
        ax.annotate('', xy=(s + 5, y_h), xytext=(s, y_h), arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
        ax.plot(s, 0, marker='o', markersize=8, markerfacecolor=s_fc, markeredgecolor='black', zorder=5)
        
    elif line_type == "向左射線":
        s = start_val
        s_fc = 'black' if start_solid else 'white'
        
        ax.set_xlim(s - 6, s + 3)
        ax.set_xticks(np.arange(int(s - 6), int(s + 4), 1))
        
        ax.plot([s, s], [0, y_h], 'k-', lw=1.5)
        ax.annotate('', xy=(s - 5, y_h), xytext=(s, y_h), arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
        ax.plot(s, 0, marker='o', markersize=8, markerfacecolor=s_fc, markeredgecolor='black', zorder=5)

    ax.plot(ax.get_xlim()[1], 0, marker='>', color='black', markersize=8, clip_on=False, zorder=4)
    ax.set_ylim(-0.5, 1)
"""
                cleanup_code = f"""
try:
    fig = plt.gcf()
    ax = plt.gca()
    fig.patch.set_visible(False)
    ax.patch.set_visible(False)
    plt.savefig('temp_diagram.png', bbox_inches='tight', dpi=300, transparent={transparent_bg})
    plt.savefig('temp_diagram.svg', bbox_inches='tight', transparent={transparent_bg})
finally:
    plt.close('all')
"""
                
                raw_code = injected_imports + font_setup + raw_code + cleanup_code
                
            st.session_state.current_code = raw_code
            st.session_state.has_image = False 
            
            if st.session_state.current_code:
                if os.path.exists('temp_diagram.png'):
                    os.remove('temp_diagram.png')
                if os.path.exists('temp_diagram.svg'):
                    os.remove('temp_diagram.svg')
                
                try:
                    exec(st.session_state.current_code, globals())
                    if os.path.exists('temp_diagram.png') and os.path.getsize('temp_diagram.png') > 0:
                        st.session_state.has_image = True
                except Exception as code_e:
                    st.error(f"⚠️ 繪圖邏輯錯誤 (題目文字仍可使用)。錯誤細節：{code_e}")
                    st.session_state.has_image = False
            
            st.success("✅ 題目生成完畢！")

        # ✅ 修改2：將 Traceback 藏進 print()，並加上友善的使用者提示
        except json.JSONDecodeError as je:
            print(f"[系統日誌] JSON 格式解析失敗: {je}")
            st.error("❌ 哎呀！AI 剛才不小心把格式弄亂了，請再點一次「產生新題目」按鈕試試看！")
            # 開發者模式：印出 JSON 解析失敗的原始回應與詳細錯誤
            if verify_code == "kaishow":
                st.error(f"🔍 [開發者除錯] JSON 解析錯誤細節：{je}")
                if 'response' in locals() and hasattr(response, 'text'):
                     st.text_area("📦 AI 原始回傳內容 (未解析)：", value=response.text, height=300)

        except Exception as e:
            error_msg = str(e)
            print(f"[系統日誌] 發生錯誤: {error_msg}")
            import traceback
            full_traceback = traceback.format_exc()
            
            if "API key not valid" in error_msg or "API_KEY_INVALID" in error_msg or "400" in error_msg:
                st.error("🔑 哎呀！您輸入的 API 金鑰好像無效或是打錯了，請點擊左側連結重新申請或檢查一下喔！")
            elif "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "quota" in error_msg.lower():
                st.error("😭 你的免費 API 額度用完了 QQ，換一個 Google 帳號申請新的金鑰試試看吧！")
			elif "503" in error_msg or "UNAVAILABLE" in error_msg:
			    # 👇 新增這段來捕捉伺服器塞車
    			st.error("🚦 目前 Google AI 伺服器大塞車 (Error 503)！請稍等幾分鐘後再試，或先切換成 Gemma 模型喔！")
            else:
                st.error("❌ 系統遇到了一點小麻煩，請稍後再試！(詳細錯誤已記錄於後台)")
                
            # 開發者模式：直接在網頁上印出最真實的錯誤堆疊 (Traceback)
            if verify_code == "kaishow":
                st.error("🔍 [開發者除錯] 詳細錯誤堆疊：")
                st.code(full_traceback, language="python")

# =======================================================
# 綁定按鈕動作
# =======================================================
with col_gen:
    if st.button("🌟 產生新題目", type="primary"):
        run_ai_generation(is_reroll=False)

with col_reroll:
    if st.button("🎲 換一組數字"):
        run_ai_generation(is_reroll=True)

# =======================================================
# 顯示產出結果與 Pandoc Word 匯出區塊
# =======================================================
if st.session_state.current_question:
    st.divider()
    
    if st.session_state.has_image and os.path.exists('temp_diagram.png'):
        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("📝 測驗題目 (預覽)")
            st.markdown(st.session_state.current_question, unsafe_allow_html=True)
        with c2:
            st.subheader("📊 題目配圖")
            st.image('temp_diagram.png', use_container_width=True)
    else:
        st.subheader("📝 測驗題目 (預覽)")
        st.markdown(st.session_state.current_question, unsafe_allow_html=True)
    
    st.divider()
    
    st.subheader("📥 匯出 Word 考卷 (Pandoc 完美公式渲染)")
    
    if st.button("🚀 轉換 LaTeX 公式並下載 Word 檔", type="primary"):
        with st.spinner("Pandoc 引擎排版中... (正在轉換 LaTeX 數學公式)"):
            try:
                full_md = st.session_state.current_question
                
                export_ext = "svg" if ".svg" in img_format else "png"
                
                if st.session_state.has_image and os.path.exists(f'temp_diagram.{export_ext}'):
                    full_md += f"\n\n### 題目配圖\n\n![幾何配圖](temp_diagram.{export_ext})\n"
                
                output_filename = "math_test_pandoc.docx"
                pypandoc.convert_text(full_md, 'docx', format='md', outputfile=output_filename)
                
                with open(output_filename, "rb") as f:
                    st.download_button(
                        label="✅ 點此下載完美排版 Word 檔",
                        data=f,
                        file_name="阿凱老師數學單題.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
            except Exception as e:
                st.error(f"Pandoc 轉檔失敗：{e}")
    
    st.divider()
    
    st.subheader("📋 題目原始碼 (供複製)")
    st.code(st.session_state.current_question, language='markdown')
            
    if st.session_state.current_code.strip():
        if verify_code == "kaishow":
            with st.expander("👀 查看 Python 繪圖程式碼"):
                st.code(st.session_state.current_code, language='python')