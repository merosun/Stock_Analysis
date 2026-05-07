import streamlit as st
import requests
import pandas as pd
import time
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime

# ==========================================
# 核心資料截獲模組 (API & 爬蟲引擎)
# ==========================================

@st.cache_data(ttl=86400) # 快取 24 小時，減輕伺服器負擔
def get_industry_mapping():
    """從 FinMind 動態獲取台股全市場分類清單，並建立 [代碼 -> 名稱] 的對照表"""
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    industry_dict = {}
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get('status') == 200:
            for stock in data.get('data', []):
                category = stock.get('industry_category', '*未分類')
                code = stock.get('stock_id', '')
                name = stock.get('stock_name', '')
                
                # 只抓取標準 4 碼的上市櫃現貨股票
                if len(code) == 4 and code.isdigit():
                    if category not in industry_dict:
                        industry_dict[category] = {}
                    industry_dict[category][code] = name
    except Exception as e:
        st.error(f"獲取產業清單失敗: {e}")
        
    return {k: v for k, v in sorted(industry_dict.items()) if v}

def get_stock_code(stock_input):
    """將使用者輸入的中文名稱轉換為股票代碼"""
    if stock_input.isdigit(): 
        return stock_input
        
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get('status') == 200:
            for stock in data.get('data', []):
                if stock.get('stock_name', '').strip() == stock_input.strip():
                    return stock.get('stock_id', '')
    except: 
        pass
    return None

def fetch_twse_data(stock_no, target_date=None):
    """智能數據截獲引擎：具備自動雙軌切換 (上市 .TW -> 上櫃 .TWO) 容錯機制"""
    ticker = f"{stock_no}.TW"
    try:
        # 第一階段：嘗試上市市場
        df = yf.download(ticker, period="3mo", progress=False)
        
        # 第二階段：若查無資料，自動切換至上櫃市場
        if df.empty:
            ticker = f"{stock_no}.TWO"
            df = yf.download(ticker, period="3mo", progress=False)
            
            if df.empty:
                return None
                
        # 數據標準化
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.rename(columns={
            'Date': '日期', 'Open': '開盤價', 'High': '最高價', 
            'Low': '最低價', 'Close': '收盤價', 'Volume': '成交股數'
        })
        df['日期'] = df['日期'].dt.strftime('%Y%m%d')
        
        return df[['日期', '開盤價', '最高價', '最低價', '收盤價', '成交股數']]
        
    except Exception as e:
        print(f"yfinance 數據截獲失敗 ({ticker}): {e}")
        return None

# ==========================================
# 策略運算與分析模組
# ==========================================

def process_and_analyze(df):
    """計算價格均線與籌碼均量"""
    cols = ['開盤價', '最高價', '最低價', '收盤價', '成交股數']
    df[cols] = df[cols].astype(float)
    
    df['MA5'] = df['收盤價'].rolling(window=5).mean()
    df['MA10'] = df['收盤價'].rolling(window=10).mean()
    df['Vol_MA5'] = df['成交股數'].rolling(window=5).mean()
    return df

def generate_trend_report(df):
    """專業趨勢判定與量能策略生成器"""
    df_sorted = df.sort_values(by='日期', ascending=True).dropna(subset=['MA10', 'Vol_MA5'])
    if len(df_sorted) < 2:
        return "⚠️ 資料天數不足，無法產生具參考價值的評語。", "warning"

    latest = df_sorted.iloc[-1]
    prev = df_sorted.iloc[-2]

    # 提取數據
    close = latest['收盤價']
    ma5, prev_ma5 = latest['MA5'], prev['MA5']
    ma10, prev_ma10 = latest['MA10'], prev['MA10']
    vol_latest = latest['成交股數'] / 1000  # 換算為張
    vol_ma5 = latest['Vol_MA5'] / 1000      # 換算為張

    # 1. 量能判定 (流動性控管)
    if vol_ma5 < 500:
        vol_status = "⚠️ 流動性低迷"
        vol_advice = f"近5日均量僅 {vol_ma5:.0f} 張。籌碼流動性極差，容易產生滑價風險或遭主力控盤，建議避開此類標的。"
    elif vol_latest > (vol_ma5 * 2) and vol_ma5 > 0:
        vol_status = "🔥 異常爆量表態"
        vol_advice = f"今日成交量達 {vol_latest:.0f} 張，突破5日均量兩倍以上。顯示有主力資金進駐或換手跡象，量能充沛。"
    else:
        vol_status = "🌊 量能健康穩定"
        vol_advice = f"今日成交量 {vol_latest:.0f} 張，維持在近期常態水準，適合依循技術面操作。"

    # 2. 價格趨勢判定
    if prev_ma5 <= prev_ma10 and ma5 > ma10:
        trend = "🌟 黃金交叉成型"
        price_advice = "短期均線向上突破長期均線，此為波段起漲的強烈買點訊號。"
        color = "success"
    elif prev_ma5 >= prev_ma10 and ma5 < ma10:
        trend = "⚠️ 死亡交叉成型"
        price_advice = "短期均線向下掼破長期均線，趨勢已轉弱，建議嚴格執行停損或大幅減碼。"
        color = "error"
    elif close > ma5 and ma5 > ma10:
        trend = "📈 多頭排列強勢"
        price_advice = "股價穩居均線之上，建議順勢操作，持股續抱。"
        color = "info"
    elif close < ma5 and ma5 < ma10:
        trend = "📉 空頭排列弱勢"
        price_advice = "股價遭均線沉重反壓，切忌貿然進場摸底，觀望為上策。"
        color = "warning"
    else:
        trend = "⚖️ 區間震盪盤整"
        price_advice = "均線糾結，多空方向未明，建議耐心等待帶量突破盤整區間。"
        color = "info"

    # 3. 組合報告
    report = f"""
    ### 📊 系統綜合評測
    #### 【價格面】 {trend}
    * **最新收盤價：** {close:.2f} 元
    * **5日均線 (MA5)：** {ma5:.2f} 元
    * **10日均線 (MA10)：** {ma10:.2f} 元
    > **💡 策略：** {price_advice}
    
    #### 【籌碼面】 {vol_status}
    * **今日成交量：** {vol_latest:.0f} 張
    * **5日均量：** {vol_ma5:.0f} 張
    > **💡 策略：** {vol_advice}
    """
    return report, color

