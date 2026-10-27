import unittest
from pathlib import Path
import tempfile

import numpy as np

from bench_build import check_gpu_trace, latency_summary, validate_result, vector_literal


class BenchmarkInputTest(unittest.TestCase):
    def test_latency_percentile(self):
        self.assertEqual(latency_summary(list(range(1, 101))),
                         {"mean": 50.5, "p50": 50.5, "p95": 95.0, "max": 100})

    def test_fp32_round_trip(self):
        values = np.array([0.123456791, -1.23456789, 0, np.finfo(np.float32).tiny,
                           np.finfo(np.float32).max], dtype=np.float32)
        decoded = np.fromstring(vector_literal(values)[1:-1], sep=",", dtype=np.float32)
        np.testing.assert_array_equal(decoded, values)

    def test_result_cardinality_and_ids(self):
        self.assertEqual(validate_result([(0,), (2,)], 2, 3), [0, 2])
        for rows in ([(0,)], [(0,), (0,)], [(0,), (3,)], [(-1,), (2,)]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                validate_result(rows, 2, 3)

    def test_gpu_trace_must_belong_to_this_query(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.log"
            path.write_bytes(b"cuvs_build handle=1\ncuvs_serve handle=1\n")
            offset = check_gpu_trace(path, 0, need_build=True)
            with path.open("ab") as trace:
                trace.write(b"knn_simple handle=1\n")
            with self.assertRaises(RuntimeError):
                check_gpu_trace(path, offset)
            path.write_bytes(b"cuvs_serve handle=1\n")
            with self.assertRaises(RuntimeError):
                check_gpu_trace(path, 0, need_build=True)
            path.write_bytes(b"cuvs_raw_batch handle=1\n")
            self.assertEqual(check_gpu_trace(path, 0, marker=b"cuvs_raw_batch"), path.stat().st_size)
            with self.assertRaises(RuntimeError):
                check_gpu_trace(path, 0)


if __name__ == "__main__":
    unittest.main()
