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
    return "[" + ",".join(f"{float(value):.7g}" for value in values) + "]"


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
    args = parser.parse_args()

    if args.rows < 256:
        parser.error("rows must be >= 256 for the CAGRA route")

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
    recall_query = (
        f"SELECT id FROM {table} ORDER BY l2_distance(v, %s) "
        "APPROXIMATE LIMIT 100"
    )

    create_start = time.perf_counter()
    cur.execute(index_ddl)
    create_sec = time.perf_counter() - create_start

    first_start = time.perf_counter()
    cur.execute(first_query, (vector_literal(queries[0]),))
    first_rows = cur.fetchall()
    first_query_sec = time.perf_counter() - first_start
    build_total_sec = create_sec + first_query_sec

    approx = []
    latencies = []
    for query in queries:
        start = time.perf_counter()
        cur.execute(recall_query, (vector_literal(query),))
        rows = cur.fetchall()
        latencies.append((time.perf_counter() - start) * 1000.0)
        approx.append([row[0] for row in rows])

    result = {
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
            "recall@10": recall_at(approx, truth, 10),
            "recall@100": recall_at(approx, truth, 100),
        },
        "query_latency_ms": {
            "mean": statistics.mean(latencies),
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))],
            "max": max(latencies),
        },
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
