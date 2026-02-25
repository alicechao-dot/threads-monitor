import streamlit as st
import time
import json
import requests
import re
import pandas as pd
from datetime import datetime, timedelta
from apify_client import ApifyClient

# ==========================================
# 🔑 安全設定區 (從 Secrets 讀取)
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
APIFY_TOKEN = st.secrets["APIFY_TOKEN"]
MODEL_NAME = "gemini-3.0-flash"

# ==========================================

st.set_page_config(page_title="Threads 大數據監測 V8.5", page_icon="📊", layout="wide")
def scrape_threads_massive(keyword, max_posts, exclude_words_str, date_range):
    client = ApifyClient(APIFY_TOKEN)
    fetch_count = int(max_posts * 2)
    if fetch_count > 500: fetch_count = 500
    
    run_input = {
        "keywords": [keyword],         
        "maxItemsPerKeyword": fetch_count 
    }

    try:
        run = client.actor("watcher.data/search-threads-by-keywords").call(run_input=run_input)
        exclude_list = [w.strip() for w in exclude_words_str.split() if w.strip()]
        
        start_date = datetime.combine(date_range[0], datetime.min.time())
        end_date = datetime.combine(date_range[1], datetime.max.time())

        results = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            text = item.get("text", "")
            if not text: continue
            if any(bad_word in text for bad_word in exclude_list): continue
            
            try:
                post_date = datetime.strptime(item.get("created_at", "").split('.')[0].replace('Z', ''), "%Y-%m-%dT%H:%M:%S")
            except:
                post_date = datetime.now()
                
            if not (start_date <= post_date <= end_date): continue
            
            results.append({
                "關鍵字": keyword,
                "發布日期": post_date.strftime("%Y-%m-%d %H:%M"),
                "作者": item.get("author", "匿名"),
                "內容": text,
                "愛心數": item.get("like_count", 0),
                "回覆數": item.get("reply_count", 0),
                "網址": item.get("url", "#") # 👈 確保網址有被抓到
            })
            if len(results) >= max_posts: break
        return results
    except Exception as e:
        st.error(f"抓取失敗: {e}")
        return []

def analyze_massive_with_ai(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    分析這則貼文並以純 JSON 格式回傳 (不要 Markdown)：
    {{ "sentiment": "正面/負面/中立", "summary": "10字內摘要", "score": 1-5, "insight": "一句話重點" }}
    貼文內容："{text}"
    """
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return None

# --- UI 介面 ---
st.title("📊 Threads 輿情大數據監測 V8.3")
st.markdown(f"核心大腦：**Gemini 3.0 Flash** | 已修正網址連結顯示問題。")

with st.sidebar:
    st.header("⚙️ 篩選與監測設定")
    date_range = st.date_input("📅 監測日期範圍", (datetime.now() - timedelta(days=7), datetime.now()))
    exclude_input = st.text_input("🚫 排除關鍵字 (空白隔開)", "廣告 詐騙 抽獎 加賴 官方")
    st.divider()
    keywords_input = st.text_area("🔑 監測關鍵字 (一行一個)", "凱基\n國泰", height=100)
    post_limit = st.number_input("每個關鍵字抓取篇數", min_value=1, max_value=500, value=50)

if st.button("🚀 開始精準大數據分析", type="primary"):
    k_list = [k.strip() for k in keywords_input.split('\n') if k.strip()]
    if not k_list:
        st.warning("請輸入關鍵字")
    else:
        st.info(f"正在分析中...")
        all_data = []
        progress_bar = st.progress(0)
        
        for k_idx, kw in enumerate(k_list):
            raw_posts = scrape_threads_massive(kw, post_limit, exclude_input, date_range)
            for p in raw_posts:
                ai_res = analyze_massive_with_ai(p['內容'])
                analysis = {"sentiment": "中立", "summary": "無法解析", "score": 3, "insight": "無"}
                if ai_res:
                    try:
                        clean = ai_res.replace("```json", "").replace("```", "").strip()
                        match = re.search(r"\{.*\}", clean, re.DOTALL)
                        analysis = json.loads(match.group(0)) if match else json.loads(clean)
                    except: pass
                p.update({
                    "情緒": analysis.get('sentiment'),
                    "摘要": analysis.get('summary'),
                    "評分": analysis.get('score'),
                    "核心洞察": analysis.get('insight')
                })
                all_data.append(p)
            progress_bar.progress((k_idx + 1) / len(k_list))
        
        if all_data:
            df = pd.DataFrame(all_data)
            st.success(f"✅ 成功處理 {len(df)} 則精準貼文！")
            
            # --- 下載區 ---
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載完整輿情報表 (CSV)", csv, f"threads_report.csv", "text/csv")
            
            # --- 預覽表格 (優化連結顯示) ---
            st.subheader("📋 最新輿情預覽 (網址欄位可直接點擊)")
            
            # 使用 column_config 讓網址變亮、可點擊
            st.dataframe(
                df[["發布日期", "關鍵字", "情緒", "摘要", "評分", "愛心數", "核心洞察", "網址", "內容"]],
                column_config={
                    "網址": st.column_config.LinkColumn(
                        "🔗 查看原文",
                        help="點擊跳轉至 Threads 貼文頁面",
                        validate="^https://.*",
                        display_text="點擊開啟"
                    ),
                    "評分": st.column_config.NumberColumn(format="%d ⭐")
                },
                use_container_width=True,
                hide_index=True

            )

