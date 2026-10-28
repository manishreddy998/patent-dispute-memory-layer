"""Cloud Composer (Apache Airflow) DAG for the cross-venue patent dispute memory layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class SimpleDAG:
    dag_id: str
    schedule_interval: str
    start_date: datetime
    catchup: bool = False
    default_args: dict = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)


dag = SimpleDAG(
    dag_id="patent_dispute_memory_layer_pipeline",
    schedule_interval="0 5 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "lexdana-data-eng", "retries": 2, "retry_delay": timedelta(minutes=5)},
    tasks=[
        "ingest_docket_pdfs_beam",
        "extract_claim_positions_async",
        "dbt_build_staging",
        "resolve_entities_and_claim_graph",
        "dbt_build_temporal_marts",
        "verify_rule11_pdf_receipts_and_gate",
    ],
)
