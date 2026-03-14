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
# 徹底移除 txt 檔案讀寫，改用 Session State 確保每個使用者的 API Key 獨立且網頁關閉即銷毀
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
# 側邊欄：設定與參數
# =======================================================
with st.sidebar:
    st.header("⚙️ 系統設定")
    user_input_key = st.text_input("🔑 請輸入 Google API Key", type="password", value=st.session_state.api_key)
    
    if user_input_key != st.session_state.api_key:
        st.session_state.api_key = user_input_key
    
    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
        st.rerun()
        
    st.markdown("*(您的 API Key 僅於本次連線暫存，關閉網頁即自動銷毀，絕對安全)*")
    st.markdown("---")
    st.header("🎚️ 題目參數設定")
    difficulty = st.select_slider("難度級別", options=["基礎概念", "標準段考", "進階挑戰"], value="標準段考")
    
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
    topic = st.text_input("💡 請輸入出題單元：", value="直角三角形斜邊上的高")
elif question_type == "立體圖形三視圖 (積木堆疊)":
    st.info("💡 系統已注入隨機空間陣列引擎，並強制關閉渲染陰影(shade=False)，確保印刷純黑白！")
elif question_type == "立體圖形展開圖 (圓柱/圓錐/角柱)":
    topic = st.text_input("💡 請輸入要測驗的展開圖圖形：", value="五角柱的展開圖與表面積")
    st.info("💡 系統已注入絕對三角函數公式，圓錐底圓強制接於弧線，角柱保證完美共邊相黏。")
elif question_type == "統計圖表 (折線圖/圓餅圖/長條圖/直方圖)":
    topic = st.text_input("💡 請輸入圖表主題與資料情境：", value="某班學生數學成績直方圖")
    st.info("💡 系統將確保圖表全繁體中文，直方圖連續無空隙。")
elif question_type == "一元一次不等式圖解 (數線)":
    topic = st.text_input("💡 請輸入不等式主題：", value="解一元一次不等式並在數線上圖示")
    st.info("💡 系統已鎖定標準格式：單一數線、無多餘橫線，實/空心圓並以垂直線連接水平範圍箭頭。")
elif question_type == "純文字計算題 (無插圖)":
    topic = st.text_input("💡 請輸入代數或計算主題：", value="一元一次方程式的應用")
elif question_type == "會考非選素養題 (情境+兩小題)":
    topic = st.text_input("💡 請輸入生活情境主題：", value="線性函數與電信資費方案比較")
    st.info("💡 已全面載入阿凱老師的「神級會考非選素養模板」，保證不預設變數、時事導向。")

st.markdown("### 🚀 第二步：生成或修改考題")

col_gen, col_reroll = st.columns([1, 4])

