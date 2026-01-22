# main.py
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import yfinance as yf

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

# ---- 야후 차단 완화를 위한 세션(User-Agent) ----
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

# ---- 여러 티커를 한 번에 다운로드(요청 횟수 최소화) ----
@st.cache_data(show_spinner=False, ttl=60 * 60)  # 1시간 캐시
def fetch_prices_batch(tickers: list[str], lookback_calendar_days: int) -> tuple[pd.DataFrame, str | None]:
    """
    return: (prices_df, error_message)
    prices_df columns: Date, Ticker, Open, High, Low, Close, Adj Close, Volume
    """
    if not tickers:
        return pd.DataFrame(), "No tickers."

    end = datetime.utcnow().date() + timedelta(days=1)
    start = end - timedelta(days=lookback_calendar_days)

    session = make_session()

    # 재시도(간단 백오프)
    last_err = None
    for attempt in range(1, 4):  # 3회
        try:
            raw = yf.download(
                tickers=tickers,
                start=start.isoformat(),
                end=end.isoformat(),
                group_by="column",
                progress=False,
                threads=True,
                auto_adjust=False,
                session=session,   # 핵심: 세션 주입
            )

            if raw is None or raw.empty:
                last_err = "yfinance returned empty dataframe."
                time.sleep(0.8 * attempt)
                continue

            # raw가 멀티인덱스 컬럼일 수 있음: (Open, AAPL) 같은 형태
            raw = raw.reset_index()

            # 멀티티커 형태 정규화
            # 1) 단일 티커면 컬럼이 평평할 수도 있음
            if isinstance(raw.columns, pd.MultiIndex):
                # Date + (field, ticker) -> long
                date_col = raw.columns[0]
                long_rows = []
                fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
                for t in tickers:
                    cols = []
                    for f in fields:
                        if (f, t) in raw.columns:
                            cols.append((f, t))
                        else:
                            cols.append(None)
                    # 하나라도 있어야 유효
                    if all(c is None for c in cols):
                        continue

                    tmp = pd.DataFrame({"Date": raw[date_col]})
                    for f, c in zip(fields, cols):
                        tmp[f] = raw[c] if c is not None else pd.NA
                    tmp["Ticker"] = t
                    long_rows.append(tmp)

                out = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()
            else:
                # 단일 티커 다운로드로 들어온 경우
                out = raw.copy()
                out["Ticker"] = tickers[0]
                out.rename(columns={"index": "Date"}, inplace=True)

            # 필수 정리
            out = out.dropna(subset=["Close"])
            out["Date"] = pd.to_datetime(out["Date"])
            out = out.sort_values(["Ticker", "Date"])
            return out, None

        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(0.8 * attempt)

    return pd.DataFrame(), last_err


def compute_move_from_prices(prices: pd.DataFrame, ticker: str, n_trading_days: int) -> dict:
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


st.title("🌍 글로벌 시총 Top10: 최근 N일 주가 변동 Top/Bottom 분석 (yfinance + Plotly)")
st.caption("Streamlit Cloud에서 yfinance가 빈 데이터/429를 주는 경우가 있어 배치 다운로드+세션 헤더+재시도를 적용했습니다.")

with st.sidebar:
    st.header("설정")
    n_days = st.slider("최근 N일(거래일 기준에 가깝게)", 1, 120, 20, 1)

    metric = st.radio("정렬 기준", ["등락률(%)", "등락액(가격)"], horizontal=True)
    lookback_calendar = int(max(45, n_days * 3))

    st.divider()
    tickers_text = st.text_area(
        "티커 입력(쉼표 구분)",
        value=",".join(DEFAULT_TOP10.keys()),
        height=80,
    )
    tickers = [t.strip().upper() for t in tickers_text.split(",") if t.strip()]
    top_k = st.slider("Top/Bottom 개수", 3, 10, 5, 1)

    st.divider()
    chart_mode = st.selectbox("차트", ["개별 종목 라인", "등락률 막대", "등락액 막대"])

# ---- “분석 실행” 버튼으로 불필요한 재요청 줄이기 ----
run = st.button("🚀 분석 실행", type="primary")

if run:
    with st.spinner("야후에서 데이터를 불러오는 중..."):
        prices, err = fetch_prices_batch(tickers, lookback_calendar)

    if err or prices.empty:
        st.error("데이터를 불러오지 못했어요.")
        st.write("아래는 디버그 정보예요(대부분 429/차단/네트워크 이슈).")
        st.code(str(err))
        st.info(
            "해결 팁:\n"
            "1) 잠시 후 다시 실행(429일 수 있음)\n"
            "2) 티커 수를 줄여서 테스트\n"
            "3) 캐시가 유지되도록 너무 자주 새로고침하지 않기\n"
        )
        st.stop()

    rows = []
    for t in tickers:
        move = compute_move_from_prices(prices, t, n_days)
        rows.append(
            {
                "Ticker": t,
                "Name": DEFAULT_TOP10.get(t, t),
                "Start Close": move["start_close"],
                "Last Close": move["last_close"],
                "Change": move["chg"],
                "Change (%)": move["pct"],
                "Used Trading Days": move["used_days"],
                "Data Points": move["points"],
            }
        )

    result = pd.DataFrame(rows)

    if metric == "등락률(%)":
        sortable = result.dropna(subset=["Change (%)"]).copy()
        sort_col = "Change (%)"
    else:
        sortable = result.dropna(subset=["Change"]).copy()
        sort_col = "Change"

    if sortable.empty:
        st.error("계산 가능한 결과가 없어요(가격 데이터가 비었거나 Close가 부족).")
        st.dataframe(result, use_container_width=True)
        st.stop()

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
        dfp = prices[prices["Ticker"] == pick].sort_values("Date").tail(max(60, n_days * 2))
        fig = px.line(dfp, x="Date", y="Close", title=f"{pick} Close Price (최근 구간)")
        st.plotly_chart(fig, use_container_width=True)

    elif chart_mode == "등락률 막대":
        fig = px.bar(
            sortable.dropna(subset=["Change (%)"]),
            x="Ticker",
            y="Change (%)",
            hover_data=["Name", "Start Close", "Last Close", "Used Trading Days", "Data Points"],
            title=f"최근 ~{n_days} 거래일 등락률(%) 비교",
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        fig = px.bar(
            sortable.dropna(subset=["Change"]),
            x="Ticker",
            y="Change",
            hover_data=["Name", "Start Close", "Last Close", "Used Trading Days", "Data Points"],
            title=f"최근 ~{n_days} 거래일 등락액(가격) 비교",
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("왼쪽에서 설정 후 **‘🚀 분석 실행’**을 눌러 주세요. (Streamlit Cloud에서 과도한 재요청을 줄이기 위해 버튼으로 실행합니다.)")
