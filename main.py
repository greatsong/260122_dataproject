# main.py
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import yfinance as yf
from pandas_datareader import data as pdr

st.set_page_config(page_title="Global Top10 Movers", layout="wide")

DEFAULT_TOP10 = {
    "NVDA": "NVIDIA",
    "AAPL": "Apple",
    "GOOG": "Alphabet (GOOG)",
    "MSFT": "Microsoft",
    "AMZN": "Amazon",
    "TSM": "TSMC (ADR)",
    "META": "Meta Platforms",
    "AVGO": "Broadcom",
    "TSLA": "Tesla",
    "BRK-B": "Berkshire Hathaway (B)",
}

# --- Yahoo 차단 완화용 Session(User-Agent) ---
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )
    return s


def quick_yahoo_healthcheck(session: requests.Session) -> tuple[bool, str]:
    """
    Yahoo 엔드포인트가 최소한 응답은 하는지 빠르게 체크.
    (권한/차단이면 401/403/429가 뜨는 경우가 많음)
    """
    url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL"
    try:
        r = session.get(url, timeout=8)
        return (200 <= r.status_code < 300), f"Yahoo healthcheck status={r.status_code}"
    except Exception as e:
        return False, f"Yahoo healthcheck error: {type(e).__name__}: {e}"


@st.cache_data(show_spinner=False, ttl=60 * 60)
def fetch_prices_yfinance(tickers: list[str], lookback_calendar_days: int) -> tuple[pd.DataFrame, str | None]:
    """
    yfinance로 멀티티커 배치 다운로드.
    return: (long_df, err)
    """
    if not tickers:
        return pd.DataFrame(), "No tickers."

    end = datetime.utcnow().date() + timedelta(days=1)
    start = end - timedelta(days=lookback_calendar_days)
    session = make_session()

    # (선택) healthcheck
    ok, msg = quick_yahoo_healthcheck(session)

    last_err = None
    for attempt in range(1, 4):
        try:
            raw = yf.download(
                tickers=tickers,
                start=start.isoformat(),
                end=end.isoformat(),
                group_by="column",
                progress=False,
                threads=True,
                auto_adjust=False,
                session=session,
            )
            if raw is None or raw.empty:
                last_err = f"yfinance returned empty dataframe. ({msg})"
                time.sleep(0.9 * attempt)
                continue

            raw = raw.reset_index()

            # 멀티티커 -> long 변환
            if isinstance(raw.columns, pd.MultiIndex):
                date_col = raw.columns[0]
                fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
                long_rows = []

                for t in tickers:
                    has_any = any(((f, t) in raw.columns) for f in fields)
                    if not has_any:
                        continue

                    tmp = pd.DataFrame({"Date": raw[date_col]})
                    for f in fields:
                        tmp[f] = raw[(f, t)] if (f, t) in raw.columns else pd.NA
                    tmp["Ticker"] = t
                    long_rows.append(tmp)

                out = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()
            else:
                # 단일 티커
                out = raw.copy()
                out["Ticker"] = tickers[0]
                if "Date" not in out.columns and "index" in out.columns:
                    out.rename(columns={"index": "Date"}, inplace=True)

            out = out.dropna(subset=["Close"])
            out["Date"] = pd.to_datetime(out["Date"])
            out = out.sort_values(["Ticker", "Date"])
            return out, None

        except Exception as e:
            last_err = f"{type(e).__name__}: {e} ({msg})"
            time.sleep(0.9 * attempt)

    return pd.DataFrame(), last_err


