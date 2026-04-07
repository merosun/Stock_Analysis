import streamlit as st
import requests
import pandas as pd
import time
import plotly.graph_objects as go
import yfinance as yf

@st.cache_data(ttl=86400) # 快取 24 小時，避免頻繁發送 1700 檔清單請求

def get_industry_mapping():
    """從 FinMind 動態獲取台股全市場分類清單"""
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    industry_dict = {}
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get('status') == 200:
            for stock in data.get('data', []):
                category = stock.get('industry_category', '*未分類')
                code = stock.get('stock_id', '')
                name = stock.get('stock_name', '') # 取得中文名稱

                # 只抓取標準 64 碼的上市櫃股票，過濾掉權證與牛熊證
                if len(code) == 4 and code.isdigit():
                    if category not in industry_dict:
                        industry_dict[category] = {} # 改用字典存儲
                    industry_dict[category][code] = name # 建立 ID -> Name 的映射
    except Exception as e:
        st.error(f"獲取產業清單失敗: {e}")
        
    # 剔除空分類，並按字母/筆畫排序以利選單呈現
    return {k: v for k, v in sorted(industry_dict.items()) if v}

def get_stock_code(stock_input):
    """
    【引擎升級】改用 FinMind 開放金融 API，徹底繞過證交所雲端 IP 封鎖。
    """
    if stock_input.isdigit(): 
        return stock_input
        
    # FinMind 台灣股市資訊總表 API
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # 確認 API 回傳狀態碼為 200 (成功)
        if data.get('status') == 200:
            stock_list = data.get('data', [])
            
            for stock in stock_list:
                # 欄位名稱對應 FinMind 的格式：'stock_name' 與 'stock_id'
                if stock.get('stock_name', '').strip() == stock_input.strip():
                    return stock.get('stock_id', '')
    except: 
        pass
        
    return None

def fetch_twse_data(stock_no, target_date=None):
    """
    【引擎升級】改用 yfinance 繞過證交所雲端 IP 封鎖。
    自動抓取近 3 個月資料，確保均線(MA)計算有足夠的歷史數據基底。
    """
    # 台股上市代碼必須加上後綴 .TW 才能在 Yahoo 系統中識別
    ticker = f"{stock_no}.TW"
    try:
        # 下載近3個月歷史數據
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty:
            return None
            
        # 整理 DataFrame 格式以完全相容我們原本的系統架構
        df = df.reset_index()
        
        # 處理 yfinance 新版可能出現的多層級欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 將英文欄位重新命名為中文，對接原有的繪圖與分析模組
        df = df.rename(columns={
            'Date': '日期',
            'Open': '開盤價',
            'High': '最高價',
            'Low': '最低價',
            'Close': '收盤價'
        })
        
        # 轉換日期格式為字串
        df['日期'] = df['日期'].dt.strftime('%Y%m%d')
        
        # 捨棄不需要的欄位，只回傳核心價格數據
        return df[['日期', '開盤價', '最高價', '最低價', '收盤價']]
        
    except Exception as e:
        print(f"yfinance 數據截獲失敗: {e}")
        return None

def process_and_analyze(df):
    """
    資料運算模組更新
    """
    # yfinance 回傳的已經是乾淨的數值型態，不再需要去逗號轉換字串
    cols = ['開盤價', '最高價', '最低價', '收盤價']
    df[cols] = df[cols].astype(float)
    
    # 計算移動平均線
    df['MA5'] = df['收盤價'].rolling(window=5).mean()
    df['MA10'] = df['收盤價'].rolling(window=10).mean()
    return df

def generate_trend_report(df):
    """【新增】專業趨勢判定與策略生成器"""
    # 確保資料依時間正序排列，以取得最新狀態
    df_sorted = df.sort_values(by='日期', ascending=True).dropna(subset=['MA10'])
    
    if len(df_sorted) < 2:
        return "⚠️ 資料天數不足，無法產生具參考價值的均線趨勢評語（需至少大於10個交易日）。"

    latest = df_sorted.iloc[-1]
    prev = df_sorted.iloc[-2]

    close = latest['收盤價']
    ma5, prev_ma5 = latest['MA5'], prev['MA5']
    ma10, prev_ma10 = latest['MA10'], prev['MA10']

    # 核心判定邏輯
    if prev_ma5 <= prev_ma10 and ma5 > ma10:
        trend = "🌟 黃金交叉成型"
        advice = "短期均線向上突破長期均線，多頭動能轉強。此為波段起漲的強烈買點訊號，建議觀察量能是否同步放大，若帶量突破可積極佈局。"
        color = "success"
    elif prev_ma5 >= prev_ma10 and ma5 < ma10:
        trend = "⚠️ 死亡交叉成型"
        advice = "短期均線向下掼破長期均線，空頭賣壓沉重。趨勢已轉弱，建議嚴格執行停損或大幅減碼，避開後續主跌段。"
        color = "error"
    elif close > ma5 and ma5 > ma10:
        trend = "📈 多頭排列強勢"
        advice = "股價穩居均線之上，且短均線大於長均線，趨勢強勢偏多。建議順勢操作，持股續抱，並以 MA5 跌破與否作為短期移動停利點。"
        color = "info"
    elif close < ma5 and ma5 < ma10:
        trend = "📉 空頭排列弱勢"
        advice = "股價遭均線沉重反壓，趨勢偏空。底部尚未爆量成型前，切忌貿然進場摸底，保留現金觀望為上策。"
        color = "warning"
    else:
        trend = "⚖️ 區間震盪盤整"
        advice = "均線糾結或股價穿梭於均線之間，多空方向未明。目前屬於籌碼沉澱期，建議耐心等待帶量突破盤整區間的表態訊號再行操作。"
        color = "info"

    # 輸出格式化報告
    report = f"""
    ### {trend}
    * **最新收盤價：** {close} 元
    * **5日均線 (MA5)：** {ma5:.2f} 元
    * **10日均線 (MA10)：** {ma10:.2f} 元
    
    **💡 操盤策略評語：**
    > {advice}
    """
    return report, color

