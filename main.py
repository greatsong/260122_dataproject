import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(
    page_title="글로벌 시총 Top10 주가 분석",
    page_icon="📈",
    layout="wide"
)

# CSS 스타일링
st.markdown("""
<style>
    .stApp { background: #0f172a; }
    .metric-card {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #334155;
    }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; }
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
def get_stock_data(ticker, days):
    """개별 주식 데이터 가져오기 - Ticker.history() 방식"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{days + 10}d")
        
        if hist.empty or len(hist) < 2:
            return None
            
        return hist
    except Exception as e:
        return None

def calculate_return(hist, days):
    """수익률 계산"""
    if hist is None or len(hist) < 2:
        return None
    
    df = hist.tail(days + 1)
    if len(df) < 2:
        return None
        
    start_price = df['Close'].iloc[0]
    end_price = df['Close'].iloc[-1]
    pct_change = ((end_price - start_price) / start_price) * 100
    
    return {
        'start_price': float(start_price),
        'end_price': float(end_price),
        'change_pct': float(pct_change),
        'change_abs': float(end_price - start_price)
    }

def main():
    st.title("📈 글로벌 시총 Top10 주가 분석")
    st.markdown("---")
    
    # 사이드바 설정
    st.sidebar.header("⚙️ 설정")
    days = st.sidebar.slider("분석 기간 (일)", min_value=1, max_value=365, value=30)
    
    if st.sidebar.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()
    
    # 데이터 로드
    with st.spinner('주가 데이터를 불러오는 중...'):
        stock_data = {}
        returns = {}
        
        for ticker, name in TOP10_STOCKS.items():
            hist = get_stock_data(ticker, days)
            if hist is not None:
                stock_data[ticker] = hist
                ret = calculate_return(hist, days)
                if ret:
                    returns[ticker] = {**ret, 'name': name}
    
    if not returns:
        st.error("데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return
    
    st.sidebar.success(f"✅ {len(returns)}/{len(TOP10_STOCKS)} 종목 로드됨")
    
    # 수익률 정렬
    sorted_returns = dict(sorted(returns.items(), key=lambda x: x[1]['change_pct'], reverse=True))
    tickers_sorted = list(sorted_returns.keys())
    
    best_ticker = tickers_sorted[0]
    worst_ticker = tickers_sorted[-1]
    avg_return = sum(r['change_pct'] for r in returns.values()) / len(returns)
    
    # 메트릭 표시
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label=f"🚀 최고 상승 - {returns[best_ticker]['name']}",
            value=f"${returns[best_ticker]['end_price']:.2f}",
            delta=f"{returns[best_ticker]['change_pct']:.2f}%"
        )
    
    with col2:
        st.metric(
            label=f"📉 최고 하락 - {returns[worst_ticker]['name']}",
            value=f"${returns[worst_ticker]['end_price']:.2f}",
            delta=f"{returns[worst_ticker]['change_pct']:.2f}%"
        )
    
    with col3:
        st.metric(
            label="📊 평균 수익률",
            value=f"{avg_return:.2f}%",
            delta="Top10 평균"
        )
    
    st.markdown("---")
    
    # 수익률 바 차트
    st.subheader(f"📊 최근 {days}일 수익률 비교")
    
    names = [returns[t]['name'] for t in tickers_sorted]
    changes = [returns[t]['change_pct'] for t in tickers_sorted]
    colors = ['#22c55e' if x >= 0 else '#ef4444' for x in changes]
    
    fig_bar = go.Figure(data=[
        go.Bar(
            x=names,
            y=changes,
            marker_color=colors,
            text=[f"{x:.2f}%" for x in changes],
            textposition='outside'
        )
    ])
    
    fig_bar.update_layout(
        xaxis_title="종목",
        yaxis_title="수익률 (%)",
        height=450,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e2e8f0'),
        xaxis=dict(gridcolor='#334155'),
        yaxis=dict(gridcolor='#334155')
    )
    
    st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # 주가 추이 차트
    st.subheader("📈 주가 추이 (정규화)")
    
    available = list(stock_data.keys())
    default_selection = [best_ticker, worst_ticker] if best_ticker in available and worst_ticker in available else available[:2]
    
    selected = st.multiselect(
        "종목 선택",
        options=available,
        default=default_selection,
        format_func=lambda x: f"{TOP10_STOCKS[x]} ({x})"
    )
    
    if selected:
        fig_line = go.Figure()
        
        for ticker in selected:
            df = stock_data[ticker].tail(days + 1)
            normalized = (df['Close'] / df['Close'].iloc[0]) * 100
            
            fig_line.add_trace(go.Scatter(
                x=df.index,
                y=normalized,
                mode='lines',
                name=f"{TOP10_STOCKS[ticker]}",
                hovertemplate=f"{TOP10_STOCKS[ticker]}<br>날짜: %{{x|%Y-%m-%d}}<br>정규화: %{{y:.2f}}<br>실제가: $%{{customdata:.2f}}<extra></extra>",
                customdata=df['Close']
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
            xaxis=dict(gridcolor='#334155'),
            yaxis=dict(gridcolor='#334155')
        )
        
        st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("---")
    
    # 상세 테이블
    st.subheader("📋 상세 데이터")
    
    table_data = []
    for ticker in tickers_sorted:
        r = returns[ticker]
        table_data.append({
            "종목": f"{r['name']} ({ticker})",
            "시작가": f"${r['start_price']:.2f}",
            "종가": f"${r['end_price']:.2f}",
            "변동률": f"{r['change_pct']:.2f}%",
            "변동액": f"${r['change_abs']:.2f}"
        })
    
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
    
    # 푸터
    st.markdown("---")
    st.caption("데이터: Yahoo Finance | 1시간 캐시 | 시총 순위는 변동 가능")

if __name__ == "__main__":
    main()
