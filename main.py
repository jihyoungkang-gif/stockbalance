"""Analyze volatility and suggest KRW allocation for the watchlist."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from analysis.allocation import allocate_capital
from analysis.data import asset_labels, build_return_panel
from analysis.volatility import correlation_matrix, summarize_risk

load_dotenv(Path(__file__).resolve().parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _format_krw(value: float) -> str:
    return f"{value:,.0f}원"


def main() -> None:
    lookback = int(os.getenv("LOOKBACK_DAYS", "252"))
    total_krw = float(os.getenv("PORTFOLIO_AMOUNT_KRW", "100000000"))
    labels = asset_labels()

    print("=" * 60)
    print("StockInsight - 변동성 기반 배분 분석")
    print("=" * 60)
    print(f"분석 기간: 최근 {lookback} 영업일")
    print(f"투자 가정 금액: {_format_krw(total_krw)}")
    print()

    returns = build_return_panel(lookback_days=lookback)
    if returns.empty:
        print("수익률 데이터를 만들 수 없습니다. API 키와 네트워크를 확인하세요.")
        return

    valid = returns.dropna(axis=1, how="any")
    dropped = [col for col in returns.columns if col not in valid.columns]
    if dropped:
        print(f"공통 기간 데이터 부족으로 제외된 종목: {', '.join(dropped)}")
        print()

    if valid.empty:
        print("공통 거래일 기준으로 분석 가능한 종목이 없습니다.")
        return

    risk = summarize_risk(valid)
    print("[ 연율화 변동성 ]")
    for ticker, row in risk.iterrows():
        name = labels.get(ticker, ticker)
        print(f"  {name} ({ticker}): {row['annual_volatility'] * 100:.1f}%")
    print()

    corr = correlation_matrix(valid)
    print("[ 상관계수 (요약) ]")
    print(corr.round(2).to_string())
    print()

    allocation = allocate_capital(valid, total_krw, labels=labels)
    print("[ 역변동성 가중 배분 ]")
    print("(변동성이 큰 종목일수록 비중을 낮추는 단순 모델입니다. 투자 권유가 아닙니다.)")
    print()
    for _, row in allocation.iterrows():
        print(
            f"  {row['name']} ({row['ticker']}): "
            f"{row['weight_pct']:.1f}% / "
            f"{_format_krw(row['amount_krw'])} "
            f"({row['amount_manwon']:,.0f}만원)"
        )

    print()
    print(f"합계: {_format_krw(allocation['amount_krw'].sum())}")


if __name__ == "__main__":
    main()
