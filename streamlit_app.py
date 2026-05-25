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
    st.dataframe(rows, use_container_width=True, hide_index=True)


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
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)
    else:
        st.info("요약할 성공 결과가 없습니다.")

    st.subheader("적색신호 상세")
    if red_flag_rows:
        st.dataframe(red_flag_rows, use_container_width=True, hide_index=True)
    else:
        st.info("적색신호 상세가 없습니다.")

    st.subheader("오류 / 누락")
    if analysis["errors"]:
        st.dataframe(analysis["errors"], use_container_width=True, hide_index=True)
    else:
        st.info("오류 없이 처리되었습니다.")

    filename = f"opendart_screening_{start_year}_{end_year}.xlsx"
    st.download_button(
        label="엑셀 다운로드",
        data=workbook_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon=":bar_chart:", layout="wide")

    st.title(APP_TITLE)
    st.caption("건설사, EPC, 하도급사, PPP 참여 후보에 대한 preliminary financial screening 도구입니다. 정식 신용등급이 아니며 human review required.")

    api_key = get_api_key()

    with st.sidebar:
        st.header("입력")
        default_companies = "현대건설\nDL이앤씨\n대우건설\nGS건설"
        company_text = st.text_area("회사명 목록", value=default_companies, height=180, help="쉼표 또는 줄바꿈으로 여러 회사를 입력하세요.")
        start_year = st.number_input("시작 연도", min_value=2015, max_value=2100, value=2022, step=1)
        end_year = st.number_input("종료 연도", min_value=2015, max_value=2100, value=2024, step=1)
        run_button = st.button("스크리닝 실행", type="primary", use_container_width=True)

    company_names = parse_company_names([company_text])

    st.subheader("회사 선택 미리보기")
    if company_names:
        render_candidate_preview(api_key, company_names)
    else:
        st.info("회사명을 입력하면 자동 선택 후보를 보여드립니다.")

    if run_button:
        if not company_names:
            st.error("회사명을 하나 이상 입력하세요.")
            return
        if start_year > end_year:
            st.error("시작 연도는 종료 연도보다 클 수 없습니다.")
            return

        with st.spinner("OpenDART에서 데이터를 수집하고 엑셀을 생성하고 있습니다..."):
            analysis, workbook_bytes = run_screening(api_key, company_names, int(start_year), int(end_year))
        render_results(analysis, workbook_bytes, int(start_year), int(end_year))

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
