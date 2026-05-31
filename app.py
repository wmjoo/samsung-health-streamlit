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

# ── 상수 ──────────────────────────────────────────────────────────────────────
PERIOD_OPTIONS = {
    "최근 30일": 30,
    "최근 90일": 90,
    "최근 180일": 180,
    "최근 1년": 365,
    "최근 3년": 365 * 3,
    "최근 5년": 365 * 5,
    "전체": None,
}
PERIOD_DTICK = {
    "최근 30일":  (3 * 24 * 3600000, 24 * 3600000),
    "최근 90일":  (7 * 24 * 3600000, 3 * 24 * 3600000),
    "최근 180일": ("M1", 7 * 24 * 3600000),
    "최근 1년":   ("M1", 7 * 24 * 3600000),
    "최근 3년":   ("M3", "M1"),
    "최근 5년":   ("M3", "M1"),
    "전체":       ("M6", "M1"),
}
COLOR_MIN = "#1c7c3a"
COLOR_MAX = "#a63228"

# ── 파일 업로드 + 글로벌 필터 (사이드바) ─────────────────────────────────────
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
    df = pd.read_csv(StringIO("\n".join(lines[1:])), low_memory=False, index_col=False)
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    numeric_cols = ["weight", "body_fat", "body_fat_mass", "muscle_mass",
                    "skeletal_muscle_mass", "fat_free_mass", "basal_metabolic_rate",
                    "height", "total_body_water"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["weight"] >= 70]
    df = df.dropna(subset=["start_time", "weight"])
    df = df.sort_values("start_time").reset_index(drop=True)
    df["date"] = df["start_time"].dt.date
    df["year_month"] = df["start_time"].dt.to_period("M").astype(str)
    return df


def daily_agg(source: pd.DataFrame, cols: list, func: str = "mean") -> pd.DataFrame:
    valid = [c for c in cols if c in source.columns]
    return (
        source.groupby("date")[valid]
        .agg(func)
        .reset_index()
        .assign(date=lambda d: pd.to_datetime(d["date"]),
                year_month=lambda d: d["date"].dt.to_period("M").astype(str))
    )


df = load_data(uploaded.read())

if df.empty:
    st.error("데이터를 파싱할 수 없습니다. 올바른 Samsung Health 체중 CSV인지 확인하세요.")
    st.stop()

# ── 글로벌 필터 (사이드바, session_state로 상호 배타) ─────────────────────────
all_years = sorted(df["start_time"].dt.year.unique(), reverse=True)
year_options = ["전체"] + [str(y) for y in all_years]

# session_state 초기화
if "filter_period" not in st.session_state:
    st.session_state["filter_period"] = "최근 90일"
if "filter_year" not in st.session_state:
    st.session_state["filter_year"] = "전체"

def on_period_change():
    if st.session_state["_period_select"] != "전체":
        st.session_state["filter_year"] = "전체"
    st.session_state["filter_period"] = st.session_state["_period_select"]

def on_year_change():
    if st.session_state["_year_select"] != "전체":
        st.session_state["filter_period"] = "전체"
    st.session_state["filter_year"] = st.session_state["_year_select"]

with st.sidebar:
    st.divider()
    st.header("🔍 기간 필터")
    st.selectbox(
        "최근 기간",
        options=list(PERIOD_OPTIONS.keys()),
        index=list(PERIOD_OPTIONS.keys()).index(st.session_state["filter_period"]),
        key="_period_select",
        on_change=on_period_change,
    )
    st.selectbox(
        "연도",
        options=year_options,
        index=year_options.index(st.session_state["filter_year"]),
        key="_year_select",
        on_change=on_year_change,
    )

# 필터 적용 → df_f (전 탭 공통)
sel_period = st.session_state["filter_period"]
sel_year   = st.session_state["filter_year"]

if sel_year != "전체":
    df_f = df[df["start_time"].dt.year == int(sel_year)].copy()
    active_filter_label = f"{sel_year}년"
elif PERIOD_OPTIONS[sel_period] is not None:
    cutoff = df["start_time"].max() - timedelta(days=PERIOD_OPTIONS[sel_period])
    df_f = df[df["start_time"] >= cutoff].copy()
    active_filter_label = sel_period
