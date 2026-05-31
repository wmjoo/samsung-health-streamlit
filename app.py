import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from io import StringIO
from datetime import timedelta

st.set_page_config(
    page_title="Samsung Health - 체중 분석",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Samsung Health 체중 데이터 분석")
st.caption("데이터는 업로드 즉시 브라우저 세션에서만 처리되며, 서버에 저장되지 않습니다.")

# ── 공통 격자선 레이아웃 ──────────────────────────────────────────────────────
GRID = dict(
    xaxis=dict(
        showgrid=True,
        gridcolor="rgba(200,200,200,0.4)",
        gridwidth=1,
        dtick="M1",          # x축: 1개월 간격 격자
        tickformat="%y-%m",
        minor=dict(
            showgrid=True,
            gridcolor="rgba(200,200,200,0.2)",
            gridwidth=0.5,
            dtick=7 * 24 * 3600000,  # 1주 단위 세밀 격자 (밀리초)
        ),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(200,200,200,0.5)",
        gridwidth=1,
    ),
    plot_bgcolor="white",
)

# ── 파일 업로드 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 데이터 업로드")
    st.info(
        "Samsung Health에서 내보낸 **체중 CSV 파일**을 업로드하세요.\n\n"
        "`com.samsung.health.weight.*.csv`"
    )
    uploaded = st.file_uploader("CSV 파일 선택", type="csv", label_visibility="collapsed")
    st.divider()
    st.markdown("**📌 데이터 내보내기 방법**")
    st.markdown(
        "1. Samsung Health 앱 → 설정\n"
        "2. 개인 데이터 내보내기\n"
        "3. 압축 해제 후 체중 CSV 업로드"
    )

if uploaded is None:
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            """
            ### 👈 왼쪽에서 CSV 파일을 업로드하세요

            업로드한 데이터는 **이 브라우저 세션에서만** 임시로 사용되며,
            서버에 저장되거나 전송되지 않습니다.
            """
        )
    st.stop()


