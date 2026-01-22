import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(
    page_title="글로벌 시총 Top10 주가 분석",
    page_icon="📈",
    layout="wide"
)

# 글로벌 시총 Top10 종목 (2024년 기준)
TOP10_STOCKS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet (Google)",
    "AMZN": "Amazon",
    "META": "Meta (Facebook)",
    "BRK-B": "Berkshire Hathaway",
    "TSM": "TSMC",
    "LLY": "Eli Lilly",
    "AVGO": "Broadcom"
}

@st.cache_data(ttl=3600)
def get_stock_data(tickers, days):
    """주식 데이터 가져오기"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 10)  # 여유분 추가
    
    data = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            if not hist.empty:
                data[ticker] = hist
        except Exception as e:
            st.warning(f"{ticker} 데이터 로드 실패: {e}")
    
    return data

def calculate_returns(data, days):
    """수익률 계산"""
    returns = {}
    for ticker, df in data.items():
        if len(df) >= 2:
            # 최근 N일 데이터만 사용
            df_recent = df.tail(days + 1)
            if len(df_recent) >= 2:
                start_price = df_recent['Close'].iloc[0]
                end_price = df_recent['Close'].iloc[-1]
                pct_change = ((end_price - start_price) / start_price) * 100
                returns[ticker] = {
                    'name': TOP10_STOCKS[ticker],
                    'start_price': start_price,
                    'end_price': end_price,
                    'change_pct': pct_change,
                    'change_abs': end_price - start_price
                }
    return returns

def main():
    st.title("📈 글로벌 시총 Top10 주가 분석")
    st.markdown("---")
    
    # 사이드바 설정
    st.sidebar.header("⚙️ 설정")
    days = st.sidebar.slider("분석 기간 (일)", min_value=1, max_value=365, value=30)
    
    # 데이터 로드
    with st.spinner("주가 데이터를 불러오는 중..."):
        stock_data = get_stock_data(list(TOP10_STOCKS.keys()), days)
    
    if not stock_data:
        st.error("데이터를 불러올 수 없습니다.")
        return
    
    # 수익률 계산
    returns = calculate_returns(stock_data, days)
    
    if not returns:
        st.error("수익률을 계산할 수 없습니다.")
        return
    
    # 수익률 데이터프레임 생성
    df_returns = pd.DataFrame(returns).T
    df_returns = df_returns.sort_values('change_pct', ascending=False)
    
    # 최고/최저 종목
    best_ticker = df_returns.index[0]
    worst_ticker = df_returns.index[-1]
    
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
        avg_return = df_returns['change_pct'].mean()
        st.metric(
            label="📊 평균 수익률",
            value=f"{avg_return:.2f}%",
            delta="Top10 평균"
        )
    
    st.markdown("---")
    
    # 수익률 바 차트
    st.subheader(f"📊 최근 {days}일 수익률 비교")
    
    colors = ['#00CC96' if x >= 0 else '#EF553B' for x in df_returns['change_pct']]
    
    fig_bar = go.Figure(data=[
        go.Bar(
            x=[f"{row['name']}" for _, row in df_returns.iterrows()],
            y=df_returns['change_pct'],
            marker_color=colors,
            text=[f"{x:.2f}%" for x in df_returns['change_pct']],
            textposition='outside'
        )
    ])
    
    fig_bar.update_layout(
        xaxis_title="종목",
        yaxis_title="수익률 (%)",
        height=500,
        showlegend=False
    )
    
    st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("---")
    
    # 주가 추이 차트
    st.subheader("📈 주가 추이")
    
    selected_stocks = st.multiselect(
        "종목 선택",
        options=list(TOP10_STOCKS.keys()),
        default=[best_ticker, worst_ticker],
        format_func=lambda x: f"{TOP10_STOCKS[x]} ({x})"
    )
    
    if selected_stocks:
        fig_line = go.Figure()
        
        for ticker in selected_stocks:
            if ticker in stock_data:
                df = stock_data[ticker].tail(days + 1)
                # 정규화 (시작점 = 100)
                normalized = (df['Close'] / df['Close'].iloc[0]) * 100
                
                fig_line.add_trace(go.Scatter(
                    x=df.index,
                    y=normalized,
                    mode='lines',
                    name=f"{TOP10_STOCKS[ticker]} ({ticker})",
                    hovertemplate=f"{TOP10_STOCKS[ticker]}<br>날짜: %{{x}}<br>정규화: %{{y:.2f}}<br>실제가: $%{{customdata:.2f}}<extra></extra>",
                    customdata=df['Close']
                ))
        
        fig_line.update_layout(
            xaxis_title="날짜",
            yaxis_title="정규화 가격 (시작=100)",
            height=500,
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig_line, use_container_width=True)
    
    st.markdown("---")
    
    # 상세 데이터 테이블
    st.subheader("📋 상세 데이터")
    
    display_df = df_returns.copy()
    display_df.index = [f"{TOP10_STOCKS[t]} ({t})" for t in display_df.index]
    display_df.columns = ['종목명', '시작가($)', '종가($)', '변동률(%)', '변동액($)']
    display_df = display_df.drop('종목명', axis=1)
    
    # 포맷팅
    display_df['시작가($)'] = display_df['시작가($)'].apply(lambda x: f"${x:.2f}")
    display_df['종가($)'] = display_df['종가($)'].apply(lambda x: f"${x:.2f}")
    display_df['변동률(%)'] = display_df['변동률(%)'].apply(lambda x: f"{x:.2f}%")
    display_df['변동액($)'] = display_df['변동액($)'].apply(lambda x: f"${x:.2f}")
    
    st.dataframe(display_df, use_container_width=True)
    
    # 푸터
    st.markdown("---")
    st.caption("데이터 출처: Yahoo Finance | 시총 순위는 변동될 수 있습니다.")

if __name__ == "__main__":
    main()
