from __future__ import annotations

from pathlib import Path
import tempfile

import altair as alt
import pandas as pd
import streamlit as st

from dart_credit_evaluator import (
    BUILT_IN_API_KEY,
    build_red_flag_rows,
    build_summary_rows,
    parse_company_names,
    run_multi_company_analysis,
    search_company_candidates,
    write_workbook,
    year_range,
)


APP_TITLE = "OpenDART 예비 재무 스크리닝"


def get_api_key() -> str:
    if "DART_API_KEY" in st.secrets:
        return st.secrets["DART_API_KEY"]
    return BUILT_IN_API_KEY


def candidate_option_label(candidate: dict) -> str:
    stock = candidate.get("stock_code") or "비상장"
    listed = "상장" if candidate.get("listed") else "비상장/기타"
    return f"{candidate['company']} | 종목코드 {stock} | 고유번호 {candidate['corp_code']} | {listed}"


def resolve_selected_companies(query_candidates: list[tuple[str, list[dict]]]) -> tuple[list[dict], list[dict]]:
    selected_companies = []
    preview_rows = []

    for index, (company_name, candidates) in enumerate(query_candidates, start=1):
        st.markdown(f"**{index}. 입력 회사명:** `{company_name}`")
        if not candidates:
            st.warning("검색 결과가 없습니다.")
            preview_rows.append(
                {
                    "입력회사명": company_name,
                    "선택회사": "-",
                    "종목코드": "-",
                    "고유번호": "-",
                    "비고": "검색 결과 없음",
                }
            )
            continue

        options = [candidate_option_label(candidate) for candidate in candidates]
        selected_label = st.selectbox(
            f"{company_name} 후보 선택",
            options=options,
            index=0,
            key=f"dart_company_match_{index}_{company_name}",
            label_visibility="collapsed",
        )
        selected_candidate = candidates[options.index(selected_label)]
        selected_companies.append(
            {
                "input_company": company_name,
                "company": selected_candidate["company"],
                "corp_code": selected_candidate["corp_code"],
                "stock_code": selected_candidate.get("stock_code") or "",
                "modify_date": selected_candidate.get("modify_date", ""),
            }
        )
        preview_rows.append(
            {
                "입력회사명": company_name,
                "선택회사": selected_candidate["company"],
                "종목코드": selected_candidate.get("stock_code") or "-",
                "고유번호": selected_candidate["corp_code"],
                "비고": "사용자 선택",
            }
        )
        with st.expander(f"{company_name} 후보 상세", expanded=False):
            st.dataframe(
                [
                    {
                        "회사명": candidate["company"],
                        "종목코드": candidate.get("stock_code") or "-",
                        "고유번호": candidate["corp_code"],
                        "수정일": candidate.get("modify_date") or "-",
                        "상장여부": "상장" if candidate.get("listed") else "비상장/기타",
                    }
                    for candidate in candidates
                ],
                width="stretch",
                hide_index=True,
            )

    if preview_rows:
        st.subheader("선택 요약")
        st.dataframe(preview_rows, width="stretch", hide_index=True)

    return selected_companies, preview_rows


def run_screening(api_key: str, selected_companies: list[dict], start_year: int, end_year: int):
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "opendart_screening.xlsx"
        analysis = run_multi_company_analysis(api_key, selected_companies, year_range(start_year, end_year))
        write_workbook(analysis, output_path)
        workbook_binary = output_path.read_bytes()
    return analysis, workbook_binary