# ── 데이터 파싱 ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="데이터 분석 중...")
def load_data(content: bytes) -> pd.DataFrame:
    text = content.decode("utf-8-sig")
    lines = text.splitlines()

    # 삼성헬스 CSV: 1행은 메타데이터, 2행부터 실제 헤더
    # 데이터 행이 헤더보다 열이 1개 많아 index_col=False 필요
    df = pd.read_csv(StringIO("\n".join(lines[1:])), low_memory=False, index_col=False)

    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")

    numeric_cols = ["weight", "body_fat", "body_fat_mass", "muscle_mass",
                    "skeletal_muscle_mass", "fat_free_mass", "basal_metabolic_rate",
                    "height", "total_body_water"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 비정상 체중값 제거 (70kg 미만)
    df = df[df["weight"] >= 70]

    df = df.dropna(subset=["start_time", "weight"])
    df = df.sort_values("start_time").reset_index(drop=True)
    df["date"] = df["start_time"].dt.date
    df["year_month"] = df["start_time"].dt.to_period("M").astype(str)
    return df


def daily_agg(df: pd.DataFrame, cols: list, func: str = "mean") -> pd.DataFrame:
    """날짜별 집계 (평균 or 중앙값). date 컬럼 + 지정 컬럼만 반환."""
    return (
        df.groupby("date")[cols]
        .agg(func)
        .reset_index()
        .assign(date=lambda d: pd.to_datetime(d["date"]),
                year_month=lambda d: d["date"].dt.to_period("M").astype(str))
    )


df = load_data(uploaded.read())

if df.empty:
    st.error("데이터를 파싱할 수 없습니다. 올바른 Samsung Health 체중 CSV인지 확인하세요.")
    st.stop()

# ── 요약 지표 (전체 데이터 기준) ──────────────────────────────────────────────
latest = df.iloc[-1]
first = df.iloc[0]

st.subheader("📊 요약")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("현재 체중", f"{latest['weight']:.1f} kg",
            f"{latest['weight'] - first['weight']:+.1f} kg")
col2.metric("최저 체중", f"{df['weight'].min():.1f} kg")
col3.metric("최고 체중", f"{df['weight'].max():.1f} kg")
if pd.notna(latest.get("body_fat")):
    col4.metric("현재 체지방률", f"{latest['body_fat']:.1f} %")
else:
    col4.metric("체지방률", "데이터 없음")
col5.metric("전체 기록", f"{len(df):,} 건")

st.divider()

# ── 탭 구성 ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📈 체중 추이", "💪 체성분", "📅 월별 분석", "🗃️ 원시 데이터"])

# ── Tab 1: 체중 추이 ──────────────────────────────────────────────────────────
with tab1:
    PERIOD_OPTIONS = {
        "최근 30일": 30,
        "최근 90일": 90,
        "최근 180일": 180,
        "최근 1년": 365,
        "최근 3년": 365 * 3,
        "최근 5년": 365 * 5,
        "전체": None,
    }
    # 기간에 따라 x축 격자 간격 자동 조정
    PERIOD_DTICK = {
        "최근 30일":  (3 * 24 * 3600000, 24 * 3600000),      # 3일/1일
        "최근 90일":  (7 * 24 * 3600000, 3 * 24 * 3600000),  # 1주/3일
        "최근 180일": ("M1", 7 * 24 * 3600000),               # 1개월/1주
        "최근 1년":   ("M1", 7 * 24 * 3600000),
        "최근 3년":   ("M3", "M1"),
        "최근 5년":   ("M3", "M1"),
        "전체":       ("M6", "M1"),
    }

    col_period, col_agg = st.columns([2, 2])
    with col_period:
        period_label = st.selectbox(
            "기간",
            options=list(PERIOD_OPTIONS.keys()),
            index=1,
        )
    with col_agg:
        use_median = st.toggle("중앙값 사용 (기본: 평균)", value=False)

    agg_func = "median" if use_median else "mean"
    agg_label = "중앙값" if use_median else "평균"

    period_days = PERIOD_OPTIONS[period_label]
    if period_days is not None:
        cutoff = df["start_time"].max() - timedelta(days=period_days)
        df_t = df[df["start_time"] >= cutoff].copy()
    else:
        df_t = df.copy()

    # 일별 집계 (평균 or 중앙값)
    df_daily = (
        df_t.groupby("date")["weight"]
        .agg(agg_func)
        .reset_index()
    )
    df_daily["date"] = pd.to_datetime(df_daily["date"])

    dtick_major, dtick_minor = PERIOD_DTICK[period_label]

    MA_LINES = [
        (7,  "7일 MA",  "rgba(255,165,0,0.9)"),
        (15, "15일 MA", "rgba(239,85,59,0.9)"),
        (30, "30일 MA", "rgba(0,180,100,0.9)"),
        (90, "90일 MA", "rgba(99,110,250,0.9)"),
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_daily["date"], y=df_daily["weight"],
        mode="markers",
        name=f"일별 {agg_label}",
        marker=dict(size=4, color="rgba(160,160,180,0.5)"),
        hovertemplate="%{x|%Y-%m-%d}<br>체중: %{y:.2f} kg<extra></extra>",
    ))

    if len(df_daily) > 0:
        ts = df_daily.set_index("date")["weight"]
        for ma_d, ma_name, ma_color in MA_LINES:
            ma = ts.rolling(f"{ma_d}D", min_periods=1).mean().reset_index()
            fig.add_trace(go.Scatter(
                x=ma["date"], y=ma["weight"],
                mode="lines",
                name=ma_name,
                line=dict(color=ma_color, width=2),
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{ma_name}: %{{y:.2f}} kg<extra></extra>",
            ))

    fig.update_layout(
        title=f"체중 변화 추이 ({period_label} · 일별 {agg_label})",
        xaxis_title=None,
        yaxis_title="체중 (kg)",
        hovermode="x unified",
        height=480,
        plot_bgcolor="white",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5,
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(150,150,150,0.4)",
            gridwidth=1,
            dtick=dtick_major,
            tickformat="%y-%m-%d" if period_days and period_days <= 90 else "%y-%m",
            minor=dict(
                showgrid=True,
                gridcolor="rgba(200,200,200,0.25)",
                gridwidth=0.5,
                dtick=dtick_minor,
            ),
            showline=True,
            linecolor="rgba(100,100,100,0.5)",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(150,150,150,0.4)",
            gridwidth=1,
            minor=dict(
                showgrid=True,
                gridcolor="rgba(200,200,200,0.25)",
                gridwidth=0.5,
            ),
            showline=True,
            linecolor="rgba(100,100,100,0.5)",
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    if len(df_daily) > 0:
        col_l, col_r = st.columns(2)
        with col_l:
            r = df_daily.loc[df_daily["weight"].idxmin()]
            st.success(f"**최저 체중**: {r['weight']:.2f} kg — {r['date'].strftime('%Y-%m-%d')}")
        with col_r:
            r = df_daily.loc[df_daily["weight"].idxmax()]
            st.error(f"**최고 체중**: {r['weight']:.2f} kg — {r['date'].strftime('%Y-%m-%d')}")


# ── Tab 2: 체성분 ─────────────────────────────────────────────────────────────
with tab2:
    comp_cols = {
        "body_fat": "체지방률 (%)",
        "body_fat_mass": "체지방량 (kg)",
        "muscle_mass": "근육량 (kg)",
        "skeletal_muscle_mass": "골격근량 (kg)",
        "fat_free_mass": "제지방량 (kg)",
        "total_body_water": "체수분 (kg)",
    }
    available = {k: v for k, v in comp_cols.items() if k in df.columns and df[k].notna().sum() > 5}

    if not available:
        st.info("체성분 데이터가 충분하지 않습니다. 상세 측정 기기의 데이터를 포함한 파일을 업로드하세요.")
    else:
        selected = st.multiselect(
            "표시할 항목 선택",
            options=list(available.keys()),
            default=list(available.keys())[:3],
            format_func=lambda k: available[k],
        )

        if selected:
            # 일별 집계
            df_comp = daily_agg(df, [k for k in selected if k in df.columns])

            fig2 = make_subplots(
                rows=len(selected), cols=1,
                shared_xaxes=True,
                subplot_titles=[available[k] for k in selected],
                vertical_spacing=0.06,
            )
            colors = px.colors.qualitative.Plotly

            for i, key in enumerate(selected, 1):
                sub = df_comp[["date", key]].dropna()
                fig2.add_trace(
                    go.Scatter(
                        x=sub["date"], y=sub[key],
                        mode="lines+markers",
                        name=available[key],
                        line=dict(color=colors[(i - 1) % len(colors)]),
                        marker=dict(size=4),
                        hovertemplate=f"%{{x|%Y-%m-%d}}<br>{available[key]}: %{{y:.2f}}<extra></extra>",
                    ),
                    row=i, col=1,
                )
                fig2.update_xaxes(
                    showgrid=True, gridcolor="rgba(150,150,150,0.4)", gridwidth=1,
                    dtick="M3", tickformat="%y-%m",
                    minor=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)",
                               gridwidth=0.5, dtick="M1"),
                    showline=True, linecolor="rgba(100,100,100,0.5)",
                    row=i, col=1,
                )
                fig2.update_yaxes(
                    showgrid=True, gridcolor="rgba(150,150,150,0.4)", gridwidth=1,
                    minor=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)", gridwidth=0.5),
                    showline=True, linecolor="rgba(100,100,100,0.5)",
                    row=i, col=1,
                )

            fig2.update_layout(
                height=300 * len(selected),
                showlegend=False,
                hovermode="x unified",
                plot_bgcolor="white",
            )
            st.plotly_chart(fig2, use_container_width=True)