def plot_candlestick(df, stock_name):
    """繪製專業技術線圖"""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df['日期'], open=df['開盤價'], high=df['最高價'], low=df['最低價'], close=df['收盤價'],
        name='K線', increasing_line_color='red', decreasing_line_color='green'
    ))
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA5'], mode='lines', name='MA5', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=df['日期'], y=df['MA10'], mode='lines', name='MA10', line=dict(color='blue', width=2)))
    fig.update_layout(title=f"{stock_name} 技術分析圖", yaxis_title="股價 (TWD)", xaxis_rangeslider_visible=False, template="plotly_dark")
    return fig


# ==========================================
# Web UI 介面設計 (雙標籤頁架構)
# ==========================================
st.set_page_config(layout="wide", page_title="量化交易終端機")
st.title("📈 量化交易終端機 - 智能評估版")

tab1, tab2 = st.tabs(["📊 單檔智能分析", "🚀 板塊爆量掃描"])

# --- 標籤頁一：單檔智能分析 ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        user_input = st.text_input("輸入股票名稱或代碼", "台積電")
    with col2:
        # 自動獲取當天日期做為預設值
        today_str = datetime.now().strftime("%Y%m%d")
        target_date = st.text_input("輸入查詢年月 (YYYYMMDD) - 預設為今日", today_str)

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
                    st.error("查無數據，請確認該標的近期是否有交易，或代碼是否正確。")
            else:
                st.error("找不到該股票，請確認名稱是否正確。")

# --- 標籤頁二：板塊爆量掃描 ---
with tab2:
    st.markdown("### 🔍 產業板塊掃描器")
    
    INDUSTRY_STOCKS = get_industry_mapping()
    
    if not INDUSTRY_STOCKS:
        st.warning("目前無法從 API 獲取產業分類，請稍後再試。")
    else:
        selected_industry = st.selectbox("請選擇要掃描的資金板塊：", list(INDUSTRY_STOCKS.keys()))
        
        current_sector_map = INDUSTRY_STOCKS[selected_industry]
        watch_list = list(current_sector_map.keys()) 
        stock_count = len(watch_list)
        st.caption(f"該板塊目前共收錄 {stock_count} 檔標的")
        
        if st.button(f"🚀 開始掃描【{selected_industry}】", use_container_width=True):
            with st.spinner('掃描運算中 (自動過濾上市與上櫃資料)...'):
                
                # 建立雙市場代碼清單，進行批次大網撈魚
                tickers_tw = [f"{code}.TW" for code in watch_list]
                tickers_two = [f"{code}.TWO" for code in watch_list]
                all_tickers = tickers_tw + tickers_two 
                
                try:
                    data = yf.download(all_tickers, period="1mo", group_by='ticker', progress=False)
                    
                    results = []
                    for code in watch_list:
                        ticker_tw = f"{code}.TW"
                        ticker_two = f"{code}.TWO"
                        df = None
                        
                        # 動態判斷 API 抓到了上市還是上櫃的資料
                        if isinstance(data.columns, pd.MultiIndex):
                            available_tickers = data.columns.get_level_values(0).unique()
                            if ticker_tw in available_tickers:
                                df = data[ticker_tw].copy()
                            elif ticker_two in available_tickers:
                                df = data[ticker_two].copy()
                        else:
                            df = data.copy() 

                        if df is None or df.empty: 
                            continue 
                            
                        df = df.dropna()
                        if len(df) < 20: continue 

                        # 策略運算取值
                        latest_close = float(df['Close'].iloc[-1])
                        lowest_20d = float(df['Low'].rolling(window=20).min().iloc[-1])
                        latest_vol = float(df['Volume'].iloc[-1])
                        avg_vol_5d = float(df['Volume'].iloc[-6:-1].mean())

                        # 核心選股邏輯：底部 & 爆量
                        is_low_price = latest_close <= (lowest_20d * 1.05)
                        is_high_vol = latest_vol > (avg_vol_5d * 2) if avg_vol_5d > 0 else False

                        if is_low_price and is_high_vol:
                            results.append({
                                "股票代碼": code,
                                "股票名稱": current_sector_map[code],
                                "最新收盤價": round(latest_close, 2),
                                "20日最低價": round(lowest_20d, 2),
                                "今日成交量(股)": f"{int(latest_vol):,}",
                                "突破爆量倍數": f"{round(latest_vol / avg_vol_5d, 1)} 倍"
                            })

                    if results:
                        st.success(f"🎯 發現 {len(results)} 檔符合『底部出量』型態標的：")
                        final_df = pd.DataFrame(results)
                        final_df.index = range(1, len(final_df) + 1) # 序號從 1 開始
                        st.dataframe(final_df, use_container_width=True)
                    else:
                        st.info(f"平靜無波。目前【{selected_industry}】內無底部爆量訊號。")

                except Exception as e:
                    st.error(f"掃描引擎發生異常: {e}")