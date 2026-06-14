"""StockInsight web dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from analysis.allocation import allocate_capital
from analysis.annual_returns import compute_annual_returns, compute_cumulative_growth
from analysis.data import asset_labels, build_price_panel, build_price_panel_since, build_return_panel
from analysis.volatility import correlation_matrix, summarize_risk

START_YEAR = int(os.getenv("ANNUAL_START_YEAR", "2002"))

load_dotenv(Path(__file__).resolve().parent / ".env")

st.set_page_config(
    page_title="StockInsight",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False, ttl=3600)
def load_market_data(lookback_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = build_price_panel(lookback_days=lookback_days)
    returns = prices.pct_change().dropna(how="all")
    return prices, returns


@st.cache_data(show_spinner="2002년 이후 시세를 불러오는 중... (최초 1회는 1~2분)", ttl=86400)
def load_annual_data(start_year: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices = build_price_panel_since(start_year=start_year)
    annual = compute_annual_returns(prices, start_year=start_year)
    cumulative = compute_cumulative_growth(prices, start_year=start_year)
    return prices, annual, cumulative


def _label_columns(frame: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    renamed = frame.copy()
    renamed.columns = [f"{labels.get(col, col)} ({col})" for col in renamed.columns]
    return renamed


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:+.1f}%"


def main() -> None:
    labels = asset_labels()
    default_amount = int(float(os.getenv("PORTFOLIO_AMOUNT_KRW", "100000000")))
    default_lookback = int(os.getenv("LOOKBACK_DAYS", "252"))

    st.title("StockInsight")
    st.caption("국내·해외 메모리/스토리지 종목 변동성 분석 및 1억 원 배분 시뮬레이션")

    with st.sidebar:
        st.header("설정")
        total_krw = st.number_input(
            "투자 가정 금액 (원)",
            min_value=1_000_000,
            max_value=1_000_000_000,
            value=default_amount,
            step=1_000_000,
            format="%d",
        )
        lookback = st.slider("분석 기간 (영업일)", min_value=60, max_value=504, value=default_lookback)
        refresh = st.button("데이터 새로고침", type="primary", use_container_width=True)
        st.caption(f"연도별 수익률: {START_YEAR}년~현재 (원화 환산)")
        st.divider()
        st.markdown("**데이터 소스**")
        st.markdown("- 국내: 공공데이터포털")
        st.markdown("- 해외(USD): yfinance")
        st.markdown("- 일본(JPY): yfinance · 285A.T 키옥시아")
        st.info("투자 권유가 아닌 참고용 분석입니다.")

    if refresh:
        load_market_data.clear()
        load_annual_data.clear()

    with st.spinner("시세·환율 데이터를 불러오는 중..."):
        prices, returns = load_market_data(lookback)

    if prices.empty or returns.empty:
        st.error("데이터를 불러오지 못했습니다. `.env` API 키와 네트워크를 확인하세요.")
        return

    valid = returns.dropna(axis=1, how="any")
    dropped = [col for col in returns.columns if col not in valid.columns]
    if dropped:
        st.warning(f"공통 기간 데이터 부족으로 제외된 종목: {', '.join(dropped)}")

    if valid.empty:
        st.error("공통 거래일 기준으로 분석 가능한 종목이 없습니다.")
        return

    risk = summarize_risk(valid)
    corr = correlation_matrix(valid)
    allocation = allocate_capital(valid, float(total_krw), labels=labels)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("분석 종목 수", f"{len(valid.columns)}개")
    col2.metric("공통 거래일", f"{len(valid)}일")
    col3.metric("평균 연율화 변동성", f"{risk['annual_volatility'].mean() * 100:.1f}%")
    col4.metric("투자 가정 금액", f"{total_krw:,.0f}원")

    tab_alloc, tab_risk, tab_corr, tab_price, tab_annual = st.tabs(
        ["배분 결과", "변동성", "상관관계", "가격 추이", "연도별 수익률"]
    )

    with tab_alloc:
        left, right = st.columns([1.1, 1])

        pie = px.pie(
            allocation,
            names="name",
            values="amount_krw",
            hole=0.45,
            title="역변동성 가중 배분",
        )
        pie.update_traces(textposition="inside", textinfo="percent+label")
        pie.update_layout(margin=dict(t=40, b=20, l=20, r=20), height=420)
        left.plotly_chart(pie, use_container_width=True)

        display_alloc = allocation.copy()
        display_alloc["weight_pct"] = display_alloc["weight_pct"].map(lambda x: f"{x:.1f}%")
        display_alloc["amount_krw"] = display_alloc["amount_krw"].map(lambda x: f"{x:,.0f}원")
        display_alloc["amount_manwon"] = display_alloc["amount_manwon"].map(lambda x: f"{x:,.0f}만원")
        display_alloc = display_alloc.rename(
            columns={
                "name": "종목",
                "ticker": "티커",
                "weight_pct": "비중",
                "amount_krw": "금액",
                "amount_manwon": "만원",
            }
        )
        right.subheader("배분표")
        right.dataframe(display_alloc, hide_index=True, use_container_width=True)
        right.caption("변동성이 큰 종목일수록 비중을 낮춥니다.")

    with tab_risk:
        risk_display = risk.copy()
        risk_display.index = [f"{labels.get(t, t)} ({t})" for t in risk_display.index]
        risk_display["annual_volatility_pct"] = risk_display["annual_volatility"] * 100

        bar = px.bar(
            risk_display.reset_index(names="asset"),
            x="annual_volatility_pct",
            y="asset",
            orientation="h",
            labels={"annual_volatility_pct": "연율화 변동성 (%)", "asset": "종목"},
            title="종목별 연율화 변동성",
        )
        bar.update_layout(height=360, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(bar, use_container_width=True)

        table = risk_display[["annual_volatility", "daily_volatility", "avg_daily_return", "observations"]].copy()
        table["annual_volatility"] = (table["annual_volatility"] * 100).map(lambda x: f"{x:.2f}%")
        table["daily_volatility"] = (table["daily_volatility"] * 100).map(lambda x: f"{x:.3f}%")
        table["avg_daily_return"] = (table["avg_daily_return"] * 100).map(lambda x: f"{x:.3f}%")
        table = table.rename(
            columns={
                "annual_volatility": "연율화 변동성",
                "daily_volatility": "일간 변동성",
                "avg_daily_return": "평균 일간 수익률",
                "observations": "표본 수",
            }
        )
        st.dataframe(table, use_container_width=True)

    with tab_corr:
        corr_labeled = _label_columns(corr, labels)
        heatmap = px.imshow(
            corr_labeled,
            text_auto=".2f",
            aspect="auto",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="종목 간 상관계수",
        )
        heatmap.update_layout(height=520, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(heatmap, use_container_width=True)

    with tab_price:
        st.subheader("원화 기준 정규화 가격 (시작일 = 100)")
        normalized = prices[valid.columns].div(prices[valid.columns].iloc[0]).mul(100)
        normalized_labeled = _label_columns(normalized, labels)

        line = go.Figure()
        for column in normalized_labeled.columns:
            line.add_trace(
                go.Scatter(
                    x=normalized_labeled.index,
                    y=normalized_labeled[column],
                    mode="lines",
                    name=column,
                )
            )
        line.update_layout(
            height=460,
            xaxis_title="날짜",
            yaxis_title="지수 (100 = 시작일)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=20, b=20, l=20, r=20),
        )
        st.plotly_chart(line, use_container_width=True)

    with tab_annual:
        annual_prices, annual_returns, cumulative = load_annual_data(START_YEAR)

        if annual_returns.empty:
            st.error(f"{START_YEAR}년 이후 연도별 수익률 데이터를 만들 수 없습니다.")
        else:
            current_year = int(annual_returns.index.max())
            st.subheader(f"연도별 수익률 ({START_YEAR}년 ~ {current_year}년)")
            st.caption(
                "전년 말 종가 대비 해당 연도 말(또는 최신 거래일) 수익률 · "
                "해외 종목은 원화 환산 · 올해는 진행 중(YTD) 기준"
            )

            avg_row = annual_returns.mean(axis=1, skipna=True)
            stock_count = len(annual_returns.columns)
            best_year = avg_row.idxmax()
            worst_year = avg_row.idxmin()
            m1, m2, m3 = st.columns(3)
            m1.metric("분석 연도 수", f"{len(annual_returns)}년")
            m2.metric(f"{stock_count}종목 평균 최고 연도", f"{best_year}년", f"{avg_row[best_year]:+.1f}%")
            m3.metric(f"{stock_count}종목 평균 최저 연도", f"{worst_year}년", f"{avg_row[worst_year]:+.1f}%")

            annual_labeled = _label_columns(annual_returns, labels)
            heatmap = px.imshow(
                annual_labeled.T,
                text_auto=".1f",
                aspect="auto",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                labels={"x": "연도", "y": "종목", "color": "수익률 (%)"},
                title="연도별 수익률 히트맵 (%)",
            )
            heatmap.update_layout(height=360, margin=dict(t=40, b=20, l=20, r=20))
            st.plotly_chart(heatmap, use_container_width=True)

            chart_col, table_col = st.columns([1.2, 1])
            melted = annual_returns.reset_index().melt(id_vars="year", var_name="ticker", value_name="return_pct")
            melted["name"] = melted["ticker"].map(lambda t: labels.get(t, t))
            bar = px.bar(
                melted.dropna(subset=["return_pct"]),
                x="year",
                y="return_pct",
                color="name",
                barmode="group",
                labels={"year": "연도", "return_pct": "수익률 (%)", "name": "종목"},
                title="연도별 수익률 비교",
            )
            bar.update_layout(height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1))
            chart_col.plotly_chart(bar, use_container_width=True)

            display = annual_labeled.copy()
            for col in display.columns:
                display[col] = display[col].map(_format_pct)
            display.index = [
                f"{int(year)}년{' (YTD)' if int(year) == current_year else ''}"
                for year in display.index
            ]
            display.index.name = "연도"
            table_col.subheader("연도별 수익률 표")
            table_col.dataframe(display, use_container_width=True)

            if not cumulative.empty:
                st.subheader("누적 성장 지수 (기준 = 100)")
                cumulative_labeled = _label_columns(cumulative, labels)
                cum_line = go.Figure()
                for column in cumulative_labeled.columns:
                    cum_line.add_trace(
                        go.Scatter(
                            x=cumulative_labeled.index,
                            y=cumulative_labeled[column],
                            mode="lines+markers",
                            name=column,
                        )
                    )
                cum_line.update_layout(
                    height=420,
                    xaxis_title="연도",
                    yaxis_title="지수",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(t=20, b=20, l=20, r=20),
                )
                st.plotly_chart(cum_line, use_container_width=True)

            with st.expander("데이터 상세"):
                st.write(f"일별 시세 구간: {annual_prices.index.min().date()} ~ {annual_prices.index.max().date()}")
                st.dataframe(annual_returns.map(_format_pct), use_container_width=True)


if __name__ == "__main__":
    main()