else:
    df_f = df.copy()
    active_filter_label = "전체"

latest = df_f.iloc[-1] if len(df_f) else df.iloc[-1]
first  = df_f.iloc[0]  if len(df_f) else df.iloc[0]

# ── 탭 구성 ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📈 체중 추이", "💪 체성분", "📅 월별 분석", "🗃️ 원시 데이터"])

# ── Tab 1: 체중 추이 ──────────────────────────────────────────────────────────
with tab1:
    col_agg, _ = st.columns([2, 2])
    with col_agg:
        use_median = st.toggle("중앙값 사용 (기본: 평균)", value=False)

    agg_func  = "median" if use_median else "mean"
    agg_label = "중앙값"  if use_median else "평균"

    df_daily = (
        df_f.groupby("date")["weight"]
        .agg(agg_func)
        .reset_index()
        .assign(date=lambda d: pd.to_datetime(d["date"]))
    )

    # 격자 간격: 연도 필터면 월 단위, 기간 필터면 PERIOD_DTICK
    if sel_year != "전체":
        dtick_major, dtick_minor = "M1", 7 * 24 * 3600000
        tick_fmt = "%y-%m"
    else:
        dtick_major, dtick_minor = PERIOD_DTICK[sel_period]
        period_days = PERIOD_OPTIONS[sel_period]
        tick_fmt = "%y-%m-%d" if period_days and period_days <= 90 else "%y-%m"

    MA_LINES = [
        (7,  "7일 MA",  "rgba(255,165,0,0.9)",  True),
        (15, "15일 MA", "rgba(239,85,59,0.9)",  False),
        (30, "30일 MA", "rgba(0,180,100,0.9)",  False),
        (90, "90일 MA", "rgba(99,110,250,0.9)", False),
    ]

    if len(df_daily) > 0:
        idx_min = df_daily["weight"].idxmin()
        idx_max = df_daily["weight"].idxmax()
        d_min = df_daily.loc[idx_min]
        d_max = df_daily.loc[idx_max]
        mask_normal = ~df_daily.index.isin([idx_min, idx_max])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_daily.loc[mask_normal, "date"],
            y=df_daily.loc[mask_normal, "weight"],
            mode="markers",
            name=f"일별 {agg_label}",
            marker=dict(size=6, color="rgba(100,100,110,0.6)"),
            hovertemplate="%{x|%Y-%m-%d}<br>체중: %{y:.2f} kg<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[d_min["date"]], y=[d_min["weight"]],
            mode="markers", name="최저",
            marker=dict(size=11, color=COLOR_MIN, line=dict(color=COLOR_MIN, width=1.5)),
            hovertemplate=f"최저: {d_min['weight']:.2f} kg<br>{d_min['date'].strftime('%Y-%m-%d')}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[d_max["date"]], y=[d_max["weight"]],
            mode="markers", name="최고",
            marker=dict(size=11, color=COLOR_MAX, line=dict(color=COLOR_MAX, width=1.5)),
            hovertemplate=f"최고: {d_max['weight']:.2f} kg<br>{d_max['date'].strftime('%Y-%m-%d')}<extra></extra>",
        ))

        ts = df_daily.set_index("date")["weight"]
        for ma_d, ma_name, ma_color, vis in MA_LINES:
            ma = ts.rolling(f"{ma_d}D", min_periods=1).mean().reset_index()
            fig.add_trace(go.Scatter(
                x=ma["date"], y=ma["weight"],
                mode="lines", name=ma_name,
                visible=True if vis else "legendonly",
                line=dict(color=ma_color, width=2),
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{ma_name}: %{{y:.2f}} kg<extra></extra>",
            ))

        annotations = [
            dict(x=d_min["date"], y=d_min["weight"],
                 text=f"<b>{d_min['weight']:.1f} kg</b>",
                 showarrow=True, arrowhead=2, arrowcolor=COLOR_MIN,
                 ax=0, ay=30, font=dict(color=COLOR_MIN, size=12)),
            dict(x=d_max["date"], y=d_max["weight"],
                 text=f"<b>{d_max['weight']:.1f} kg</b>",
                 showarrow=True, arrowhead=2, arrowcolor=COLOR_MAX,
                 ax=0, ay=-30, font=dict(color=COLOR_MAX, size=12)),
        ]

        fig.update_layout(
            title=f"체중 변화 추이 ({active_filter_label} · 일별 {agg_label})",
            annotations=annotations,
            xaxis_title=None,
            yaxis_title="체중 (kg)",
            hovermode="x unified",
            height=480,
            plot_bgcolor="white",
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
            xaxis=dict(
                showgrid=True, gridcolor="rgba(150,150,150,0.4)", gridwidth=1,
                dtick=dtick_major, tickformat=tick_fmt,
                minor=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)",
                           gridwidth=0.5, dtick=dtick_minor),
                showline=True, linecolor="rgba(100,100,100,0.5)",
            ),
            yaxis=dict(
                showgrid=True, gridcolor="rgba(150,150,150,0.4)", gridwidth=1,
                minor=dict(showgrid=True, gridcolor="rgba(200,200,200,0.25)", gridwidth=0.5),
                showline=True, linecolor="rgba(100,100,100,0.5)",
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.success(f"**최저 체중**: {d_min['weight']:.2f} kg — {d_min['date'].strftime('%Y-%m-%d')}")
        with col_r:
            st.error(f"**최고 체중**: {d_max['weight']:.2f} kg — {d_max['date'].strftime('%Y-%m-%d')}")

    st.divider()
    st.subheader("📊 요약")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("현재 체중", f"{latest['weight']:.1f} kg",
                f"{latest['weight'] - first['weight']:+.1f} kg")
    col2.metric("최저 체중", f"{df_f['weight'].min():.1f} kg")
    col3.metric("최고 체중", f"{df_f['weight'].max():.1f} kg")
    if pd.notna(latest.get("body_fat")):
        col4.metric("현재 체지방률", f"{latest['body_fat']:.1f} %")
    else:
        col4.metric("체지방률", "데이터 없음")
    col5.metric("기간 기록", f"{len(df_f):,} 건")


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
        st.info("체성분 데이터가 충분하지 않습니다.")
    else:
        selected = st.multiselect(
            "표시할 항목 선택",
            options=list(available.keys()),
            default=list(available.keys())[:3],
            format_func=lambda k: available[k],
        )

        if selected:
            df_comp = daily_agg(df_f, selected)
            colors = px.colors.qualitative.Plotly

            fig2 = make_subplots(
                rows=len(selected), cols=1,
                shared_xaxes=True,
                subplot_titles=[available[k] for k in selected],
                vertical_spacing=0.06,
            )
            for i, key in enumerate(selected, 1):
                sub = df_comp[["date", key]].dropna()
                fig2.add_trace(
                    go.Scatter(
                        x=sub["date"], y=sub[key],
                        mode="lines+markers",
                        name=available[key],
                        line=dict(color=colors[(i - 1) % len(colors)]),
                        marker=dict(size=7),
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
                title=f"체성분 추이 ({active_filter_label})",
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
        df_box = daily_agg(df_f, list(available_box.keys()))
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
                        y=vals, name=month, marker_color=color,
                        boxmean=True, showlegend=False,
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
        fig_box.update_xaxes(
            showgrid=True, gridcolor="rgba(150,150,150,0.5)", gridwidth=1,
            tickangle=-45,
            showline=True, linecolor="rgba(100,100,100,0.5)",
            row=n, col=1,
        )
        fig_box.update_layout(
            title=f"월별 체성분 분포 ({active_filter_label})",
            height=320 * n,
            plot_bgcolor="white",
        )
        st.plotly_chart(fig_box, use_container_width=True)


# ── Tab 4: 원시 데이터 ────────────────────────────────────────────────────────
with tab4:
    st.info("이 데이터는 현재 세션에서만 존재하며 페이지를 닫으면 사라집니다.")
    agg_cols = ["weight", "body_fat", "body_fat_mass", "muscle_mass",
                "skeletal_muscle_mass", "fat_free_mass", "basal_metabolic_rate"]
    df_raw_daily = daily_agg(df_f, agg_cols).drop(columns="year_month")
    df_raw_daily = df_raw_daily.sort_values("date", ascending=False)
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
