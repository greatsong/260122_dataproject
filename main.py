import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 페이지 설정
st.set_page_config(
    page_title="글로벌 시총 Top10 주가 분석",
    page_icon="📈",
    layout="wide"
)

# CSS 스타일링 (작동하는 코드와 동일한 방식)
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

@st.cache_data(ttl=3600)
def get_stock_data(ticker):
    """주식 데이터 가져오기 - 작동하는 코드와 동일한 방식"""
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
            'hist': hist
        }
    except Exception as e:
        return None

@st.cache_data(ttl=3600)
def get_stock_history(ticker, days):
    """N일 히스토리 데이터"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="{}d".format(days + 10))
        return hist if not hist.empty else None
    except:
        return None

def calculate_n_day_return(hist, days):
    """N일 수익률 계산"""
    if hist is None or len(hist) < 2:
        return None
    df = hist.tail(days + 1)
    if len(df) < 2:
        return None
    start = df['Close'].iloc[0]
    end = df['Close'].iloc[-1]
    return ((end - start) / start) * 100

def format_market_cap(mc):
    if mc >= 1e12:
        return "${:.2f}T".format(mc/1e12)
    elif mc >= 1e9:
        return "${:.2f}B".format(mc/1e9)
    return "${:.0f}M".format(mc/1e6)

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
with st.spinner('🔄 주식 데이터를 불러오는 중...'):
    stock_data = {}
    for ticker, name in TOP10_STOCKS.items():
        data = get_stock_data(ticker)
        if data:
            # N일 수익률 계산을 위한 히스토리
            hist_n = get_stock_history(ticker, analysis_days)
            n_day_return = calculate_n_day_return(hist_n, analysis_days)
            
            stock_data[ticker] = {
                **data,
                'ticker': ticker,
                'n_day_return': n_day_return if n_day_return else data['change_pct'],
                'hist_n': hist_n
            }

if not stock_data:
    st.error("데이터를 불러올 수 없습니다. 잠시 후 새로고침을 눌러주세요.")
    st.info("💡 Yahoo Finance API 제한으로 인해 일시적으로 접속이 안될 수 있습니다.")
    st.stop()

st.sidebar.success("✅ {}/{} 종목 로드".format(len(stock_data), len(TOP10_STOCKS)))

# 수익률 기준 정렬
sorted_data = sorted(stock_data.items(), key=lambda x: x[1]['n_day_return'], reverse=True)
best_ticker, best_data = sorted_data[0]
worst_ticker, worst_data = sorted_data[-1]
avg_return = sum(d['n_day_return'] for _, d in sorted_data) / len(sorted_data)

# 메트릭 카드
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

# 수익률 바 차트
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

# 주가 추이 차트
st.subheader("📈 주가 추이 (정규화)")

available_tickers = [t for t, d in stock_data.items() if d.get('hist_n') is not None and len(d['hist_n']) > 1]

selected = st.multiselect(
    "종목 선택",
    options=available_tickers,
    default=[best_ticker, worst_ticker] if best_ticker in available_tickers and worst_ticker in available_tickers else available_tickers[:2],
    format_func=lambda x: "{} ({})".format(TOP10_STOCKS[x], x)
)

if selected:
    fig_line = go.Figure()
    
    for ticker in selected:
        hist = stock_data[ticker]['hist_n']
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
        yaxis_title="정규화 가격 (시작=100)",
        height=450,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e2e8f0'),
        xaxis=dict(gridcolor='#334155', tickfont=dict(color='#94a3b8')),
        yaxis=dict(gridcolor='#334155', tickfont=dict(color='#94a3b8'))
    )
    
    st.plotly_chart(fig_line, use_container_width=True)

st.markdown("---")

# 요약 테이블
st.subheader("📋 상세 데이터")

table_data = []
for ticker, data in sorted_data:
    change_symbol = "+" if data['n_day_return'] >= 0 else ""
    table_data.append({
        "종목": "{} ({})".format(data['name'], ticker),
        "현재가": "${:.2f}".format(data['price']),
        "시가총액": format_market_cap(data['market_cap']),
        "{}일 수익률".format(analysis_days): "{}{}%".format(change_symbol, round(data['n_day_return'], 2))
    })

st.dataframe(
    pd.DataFrame(table_data),
    use_container_width=True,
    hide_index=True
)

# 푸터
st.markdown("---")
st.caption("📈 데이터: Yahoo Finance | 실시간 데이터와 차이가 있을 수 있습니다 | 1시간 캐시")
