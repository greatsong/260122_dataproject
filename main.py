# main.py
import glob
from pathlib import Path

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


st.set_page_config(page_title="최근 10일 기온 시각화", layout="wide")
st.title("최근 10일 기온 시각화 (matplotlib / Streamlit / Altair)")


def _detect_skiprows_for_kma_style(file_path: str, encoding: str = "cp949") -> int:
    """
    '기온분석'처럼 상단에 메타정보가 있고,
    헤더가 '날짜,지점,평균기온(℃),최저기온(℃),최고기온(℃)' 형태로 나오는 CSV를 자동 감지.
    헤더 라인 인덱스를 찾아 skiprows로 사용.
    """
    try:
        text = Path(file_path).read_bytes().decode(encoding, errors="ignore")
    except Exception:
        return 0

    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines[:200]):  # 앞부분만 스캔
        if ("날짜" in line) and ("," in line) and ("기온" in line):
            header_idx = i
            break

    return header_idx if header_idx is not None else 0


@st.cache_data(show_spinner=False)
def load_data(file_path: str) -> pd.DataFrame:
    # 인코딩 후보를 순서대로 시도
    encodings = ["cp949", "euc-kr", "utf-8", "latin1"]

    last_err = None
    for enc in encodings:
        try:
            skiprows = _detect_skiprows_for_kma_style(file_path, encoding=enc)
            df = pd.read_csv(file_path, encoding=enc, skiprows=skiprows)
            # 컬럼명/문자열 정리
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            last_err = e

    raise RuntimeError(f"CSV를 읽지 못했습니다. (마지막 오류: {last_err})")


# --- 파일 선택 (같은 폴더에 있다고 가정) ---
DEFAULT_FILE = "ta_20260122174530.csv"

csv_candidates = sorted(glob.glob("*.csv"))
if DEFAULT_FILE not in csv_candidates and csv_candidates:
    default_index = 0
elif DEFAULT_FILE in csv_candidates:
    default_index = csv_candidates.index(DEFAULT_FILE)
else:
    default_index = None

st.sidebar.header("데이터 파일")
if not csv_candidates:
    st.error("현재 폴더에서 CSV 파일을 찾지 못했어요. (예: ta_20260122174530.csv 를 main.py와 같은 폴더에 두세요)")
    st.stop()

file_path = st.sidebar.selectbox(
    "사용할 CSV 선택",
    options=csv_candidates,
    index=default_index if default_index is not None else 0,
)

df = load_data(file_path)

# --- 날짜 컬럼 찾기 ---
date_col = None
for cand in ["날짜", "date", "Date", "DATE"]:
    if cand in df.columns:
        date_col = cand
        break

if date_col is None:
    # 혹시 첫 컬럼이 날짜일 수 있으니 검사
    first_col = df.columns[0]
    date_col = first_col

# 날짜 파싱
df[date_col] = df[date_col].astype(str).str.strip()
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

df = df.dropna(subset=[date_col]).sort_values(date_col)

# --- 기온 컬럼 찾기 ---
# (기상청 '기온분석' CSV 기준: 평균기온(℃), 최저기온(℃), 최고기온(℃))
temp_candidates = ["평균기온(℃)", "최저기온(℃)", "최고기온(℃)", "평균기온", "최저기온", "최고기온"]
temp_cols = [c for c in temp_candidates if c in df.columns]

# 숫자 변환
for c in temp_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

if not temp_cols:
    # fallback: 숫자형 컬럼 중 앞에서 몇 개를 온도로 간주
    numeric_cols = [c for c in df.columns if c != date_col]
    # 숫자 변환 시도
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    numeric_cols = [c for c in numeric_cols if pd.api.types.is_numeric_dtype(df[c])]
    temp_cols = numeric_cols[:3]  # 최대 3개만
    if not temp_cols:
        st.error("기온(숫자) 컬럼을 찾지 못했어요. CSV 컬럼명을 확인해 주세요.")
        st.write("컬럼 목록:", list(df.columns))
        st.stop()

# 최근 10일 데이터
recent = df.tail(10).copy()

st.subheader("최근 10일 데이터")
st.dataframe(recent[[date_col] + temp_cols], use_container_width=True)

left, right = st.columns([1, 1])

with left:
    st.markdown("### 1) matplotlib")
    fig, ax = plt.subplots()
    for c in temp_cols:
        ax.plot(recent[date_col], recent[c], marker="o", label=c)
    ax.set_xlabel("날짜")
    ax.set_ylabel("기온")
    ax.legend()
    ax.grid(True, alpha=0.3)
    st.pyplot(fig, clear_figure=True)

with right:
    st.markdown("### 2) Streamlit 기본 그래프")
    chart_df = recent.set_index(date_col)[temp_cols]
    st.line_chart(chart_df)

st.markdown("### 3) Altair")
melted = recent[[date_col] + temp_cols].melt(id_vars=[date_col], var_name="구분", value_name="기온")
alt_chart = (
    alt.Chart(melted)
    .mark_line(point=True)
    .encode(
        x=alt.X(f"{date_col}:T", title="날짜"),
        y=alt.Y("기온:Q", title="기온"),
        color=alt.Color("구분:N", title="구분"),
        tooltip=[alt.Tooltip(f"{date_col}:T", title="날짜"), alt.Tooltip("구분:N"), alt.Tooltip("기온:Q")],
    )
    .properties(height=380)
)
st.altair_chart(alt_chart, use_container_width=True)

st.caption("※ CSV가 '기온분석' 형식(상단 메타정보 포함)이어도 자동으로 헤더 라인을 찾아 읽도록 처리했습니다.")
