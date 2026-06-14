"""Quick check: yfinance can fetch MU, WDC, STX."""

from collectors.us_stocks import fetch_us_latest, get_us_tickers


def main() -> None:
    tickers = get_us_tickers()
    print(f"Tickers: {', '.join(tickers)}")

    latest = fetch_us_latest()
    if latest.empty:
        print("No data returned. Check network or ticker symbols.")
        return

    for _, row in latest.iterrows():
        date = row["date"].strftime("%Y-%m-%d")
        print(f"{row['ticker']:>4}  {date}  close={row['Close']:.2f}  volume={int(row['Volume']):,}")


if __name__ == "__main__":
    main()