@st.cache_data(show_spinner=False, ttl=60 * 60)
def fetch_prices_stooq_fallback(tickers: list[str], lookback_calendar_days: int) -> tuple[pd.DataFrame, str | None]:
    """
    yfinance가 막힐 때 Stooq로 대체 수집.
    Stooq는 보통 US 종목을 'AAPL.US' 형태로 받음.
    """
    if not tickers:
        return pd.DataFrame(), "No tickers."

    end = datetime.utcnow().date() + timedelta(days=1)
    start = end - timedelta(days=lookback_calendar_days)

    rows = []
    errs = []

    for t in tickers:
        # BRK-B 등 특수표기 보정: Stooq는 '-' 대신 '.' 또는 다른 표기를 쓰는 경우가 있어 예외처리
        # 가장 많이 통하는 기본: 미국주식은 {TICKER}.US
        stooq_symbol = f"{t.replace('-', '.').upper()}.US"
        try:
            df = pdr.DataReader(stooq_symbol, "stooq", start, end)
            if df is None or df.empty:
                errs.append(f"{t}: stooq empty ({stooq_symbol})")
                continue

            df = df.reset_index().rename(columns={"Date": "Date"})
            # stooq는 컬럼명이 대문자(Open/High/Low/Close/Volume)
            rename_map = {"Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"}
            df = df.rename(columns=rename_map)

            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date")

            df["Adj Close"] = pd.NA
            df["Ticker"] = t
            df = df[["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "Ticker"]]
            rows.append(df)
        except Exception as e:
            errs.append(f"{t}: {type(e).__name__}: {e} ({stooq_symbol})")

    if not rows:
        return pd.DataFrame(), " / ".join(errs) if errs else "stooq failed."

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["Close"]).sort_values(["Ticker", "Date"])
    err = " / ".join(errs) if errs else None
    return out, err


def compute_move(prices: pd.DataFrame, ticker: str, n_trading_days: int) -> dict:
    df = prices[prices["Ticker"] == ticker].sort_values("Date")
    if df.empty:
        return {"start_close": None, "last_close": None, "chg": None, "pct": None, "used_days": 0, "points": 0}

    close = df["Close"].dropna()
    if close.shape[0] < 2:
        last = float(close.iloc[-1]) if close.shape[0] else None
        return {"start_close": None, "last_close": last, "chg": None, "pct": None, "used_days": int(close.shape[0]), "points": int(df.shape[0])}

    idx_start = max(0, close.shape[0] - 1 - n_trading_days)
    start_close = float(close.iloc[idx_start])
    last_close = float(close.iloc[-1])
    chg = last_close - start_close
    pct = (chg / start_close) * 100 if start_close != 0 else None
    used_days = (close.shape[0] - 1) - idx_start

    return {
        "start_close": start_close,
        "last_close": last_close,
        "chg": chg,
        "pct": pct,
        "used_days": used_days,
        "points": int(df.shape[0]),
    }


st.title("🌍 글로벌 Top10: 최근 N일 변동 Top/Bottom (yfinance + Plotly)")
st.caption("yfinance가 빈 데이터로 떨어지면 자동으로 Stooq로 fallback합니다.")

with st.sidebar:
    st.header("설정")
    n_days = st.slider("최근 N일(거래일 기준에 가깝게)", 1, 120, 20, 1)
    metric = st.radio("정렬 기준", ["등락률(%)", "등락액(가격)"], horizontal=True)

    lookback_calendar = int(max(60, n_days * 3))

    st.divider()
    tickers_text = st.text_area("티커(쉼표 구분)", value=",".join(DEFAULT_TOP10.keys()), height=80)
    tickers = [t.strip().upper() for t in tickers_text.split(",") if t.strip()]
    top_k = st.slider("Top/Bottom 개수", 3, 10, 5, 1)

    st.divider()
    chart_mode = st.selectbox("차트", ["개별 종목 라인", "등락률 막대", "등락액 막대"])

run = st.button("🚀 분석 실행", type="primary")

if not run:
    st.info("왼쪽 설정 후 **‘🚀 분석 실행’** 버튼을 눌러 주세요.")
    st.stop()

# --- 1) yfinance 시도 ---
with st.spinner("1) yfinance로 데이터 불러오는 중..."):
    prices, err = fetch_prices_yfinance(tickers, lookback_calendar)

source_used = "yfinance"

# --- 2) 실패하면 Stooq fallback ---
if prices.empty:
    st.warning("yfinance가 빈 데이터를 반환했어요. (Yahoo 차단/429 가능) → Stooq로 대체 수집합니다.")
    with st.spinner("2) Stooq로 대체 수집 중..."):
        prices, err2 = fetch_prices_stooq_fallback(tickers, lookback_calendar)
    source_used = "stooq-fallback"
    if err:
        st.code(f"yfinance debug: {err}")
    if err2:
        st.code(f"stooq note: {err2}")

if prices.empty:
    st.error("yfinance도 실패했고, fallback도 실패했어요.")
    st.write("가능한 원인: (1) 외부망 차단 (2) 해당 종목의 stooq 티커 매칭 실패 (3) 일시적 네트워크 문제")
    st.stop()

st.success(f"데이터 소스: {source_used}")

# --- 계산 ---
rows = []
for t in tickers:
    m = compute_move(prices, t, n_days)
    rows.append(
        {
            "Ticker": t,
            "Name": DEFAULT_TOP10.get(t, t),
            "Start Close": m["start_close"],
            "Last Close": m["last_close"],
            "Change": m["chg"],
            "Change (%)": m["pct"],
            "Used Trading Days": m["used_days"],
            "Data Points": m["points"],
        }
    )

result = pd.DataFrame(rows)

if metric == "등락률(%)":
    sortable = result.dropna(subset=["Change (%)"]).copy()
    sort_col = "Change (%)"
else:
    sortable = result.dropna(subset=["Change"]).copy()
    sort_col = "Change"

sortable = sortable.sort_values(sort_col, ascending=False).reset_index(drop=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader(f"📈 상승 Top {top_k}")
    st.dataframe(sortable.head(top_k), use_container_width=True)
with c2:
    st.subheader(f"📉 하락 Top {top_k}")
    st.dataframe(sortable.tail(top_k).sort_values(sort_col, ascending=True), use_container_width=True)

st.divider()
st.subheader("전체 결과")
st.dataframe(sortable, use_container_width=True)

st.divider()
st.subheader("📊 시각화")

if chart_mode == "개별 종목 라인":
    pick = st.selectbox("종목 선택", sortable["Ticker"].tolist(), index=0)
    dfp = prices[prices["Ticker"] == pick].sort_values("Date").tail(max(90, n_days * 2))
    fig = px.line(dfp, x="Date", y="Close", title=f"{pick} Close Price (최근 구간)")
    st.plotly_chart(fig, use_container_width=True)

elif chart_mode == "등락률 막대":
    fig = px.bar(
        sortable.dropna(subset=["Change (%)"]),
        x="Ticker",
        y="Change (%)",
        hover_data=["Name", "Used Trading Days", "Data Points"],
        title=f"최근 ~{n_days} 거래일 등락률(%) 비교",
    )
    st.plotly_chart(fig, use_container_width=True)

else:
    fig = px.bar(
        sortable.dropna(subset=["Change"]),
        x="Ticker",
        y="Change",
        hover_data=["Name", "Used Trading Days", "Data Points"],
        title=f"최근 ~{n_days} 거래일 등락액(가격) 비교",
    )
    st.plotly_chart(fig, use_container_width=True)
