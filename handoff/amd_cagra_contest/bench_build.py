#!/usr/bin/env python3
"""Cold-start build benchmark for the official lib=cuvs baseline.

One invocation = one fresh process/index lifecycle. Restart seekdb between runs
and clear the database to match the official alternating cold-start protocol.

The timed region is:
  CREATE VECTOR INDEX ... WITH(lib=cuvs, ...) + first fixed APPROXIMATE query
This includes lazy CAGRA construction triggered by the first query.

Not yet executed on AMD GPU hardware. Use only as the development harness; the
organizer's fixed harness is the official score.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid

import numpy as np
import pymysql

HOST = os.environ.get("SEEKDB_HOST", "127.0.0.1")
PORT = int(os.environ.get("SEEKDB_PORT", "2881"))
USER = os.environ.get("SEEKDB_USER", "root")
PASSWORD = os.environ.get("SEEKDB_PASSWORD", "")


def vector_literal(values):
    return "[" + ",".join(f"{float(value):.9g}" for value in values) + "]"


def validate_result(rows, k, total_rows):
    ids = [row[0] for row in rows]
    if len(ids) != k or len(set(ids)) != k or any(i < 0 or i >= total_rows for i in ids):
        raise RuntimeError(f"invalid Top-{k} result: expected unique IDs in [0, {total_rows})")
    return ids


def check_gpu_trace(path, offset, need_build=False, marker=b"cuvs_serve"):
    with Path(path).open("rb") as trace:
        trace.seek(offset)
        markers = [line.split()[0] for line in trace if line.strip()]
        end = trace.tell()
    if marker not in markers or (need_build and b"cuvs_build" not in markers):
        raise RuntimeError("query has no successful CAGRA build/serve evidence")
    return end


def exact_topk(base, queries, k):
    b = base.astype(np.float64)
    q = queries.astype(np.float64)
    distances = (q * q).sum(axis=1)[:, None] + (b * b).sum(axis=1)[None, :] - 2.0 * (q @ b.T)
    truth = np.argpartition(distances, k - 1, axis=1)[:, :k]
    rows = np.arange(len(q))[:, None]
    order = np.argsort(distances[rows, truth], axis=1, kind="stable")
    return truth[rows, order]


def recall_at(approx, truth, k):
    return float(np.mean([
        len(set(a[:k]) & set(t[:k])) / k for a, t in zip(approx, truth)
    ]))


def latency_summary(values):
    return {"mean": statistics.mean(values), "p50": statistics.median(values),
            "p95": float(np.percentile(values, 95, method="inverted_cdf")), "max": max(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--first-k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lib", choices=("cuvs", "vsag"), default="cuvs")
    parser.add_argument("--distance", choices=("L2",), default="L2")
    parser.add_argument("--m", type=int, default=16)
    parser.add_argument("--ef-construction", type=int, default=200)
    parser.add_argument("--ef-search", type=int, default=200)
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trace-file", default=os.environ.get("OB_VSAG_TRACE_FILE"))
    args = parser.parse_args()

    if args.rows < 256:
        parser.error("rows must be >= 256 for the CAGRA route")
    if min(args.dim, args.queries, args.batch) <= 0 or not 1 <= args.first_k <= args.rows:
        parser.error("dim, queries, batch must be positive; first-k must be in [1, rows]")
    if args.lib == "cuvs" and not args.trace_file:
        parser.error("lib=cuvs requires --trace-file from a fresh TRACE-enabled observer")

    rng = np.random.default_rng(args.seed)
    base = rng.standard_normal((args.rows, args.dim), dtype=np.float32)
    queries = rng.standard_normal((args.queries, args.dim), dtype=np.float32)
    truth = exact_topk(base, queries, 100)

    db = "amd_build_bench_" + uuid.uuid4().hex[:10]
    table = "vecs"
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PASSWORD,
                           database="", autocommit=True)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE {db}")
    cur.execute(f"USE {db}")
    cur.execute(
        f"CREATE TABLE {table} (id INT PRIMARY KEY, v VECTOR({args.dim})) "
        "ORGANIZATION = HEAP"
    )

    load_start = time.perf_counter()
    sql = f"INSERT INTO {table}(id, v) VALUES (%s, %s)"
    for start in range(0, args.rows, args.batch):
        batch = [
            (row_id, vector_literal(base[row_id]))
            for row_id in range(start, min(start + args.batch, args.rows))
        ]
        cur.executemany(sql, batch)
    load_sec = time.perf_counter() - load_start

    index_ddl = (
        f"CREATE VECTOR INDEX idx_v ON {table}(v) WITH ("
        f"DISTANCE={args.distance}, TYPE=hnsw, LIB={args.lib}, "
        f"M={args.m}, EF_CONSTRUCTION={args.ef_construction}, "
        f"EF_SEARCH={args.ef_search})"
    )
    first_query = (
        f"SELECT id FROM {table} ORDER BY l2_distance(v, %s) "
        f"APPROXIMATE LIMIT {args.first_k}"
    )
    first_literal = vector_literal(queries[0])
    trace_offset = (Path(args.trace_file).stat().st_size
                    if args.trace_file and Path(args.trace_file).exists() else 0)

    create_start = time.perf_counter()
    cur.execute(index_ddl)
    create_sec = time.perf_counter() - create_start

    first_start = time.perf_counter()
    cur.execute(first_query, (first_literal,))
    first_rows = cur.fetchall()
    validate_result(first_rows, args.first_k, args.rows)
    first_query_sec = time.perf_counter() - first_start
    build_total_sec = time.perf_counter() - create_start
    if args.lib == "cuvs":
        try:
            trace_offset = check_gpu_trace(args.trace_file, trace_offset, need_build=True)
        except RuntimeError as exc:
            Path(args.out).write_text(json.dumps({
                "status": "FAIL", "error": str(exc), "config": vars(args),
                "timing": {"create_index_sec": create_sec, "first_query_sec": first_query_sec,
                           "build_total_sec": build_total_sec},
                "first_query_ids": [row[0] for row in first_rows],
                "note": "Invalid for GPU scoring: these elapsed times may include CPU fallback.",
            }, indent=2) + "\n")
            raise

    approx = {10: [], 100: []}
    query_latencies = {10: [], 100: []}
    for k in (10, 100):
        recall_query = (
            f"SELECT id FROM {table} ORDER BY l2_distance(v, %s) "
            f"APPROXIMATE LIMIT {k}"
        )
        for query in queries:
            start = time.perf_counter()
            cur.execute(recall_query, (vector_literal(query),))
            rows = cur.fetchall()
            query_latencies[k].append((time.perf_counter() - start) * 1000.0)
            approx[k].append(validate_result(rows, k, args.rows))
            if args.lib == "cuvs":
                trace_offset = check_gpu_trace(args.trace_file, trace_offset)
    latencies = query_latencies[100]

    cur.execute(f"CREATE TABLE probes (id BIGINT PRIMARY KEY, v VECTOR({args.dim}))")
    cur.executemany("INSERT INTO probes VALUES (%s, %s)",
                    [(i, vector_literal(q)) for i, q in enumerate(queries)])
    cur.execute("CREATE TABLE batch_out (probe_id BIGINT, neighbor_id BIGINT, distance FLOAT, rk INT)")
    batch_results = {}
    for k in ((10, 100) if args.lib == "cuvs" else ()):
        batch_times, batch_recalls = [], []
        for _ in range(3):
            cur.execute("TRUNCATE TABLE batch_out")
            start = time.perf_counter()
            cur.execute(f'CALL dbms_vector.batch_knn("vecs","probes",{k},"batch_out")')
            batch_times.append(time.perf_counter() - start)
            if args.lib == "cuvs":
                trace_offset = check_gpu_trace(args.trace_file, trace_offset, marker=b"cuvs_raw_batch")
            cur.execute("SELECT probe_id, neighbor_id FROM batch_out ORDER BY probe_id,rk")
            groups = [[] for _ in queries]
            for probe_id, neighbor_id in cur.fetchall():
                if not 0 <= probe_id < args.queries:
                    raise RuntimeError("invalid batch probe ID")
                groups[probe_id].append((neighbor_id,))
            ids = [validate_result(group, k, args.rows) for group in groups]
            batch_recalls.append(recall_at(ids, truth, k))
        batch_results[str(k)] = {
            "call_seconds": batch_times,
            "qps": args.queries / statistics.median(batch_times),
            "call_p50_ms": 1000 * statistics.median(batch_times),
            "call_p95_ms": 1000 * max(batch_times),
            "recall": batch_recalls,
            "note": "Each SQL batch call includes its one-shot CAGRA build; latency is per batch call.",
        }

    result = {
        "status": "PASS",
        "config": vars(args),
        "environment": {
            "host": HOST,
            "port": PORT,
            "python": sys.version,
            "numpy": np.__version__,
            "pymysql": pymysql.__version__,
        },
        "data": {
            "rows": args.rows,
            "dim": args.dim,
            "queries": args.queries,
            "seed": args.seed,
            "generator": "numpy standard_normal float32",
        },
        "timing": {
            "load_sec": load_sec,
            "create_index_sec": create_sec,
            "first_query_sec": first_query_sec,
            "build_total_sec": build_total_sec,
            "first_query_rows": len(first_rows),
        },
        "recall": {
            "recall@10": recall_at(approx[10], truth, 10),
            "recall@100": recall_at(approx[100], truth, 100),
        },
        "query_latency_ms": latency_summary(latencies),
        "query_latency_by_k_ms": {str(k): latency_summary(values) for k, values in query_latencies.items()},
        "percentile_method": "nearest rank (inverted empirical CDF)",
        "query_qps": {str(k): 1000.0 * len(values) / sum(values)
                      for k, values in query_latencies.items()},
        "query_raw": {str(k): {"latencies_ms": query_latencies[k], "ids": approx[k]}
                      for k in (10, 100)},
        "batch_query": batch_results,
        "index_ddl": index_ddl,
        "note": "One fresh DB/index per invocation. Restart seekdb between runs; first query is included in build_total_sec.",
    }

    with open(args.out, "w", encoding="utf-8") as output:
        json.dump(result, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    conn.close()


if __name__ == "__main__":
    main()
