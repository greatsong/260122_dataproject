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
def fetch_prices_batch(tickers: list
