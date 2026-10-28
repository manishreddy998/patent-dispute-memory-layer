"""FastAPI service exposing cite-backed patent dispute positions, temporal claim lineage, and PDF receipts."""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from src.config import RESULTS
from src.warehouse import read_sql

app = FastAPI(
    title="Patent Dispute Memory Layer API",
    version="1.0.0",
    description="Cite-backed cross-venue patent dispute positions with temporal claim lineage and Rule-11 PDF receipt verification.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/positions")
def list_positions(
    family: str | None = Query(default=None),
    practice_area: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    if family:
        safe_f = family.replace("'", "''")
        clauses.append(f"lower(municipality_name) LIKE '%{safe_f.lower()}%'")
    if practice_area:
        safe_p = practice_area.replace("'", "''")
        clauses.append(f"lower(asset_category) = '{safe_p.lower()}'")
    where_sql = " AND ".join(clauses)
    q = f"""
        SELECT signal_id, project_code AS matter_code, municipality_name AS patent_family,
               region AS jurisdiction, agency_type AS lead_counsel,
               latest_project_title AS claim_limitation_title, asset_category AS practice_area,
               lifecycle_stage AS latest_venue, resolution_status,
               initial_budget_cad AS initial_exposure_usd,
               latest_verified_budget_cad AS latest_verified_exposure_usd,
               active_approved_budget_cad AS active_enforceable_exposure_usd,
               cumulative_amendment_delta_cad AS scope_shift_delta_usd,
               document_appearances, fiscal_years AS patent_number,
               funding_source AS doctrine_basis, regulatory_driver AS prior_art_reference,
               latest_doc_id, latest_file_name, latest_file_sha256,
               latest_page_number, latest_line_number, latest_verbatim_quote, receipt_verified
        FROM marts.mart_infrastructure_signals
        WHERE {where_sql}
        ORDER BY active_approved_budget_cad DESC, signal_id ASC
        LIMIT {int(limit)}
    """
    return read_sql(q).to_dict(orient="records")


@app.get("/lineage/{signal_id}")
def claim_lineage(signal_id: str) -> dict[str, Any]:
    safe_id = signal_id.replace("'", "''")
    df = read_sql(f"""
        SELECT appearance_seq, mention_id, doc_id, doc_type AS filing_type,
               meeting_date AS filing_date, project_code_stated AS matter_code_stated,
               mention_project_name AS position_title, lifecycle_stage AS venue,
               resolution_status, stated_total_cad AS stated_exposure_usd,
               verified_sum_cad AS verified_exposure_usd,
               table_math_gap_cad AS schedule_math_gap_usd,
               cumulative_amendment_delta_cad AS scope_shift_delta_usd,
               is_latest_record, is_superseded, file_name, file_sha256,
               page_number, line_number, verbatim_quote, receipt_verified
        FROM core.int_budget_amendment_chains
        WHERE resolved_entity_id = '{safe_id}'
        ORDER BY appearance_seq ASC
    """)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"Matter {signal_id} not found")
    return {
        "signal_id": signal_id,
        "appearances": len(df),
        "lineage": df.to_dict(orient="records"),
    }


@app.get("/scoreboard")
def get_scoreboard() -> dict[str, Any]:
    sb_path = RESULTS / "scoreboard.json"
    if not sb_path.exists():
        raise HTTPException(status_code=404, detail="scoreboard.json not generated yet")
    return json.loads(sb_path.read_text(encoding="utf-8"))
