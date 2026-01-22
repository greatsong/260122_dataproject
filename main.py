import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

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

@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_data(tickers_tuple, days):
    """주식 데이터 가져오기 - 배치 다운로드로 Rate Limit 방지"""
    tickers = list(tickers_tuple)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 10)
    
    data = {}
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # 모든 종목을 한 번에 다운로드 (Rate Limit 방지)
            tickers_str = " ".join(tickers)
            df_all = yf.download(
                tickers_str,
                start=start_date,
                end=end_date,
                group_by='ticker',
                progress=False,
                threads=False  # 스레드 비활성화로 안정성 향상
            )
            
            if df_all.empty:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 지수 백오프
                    continue
                return {}
            
            # 단일 종목인 경우 처리
            if len(tickers) == 1:
                ticker = tickers[0]
                data[ticker] = df_all[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            else:
                # 여러 종목인 경우 분리
                for ticker in tickers:
                    try:
                        if ticker in df_all.columns.get_level_values(0):
                            ticker_data = df_all[ticker].copy()
                            ticker_data = ticker_data.dropna()
                            if not ticker_data.empty:
                                data[ticker] = ticker_data
                    except Exception:
                        continue
            
            if data:
                return data
                
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                st.error(f"데이터 로드 실패: {e}")
    
    return data

def calculate_returns(data, days):
    """수익률 계산"""
    returns = {}
    for ticker, df in data.items():
        if len(df) >= 2:
            df_recent = df.tail(days + 1)
            if len(df_recent) >= 2:
                start_price = df_recent['Close'].iloc[0]
                end_price = df_recent['Close'].iloc[-1]
                pct_change = ((end_price - start_price) / start_price) * 100
                returns[ticker] = {
                    'name': TOP10_STOCKS.get(ticker, ticker),
                    'start_price': float(start_price),
                    'end_price': float(end_price),
                    'change_pct': float(pct_change),
                    'change_abs': float(end_price - start_price)
                }
    return returns

def main():
    st.title("📈 글로벌 시총 Top10 주가 분석")
    st.markdown("---")
    
    # 사이드바 설정
    st.sidebar.header("⚙️ 설정")
    days = st.sidebar.slider("분석 기간 (일)", min_value=1, max_value=365, value=30)
    
    # 캐시 초기화 버튼
    if st.sidebar.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()
    
    # 데이터 로드
    with st.spinner("주가 데이터를 불러오는 중... (최초 로드 시 시간이 걸릴 수 있습니다)"):
        stock_data = get_stock_data(tuple(TOP10_STOCKS.keys()), days)
    
    if not stock_data:
        st.error("데이터를 불러올 수 없습니다. 잠시 후 '데이터 새로고침' 버튼을 눌러주세요.")
        st.info("💡 Yahoo Finance API의 요청 제한으로 인해 일시적으로 데이터를 가져올 수 없습니다.")
        return
    
    # 로드된 종목 수 표시
    st.sidebar.success(f"✅ {len(stock_data)}/{len(TOP10_STOCKS)} 종목 로드됨")
    
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
    
    available_stocks = [t for t in TOP10_STOCKS.keys() if t in stock_data]
    
    selected_stocks = st.multiselect(
        "종목 선택",
        options=available_stocks,
        default=[best_ticker, worst_ticker] if best_ticker in available_stocks and worst_ticker in available_stocks else available_stocks[:2],
        format_func=lambda x: f"{TOP10_STOCKS[x]} ({x})"
    )
    
    if selected_stocks:
        fig_line = go.Figure()
        
        for ticker in selected_stocks:
            if ticker in stock_data:
                df = stock_data[ticker].tail(days + 1)
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
    display_df.index = [f"{TOP10_STOCKS.get(t, t)} ({t})" for t in display_df.index]
    display_df.columns = ['종목명', '시작가($)', '종가($)', '변동률(%)', '변동액($)']
    display_df = display_df.drop('종목명', axis=1)
    
    display_df['시작가($)'] = display_df['시작가($)'].apply(lambda x: f"${x:.2f}")
    display_df['종가($)'] = display_df['종가($)'].apply(lambda x: f"${x:.2f}")
    display_df['변동률(%)'] = display_df['변동률(%)'].apply(lambda x: f"{x:.2f}%")
    display_df['변동액($)'] = display_df['변동액($)'].apply(lambda x: f"${x:.2f}")
    
    st.dataframe(display_df, use_container_width=True)
    
    # 푸터
    st.markdown("---")
    st.caption("데이터 출처: Yahoo Finance | 시총 순위는 변동될 수 있습니다. | 데이터는 1시간 캐시됩니다.")

if __name__ == "__main__":
    main()
