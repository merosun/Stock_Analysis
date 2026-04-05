import requests
import pandas as pd
import time

def get_stock_code(stock_input):
    """
    量化系統的自動導航：從證交所調閱最新名冊，輸入名稱自動轉代碼
    """
    # 如果輸入本身已經是數字代碼，直接放行
    if stock_input.isdigit():
        return stock_input
        
    print(f"正在從證交所調閱最新名冊，為您鎖定「{stock_input}」的標的代碼...")
    
    # 證交所 OpenAPI：取得今日所有上市股票的代碼與名稱對照表
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        stock_list = response.json()
        
        # 遍歷名冊，精準比對名稱 (使用 strip 去除可能的空白)
        for stock in stock_list:
            if stock.get('Name', '').strip() == stock_input.strip():
                code = stock.get('Code', '')
                print(f"🎯 鎖定標的：{stock_input} (代碼: {code})")
                return code
                
        print(f"⚠️ 在上市名冊中找不到名為「{stock_input}」的標的。")
        print("💡 提示：目前本系統鎖定「上市」股票，若為「上櫃」股票需另接櫃買中心API。")
        return None

    except Exception as e:
        print(f"連線證交所名冊時發生錯誤: {e}")
        return None

def fetch_twse_data(stock_no, year_month):
    """
    從台灣證券交易所抓取指定月份的股票日成交資訊
    """
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={year_month}&stockNo={stock_no}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['stat'] == 'OK':
            df = pd.DataFrame(data['data'], columns=data['fields'])
            return df
        else:
            print(f"無法獲取資料，狀態回應：{data.get('stat')}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"網路連線發生錯誤: {e}")
        return None

if __name__ == "__main__":
    print("========================================")
    print("📈 股神量化終端機啟動：尋找市場獲利契機")
    print("========================================")
    
    # 利用 input() 讓你可以靈活手動輸入標的與時間
    user_input = input("請輸入你想狙擊的股票名稱 (例如: 和桐, 台積電) 或 代碼: ")
    target_date = input("請輸入查詢年月 (格式 YYYYMMDD，例如 20260401): ")
    
    # 1. 啟動名稱轉換代碼機制
    target_stock_code = get_stock_code(user_input)
    
    if target_stock_code:
        print(f"\n開始調閱 {user_input} 於 {target_date} 的歷史籌碼與價量數據...")
        
        # 2. 遵守交易紀律：設定延遲，保護我們的 IP 不被交易所封鎖
        time.sleep(2) 
        
        # 3. 抓取核心數據
        stock_df = fetch_twse_data(target_stock_code, target_date)

        if stock_df is not None:
            print(f"\n✅ 成功截獲 {user_input} ({target_stock_code}) 的核心數據！前五筆資料如下：")
            print(stock_df.head())
            
            # 將資料匯出成 CSV 檔案，這將是我們後續挖掘買賣點的基石
            # file_name = f"{target_stock_code}_{target_date}.csv"
            # stock_df.to_csv(file_name, index=False, encoding='utf-8-sig')
            # print(f"\n📊 數據已儲存為 {file_name}")