def plot_candlestick(df, stock_name):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['日期'], open=df['開盤價'], high=df['最高價'], low=df['最低價'], close=df['收盤價'],
        name='K線', increasing_line_color='red', decreasing_line_color='green'
    ))
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA5'], mode='lines', name='MA5', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA10'], mode='lines', name='MA10', line=dict(color='blue', width=2)))
    fig.update_layout(title=f"{stock_name} 技術分析圖", yaxis_title="股價 (TWD)", xaxis_rangeslider_visible=False, template="plotly_dark")
    return fig

# --- Web UI 介面設計 ---
st.set_page_config(layout="wide")
st.title("📈 量化交易終端機 - 智能評估版")

# 【核心修改】建立兩個標籤頁來區分功能，避免狀態重置
tab1, tab2 = st.tabs(["📊 單檔智能分析", "🚀 板塊爆量掃描"])

# ==========================================
# 標籤頁一：單檔智能分析
# ==========================================
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        user_input = st.text_input("輸入股票名稱或代碼", "台積電")
    with col2:
        target_date = st.text_input("輸入查詢年月 (YYYYMMDD)", "20260401")

    if st.button("執行單檔智能分析", use_container_width=True):
        with st.spinner('正在截獲數據並進行運算...'):
            stock_code = get_stock_code(user_input)
            if stock_code:
                time.sleep(1) 
                raw_df = fetch_twse_data(stock_code, target_date)
                
                if raw_df is not None:
                    analyzed_df = process_and_analyze(raw_df.copy())
                    
                    report_md, alert_color = generate_trend_report(analyzed_df)
                    if alert_color == "success": st.success(report_md)
                    elif alert_color == "error": st.error(report_md)
                    elif alert_color == "warning": st.warning(report_md)
                    else: st.info(report_md)

                    chart = plot_candlestick(analyzed_df, user_input)
                    st.plotly_chart(chart, use_container_width=True)
                    
                    analyzed_df = analyzed_df.sort_values(by='日期', ascending=False)
                    st.dataframe(analyzed_df, use_container_width=True) 
                else:
                    st.error("查無數據，請確認該標的近期是否有交易。")
            else:
                st.error("找不到該股票，請確認名稱是否正確。")

# ==========================================
# 標籤頁二：全自動板塊掃描引擎 (含中文名稱與序號優化)
# ==========================================
with tab2:
    st.markdown("### 🔍 產業板塊掃描器")
    
    INDUSTRY_STOCKS = get_industry_mapping()
    
    if not INDUSTRY_STOCKS:
        st.warning("無法獲取產業分類。")
    else:
        selected_industry = st.selectbox("請選擇要掃描的資金板塊：", list(INDUSTRY_STOCKS.keys()))
        
        # 取得該板塊下「代碼對名稱」的字典
        current_sector_map = INDUSTRY_STOCKS[selected_industry]
        watch_list = list(current_sector_map.keys()) # 所有的代碼
        stock_count = len(watch_list)
        st.caption(f"該板塊目前共收錄 {stock_count} 檔標的")
        
        if st.button(f"🚀 開始掃描【{selected_industry}】", use_container_width=True):
            with st.spinner('掃描運算中...'):
                tickers = [f"{code}.TW" for code in watch_list]
                try:
                    data = yf.download(tickers, period="1mo", group_by='ticker', progress=False)
                    
                    results = []
                    for code in watch_list:
                        ticker_tw = f"{code}.TW"
                        
                        # 數據處理邏輯 (與先前相同)
                        if len(watch_list) == 1:
                            df = data.copy()
                        else:
                            if ticker_tw not in data.columns.get_level_values(0).unique(): continue
                            df = data[ticker_tw].copy()
                            
                        df = df.dropna()
                        if len(df) < 20: continue 

                        latest_close = float(df['Close'].iloc[-1])
                        lowest_20d = float(df['Low'].rolling(window=20).min().iloc[-1])
                        latest_vol = float(df['Volume'].iloc[-1])
                        avg_vol_5d = float(df['Volume'].iloc[-6:-1].mean())

                        is_low_price = latest_close <= (lowest_20d * 1.05)
                        is_high_vol = latest_vol > (avg_vol_5d * 2) if avg_vol_5d > 0 else False

                        if is_low_price and is_high_vol:
                            results.append({
                                "股票代碼": code,
                                "股票名稱": current_sector_map[code], # 從映射表中取出名稱
                                "最新收盤價": round(latest_close, 2),
                                "20日最低價": round(lowest_20d, 2),
                                "今日成交量": f"{int(latest_vol):,}",
                                "突破爆量倍數": f"{round(latest_vol / avg_vol_5d, 1)} 倍"
                            })

                    if results:
                        st.success(f"🎯 發現 {len(results)} 檔符合型態標的：")
                        
                        # --- 序號優化處理 ---
                        final_df = pd.DataFrame(results)
                        # 將索引設為從 1 開始
                        final_df.index = range(1, len(final_df) + 1) 
                        
                        st.dataframe(final_df, use_container_width=True)
                    else:
                        st.info(f"【{selected_industry}】目前無底部爆量訊號。")

                except Exception as e:
                    st.error(f"掃描引擎異常: {e}")