# ── Tab 3: 월별 분석 (박스플롯 서브플롯) ─────────────────────────────────────
with tab3:
    BOX_COLS = {
        "weight": ("체중 (kg)", "rgba(99,110,250,0.7)"),
        "body_fat": ("체지방률 (%)", "rgba(239,85,59,0.7)"),
        "skeletal_muscle_mass": ("골격근량 (kg)", "rgba(0,204,150,0.7)"),
    }
    available_box = {k: v for k, v in BOX_COLS.items()
                     if k in df.columns and df[k].notna().sum() > 5}

    if available_box:
        n = len(available_box)
        # 일별 집계 후 월별 박스플롯 — 하루에 여러 번 측정해도 1일 1값
        box_keys = [k for k in available_box]
        df_box = daily_agg(df, [k for k in box_keys if k in df.columns])
        all_months = sorted(df_box["year_month"].unique())

        fig_box = make_subplots(
            rows=n, cols=1,
            shared_xaxes=True,
            subplot_titles=[v[0] for v in available_box.values()],
            vertical_spacing=0.06,
        )

        for row, (col_key, (label, color)) in enumerate(available_box.items(), 1):
            sub = df_box[["year_month", col_key]].dropna()
            for month in all_months:
                vals = sub.loc[sub["year_month"] == month, col_key]
                fig_box.add_trace(
                    go.Box(
                        y=vals,
                        name=month,
                        marker_color=color,
                        boxmean=True,
                        showlegend=False,
                        hovertemplate=f"{month}<br>{label}: %{{y:.2f}}<extra></extra>",
                    ),
                    row=row, col=1,
                )
            fig_box.update_yaxes(
                title_text=label,
                showgrid=True, gridcolor="rgba(150,150,150,0.4)", gridwidth=1,
                minor=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)", gridwidth=0.5),
                showline=True, linecolor="rgba(100,100,100,0.5)",
                row=row, col=1,
            )

        # x축은 맨 아래 행만 표시
        fig_box.update_xaxes(
            showgrid=True, gridcolor="rgba(150,150,150,0.5)", gridwidth=1,
            tickangle=-45,
            showline=True, linecolor="rgba(100,100,100,0.5)",
            row=n, col=1,
        )
        fig_box.update_layout(
            title="월별 체성분 분포",
            height=320 * n,
            plot_bgcolor="white",
        )
        st.plotly_chart(fig_box, use_container_width=True)


# ── Tab 4: 원시 데이터 ────────────────────────────────────────────────────────
with tab4:
    st.info("이 데이터는 현재 세션에서만 존재하며 페이지를 닫으면 사라집니다.")
    agg_cols = ["weight", "body_fat", "body_fat_mass", "muscle_mass",
                "skeletal_muscle_mass", "fat_free_mass", "basal_metabolic_rate"]
    valid_agg_cols = [c for c in agg_cols if c in df.columns]
    df_raw_daily = daily_agg(df, valid_agg_cols).drop(columns="year_month")
    df_raw_daily = df_raw_daily.sort_values("date", ascending=False)
    # 전체가 결측치인 컬럼 제거
    df_raw_daily = df_raw_daily.dropna(axis=1, how="all")
    df_raw_daily.columns = [c if c != "date" else "날짜" for c in df_raw_daily.columns]

    st.dataframe(df_raw_daily, use_container_width=True, hide_index=True)
    csv_export = df_raw_daily.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ 일별 집계 CSV 다운로드",
        csv_export,
        file_name="weight_daily.csv",
        mime="text/csv",
    )
