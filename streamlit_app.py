from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile

import streamlit as st

from dart_credit_evaluator import (
    BUILT_IN_API_KEY,
    build_red_flag_rows,
    build_summary_rows,
    evaluate_companies,
    parse_company_names,
    search_company_candidates,
)


APP_TITLE = "OpenDART 예비 재무 스크리닝"


def get_api_key() -> str:
    if "DART_API_KEY" in st.secrets:
        return st.secrets["DART_API_KEY"]
    return BUILT_IN_API_KEY


def render_candidate_preview(api_key: str, company_names: list[str]):
    rows = []
    for company_name in company_names:
        candidates = search_company_candidates(api_key, company_name, limit=3)
        if not candidates:
            rows.append(
                {
                    "입력회사명": company_name,
                    "자동선택회사": "-",
                    "종목코드": "-",
                    "고유번호": "-",
                    "비고": "검색 결과 없음",
                }
            )
            continue
        best = candidates[0]
        rows.append(
            {
                "입력회사명": company_name,
                "자동선택회사": best["company"],
                "종목코드": best.get("stock_code") or "-",
                "고유번호": best["corp_code"],
                "비고": "상위 검색 결과 자동 선택",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def run_screening(api_key: str, company_names: list[str], start_year: int, end_year: int):
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "opendart_screening.xlsx"
        analysis = evaluate_companies(api_key, company_names, start_year, end_year, output_path)
        workbook_bytes = output_path.read_bytes()
    return analysis, workbook_bytes


def render_results(analysis: dict, workbook_bytes: bytes, start_year: int, end_year: int):
    summary_rows = build_summary_rows(analysis["results"])
    red_flag_rows = build_red_flag_rows(analysis["results"])

    st.success("예비 재무 스크리닝이 완료되었습니다. 결과는 정식 신용등급이 아니며 인적 검토가 필요합니다.")

    col1, col2, col3 = st.columns(3)
    col1.metric("성공 건수", len(analysis["results"]))
    col2.metric("오류 건수", len(analysis["errors"]))
    col3.metric("회사 수", len({row["회사명"] for row in summary_rows}) if summary_rows else 0)

    st.subheader("최신 연도 요약")
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
        data=workbook_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon=":bar_chart:", layout="wide")

    st.title(APP_TITLE)
    st.caption("건설사, EPC, 하도급사, PPP 참여 후보에 대한 preliminary financial screening 도구입니다. 정식 신용등급이 아니며 human review required.")

    api_key = get_api_key()
    st.session_state.setdefault("preview_rows", None)
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
        st.session_state["preview_rows"] = None
        if not company_names:
            st.warning("회사명을 입력한 뒤 회사 후보 확인을 눌러주세요.")
        else:
            with st.spinner("회사 후보를 확인하고 있습니다..."):
                try:
                    preview_rows = []
                    for company_name in company_names:
                        candidates = search_company_candidates(api_key, company_name, limit=3)
                        if not candidates:
                            preview_rows.append(
                                {
                                    "입력회사명": company_name,
                                    "자동선택회사": "-",
                                    "종목코드": "-",
                                    "고유번호": "-",
                                    "비고": "검색 결과 없음",
                                }
                            )
                        else:
                            best = candidates[0]
                            preview_rows.append(
                                {
                                    "입력회사명": company_name,
                                    "자동선택회사": best["company"],
                                    "종목코드": best.get("stock_code") or "-",
                                    "고유번호": best["corp_code"],
                                    "비고": "상위 검색 결과 자동 선택",
                                }
                            )
                    st.session_state["preview_rows"] = preview_rows
                except Exception as exc:
                    st.session_state["last_error"] = f"회사 후보 확인 중 오류가 발생했습니다: {exc}"
    if st.session_state.get("preview_rows"):
        st.dataframe(st.session_state["preview_rows"], width="stretch", hide_index=True)
    else:
        st.info("회사명을 입력하면 자동 선택 후보를 보여드립니다.")

    if run_button:
        st.session_state["last_error"] = None
        st.session_state["last_analysis"] = None
        st.session_state["last_workbook_bytes"] = None
        if not company_names:
            st.error("회사명을 하나 이상 입력하세요.")
            return
        if start_year > end_year:
            st.error("시작 연도는 종료 연도보다 클 수 없습니다.")
            return

        status = st.status("스크리닝을 시작합니다...", expanded=True)
        try:
            status.write("1. 입력값 검증 완료")
            if api_key == BUILT_IN_API_KEY:
                status.write("2. 기본 API 키로 실행합니다. 운영 배포에서는 Secrets의 DART_API_KEY 사용을 권장합니다.")
            else:
                status.write("2. Streamlit Secrets의 DART_API_KEY를 사용합니다.")
            status.write("3. OpenDART 데이터를 조회 중입니다...")
            analysis, workbook_bytes = run_screening(api_key, company_names, int(start_year), int(end_year))
            status.write("4. 엑셀 워크북 생성 완료")
            status.update(label="스크리닝 완료", state="complete")
            st.session_state["last_analysis"] = analysis
            st.session_state["last_workbook_bytes"] = workbook_bytes
            st.session_state["last_year_range"] = (int(start_year), int(end_year))
        except Exception as exc:
            status.update(label="실행 중 오류가 발생했습니다.", state="error")
            st.session_state["last_error"] = str(exc)

    if st.session_state.get("last_error"):
        st.error(f"실행 오류: {st.session_state['last_error']}")
        st.info("먼저 확인할 것: 1) Streamlit Secrets의 DART_API_KEY 설정 2) OpenDART 일시 오류 3) 회사명 검색 결과")

    if st.session_state.get("last_analysis") and st.session_state.get("last_workbook_bytes"):
        start, end = st.session_state["last_year_range"]
        render_results(st.session_state["last_analysis"], st.session_state["last_workbook_bytes"], start, end)

    with st.expander("이 도구에 대한 안내", expanded=False):
        st.markdown(
            """
            - 이 결과는 **정식 신용등급이 아니라 예비 재무 스크리닝**입니다.
            - 적색신호는 preliminary red flag이며, **최종 판단 전 인적 검토가 필요**합니다.
            - 계정 매칭은 OpenDART 공시 형식에 따라 일부 민감할 수 있습니다.
            - `Matched Accounts`, `Raw FS Data`, `Metric Definitions` 시트를 함께 검토하세요.
            """
        )


if __name__ == "__main__":
    main()
