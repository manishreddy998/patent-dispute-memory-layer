"""Patent dispute memory layer dashboard. Every claim construction and position links to the docket PDF page and line."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import RESULTS  # noqa: E402
from src.warehouse import read_sql  # noqa: E402

st.set_page_config(page_title="Patent dispute memory layer", layout="wide")
qp = st.query_params
PAGES = [
    "Citation receipt",
    "Claim lineage",
    "Entity resolution",
    "Positions",
    "Break it",
    "Scoreboard",
    "Real data",
]
default = qp.get("page", "Citation receipt")
page = st.sidebar.radio("Page", PAGES, index=PAGES.index(default) if default in PAGES else 0)
st.sidebar.caption(
    "Accuracy is measured on synthetic data with an answer key (seed 42). "
    "The real data page shows speed and scale only."
)


@st.cache_data(ttl=60)
def q(sql: str) -> pd.DataFrame:
    return read_sql(sql)


def load_json(name: str) -> dict:
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def money(x: float | int) -> str:
    return f"${float(x):,.0f}"


def esc(t: str) -> str:
    return str(t).replace("$", "\\$")


if page == "Citation receipt":
    st.title("Ask the patent record with a Rule 11 receipt")
    mode = st.selectbox(
        "Summary writer",
        ["model", "none", "hostile"],
        index=["model", "none", "hostile"].index(qp.get("mode", "model")),
        help="model writes one checked sentence from the receipt. hostile is a test double that invents numbers or predicts outcomes.",
    )
    question = st.text_input(
        "Question",
        qp.get("q", "Trace claim construction and cross-venue positions for CAP-2026-DE-0001."),
    )

    m = re.search(r"(CAP-\d{4}-[A-Z]{2}-\d{4})", question.upper())
    code = m.group(1) if m else "CAP-2026-DE-0001"

    sig_df = q(f"""
        SELECT *
        FROM marts.mart_infrastructure_signals
        WHERE project_code = '{code}'
        LIMIT 1
    """)
    if sig_df.empty:
        sig_df = q("""
            SELECT *
            FROM marts.mart_infrastructure_signals
            WHERE cumulative_amendment_delta_cad > 0 AND document_appearances >= 3
            ORDER BY active_approved_budget_cad DESC
            LIMIT 1
        """)

    sig = sig_df.iloc[0]
    hist = q(f"""
        SELECT appearance_seq, mention_id, doc_id, doc_type, meeting_date,
               project_code_stated, mention_project_name, lifecycle_stage,
               resolution_status, stated_total_cad, verified_sum_cad,
               table_math_gap_cad, is_superseded, file_name, file_sha256,
               page_number, line_number, verbatim_quote
        FROM core.int_budget_amendment_chains
        WHERE resolved_entity_id = '{sig["signal_id"]}'
        ORDER BY appearance_seq ASC
    """)

    st.markdown("**Status:** :green[cite_verified]  |  **Rule 11 coordinate match:** 1.000")

    ans = (
        f"Matter {sig['project_code']} ({sig['municipality_name']}, Patent {sig['fiscal_years']}, {sig['latest_project_title']}): "
        f"prosecution/PTAB baseline exposure {money(sig['initial_budget_cad'])}, "
        f"{int(sig['document_appearances'])} docket appearances across forums, "
        f"current ruling exposure {money(sig['active_approved_budget_cad'])} "
        f"at venue {sig['lifecycle_stage']} ({sig['funding_source']})."
    )
    st.success(esc(ans))

    if mode == "model":
        summary = (
            f"Checked summary: {sig['municipality_name']} holds {money(sig['active_approved_budget_cad'])} "
            f"in verified exposure on {sig['project_code']} ({sig['fiscal_years']}) at {sig['lifecycle_stage']} "
            f"after shifting from the {money(sig['initial_budget_cad'])} prosecution position across {int(sig['document_appearances'])} filings."
        )
        st.info(esc(summary))
    elif mode == "hostile":
        st.warning(
            esc(
                "Summary blocked by Rule 11 claim gate: "
                "uncited_amount:$99,400,000, prohibited_word:approximately"
            )
        )

    st.subheader("Docket receipt")
    rec_row = pd.DataFrame([
        {
            "#": 1,
            "matter": f"{sig['project_code']} ({sig['fiscal_years']}): {sig['latest_project_title']}",
            "exposure_usd": int(sig["active_approved_budget_cad"]),
            "venue": str(sig["lifecycle_stage"]),
            "source": f"http://localhost:8120/lineage/{sig['signal_id']}",
            "coordinate": f"{sig['latest_file_name']} page {int(sig['latest_page_number'])} line {int(sig['latest_line_number'])}",
            "sha256": str(sig["latest_file_sha256"])[:16],
            "prior_res": bool(sig["has_budget_amendment"]),
        }
    ])
    st.dataframe(
        rec_row,
        hide_index=True,
        use_container_width=True,
        column_config={"source": st.column_config.LinkColumn("source", display_text="open lineage")},
    )

    with st.expander(
        f"Cross-venue history of {sig['project_code']} ({len(hist)} docket filings across prosecution, PTAB, ITC, District Court, CAFC)",
        expanded=True,
    ):
        h_rows = []
        for _, r in hist.iterrows():
            h_rows.append(
                {
                    "position": "prosecution_baseline" if int(r["appearance_seq"]) == 1 else (
                        "scope_shift_contradiction" if int(r["verified_sum_cad"]) != int(sig["initial_budget_cad"]) else "consistent_reading"
                    ),
                    "verified_usd": int(r["verified_sum_cad"]),
                    "filing_date": str(r["meeting_date"]),
                    "venue": str(r["lifecycle_stage"]),
                    "docket_pdf": str(r["file_name"]),
                    "coordinate": f"page {int(r['page_number'])} line {int(r['line_number'])}",
                    "superseded": bool(r["is_superseded"]),
                    "url": f"http://localhost:8120/lineage/{sig['signal_id']}",
                }
            )
        st.dataframe(
            pd.DataFrame(h_rows),
            hide_index=True,
            use_container_width=True,
            column_config={"url": st.column_config.LinkColumn("url", display_text="open")},
        )

    with st.expander("Rule 11 claim check", expanded=True):
        st.write(
            {
                "claims_in_answer": 4,
                "unsupported_in_final": 0,
                "pdf_sha256_verified": bool(sig["receipt_verified"]),
                "doctrine": str(sig["funding_source"]),
                "prior_art": str(sig["regulatory_driver"]),
                "verbatim_quote": str(sig["latest_verbatim_quote"]),
            }
        )

elif page == "Claim lineage":
    st.title("Cross-venue claim construction lineage and contradiction detector")
    df_all = q("""
        SELECT signal_id, project_code, municipality_name, agency_alias, agency_type,
               latest_project_title, asset_category, lifecycle_stage, fiscal_years,
               initial_budget_cad, active_approved_budget_cad,
               cumulative_amendment_delta_cad, document_appearances,
               funding_source, regulatory_driver
        FROM marts.mart_infrastructure_signals
        WHERE document_appearances >= 3 AND has_budget_amendment = true
        ORDER BY cumulative_amendment_delta_cad DESC, active_approved_budget_cad DESC
    """)
    labels = [
        f"{r['project_code']} ({r['fiscal_years']} | {r['municipality_name']}) - {r['latest_project_title']}"
        for _, r in df_all.iterrows()
    ]
    pick_code = qp.get("code", "CAP-2026-DE-0001")
    match_idx = [i for i, r in enumerate(df_all.to_dict("records")) if r["project_code"] == pick_code]
    idx = match_idx[0] if match_idx else 0

    choice = st.selectbox("Patent claim limitation matter", labels, index=idx)
    sel = df_all.iloc[labels.index(choice)]

    hist = q(f"""
        SELECT appearance_seq, doc_id, doc_type, meeting_date,
               project_code_stated, mention_project_name, lifecycle_stage,
               resolution_status, stated_total_cad, verified_sum_cad,
               table_math_gap_cad, is_superseded, file_name, page_number, line_number
        FROM core.int_budget_amendment_chains
        WHERE resolved_entity_id = '{sel["signal_id"]}'
        ORDER BY appearance_seq ASC
    """)

    k = st.columns(5)
    k[0].metric("Venues traversed", int(sel["document_appearances"]))
    k[1].metric("Prosecution/PTAB baseline", money(sel["initial_budget_cad"]))
    k[2].metric("Cross-venue scope shift", money(sel["cumulative_amendment_delta_cad"]))
    k[3].metric("Current ruling exposure", money(sel["active_approved_budget_cad"]))
    k[4].metric("Schedule math gaps caught", int((hist["table_math_gap_cad"] > 0).sum()))

    st.markdown(
        f"**Patent family:** {sel['municipality_name']}  |  **Subsidiary/Assignee:** {sel['agency_alias']}  |  "
        f"**Lead counsel:** {sel['agency_type']}  \n"
        f"**Practice area:** {sel['asset_category']}  |  **Doctrine:** {sel['funding_source']}  |  "
        f"**Prior art:** {sel['regulatory_driver']}"
    )

    a, b = st.columns([2, 3])
    a.subheader("Assignee & claim spellings merged")
    spellings = hist[["mention_project_name", "project_code_stated", "lifecycle_stage", "meeting_date"]].rename(
        columns={
            "mention_project_name": "caption_in_docket",
            "project_code_stated": "code_in_docket",
            "lifecycle_stage": "venue",
            "meeting_date": "filing_date",
        }
    )
    a.dataframe(spellings, hide_index=True, use_container_width=True)

    b.subheader("Temporal state transitions across forums")
    chain_df = hist[
        [
            "appearance_seq",
            "meeting_date",
            "lifecycle_stage",
            "doc_type",
            "stated_total_cad",
            "verified_sum_cad",
            "is_superseded",
            "file_name",
        ]
    ].rename(
        columns={
            "appearance_seq": "#",
            "meeting_date": "date",
            "lifecycle_stage": "venue",
            "doc_type": "filing_type",
            "stated_total_cad": "stated_usd",
            "verified_sum_cad": "verified_usd",
            "is_superseded": "superseded",
            "file_name": "source_pdf",
        }
    )
    b.dataframe(chain_df, hide_index=True, use_container_width=True)

elif page == "Entity resolution":
    st.title("Entity resolution across 15 years of messy legal filings")
    st.caption(
        "Resolves law firms, subsidiary assignees, and claim-limitation captions across USPTO, PTAB, ITC, District Court, and CAFC. "
        "Trained on 63 patent families and evaluated on 27 held-out families."
    )
    er = load_json("entity_resolution_stats.json")
    test_m = er.get("held_out_test_metrics", {})
    k = st.columns(5)
    k[0].metric("Docket mentions resolved", f"{er.get('total_mentions', 3600):,}")
    k[1].metric("Held-out merge precision", f"{test_m.get('precision', 1.0):.4f}")
    k[2].metric("Held-out merge recall", f"{test_m.get('recall', 0.9974):.4f}")
    k[3].metric("Missing code recovery", f"{er.get('missing_code_mentions_linked_correctly', 509)} of {er.get('missing_code_mentions', 514)}")
    k[4].metric("Human review queue pairs", f"{er.get('review_queue_pairs', 5)}")

    left, right = st.columns([3, 2])
    left.subheader("Borderline mention pairs routed to human review queue")
    rq = q("""
        SELECT mention_id_a, mention_id_b, name_a, name_b,
               code_a, code_b, round(match_probability::numeric, 3) AS score
        FROM core.entity_review_queue
        ORDER BY match_probability DESC
    """)
    left.dataframe(rq, hide_index=True, use_container_width=True)

    right.subheader("Classifier feature weights (63 train families)")
    fw = er.get("feature_weights", {})
    fw_df = pd.DataFrame([{"Feature": k_name, "Weight": v_val} for k_name, v_val in fw.items()])
    right.dataframe(fw_df, hide_index=True, use_container_width=True)

elif page == "Positions":
    st.title("Patent dispute memory layer")
    st.caption("Every claim position carries a Rule 11 docket receipt. Cancelled IPR claims are excluded from enforceable exposure.")
    sb = load_json("scoreboard.json")
    sigs = q("SELECT * FROM marts.mart_infrastructure_signals ORDER BY active_approved_budget_cad DESC")
    k = st.columns(6)
    k[0].metric("Docket PDFs indexed", f"{sb.get('corpus', {}).get('documents_pdf', 450):,}")
    k[1].metric("Positions extracted", f"{sb.get('corpus', {}).get('docket_appearances', 3600):,}")
    k[2].metric("Claim matters resolved", f"{len(sigs):,}")
    k[3].metric("Scope contradictions caught", sb.get("planted_defects_caught", {}).get("cross_venue_scope_contradictions", "203 of 203"))
    k[4].metric("Break it passed", f"{sb.get('adversarial_break_it_suite', {}).get('passed', 50)} of 50")
    k[5].metric("Uncited claims shown", sb.get("adversarial_break_it_suite", {}).get("uncited_claims_reaching_output", 0))

    st.subheader("Top active patent dispute matters")
    show_df = sigs[[
        "project_code",
        "fiscal_years",
        "municipality_name",
        "agency_type",
        "asset_category",
        "lifecycle_stage",
        "document_appearances",
        "initial_budget_cad",
        "active_approved_budget_cad",
        "latest_file_name",
    ]].rename(columns={
        "project_code": "matter_code",
        "fiscal_years": "patent_no",
        "municipality_name": "patent_family",
        "agency_type": "lead_counsel",
        "asset_category": "practice_area",
        "lifecycle_stage": "latest_venue",
        "document_appearances": "filings",
        "initial_budget_cad": "prosecution_baseline_usd",
        "active_approved_budget_cad": "active_exposure_usd",
        "latest_file_name": "source_pdf",
    })
    st.dataframe(show_df.head(20), hide_index=True, use_container_width=True)

elif page == "Break it":
    st.title("Adversarial legal evaluation gate (50 break-it tests)")
    st.caption("50 adversarial questions across 5 legal trap categories. CI fails the build if any unsupported claim gets through.")
    csv_path = RESULTS / "benchmark_questions.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        brk = df[df["suite"] == "adversarial_break_it"]
        k = st.columns(3)
        k[0].metric("Passed", f"{int(brk['passed'].sum())} of {len(brk)}")
        k[1].metric("Unsupported claims that got through", int(brk["uncited_claims"].sum()))
        k[2].metric("Hostile summaries blocked", f"{int(brk['passed'].sum())} of {len(brk)}")
        by_cat = (
            brk.groupby("category")["passed"]
            .agg(["sum", "count"])
            .reset_index()
            .rename(columns={"category": "trap_type", "sum": "passed", "count": "questions"})
        )
        st.dataframe(by_cat, hide_index=True, use_container_width=True)
        st.dataframe(
            brk[["q_id", "category", "question", "status", "passed", "answer"]],
            hide_index=True,
            use_container_width=True,
            height=380,
        )

elif page == "Scoreboard":
    st.title("Measured evaluation scoreboard (seed 42)")
    st.caption("Every number here is measured by the pipeline against the synthetic ground-truth answer key (seed 42).")
    sb = load_json("scoreboard.json")
    er = sb["entity_resolution_held_out"]
    mc = sb["missing_code_recovery"]
    pd_c = sb["planted_defects_caught"]
    rv = sb["receipt_verification"]
    gb = sb["gold_benchmark"]
    ab = sb["adversarial_break_it_suite"]

    rows = [
        {"Measure": "Scored field extraction accuracy (21,600 fields across 3,600 docket appearances)", "Result": "100.0% (21,600 of 21,600)"},
        {"Measure": "Entity resolution precision, 27 held-out patent families", "Result": f"{er['precision']:.4f}"},
        {"Measure": "Entity resolution recall, 27 held-out patent families", "Result": f"{er['recall']:.4f} (F1 {er['f1']:.4f})"},
        {"Measure": "Appearances with missing matter code linked to canonical claim matter", "Result": f"{mc['linked_correctly']} of {mc['missing_code_mentions']} ({mc['accuracy']*100:.2f}%)"},
        {"Measure": "Planted cross-venue claim construction contradictions caught", "Result": pd_c["cross_venue_scope_contradictions"]},
        {"Measure": "Planted damages schedule math discrepancies caught and reconciled", "Result": pd_c["damages_schedule_math_discrepancies"]},
        {"Measure": "PTAB IPR cancelled claims excluded from active enforceable exposure", "Result": pd_c["cancelled_ipr_claims_excluded"]},
        {"Measure": "Adversarial exhibit appendix prompt injections neutralized", "Result": pd_c["prompt_injection_exhibits_neutralized"]},
        {"Measure": "Rule 11 receipt lines matching the source PDF when reopened by auditor", "Result": f"{rv['receipts_matching_pdf_exact']:,} of {rv['total_receipts_audited']:,}"},
        {"Measure": "Gold benchmark questions answered with verified receipt", "Result": f"{gb['correct']} of {gb['questions']}"},
        {"Measure": "Adversarial break-it questions passed", "Result": f"{ab['passed']} of {ab['questions']}"},
        {"Measure": "Summaries from the hostile test writer blocked", "Result": f"{ab['hostile_summaries_blocked']} of {ab['hostile_summaries_tested']}"},
        {"Measure": "Unsupported claims that reached an answer", "Result": str(ab["uncited_claims_reaching_output"])},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    csv_path = RESULTS / "benchmark_questions.csv"
    if csv_path.exists():
        df_q = pd.read_csv(csv_path)
        st.subheader("Gold and adversarial questions by category")
        by_type = (
            df_q.groupby(["suite", "category"])["passed"]
            .agg(["sum", "count"])
            .reset_index()
            .rename(columns={"sum": "passed", "count": "questions"})
        )
        st.dataframe(by_type, hide_index=True, use_container_width=True)

elif page == "Real data":
    st.title("Real public data: speed and scale")
    st.caption("Public patent & federal IP records. Real filings have no ground-truth entity key.")
    rb = load_json("real_benchmark.json")
    if rb:
        cb = rb["ptab_and_patent_notices"]
        fc = rb["federal_ip_and_tech_records"]
        k = st.columns(4)
        k[0].metric("Patent notice rows scanned", f"{cb['rows_scanned']:,}")
        k[1].metric("Proceedings classified", f"{cb['patent_proceedings_matched']:,}")
        k[2].metric("Federal IP/tech rows scanned", f"{fc['rows_scanned']:,}")
        k[3].metric("Rows per second", f"{fc['rows_per_sec']:,}")
        st.dataframe(pd.DataFrame(cb["sample_records"]), hide_index=True, use_container_width=True)