def run_ai_generation(is_reroll=False):
    if not st.session_state.api_key:
        st.warning("請先在左側輸入您的 Google API Key 喔！")
        return

    client = genai.Client(api_key=st.session_state.api_key)
    
    base_rules = """
    【⚠️ 極度重要：JSON、LaTeX 與 Python 繪圖複合規範】
    1. JSON 跳脫：所有的 LaTeX 語法反斜線「必須雙重跳脫」！例如：\\\\triangle。
    2. LaTeX 包覆：所有的數學符號、方程式，絕對必須用 $ 符號包覆起來，否則網頁無法渲染！
    3. 【考卷印刷視覺規範】：所有的繪圖絕對禁止使用灰色或彩色填滿！一律「純白底、純黑線」。
    4. 【⚠️ Markdown 刪除線防呆】：若要表示分數或數字範圍，【絕對使用全形波浪號「～」或連字號「-」】（例如 50～60 或 50-60），嚴禁使用半形波浪號「~」，否則會觸發 Markdown 刪除線導致排版大亂！
    """

    if is_reroll:
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
               - 使用 ax.set_aspect('equal') 與 ax.axis('off')。
               - 【⚠️ 直角記號絕對防呆】：必須照抄以下向量邏輯：
                 u = (A - D) / np.linalg.norm(A - D); v = (C - D) / np.linalg.norm(C - D)
                 p1 = D + 0.5 * u; p2 = p1 + 0.5 * v; p3 = D + 0.5 * v
                 ax.plot([p1[0], p2[0], p3[0]], [p1[1], p2[1], p3[1]], 'k-', lw=1.5)
               - 【⚠️ 圖片裁切防禦機制】：繪圖最後，請「絕對」加上以下三行，強迫系統重新計算邊界並留白，防止圓弧或圖形被卡斷：
                 ax.relim()
                 ax.autoscale_view()
                 ax.margins(0.15)
               - 存為 temp_diagram.png (bbox_inches='tight')。
            """
        elif question_type == "立體圖形三視圖 (積木堆疊)":
            # 由 Python 端負責隨機挑選視角與陣列，強迫 AI 每次考不同的圖！
            target_view = random.choice(["前視圖", "上視圖", "右視圖"])
            h_matrix = f"[[{random.randint(0,3)}, {random.randint(0,3)}, {random.randint(0,2)}], " \
                       f"[{random.randint(0,3)}, {random.randint(1,3)}, {random.randint(0,3)}], " \
                       f"[{random.randint(0,2)}, {random.randint(0,3)}, {random.randint(0,2)}]]"
            
            prompt = f"""
            請生成一道【{difficulty}】難度的「立體積木三視圖」選擇題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 
               - 題目指定測驗：【{target_view}】！
               - 題目問：「如圖為正方體堆疊的立體圖形，請判斷其【{target_view}】為何？」
               - 【⚠️ AI 空間推算防呆】：請務必根據我提供的 heights 陣列，精準推算出正確的 {target_view} 畫面，並確保它存在於選項中！
               - 【⚠️ 選項排版絕對防呆】：四個選項必須是完美的 3x3 矩陣。請「絕對」使用全形 ⬛ 與 ⬜。每一列結束務必加上 `<br>`。例如："(A)<br>⬜⬜⬜<br>⬜⬛⬜<br>⬛⬛⬛"
            2. "python_code": 
               - 【⚠️ 答案同步與重力防呆】：絕對不可以使用 np.random！請完全照抄以下我給你的陣列（這是我給你的新題目數據）：
                 heights = np.array({h_matrix})
                 cubes = np.zeros((3, 3, 3), dtype=bool)
                 for x in range(3):
                     for y in range(3):
                         for z in range(heights[x, y]):
                             cubes[x, y, z] = True
               - 【⚠️ 正方體鎖定與純黑白防呆】：繪圖時「必須」加上這行：`ax.set_box_aspect((1, 1, 1))`
               - 積木必須是純白底黑線，絕對不可有灰階陰影！請絕對照抄這行畫積木：`ax.voxels(cubes, facecolors='white', edgecolors='black', shade=False)`
               - 使用 ax.view_init(elev=30, azim=-45)。隱藏座標軸。存為 temp_diagram.png (bbox_inches='tight')。
            """
        elif question_type == "立體圖形展開圖 (圓柱/圓錐/角柱)":
            prompt = f"""
            你是一位專業的國中數學老師。請根據主題：【{topic}】，生成一道【{difficulty}】難度的「立體圖形展開圖」幾何題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與解析。
            2. "python_code": 繪製該圖形的展開圖。
               - 【⚠️ 角柱展開圖防呆演算法】：AI你不會算旋轉，請【絕對照抄】這段演算法畫角柱，它保證多邊形 100% 完美貼合矩形邊緣(以 N角柱為例)：
                 N = 5 # 依照題目多邊形邊數修改(如3,4,5,6)
                 a = 2; h = 5
                 for i in range(N): ax.add_patch(Rectangle((i*a, 0), a, h, fc='white', ec='black', lw=1.5))
                 R = a / (2 * np.sin(np.pi/N)); apothem = a / (2 * np.tan(np.pi/N))
                 # 下底 (完美貼合)
                 ax.add_patch(RegularPolygon((a/2, -apothem), numVertices=N, radius=R, orientation=np.pi/N, fc='white', ec='black', lw=1.5))
                 # 上底 (完美翻轉 180 度貼合)
                 ax.add_patch(RegularPolygon((a/2, h + apothem), numVertices=N, radius=R, orientation=(np.pi/N if N%2==0 else np.pi/N + np.pi), fc='white', ec='black', lw=1.5))
               - 【⚠️ 圓錐防呆】：底圓必須接在「弧線」正上方！請絕對照抄這段程式：
                 L = 10; r = 3; theta = 360 * (r / L)
                 # 扇形開口朝上 (弧線在上方)
                 ax.add_patch(Wedge((0,0), L, 90 - theta/2, 90 + theta/2, fc='white', ec='black', lw=1.5))
                 # 圓接在上方弧線的頂點
                 ax.add_patch(Circle((0, L + r), r, fc='white', ec='black', lw=1.5))
               - 使用 ax.set_aspect('equal') 與 ax.axis('off')。務必使用 ax.set_xlim 與 ax.set_ylim 包含全圖。
               - 存為 temp_diagram.png (bbox_inches='tight')。
            """
        elif question_type == "統計圖表 (折線圖/圓餅圖/長條圖/直方圖)":
            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的統計圖表題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、選項與解析。
            2. "python_code": 
               - 【⚠️ 繁體中文防呆】：圖表的標題、X軸標籤、Y軸標籤、圖例，全部必須使用繁體中文。
               - 圖表背景強制全白，不可有灰階填色。直方圖長條必須緊密相連 (width=組距)。
               - 存為 temp_diagram.png (bbox_inches='tight')。
            """
        elif question_type == "一元一次不等式圖解 (數線)":
            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的測驗題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 
               - 系統只配一張正確的圖作為解析，題目【絕對不可以】問「請選出正確的圖解」。
               - 題目明確問：「求此不等式的解為何？」
               - 四個選項必須是純文字的數學範圍（如 (A) $x > 3$）。數學式必須加上 $ 包覆。範圍隨機向右或向左。
            2. "python_code": 
               - 【⚠️ 完美單一數線防呆】：請絕對照抄以下畫法，不准用 ax.axhline，直接利用 spines 作為唯一數線：
                 ax.spines['top'].set_visible(False)
                 ax.spines['right'].set_visible(False)
                 ax.spines['left'].set_visible(False)
                 ax.spines['bottom'].set_position('zero')
                 ax.get_yaxis().set_visible(False)
                 # 【⚠️ 警告系統：不准亂縮放！強迫顯示完整的左右範圍！】
                 ax.set_xlim(ans - 6, ans + 6)
                 ax.set_xticks(np.arange(ans-5, ans+6, 1))
                 ax.plot([ans, ans], [0, 0.5], 'k-', lw=1.5) # 垂直線
                 # 若向右 x_end = ans + 4；若向左 x_end = ans - 4
                 ax.annotate('', xy=(x_end, 0.5), xytext=(ans, 0.5), arrowprops=dict(arrowstyle='->', lw=1.5))
                 ax.plot(ans, 0, marker='o', markersize=8, markerfacecolor='black', markeredgecolor='black', zorder=5) # 實心fc='black', 空心fc='white'
                 ax.set_ylim(-0.5, 1)
                 # 【⚠️ 圖片裁切防禦】：強制留白，確保箭頭不被切掉
                 ax.margins(0.15)
               - 存為 temp_diagram.png (bbox_inches='tight')。
            """
        elif question_type == "純文字計算題 (無插圖)":
            prompt = f"""
            請生成一道【{difficulty}】難度，主題為【{topic}】的計算題。
            {base_rules}
            請回傳 JSON：
            1. "question_text": 包含題目、四個選項與詳解。
            2. "python_code": 回傳空字串 ""。
            """
        elif question_type == "會考非選素養題 (情境+兩小題)":
            prompt = f"""
            任務說明：你是專業的台灣國中教育會考數學科出題老師，請根據指定的概念【{topic}】，設計一道符合教育會考風格的非選擇題。
            {base_rules}

            出題核心特徵：
            1. 情境設計原則：完整生活場景鋪陳(5行以上的文字描述)，建立完整故事背景。融入當前熱門時事科技趨勢。自然融入數學，素養導向。語句自然流暢像講故事。
            2. 題目結構：固定兩小題設計。
               - 第一小題：考核心概念理解，避免直接問法(如直接問邊長)，可以問周長/關係等一步推理。答案必須是整數。
               - 第二小題：具有挑戰性的應用題，需3-4個步驟思考，不超出國中範圍，考驗綜合分析能力。
            3. 解題自由度設計：絕對不預設變數(不寫「設x為...」「設y為...」)，不直接提示解法(不說請列不等式)，問法間接(如問「最多幾個」)，開放多元解法。
            4. 語言風格要求：用語台灣在地化，符合台灣國中生的認知程度。

            請嚴格回傳 JSON 格式：
            1. "question_text": 
               必須包含以下三個 Markdown 標題段落：
               ### 題目情境與問題 (包含完整情境與兩小題)
               ### 自我檢核清單 (列出你的檢查項目並打勾)
               ### 簡要解答與評分指引 (提供 0~3 分的給分標準)
            2. "python_code": 回傳空字串 ""。
            """

    with st.spinner("AI 正在雲端運算與製圖中... (這可能需要 5-10 秒)"):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
            )
            
            # 【避開 Markdown 截斷 Bug，使用 chr(96) 組合字串】
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
                # 【絕對防禦：將所有可能用到的套件強制寫入執行的程式碼中】
                injected_imports = """import matplotlib.pyplot as plt\nimport numpy as np\nfrom matplotlib.patches import Wedge, Circle, Rectangle, Polygon, RegularPolygon\nimport mpl_toolkits.mplot3d\nimport platform\nimport os\nimport urllib.request\nfrom matplotlib import font_manager\n"""
                
                # 【加入動態硬碟掃描與穩定 Github 下載機制 - 完美支援雲端 Linux 與本機】
                font_setup = """
