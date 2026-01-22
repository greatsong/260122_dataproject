import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# 페이지 설정
st.set_page_config(
    page_title="글로벌 시총 Top10 주가 분석",
    page_icon="📈",
    layout="wide"
)

# CSS 스타일링
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&display=swap');
    * { font-family: 'Noto Sans KR', sans-serif; }
    .stApp { background: #0f172a; }
    div[data-testid="stMetricValue"] { color: #e2e8f0; }
    div[data-testid="stMetricLabel"] { color: #94a3b8; }
</style>
""", unsafe_allow_html=True)

# 글로벌 시총 Top10 종목
TOP10_STOCKS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft", 
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "BRK-B": "Berkshire",
    "TSM": "TSMC",
    "LLY": "Eli Lilly",
    "AVGO": "Broadcom"
}

def format_market_cap(mc):
    if mc >= 1e12:
        return "${:.2f}T".format(mc/1e12)
    elif mc >= 1e9:
        return "${:.2f}B".format(mc/1e9)
    return "${:.0f}M".format(mc/1e6)

@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """주식 데이터 가져오기"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="5d")
        
        if len(hist) >= 2:
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2]
            price_change = current_price - prev_price
            price_change_pct = (price_change / prev_price) * 100
        else:
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            price_change = 0
            price_change_pct = 0
        
        return {
            'name': info.get('shortName', ticker),
            'price': current_price,
            'change_pct': price_change_pct,
            'market_cap': info.get('marketCap', 0),
        }
    except Exception as e:
        return None

@st.cache_data(ttl=3600)
def get_all_data_with_delay():
    """모든 종목 데이터를 딜레이와 함께 가져오기"""
    results = {}
    for ticker, name in TOP10_STOCKS.items():
        data = get_stock_data(ticker)
        if data:
            results[ticker] = data
        time.sleep(0.5)  # 요청 간 딜레이
    return results

@st.cache_data(ttl=3600)
def get_history_data(ticker, days):
    """N일 히스토리"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="{}d".format(days + 10))
        return hist if not hist.empty else None
    except:
        return None

def calculate_n_day_return(ticker, days):
    """N일 수익률"""
    hist = get_history_data(ticker, days)
    if hist is None or len(hist) < 2:
        return None, None
    df = hist.tail(days + 1)
    if len(df) < 2:
        return None, None
    start = df['Close'].iloc[0]
    end = df['Close'].iloc[-1]
    return ((end - start) / start) * 100, hist

# 메인
st.title("📈 글로벌 시총 Top10 주가 분석")

update_time = datetime.now().strftime('%Y년 %m월 %d일 %H:%M')
st.caption("📅 {} 기준".format(update_time))
st.markdown("---")

# 사이드바
st.sidebar.header("⚙️ 설정")
analysis_days = st.sidebar.slider("분석 기간 (일)", 1, 365, 30)

if st.sidebar.button("🔄 새로고침"):
    st.cache_data.clear()
    st.rerun()

# 데이터 로딩
with st.spinner('🔄 주식 데이터를 불러오는 중... (약 5초 소요)'):
    stock_data = get_all_data_with_delay()

if not stock_data:
    st.error("데이터를 불러올 수 없습니다. 잠시 후 새로고침을 눌러주세요.")
    st.stop()

st.sidebar.success("✅ {}/{} 종목 로드".format(len(stock_data), len(TOP10_STOCKS)))

# N일 수익률 계산
with st.spinner('📊 수익률 계산 중...'):
    for ticker in list(stock_data.keys()):
        n_return, hist = calculate_n_day_return(ticker, analysis_days)
        if n_return is not None:
            stock_data[ticker]['n_day_return'] = n_return
            stock_data[ticker]['hist'] = hist
        else:
            stock_data[ticker]['n_day_return'] = stock_data[ticker]['change_pct']
            stock_data[ticker]['hist'] = None
        time.sleep(0.3)

# 정렬
sorted_data = sorted(stock_data.items(), key=lambda x: x[1]['n_day_return'], reverse=True)
best_ticker, best_data = sorted_data[0]
worst_ticker, worst_data = sorted_data[-1]
avg_return = sum(d['n_day_return'] for _, d in sorted_data) / len(sorted_data)

# 메트릭
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="🚀 최고 상승 - {}".format(best_data['name']),
        value="${:.2f}".format(best_data['price']),
        delta="{:.2f}%".format(best_data['n_day_return'])
    )

with col2:
    st.metric(
        label="📉 최고 하락 - {}".format(worst_data['name']),
        value="${:.2f}".format(worst_data['price']),
        delta="{:.2f}%".format(worst_data['n_day_return'])
    )

with col3:
    st.metric(
        label="📊 평균 수익률",
        value="{:.2f}%".format(avg_return),
        delta="Top10 평균"
    )

st.markdown("---")

# 바 차트
st.subheader("📊 최근 {}일 수익률 비교".format(analysis_days))

names = [d['name'] for _, d in sorted_data]
returns = [d['n_day_return'] for _, d in sorted_data]
colors = ['#22c55e' if r >= 0 else '#ef4444' for r in returns]

fig_bar = go.Figure(data=[
    go.Bar(
        x=names,
        y=returns,
        marker_color=colors,
        text=["{:.1f}%".format(r) for r in returns],
        textposition='outside'
    )
])

fig_bar.update_layout(
    xaxis_title="종목",
    yaxis_title="수익률 (%)",
    height=450,
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    font=dict(color='#e2e8f0'),
    xaxis=dict(gridcolor='#334155', tickfont=dict(color='#94a3b8')),
    yaxis=dict(gridcolor='#334155', tickfont=dict(color='#94a3b8'))
)

st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# 라인 차트
st.subheader("📈 주가 추이 (정규화)")

available = [t for t, d in stock_data.items() if d.get('hist') is not None]

selected = st.multiselect(
    "종목 선택",
    options=available,
    default=[best_ticker, worst_ticker] if best_ticker in available and worst_ticker in available else available[:2],
    format_func=lambda x: "{} ({})".format(TOP10_STOCKS[x], x)
)

if selected:
    fig_line = go.Figure()
    
    for ticker in selected:
        hist = stock_data[ticker].get('hist')
        if hist is not None and len(hist) > 1:
            df = hist.tail(analysis_days + 1)
            normalized = (df['Close'] / df['Close'].iloc[0]) * 100
            fig_line.add_trace(go.Scatter(
                x=df.index,
                y=normalized,
                mode='lines',
                name=TOP10_STOCKS[ticker]
            ))
    
    fig_line.update_layout(
        xaxis_title="날짜",
        yaxis_title="정규화 (시작=100)",
        height=450,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e2e8f0'),
        xaxis=dict(gridcolor='#334155'),
        yaxis=dict(gridcolor='#334155')
    )
    
    st.plotly_chart(fig_line, use_container_width=True)

st.markdown("---")

# 테이블
st.subheader("📋 상세 데이터")

table_data = []
for ticker, data in sorted_data:
    symbol = "+" if data['n_day_return'] >= 0 else ""
    table_data.append({
        "종목": "{} ({})".format(data['name'], ticker),
        "현재가": "${:.2f}".format(data['price']),
        "시가총액": format_market_cap(data['market_cap']),
        "{}일 수익률".format(analysis_days): "{}{}%".format(symbol, round(data['n_day_return'], 2))
    })

st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

st.caption("📈 데이터: Yahoo Finance | 1시간 캐시")
