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

@st.cache_data(ttl=86400)
def get_industry_mapping():
    """從 FinMind 獲取台股全市場清單，並建立索引以供快速查詢"""
    url = "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
    industry_dict = {}
    lookup_table = {} 
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get('status') == 200:
            for stock in data.get('data', []):
                category = stock.get('industry_category', '*未分類')
                code = stock.get('stock_id', '')
                name = stock.get('stock_name', '')
                market_type = stock.get('type', 'twse')
                
                if len(code) == 4 and code.isdigit():
                    if category not in industry_dict:
                        industry_dict[category] = {}
                    industry_dict[category][code] = name
                    
                    lookup_table[code] = {
                        "name": name,
                        "category": category,
                        "type": "上市" if market_type == "twse" else "上櫃"
                    }
    except Exception as e:
        st.error(f"獲取產業清單失敗: {e}")
        
    sorted_industry = {k: v for k, v in sorted(industry_dict.items()) if v}
    return sorted_industry, lookup_table

def get_stock_code(stock_input):
    if stock_input.isdigit(): return stock_input
    _, lookup = get_industry_mapping()
    for code, info in lookup.items():
        if info['name'].strip() == stock_input.strip():
            return code
    return None

def fetch_twse_data(stock_no, target_date=None):
    ticker = f"{stock_no}.TW"
    try:
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty:
            ticker = f"{stock_no}.TWO"
            df = yf.download(ticker, period="3mo", progress=False)
            if df.empty: return None
                
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.rename(columns={
            'Date': '日期', 'Open': '開盤價', 'High': '最高價', 
            'Low': '最低價', 'Close': '收盤價', 'Volume': '成交股數'
        })
        df['日期'] = df['日期'].dt.strftime('%Y%m%d')
        return df[['日期', '開盤價', '最高價', '最低價', '收盤價', '成交股數']]
    except:
        return None

def get_stock_fundamentals(stock_code, lookup_table):
    """
    優先從 FinMind 緩存讀取產業，再嘗試從 Yahoo 爬取業務描述。
    保障網頁在 yfinance 阻擋時依然能顯示基本架構。
    """
    base_info = lookup_table.get(stock_code, {"category": "未知", "type": "未知"})
    
    result = {
        "industry": base_info['category'],
        "market": base_info['type'],
        "business": "無法從 Yahoo Finance 取得詳細簡介（可能受限於 IP 封鎖或個股資料未登錄）。"
    }

    try:
        suffix = ".TW" if base_info['type'] == "上市" else ".TWO"
        ticker = yf.Ticker(f"{stock_code}{suffix}")
        info = ticker.info
        
        if info and 'longBusinessSummary' in info:
            result["business"] = info.get("longBusinessSummary")
    except:
        pass 
        
    return result

# ==========================================
# 策略運算與分析模組
# ==========================================

def process_and_analyze(df):
    cols = ['開盤價', '最高價', '最低價', '收盤價', '成交股數']
    df[cols] = df[cols].astype(float)
    df['MA5'] = df['收盤價'].rolling(window=5).mean()
    df['MA10'] = df['收盤價'].rolling(window=10).mean()
    df['Vol_MA5'] = df['成交股數'].rolling(window=5).mean()
    return df

def generate_trend_report(df):
    df_sorted = df.sort_values(by='日期', ascending=True).dropna(subset=['MA10', 'Vol_MA5'])
    if len(df_sorted) < 2: return "⚠️ 資料天數不足，無法產生具參考價值的評語。", "warning"

    latest = df_sorted.iloc[-1]
    prev = df_sorted.iloc[-2]
    close, ma5, ma10 = latest['收盤價'], latest['MA5'], latest['MA10']
    vol_latest, vol_ma5 = latest['成交股數'] / 1000, latest['Vol_MA5'] / 1000

    if vol_ma5 < 500:
        vol_status, vol_advice, color_v = "⚠️ 流動性低迷", "流動性不足，避開殭屍股。", "warning"
    elif vol_latest > (vol_ma5 * 2) and vol_ma5 > 0:
        vol_status, vol_advice, color_v = "🔥 異常爆量表態", "主力換手或資金進駐，量能充沛。", "success"
    else:
        vol_status, vol_advice, color_v = "🌊 量能健康穩定", "流動性穩定，適合依技術面操作。", "info"

    if prev_ma5 <= prev_ma10 and ma5 > ma10:
        trend, price_advice, color_p = "🌟 黃金交叉成型", "波段起漲強烈買點，觀察量能。", "success"
    elif prev_ma5 >= prev_ma10 and ma5 < ma10:
        trend, price_advice, color_p = "⚠️ 死亡交叉成型", "趨勢轉弱，建議嚴格執行停損。", "error"
    elif close > ma5 and ma5 > ma10:
        trend, price_advice, color_p = "📈 多頭排列強勢", "穩居均線之上，持股續抱。", "info"
    elif close < ma5 and ma5 < ma10:
        trend, price_advice, color_p = "📉 空頭排列弱勢", "均線沉重反壓，觀望為上策。", "warning"
    else:
        trend, price_advice, color_p = "⚖️ 區間震盪盤整", "多空方向未明，等待表態。", "info"

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
    return report, color_p

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

# ==========================================
# Web UI 介面設計
# ==========================================
st.set_page_config(layout="wide", page_title="量化交易終端機")
st.title("📈 量化交易終端機 - 專業操盤版")

tab1, tab2 = st.tabs(["📊 單檔智能分析", "🚀 板塊爆量掃描"])

INDUSTRY_STOCKS, LOOKUP_TABLE = get_industry_mapping()

# --- 標籤頁一：單檔智能分析 ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        user_input = st.text_input("輸入股票名稱或代碼", "台積電")
    with col2:
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
                    
                    # 基本面資訊面板
                    fund_info = get_stock_fundamentals(stock_code, LOOKUP_TABLE)
                    with st.expander(f"📖 【{user_input}】公司基本面資訊", expanded=True):
                        st.markdown(f"**🏢 產業結構：** {fund_info['industry']} ({fund_info['market']})")
                        st.markdown(f"**📝 業務簡介：**\n> {fund_info['business']}")

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
                    st.error("查無技術面數據，請確認該標的近期是否有交易。")
            else:
                st.error("找不到該股票，請確認名稱是否正確。")

# --- 標籤頁二：板塊爆量掃描 ---
with tab2:
    st.markdown("### 🔍 產業板塊掃描器")
    
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

                        latest_close = float(df['Close'].iloc[-1])
                        lowest_20d = float(df['Low'].rolling(window=20).min().iloc[-1])
                        latest_vol = float(df['Volume'].iloc[-1])
                        avg_vol_5d = float(df['Volume'].iloc[-6:-1].mean())

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
                        final_df.index = range(1, len(final_df) + 1) 
                        st.dataframe(final_df, use_container_width=True)
                    else:
                        st.info(f"平靜無波。目前【{selected_industry}】內無底部爆量訊號。")

                except Exception as e:
                    st.error(f"掃描引擎發生異常: {e}")