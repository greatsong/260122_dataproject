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
def get_all_stock_data(days):
    """모든 주식 데이터 한번에 가져오기"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 30)
    
    results = {}
    errors = []
    
    for ticker, name in TOP10_STOCKS.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if not hist.empty and len(hist) >= 2:
                results[ticker] = hist
            else:
                errors.append(f"{ticker}: 데이터 없음")
        except Exception as e:
            errors.append(f"{ticker}: {str(e)[:50]}")
    
    return results, errors

def calculate_return(hist, days):
    """수익률 계산"""
    if hist is None or len(hist) < 2:
        return None
    
    df = hist.tail(days + 1)
    if len(df) < 2:
        df = hist.tail(2)
        
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
    
    # 사이드바
    st.sidebar.header("⚙️ 설정")
    days = st.sidebar.slider("분석 기간 (일)", min_value=1, max_value=365, value=30)
    
    if st.sidebar.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()
    
    # 데이터 로드
    with st.spinner('데이터 로딩 중...'):
        stock_data, errors = get_all_stock_data(days)
    
    # 에러 표시 (디버깅용)
    if errors:
        with st.sidebar.expander("⚠️ 로드 실패 종목"):
            for err in errors:
                st.caption(err)
    
    if not stock_data:
        st.error("데이터를 불러올 수 없습니다.")
        st.info("잠시 후 새로고침 버튼을 눌러주세요.")
        
        # 디버깅: 단일 종목 테스트
        st.markdown("---")
        st.subheader("🔧 디버깅")
        test_ticker = st.selectbox("테스트할 종목", list(TOP10_STOCKS.keys()))
        if st.button("테스트"):
            try:
                stock = yf.Ticker(test_ticker)
                hist = stock.history(period="5d")
                st.write(f"결과: {len(hist)} rows")
                st.dataframe(hist)
            except Exception as e:
                st.error(f"에러: {e}")
        return
    
    st.sidebar.success(f"✅ {len(stock_data)}/{len(TOP10_STOCKS)} 종목 로드")
    
    # 수익률 계산
    returns = {}
    for ticker, hist in stock_data.items():
        ret = calculate_return(hist, days)
        if ret:
            returns[ticker] = {**ret, 'name': TOP10_STOCKS[ticker]}
    
    if not returns:
        st.error("수익률 계산 실패")
        return
    
    # 정렬
    sorted_tickers = sorted(returns.keys(), key=lambda x: returns[x]['change_pct'], reverse=True)
    best = sorted_tickers[0]
    worst = sorted_tickers[-1]
    avg = sum(r['change_pct'] for r in returns.values()) / len(returns)
    
    # 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric(f"🚀 {returns[best]['name']}", f"${returns[best]['end_price']:.2f}", f"{returns[best]['change_pct']:.2f}%")
    c2.metric(f"📉 {returns[worst]['name']}", f"${returns[worst]['end_price']:.2f}", f"{returns[worst]['change_pct']:.2f}%")
    c3.metric("📊 평균", f"{avg:.2f}%")
    
    st.markdown("---")
    
    # 바 차트
    st.subheader(f"📊 최근 {days}일 수익률")
    
    names = [returns[t]['name'] for t in sorted_tickers]
    vals = [returns[t]['change_pct'] for t in sorted_tickers]
    colors = ['#22c55e' if v >= 0 else '#ef4444' for v in vals]
    
    fig_bar = go.Figure(go.Bar(
        x=names, y=vals,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in vals],
        textposition='outside'
    ))
    fig_bar.update_layout(height=400, xaxis_title="종목", yaxis_title="수익률(%)")
    st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # 라인 차트
    st.subheader("📈 주가 추이")
    
    selected = st.multiselect(
        "종목 선택",
        list(stock_data.keys()),
        default=[best, worst],
        format_func=lambda x: f"{TOP10_STOCKS[x]} ({x})"
    )
    
    if selected:
        fig_line = go.Figure()
        for t in selected:
            df = stock_data[t].tail(days + 1)
            norm = (df['Close'] / df['Close'].iloc[0]) * 100
            fig_line.add_trace(go.Scatter(
                x=df.index, y=norm,
                mode='lines', name=TOP10_STOCKS[t]
            ))
        fig_line.update_layout(height=400, yaxis_title="정규화 (시작=100)")
        st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("---")
    
    # 테이블
    st.subheader("📋 상세")
    rows = [{
        "종목": f"{returns[t]['name']} ({t})",
        "시작가": f"${returns[t]['start_price']:.2f}",
        "종가": f"${returns[t]['end_price']:.2f}",
        "변동률": f"{returns[t]['change_pct']:.2f}%"
    } for t in sorted_tickers]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    
    st.caption("데이터: Yahoo Finance")

if __name__ == "__main__":
    main()