plt.rcParams.update({'font.size': 16})
plt.rcParams['axes.unicode_minus'] = False

def setup_chinese_font():
    font_url = 'https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSansTC/NotoSansTC-Regular.ttf'
    font_path = 'NotoSansTC-Regular.ttf'
    success = False
    
    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(font_url, font_path)
            success = True
        except:
            pass
    else:
        success = True

    if success:
        try:
            font_manager.fontManager.addfont(font_path)
            plt.rcParams['font.family'] = font_manager.FontProperties(fname=font_path).get_name()
            return
        except:
            pass

    # 若下載失敗，啟動動態硬碟掃描 (本機回退機制)
    sys_os = platform.system()
    search_dirs = ['C:/Windows/Fonts'] if sys_os == 'Windows' else ['/System/Library/Fonts', '/Library/Fonts', os.path.expanduser('~/Library/Fonts')]
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
                        
    # 最終備案
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei'] if sys_os == 'Windows' else ['PingFang TC', 'Noto Sans CJK TC']

setup_chinese_font()
"""
                
                raw_code = injected_imports + font_setup + raw_code
                
            st.session_state.current_code = raw_code
            st.session_state.has_image = False 
            
            if st.session_state.current_code:
                if os.path.exists('temp_diagram.png'):
                    os.remove('temp_diagram.png')
                
                try:
                    # 執行安全的隔離空間
                    exec(st.session_state.current_code, globals())
                    if os.path.exists('temp_diagram.png') and os.path.getsize('temp_diagram.png') > 0:
                        st.session_state.has_image = True
                except Exception as code_e:
                    st.error(f"⚠️ 繪圖邏輯錯誤 (題目文字仍可使用)。錯誤細節：{code_e}")
                    st.session_state.has_image = False
            
            st.success("✅ 題目生成完畢！")

        except json.JSONDecodeError as je:
            st.error(f"❌ JSON 格式解析失敗！請再點一次生成按鈕。細節: {je}")
        except Exception as e:
            st.error(f"❌ 發生錯誤。錯誤訊息: {e}")

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
                if st.session_state.has_image and os.path.exists('temp_diagram.png'):
                    full_md += "\n\n### 題目配圖\n\n![幾何配圖](temp_diagram.png)\n"
                
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
        with st.expander("👀 查看 Python 繪圖程式碼"):
            st.code(st.session_state.current_code, language='python')