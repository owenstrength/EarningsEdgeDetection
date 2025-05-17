import pandas as pd
import yfinance as yf
import numpy as np

# === Load your CSV ===
csv_path = "cli_scanner/data_exploration/trades_win_loss.csv"
df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()
df['res'] = df['res'].str.strip()
# === Separate groups ===
winners = df[df['res'] == 'Win']['Ticker'].tolist()
losers = df[df['res'] == 'Loss']['Ticker'].tolist()
ties = df[df['res'] == 'Tie']['Ticker'].tolist()

def get_ticker_features(ticker):
    print(f"Processing {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        market_cap = info.get("marketCap")
        float_shares = info.get("floatShares")
        sector = info.get("sector", "N/A")

        # Sometimes yfinance returns an empty info dict
        if not info or (market_cap is None and float_shares is None and sector == "N/A"):
            print(f"  ✗ No data found for {ticker}")
            return None

        return {
            "Ticker": ticker,
            "MarketCap_B": round(market_cap / 1e9, 2) if market_cap else None,
            "Float_M": round(float_shares / 1e6, 2) if float_shares else None,
            "Float/MarketCap": round(float_shares / market_cap, 4) if market_cap and float_shares else None,
            "Sector": sector
        }

    except Exception as e:
        print(f"  ✗ Error processing {ticker}: {e}")
        return None

def analyze_group(ticker_list, label):
    print(f"\n--- Analyzing {label} ---")
    features = []
    for ticker in ticker_list:
        data = get_ticker_features(ticker)
        if data:
            features.append(data)
    print(f"{label}: {len(features)} tickers succeeded out of {len(ticker_list)}")
    return pd.DataFrame(features)

df_winners = analyze_group(winners, "Winners")
df_losers = analyze_group(losers, "Losers")
df_ties = analyze_group(ties, "Ties")

def summarize(df_group, name):
    print(f"\n=== {name} Summary ===")
    print(df_group.describe(include='all'))
    print("\nSector counts:")
    print(df_group['Sector'].value_counts())

summarize(df_winners, "Winners")
filtered_winners = df_winners[(df_winners['Float/MarketCap'] > 0.04)]
print("Filtered out in Winners:", filtered_winners)
print(filtered_winners)

summarize(df_losers, "Losers")
filtered_losers = df_losers[(df_losers['Float/MarketCap'] > 0.04)]
print("Filtered out in Losers:", filtered_losers)
print(filtered_losers)

summarize(df_ties, "Ties")
filtered_ties = df_ties[(df_ties['Float/MarketCap'] > 0.04)]
print("Filtered out in Ties:", filtered_ties)
print(filtered_ties)