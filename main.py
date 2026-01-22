# main.py
import os
import glob
from io import StringIO

import pandas as pd
import streamlit as st

import matplotlib.pyplot as plt
import altair as alt
import plotly.express as px


st.set_page_config(page_title="최근 10일 기온 시각화", layout="wide")
st.title("최근 10일 동안의 기온 (matplotlib / Streamlit / Altair / Plotly)")


def find_header_row(csv_path: str, encoding_candidates=("utf-8", "cp949", "euc-kr")):
    """
    CSV 앞부분에 설명행이 섞여있는(예: 기온분석) 파일에서
    실제 헤더(예: '날짜,지점,평균기온(℃),...')가 있는 줄 번호를 찾는다.
    """
    for enc in encoding_candidates:
        try:
            with open(csv_path, "r", encoding=enc, errors="strict") as f:
                for i in range(0, 200):  # 앞 200줄만 탐색
                    line = f.readline()
                    if not line:
                        break
                    # 헤더 후보 조건
                    if ("날짜" in line) and ("," in line) and ("기온" in line):
                        return i, enc
        except UnicodeDecodeError:
            continue

    # 못 찾으면 그래도 읽어보기(가장 흔한 인코딩 후보로)
    return 0, "utf-8"


@st.cache_data(show_spinner=False)
def load_temperature_csv(csv_path: str) -> pd.DataFrame:
    header_row, enc = find_header_row(csv_path)
    df = pd.read_csv(csv_path, encoding=enc, skiprows=header_row)

    # 첫 컬럼(날짜)에 탭이 붙는 경우가 있어 정리
    date_col = None
    for c in df.columns:
        if "날짜" in str(c):
            date_col = c
            break
    if date_col is None:
        raise ValueError("날짜 컬럼을 찾지 못했습니다. (컬럼명에 '날짜'가 포함되어야 합니다)")

    df[date_col] = (
        df[date_col]
        .astype(str)
        .str.replace("\t", "", regex=False)
        .str.strip()
    )
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    # 숫자 컬럼 정리
    for c in df.columns:
        if c == date_col:
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


# --- 데이터 파일 선택 ---
csv_files = sorted(glob.glob("*.csv"))
if not csv_files:
    st.error("현재 폴더에서 CSV 파일을 찾지 못했습니다. main.py와 같은 폴더에 CSV를 넣어주세요.")
    st.stop()

chosen = st.selectbox("사용할 CSV 파일", csv_files, index=0)
df = load_temperature_csv(chosen)

# --- 컬럼 선택 ---
date_col = next(c for c in df.columns if "날짜" in str(c))
temp_candidates = [c for c in df.columns if ("기온" in str(c)) and (c != date_col)]

if not temp_candidates:
    st.error("기온 관련 컬럼을 찾지 못했습니다. (컬럼명에 '기온'이 포함되어야 합니다)")
    st.stop()

default_cols = [c for c in temp_candidates if "평균" in str(c)] or temp_candidates[:1]
selected_cols = st.multiselect("그래프에 표시할 기온 컬럼", temp_candidates, default=default_cols)

if not selected_cols:
    st.warning("표시할 컬럼을 1개 이상 선택해주세요.")
    st.stop()

# --- 최근 10일 데이터 ---
df_10 = df[[date_col] + selected_cols].dropna(subset=[date_col]).sort_values(date_col).tail(10)
df_10 = df_10.reset_index(drop=True)

# --- 요약 ---
latest = df_10.iloc[-1]
st.subheader("요약")
cols = st.columns(min(4, len(selected_cols) + 1))
cols[0].metric("마지막 날짜", latest[date_col].date().isoformat())
for i, c in enumerate(selected_cols, start=1):
    val = latest[c]
    cols[i].metric(str(c), "결측" if pd.isna(val) else f"{val:.1f}")

with st.expander("최근 10일 데이터 보기"):
    st.dataframe(df_10, use_container_width=True)

# =========================
# 1) matplotlib
# =========================
st.header("1) matplotlib")
fig, ax = plt.subplots()
for c in selected_cols:
    ax.plot(df_10[date_col], df_10[c], marker="o", label=str(c))
ax.set_xlabel("날짜")
ax.set_ylabel("기온")
ax.set_title("최근 10일 기온 (matplotlib)")
ax.legend()
ax.grid(True, alpha=0.3)
fig.autofmt_xdate()
st.pyplot(fig, use_container_width=True)

# =========================
# 2) Streamlit 기본 그래프
# =========================
st.header("2) Streamlit 기본 그래프 (st.line_chart)")
chart_df = df_10.set_index(date_col)[selected_cols]
st.line_chart(chart_df)

# =========================
# 3) Altair
# =========================
st.header("3) Altair")
long_df = df_10.melt(id_vars=[date_col], value_vars=selected_cols, var_name="구분", value_name="기온")
alt_chart = (
    alt.Chart(long_df)
    .mark_line(point=True)
    .encode(
        x=alt.X(f"{date_col}:T", title="날짜"),
        y=alt.Y("기온:Q", title="기온"),
        color=alt.Color("구분:N", title="컬럼"),
        tooltip=[alt.Tooltip(f"{date_col}:T", title="날짜"), alt.Tooltip("구분:N"), alt.Tooltip("기온:Q", format=".1f")],
    )
    .properties(height=380)
    .interactive()
)
st.altair_chart(alt_chart, use_container_width=True)

# =========================
# 4) Plotly
# =========================
st.header("4) Plotly")
plotly_fig = px.line(
    df_10,
    x=date_col,
    y=selected_cols,
    markers=True,
    title="최근 10일 기온 (Plotly)"
)
plotly_fig.update_layout(xaxis_title="날짜", yaxis_title="기온")
st.plotly_chart(plotly_fig, use_container_width=True)
