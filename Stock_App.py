import streamlit as st
import requests
import pandas as pd
import time
import plotly.graph_objects as go

def get_stock_code(stock_input):
    if stock_input.isdigit(): return stock_input
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        response = requests.get(url, timeout=10)
        for stock in response.json():
            if stock.get('Name', '').strip() == stock_input.strip():
                return stock.get('Code', '')
    except: pass
    return None

def fetch_twse_data(stock_no, year_month):
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={year_month}&stockNo={stock_no}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('stat') == 'OK':
            return pd.DataFrame(data['data'], columns=data['fields'])
    except: pass
    return None

def process_and_analyze(df):
    cols_to_clean = ['開盤價', '最高價', '最低價', '收盤價']
    for col in cols_to_clean:
        df[col] = df[col].str.replace(',', '').astype(float)
    
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

col1, col2 = st.columns(2)
with col1:
    user_input = st.text_input("輸入股票名稱或代碼", "台積電")
with col2:
    target_date = st.text_input("輸入查詢年月 (YYYYMMDD)", "20260401")

if st.button("執行智能分析"):
    with st.spinner('正在截獲數據並進行運算...'):
        stock_code = get_stock_code(user_input)
        if stock_code:
            time.sleep(1) 
            raw_df = fetch_twse_data(stock_code, target_date)
            
            if raw_df is not None:
                analyzed_df = process_and_analyze(raw_df.copy())
                
                # --- 【新增】渲染評語與報告 ---
                report_md, alert_color = generate_trend_report(analyzed_df)
                if alert_color == "success": st.success(report_md)
                elif alert_color == "error": st.error(report_md)
                elif alert_color == "warning": st.warning(report_md)
                else: st.info(report_md)
                # -----------------------------

                chart = plot_candlestick(analyzed_df, user_input)
                st.plotly_chart(chart, use_container_width=True)
                
                analyzed_df = analyzed_df.sort_values(by='日期', ascending=False)
                st.dataframe(analyzed_df, use_container_width=True) 
            else:
                st.error("查無數據，請確認日期格式或該月是否已開盤。")
        else:
            st.error("在上市名單中找不到該股票，請確認名稱是否正確。")