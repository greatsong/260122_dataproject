# main.py
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Global Top10 Movers", layout="wide")

# ---- 기본 Top10(글로벌 시총 상위권) 티커/이름 (앱에서 사용자가 바꿀 수 있게 설계) ----
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

# ---- 유틸: 티커별 가격 데이터 가져오기 ----
@st.cache_data(show_spinner=False, ttl=60 * 30)  # 30분 캐시
def fetch_prices(ticker: str, lookback_days_calendar: int) -> pd.DataFrame:
    """
    lookback_days_calendar: 캘린더 기준으로 넉넉히 가져오기(거래일 부족 방지)
    """
    end = datetime.utcnow().date() + timedelta(days=1)
    start = end - timedelta(days=lookback_days_calendar)

    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=end.isoformat(),
        progress=False,
        auto_adjust=False,
        group_by="column",
        threads=True,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.reset_index()
    # 표준화: Date, Close(우선), Adj Close도 같이 보관
    keep_cols = [c for c in ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df.columns]
    df = df[keep_cols].dropna(subset=["Close"])
    return df


def compute_move(df: pd.DataFrame, n_trading_days: int) -> dict:
    """
    df: 날짜 오름차순
    n_trading_days: '최근 N일'을 거래일 기준으로 최대한 맞추기 위해 Close 시계열에서 N일 전 값 사용
    """
    if df is None or df.empty:
        return {"start_close": None, "last_close": None, "chg": None, "pct": None, "used_days": 0}

    close = df["Close"].dropna()
    if close.shape[0] < 2:
        return {"start_close": None, "last_close": float(close.iloc[-1]) if close.shape[0] else None,
                "chg": None, "pct": None, "used_days": int(close.shape[0])}

    # N 거래일 전을 쓰되, 데이터가 부족하면 가능한 만큼 사용
    idx_start = max(0, close.shape[0] - 1 - n_trading_days)
    start_close = float(close.iloc[idx_start])
    last_close = float(close.iloc[-1])
    chg = last_close - start_close
    pct = (chg / start_close) * 100 if start_close != 0 else None
    used_days = (close.shape[0] - 1) - idx_start

    return {"start_close": start_close, "last_close": last_close, "chg": chg, "pct": pct, "used_days": used_days}


# ---- UI ----
st.title("🌍 글로벌 시총 Top10: 최근 N일 주가 변동 Top/Bottom 분석")
st.caption("데이터: yfinance / 시각화: Plotly")

with st.sidebar:
    st.header("설정")

    n_days = st.slider("최근 N일 (거래일 기준에 가깝게)", min_value=1, max_value=120, value=20, step=1)

    metric = st.radio("정렬 기준", ["등락률(%)", "등락액(가격)"], horizontal=True)

    # 거래일 N일 확보를 위해 캘린더 기준으로 더 넉넉히 가져옴
    # 대략 N거래일 ~ 1.4~1.7*N 캘린더일 + 여유
    lookback_calendar = int(max(30, n_days * 3))

    st.divider()
    st.subheader("분석 대상 티커")
    st.write("기본은 Top10이지만, 필요하면 여기서 직접 수정해서 비교할 수 있어요.")

    tickers_text = st.text_area(
        "티커 입력 (쉼표로 구분)",
        value=",".join(DEFAULT_TOP10.keys()),
        help="예: NVDA,AAPL,GOOG,MSFT,...  (yfinance 티커 형식에 맞춰 입력)",
        height=80,
    )
    tickers = [t.strip().upper() for t in tickers_text.split(",") if t.strip()]

    top_k = st.slider("Top/Bottom 몇 개 보여줄까?", min_value=3, max_value=10, value=5, step=1)

    st.divider()
    st.subheader("차트 옵션")
    chart_mode = st.selectbox("차트 종류", ["개별 종목 가격 추이(라인)", "등락률 막대그래프", "등락액 막대그래프"])

# ---- 데이터 수집/계산 ----
if not tickers:
    st.warning("티커를 1개 이상 입력해 주세요.")
    st.stop()

rows = []
progress = st.progress(0, text="데이터를 불러오는 중...")
for i, t in enumerate(tickers, start=1):
    df = fetch_prices(t, lookback_calendar)
    move = compute_move(df, n_days)

    name = DEFAULT_TOP10.get(t, t)
    rows.append({
        "Ticker": t,
        "Name": name,
        "Start Close": move["start_close"],
        "Last Close": move["last_close"],
        "Change": move["chg"],
        "Change (%)": move["pct"],
        "Used Trading Days": move["used_days"],
        "Data Points": 0 if df is None else int(df.shape[0]),
    })
    progress.progress(i / len(tickers), text=f"불러오는 중... ({i}/{len(tickers)})")

progress.empty()

result = pd.DataFrame(rows)

# 결측 제거(계산 불가한 항목)
if metric == "등락률(%)":
    sortable = result.dropna(subset=["Change (%)"]).copy()
    sort_col = "Change (%)"
else:
    sortable = result.dropna(subset=["Change"]).copy()
    sort_col = "Change"

if sortable.empty:
    st.error("데이터를 불러오지 못했어요. 티커가 맞는지/네트워크 상태를 확인해 주세요.")
    st.stop()

sortable = sortable.sort_values(sort_col, ascending=False).reset_index(drop=True)

# ---- 결과 표시 ----
c1, c2 = st.columns(2)

with c1:
    st.subheader(f"📈 상승 Top {top_k} ({metric})")
    top_df = sortable.head(top_k).copy()
    st.dataframe(top_df, use_container_width=True)

with c2:
    st.subheader(f"📉 하락 Top {top_k} ({metric})")
    bottom_df = sortable.tail(top_k).sort_values(sort_col, ascending=True).copy()
    st.dataframe(bottom_df, use_container_width=True)

st.divider()
st.subheader("전체 결과")
st.dataframe(sortable, use_container_width=True)

# ---- 시각화 ----
st.divider()
st.subheader("📊 시각화")

if chart_mode == "개별 종목 가격 추이(라인)":
    pick = st.selectbox("차트로 볼 종목", sortable["Ticker"].tolist(), index=0)
    dfp = fetch_prices(pick, lookback_calendar)
    if dfp.empty:
        st.warning("해당 티커의 가격 데이터를 불러오지 못했어요.")
    else:
        # 최근 구간만 표시
        dfp = dfp.sort_values("Date")
        dfp = dfp.tail(max(30, n_days * 2))
        fig = px.line(dfp, x="Date", y="Close", title=f"{pick} Close Price (최근 구간)")
        st.plotly_chart(fig, use_container_width=True)

elif chart_mode == "등락률 막대그래프":
    plot_df = sortable.dropna(subset=["Change (%)"]).copy()
    fig = px.bar(
        plot_df,
        x="Ticker",
        y="Change (%)",
        hover_data=["Name", "Start Close", "Last Close", "Used Trading Days"],
        title=f"최근 ~{n_days} 거래일 등락률(%) 비교",
    )
    st.plotly_chart(fig, use_container_width=True)

else:  # 등락액 막대그래프
    plot_df = sortable.dropna(subset=["Change"]).copy()
    fig = px.bar(
        plot_df,
        x="Ticker",
        y="Change",
        hover_data=["Name", "Start Close", "Last Close", "Used Trading Days"],
        title=f"최근 ~{n_days} 거래일 등락액(가격) 비교",
    )
    st.plotly_chart(fig, use_container_width=True)

st.caption("주의: yfinance 데이터는 거래소/티커/지연 등에 따라 값이 달라질 수 있어요.")
