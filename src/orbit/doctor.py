"""Diagnostic checks for verifying the in-process data plane (LadybugDB and LanceDB)."""

from __future__ import annotations

import os
import platform
import sys
import tempfile
import time
from typing import Any

import ladybug
import lancedb
import pyarrow as pa
from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Result of an individual diagnostic check."""

    name: str
    passed: bool
    version: str
    latency_ms: float
    details: str
    extra: dict[str, Any] = Field(default_factory=dict)


class DoctorReport(BaseModel):
    """Aggregate health check report for the Orbit environment."""

    system_info: dict[str, str]
    checks: list[CheckResult]

    @property
    def all_passed(self) -> bool:
        """Return True if all engine checks succeeded."""
        return all(c.passed for c in self.checks)


def get_system_info() -> dict[str, str]:
    """Gather runtime environment metadata."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_path": sys.executable,
        "virtual_env": os.environ.get("VIRTUAL_ENV", "None"),
    }


def check_ladybug_engine() -> CheckResult:
    """Verify that the embedded LadybugDB C++ graph engine executes in-process transactions."""
    start_time = time.perf_counter()
    try:
        # Test in-memory database instance
        db = ladybug.Database("")
        conn = ladybug.Connection(db)

        # Create schema, insert node, and query via openCypher
        conn.execute("CREATE NODE TABLE HealthCheck(id INT64, status STRING, PRIMARY KEY(id));")
        conn.execute("CREATE (:HealthCheck {id: 1, status: 'HEALTHY'});")

        query_result = conn.execute("MATCH (h:HealthCheck) RETURN h.status;")
        if isinstance(query_result, list):
            query_result = query_result[0]

        if not query_result.has_next():
            raise RuntimeError("Cypher query returned no rows.")

        row = query_result.get_next()
        if isinstance(row, dict):
            status_value = str(row.get("h.status", ""))
        else:
            status_value = str(row[0])
        latency = (time.perf_counter() - start_time) * 1000

        return CheckResult(
            name="LadybugDB Property Graph",
            passed=status_value == "HEALTHY",
            version=getattr(ladybug, "__version__", "unknown"),
            latency_ms=round(latency, 2),
            details=f"In-memory Cypher transactional read/write verified ({status_value})",
        )
    except Exception as exc:
        latency = (time.perf_counter() - start_time) * 1000
        return CheckResult(
            name="LadybugDB Property Graph",
            passed=False,
            version=getattr(ladybug, "__version__", "unknown"),
            latency_ms=round(latency, 2),
            details=f"Check failed: {exc}",
        )


def check_lancedb_engine() -> CheckResult:
    """Verify that LanceDB columnar vector store writes and retrieves vectors in-process."""
    start_time = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = lancedb.connect(tmp_dir)

            schema = pa.schema(
                [
                    pa.field("id", pa.int64()),
                    pa.field("text", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), 4)),
                ]
            )

            table = db.create_table("health_check", schema=schema)
            test_vector = [0.1, 0.2, 0.3, 0.4]
            table.add([{"id": 1, "text": "orbit-smoke-test", "vector": test_vector}])

            search_results = table.search(test_vector).limit(1).to_list()
            if not search_results:
                raise RuntimeError("Vector ANN search returned empty results.")

            matched_text = str(search_results[0].get("text", ""))
            latency = (time.perf_counter() - start_time) * 1000

            return CheckResult(
                name="LanceDB Vector Engine",
                passed=matched_text == "orbit-smoke-test",
                version=getattr(lancedb, "__version__", "unknown"),
                latency_ms=round(latency, 2),
                details=f"Arrow-backed vector index read/write verified ('{matched_text}')",
            )
    except Exception as exc:
        latency = (time.perf_counter() - start_time) * 1000
        return CheckResult(
            name="LanceDB Vector Engine",
            passed=False,
            version=getattr(lancedb, "__version__", "unknown"),
            latency_ms=round(latency, 2),
            details=f"Check failed: {exc}",
        )


def run_diagnostics() -> DoctorReport:
    """Execute all system and engine health checks."""
    system_info = get_system_info()
    checks = [
        check_ladybug_engine(),
        check_lancedb_engine(),
    ]
    return DoctorReport(system_info=system_info, checks=checks)
