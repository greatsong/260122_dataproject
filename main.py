import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(
    page_title="글로벌 Top 10 주가 분석",
    page_icon="📈",
    layout="wide"
)

# 글로벌 시총 상위 10개 종목 리스트 (티커 기준, 유동적일 수 있음)
# Apple, Nvidia, Microsoft, Alphabet(Google), Amazon, Meta, TSMC, Berkshire Hathaway, Broadcom, Tesla
TOP_10_TICKERS = {
    'AAPL': 'Apple',
    'NVDA': 'NVIDIA',
    'MSFT': 'Microsoft',
    'GOOGL': 'Alphabet (Google)',
    'AMZN': 'Amazon',
    'META': 'Meta (Facebook)',
    'TSM': 'TSMC',
    'BRK-B': 'Berkshire Hathaway',
    'AVGO': 'Broadcom',
    'TSLA': 'Tesla'
}

@st.cache_data
def load_data(tickers, days):
    """
    yfinance를 이용해 주가 데이터를 가져오는 함수
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 여러 티커의 데이터를 한 번에 다운로드
    data = yf.download(list(tickers.keys()), start=start_date, end=end_date, progress=False)
    
    # 'Close' 컬럼만 추출 (yfinance 버전에 따라 구조가 다를 수 있어 조정)
    if 'Close' in data.columns:
        df_close = data['Close']
    elif 'Adj Close' in data.columns:
        df_close = data['Adj Close']
    else:
        st.error("데이터를 가져오는데 실패했습니다.")
        return pd.DataFrame()
    
    return df_close

def calculate_performance(df):
    """
    기간 내 수익률 계산 함수
    """
    # 시작일과 종료일의 가격 비교 (결측치 제거)
    df = df.dropna()
    if len(df) < 2:
        return pd.Series()
    
    start_price = df.iloc[0]
    end_price = df.iloc[-1]
    
    # 수익률 계산: (종료가 - 시작가) / 시작가 * 100
    performance = ((end_price - start_price) / start_price) * 100
    return performance.sort_values(ascending=False)

# === 사이드바 설정 ===
st.sidebar.header("📊 분석 옵션 설정")
n_days = st.sidebar.slider("분석할 기간 (최근 N일)", min_value=5, max_value=365, value=30)
selected_tickers = st.sidebar.multiselect(
    "분석할 종목 선택", 
    options=list(TOP_10_TICKERS.keys()), 
    default=list(TOP_10_TICKERS.keys()),
    format_func=lambda x: f"{x} ({TOP_10_TICKERS[x]})"
)

# === 메인 화면 ===
st.title(f"📈 글로벌 시총 Top 10: 최근 {n_days}일 주가 분석")
st.markdown("글로벌 리딩 기업들의 최근 주가 흐름을 분석하고 가장 많이 오르거나 떨어진 종목을 찾습니다.")

if not selected_tickers:
    st.warning("분석할 종목을 하나 이상 선택해주세요.")
else:
    # 데이터 로드
    with st.spinner('데이터를 불러오는 중입니다...'):
        df = load_data(TOP_10_TICKERS, n_days)
        
        # 선택된 종목만 필터링
        df_selected = df[selected_tickers]
        
        # 수익률 계산
        performance = calculate_performance(df_selected)

    # === 1. 핵심 지표 (가장 많이 오른/내린 종목) ===
    if not performance.empty:
        best_stock = performance.index[0]
        worst_stock = performance.index[-1]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🚀 최고 상승 종목")
            st.metric(
                label=f"{TOP_10_TICKERS[best_stock]} ({best_stock})", 
                value=f"{df_selected[best_stock].iloc[-1]:.2f} USD",
                delta=f"{performance[best_stock]:.2f}%"
            )
            
        with col2:
            st.subheader("💧 최고 하락(최저 상승) 종목")
            st.metric(
                label=f"{TOP_10_TICKERS[worst_stock]} ({worst_stock})", 
                value=f"{df_selected[worst_stock].iloc[-1]:.2f} USD",
                delta=f"{performance[worst_stock]:.2f}%"
            )

        st.divider()

        # === 2. 수익률 비교 바 차트 (Plotly) ===
        st.subheader(f"📊 종목별 수익률 비교 (최근 {n_days}일)")
        
        colors = ['red' if x >= 0 else 'blue' for x in performance.values]
        
        fig_bar = go.Figure(go.Bar(
            x=performance.index,
            y=performance.values,
            text=[f"{val:.1f}%" for val in performance.values],
            textposition='auto',
            marker_color=colors
        ))
        
        fig_bar.update_layout(
            xaxis_title="종목 (Ticker)",
            yaxis_title="수익률 (%)",
            showlegend=False
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # === 3. 주가 추이 라인 차트 (Plotly) ===
        st.subheader(f"📈 주가 변동 추이")
        
        # 정규화된 그래프 (시작점을 0%로 맞춤) vs 실제 가격 선택
        view_option = st.radio("차트 보기 방식", ["수익률 기준 (%)", "실제 주가 (USD)"], horizontal=True)
        
        if view_option == "수익률 기준 (%)":
            # 시작일 가격 기준 변화율로 변환
            df_normalized = (df_selected / df_selected.iloc[0] - 1) * 100
            fig_line = px.line(df_normalized, x=df_normalized.index, y=df_normalized.columns)
            fig_line.update_layout(yaxis_title="누적 수익률 (%)")
        else:
            fig_line = px.line(df_selected, x=df_selected.index, y=df_selected.columns)
            fig_line.update_layout(yaxis_title="주가 (USD)")

        st.plotly_chart(fig_line, use_container_width=True)
        
        # === 4. 상세 데이터 보기 ===
        with st.expander("데이터 원본 보기"):
            st.dataframe(df_selected.sort_index(ascending=False))