def build_dashboard_frames(analysis: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    results = analysis["results"]
    if not results:
        return pd.DataFrame(), pd.DataFrame()

    metric_rows = []
    flag_rows = []
    for result in sorted(results, key=lambda item: (item.company, item.year)):
        severe_count = sum(
            1 for flag in (result.red_flags or [])
            if any(token in flag for token in ("200% 이상", "1배 미만", "음수", "5배를 초과"))
        )
        metric_rows.append(
            {
                "회사명": result.company,
                "입력회사명": result.input_company,
                "사업연도": result.year,
                "매출액(억원)": (result.metrics.get("revenue") or 0) / 100000000 if result.metrics.get("revenue") is not None else None,
                "영업이익률(%)": (result.metrics.get("operating_margin") or 0) * 100 if result.metrics.get("operating_margin") is not None else None,
                "부채비율(%)": (result.metrics.get("debt_ratio") or 0) * 100 if result.metrics.get("debt_ratio") is not None else None,
                "영업현금흐름(억원)": (result.metrics.get("operating_cash_flow") or 0) / 100000000 if result.metrics.get("operating_cash_flow") is not None else None,
                "계약자산/매출액(%)": (result.metrics.get("contract_assets_to_revenue") or 0) * 100 if result.metrics.get("contract_assets_to_revenue") is not None else None,
            }
        )
        flag_rows.append(
            {
                "회사명": result.company,
                "사업연도": result.year,
                "적색신호수": len(result.red_flags or []),
                "중요적색신호수": severe_count,
            }
        )
    return pd.DataFrame(metric_rows), pd.DataFrame(flag_rows)


def line_chart(metric_df: pd.DataFrame, column: str, title: str, y_title: str):
    chart_df = metric_df.dropna(subset=[column])
    if chart_df.empty:
        st.info(f"{title} 차트에 표시할 데이터가 없습니다.")
        return
    chart = alt.Chart(chart_df).mark_line(point=True).encode(
        x=alt.X("사업연도:O", title="사업연도"),
        y=alt.Y(f"{column}:Q", title=y_title),
        color=alt.Color("회사명:N", title="회사명"),
        tooltip=["회사명", "사업연도", column],
    ).properties(height=320, title=title)
    st.altair_chart(chart, use_container_width=True)


def render_dashboard(analysis: dict):
    metric_df, flag_df = build_dashboard_frames(analysis)
    if metric_df.empty:
        st.info("차트를 그릴 수 있는 성공 결과가 없습니다.")
        return

    st.subheader("대시보드")
    tab1, tab2, tab3 = st.tabs(["추세 차트", "적색신호 추이", "원시 표"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            line_chart(metric_df, "매출액(억원)", "매출액 추이", "매출액 (억원)")
        with c2:
            line_chart(metric_df, "영업이익률(%)", "영업이익률 추이", "영업이익률 (%)")

        c3, c4 = st.columns(2)
        with c3:
            line_chart(metric_df, "부채비율(%)", "부채비율 추이", "부채비율 (%)")
        with c4:
            line_chart(metric_df, "영업현금흐름(억원)", "영업현금흐름 추이", "영업현금흐름 (억원)")

        contract_df = metric_df.dropna(subset=["계약자산/매출액(%)"])
        if not contract_df.empty:
            contract_chart = alt.Chart(contract_df).mark_line(point=True).encode(
                x=alt.X("사업연도:O", title="사업연도"),
                y=alt.Y("계약자산/매출액(%):Q", title="계약자산 / 매출액 (%)"),
                color=alt.Color("회사명:N", title="회사명"),
                tooltip=["회사명", "사업연도", "계약자산/매출액(%)"],
            ).properties(height=320, title="계약자산 / 매출액 추이")
            st.altair_chart(contract_chart, use_container_width=True)

    with tab2:
        if flag_df.empty:
            st.info("적색신호 차트에 표시할 데이터가 없습니다.")
        else:
            flag_chart = alt.Chart(flag_df).mark_line(point=True).encode(
                x=alt.X("사업연도:O", title="사업연도"),
                y=alt.Y("적색신호수:Q", title="적색신호 수"),
                color=alt.Color("회사명:N", title="회사명"),
                tooltip=["회사명", "사업연도", "적색신호수", "중요적색신호수"],
            ).properties(height=320, title="적색신호 수 추이")
            st.altair_chart(flag_chart, use_container_width=True)

            severe_chart = alt.Chart(flag_df).mark_line(point=True, strokeDash=[4, 2]).encode(
                x=alt.X("사업연도:O", title="사업연도"),
                y=alt.Y("중요적색신호수:Q", title="중요 적색신호 수"),
                color=alt.Color("회사명:N", title="회사명"),
                tooltip=["회사명", "사업연도", "중요적색신호수"],
            ).properties(height=320, title="중요 적색신호 수 추이")
            st.altair_chart(severe_chart, use_container_width=True)

    with tab3:
        st.dataframe(metric_df, width="stretch", hide_index=True)
        st.dataframe(flag_df, width="stretch", hide_index=True)


def render_results(analysis: dict, workbook_binary: bytes, start_year: int, end_year: int):
    summary_rows = build_summary_rows(analysis["results"])
    red_flag_rows = build_red_flag_rows(analysis["results"])

    st.success("예비 재무 스크리닝이 완료되었습니다. 결과는 정식 신용등급이 아니며 인적 검토가 필요합니다.")

    col1, col2, col3 = st.columns(3)
    col1.metric("성공 건수", len(analysis["results"]))
    col2.metric("오류 건수", len(analysis["errors"]))
    col3.metric("회사 수", len({row["회사명"] for row in summary_rows}) if summary_rows else 0)

    st.subheader("회사-연도 요약")
    if summary_rows:
        st.dataframe(summary_rows, width="stretch", hide_index=True)
    else:
        st.info("요약할 성공 결과가 없습니다.")

    st.subheader("적색신호 상세")
    if red_flag_rows:
        st.dataframe(red_flag_rows, width="stretch", hide_index=True)
    else:
        st.info("적색신호 상세가 없습니다.")

    st.subheader("오류 / 누락")
    if analysis["errors"]:
        st.dataframe(analysis["errors"], width="stretch", hide_index=True)
    else:
        st.info("오류 없이 처리되었습니다.")

    filename = f"opendart_screening_{start_year}_{end_year}.xlsx"
    st.download_button(
        label="엑셀 다운로드",
        data=workbook_binary,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon=":bar_chart:", layout="wide")

    st.title(APP_TITLE)
    st.caption("건설사, EPC, 하도급사, PPP 참여 후보에 대한 preliminary financial screening 도구입니다. 정식 신용등급이 아니며 human review required.")

    api_key = get_api_key()
    st.session_state.setdefault("query_candidates", None)
    st.session_state.setdefault("selected_companies", None)
    st.session_state.setdefault("last_error", None)
    st.session_state.setdefault("last_analysis", None)
    st.session_state.setdefault("last_workbook_bytes", None)
    st.session_state.setdefault("last_year_range", None)

    with st.sidebar:
        st.header("입력")
        default_companies = "현대건설\nDL이앤씨\n대우건설\nGS건설"
        company_text = st.text_area("회사명 목록", value=default_companies, height=180, help="쉼표 또는 줄바꿈으로 여러 회사를 입력하세요.")
        start_year = st.number_input("시작 연도", min_value=2015, max_value=2100, value=2022, step=1)
        end_year = st.number_input("종료 연도", min_value=2015, max_value=2100, value=2024, step=1)
        preview_button = st.button("회사 후보 확인", width="stretch")
        run_button = st.button("스크리닝 실행", type="primary", width="stretch")

    company_names = parse_company_names([company_text])

    st.subheader("회사 선택 미리보기")
    if preview_button:
        st.session_state["last_error"] = None
        st.session_state["last_analysis"] = None
        st.session_state["last_workbook_bytes"] = None
        st.session_state["selected_companies"] = None
        try:
            if not company_names:
                st.session_state["last_error"] = "회사명을 입력한 뒤 회사 후보 확인을 눌러주세요."
            else:
                with st.spinner("회사 후보를 확인하고 있습니다..."):
                    query_candidates = [
                        (company_name, search_company_candidates(api_key, company_name, limit=5))
                        for company_name in company_names
                    ]
                st.session_state["query_candidates"] = query_candidates
        except Exception as exc:
            st.session_state["last_error"] = f"회사 후보 확인 중 오류가 발생했습니다: {exc}"

    query_candidates = st.session_state.get("query_candidates") or []
    if query_candidates:
        selected_companies, _preview_rows = resolve_selected_companies(query_candidates)
        st.session_state["selected_companies"] = selected_companies
    else:
        st.info("회사명을 입력하면 후보 목록을 확인하고 직접 회사를 선택할 수 있습니다.")

    if run_button:
        st.session_state["last_error"] = None
        st.session_state["last_analysis"] = None
        st.session_state["last_workbook_bytes"] = None
        if not company_names:
            st.session_state["last_error"] = "회사명을 하나 이상 입력하세요."
        elif start_year > end_year:
            st.session_state["last_error"] = "시작 연도는 종료 연도보다 클 수 없습니다."
        else:
            selected_companies = st.session_state.get("selected_companies") or []
            if not selected_companies:
                st.session_state["last_error"] = "먼저 회사 후보 확인을 눌러 회사 매칭을 확정하세요."
            else:
                status = st.status("스크리닝을 시작합니다...", expanded=True)
                try:
                    status.write("1. 입력값 검증 완료")
                    if api_key == BUILT_IN_API_KEY:
                        status.write("2. 기본 API 키로 실행합니다. 운영 배포에서는 Secrets의 DART_API_KEY 사용을 권장합니다.")
                    else:
                        status.write("2. Streamlit Secrets의 DART_API_KEY를 사용합니다.")
                    status.write("3. 선택한 회사 기준으로 OpenDART 데이터를 조회 중입니다...")
                    analysis, workbook_binary = run_screening(api_key, selected_companies, int(start_year), int(end_year))
                    status.write("4. 엑셀 워크북 생성 완료")
                    status.update(label="스크리닝 완료", state="complete")
                    st.session_state["last_analysis"] = analysis
                    st.session_state["last_workbook_bytes"] = workbook_binary
                    st.session_state["last_year_range"] = (int(start_year), int(end_year))
                except Exception as exc:
                    status.update(label="실행 중 오류가 발생했습니다.", state="error")
                    st.session_state["last_error"] = str(exc)

    if st.session_state.get("last_error"):
        st.error(f"실행 오류: {st.session_state['last_error']}")
        st.info("먼저 확인할 것: 1) Streamlit Secrets의 DART_API_KEY 설정 2) OpenDART 일시 오류 3) 회사명 검색 결과 및 선택")

    if st.session_state.get("last_analysis") and st.session_state.get("last_workbook_bytes"):
        start, end = st.session_state["last_year_range"]
        render_dashboard(st.session_state["last_analysis"])
        render_results(st.session_state["last_analysis"], st.session_state["last_workbook_bytes"], start, end)

    with st.expander("이 도구에 대한 안내", expanded=False):
        st.markdown(
            """
            - 이 결과는 **정식 신용등급이 아니라 예비 재무 스크리닝**입니다.
            - 여러 회사를 입력하면 **연도별 추세를 같은 차트에서 비교**할 수 있습니다.
            - 회사명 후보가 여러 개인 경우 **직접 회사 매칭을 선택**한 뒤 실행할 수 있습니다.
            - 적색신호는 preliminary red flag이며, **최종 판단 전 인적 검토가 필요**합니다.
            - 계정 매칭은 OpenDART 공시 형식에 따라 일부 민감할 수 있습니다.
            - `Matched Accounts`, `Raw FS Data`, `Metric Definitions` 시트를 함께 검토하세요.
            """
        )


if __name__ == "__main__":
    main()
