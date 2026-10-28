import copy
import unittest

from compare_runs import compare, summarize


def fixture(build, qps=100.0, recall=1.0):
    return {"status": "PASS", "timing": {"build_total_sec": build},
            "recall": {f"recall@{k}": recall for k in ("10", "100")},
            "batch_query": {k: {"recall": [recall] * 3, "qps": qps,
                                "call_p50_ms": 1000.0, "call_p95_ms": 1100.0}
                            for k in ("10", "100")},
            "query_qps": {k: qps for k in ("10", "100")},
            "query_latency_by_k_ms": {k: {"p50": 1.0, "p95": 2.0} for k in ("10", "100")}}


class ColdRunGatesTest(unittest.TestCase):
    def test_median_does_not_select_fastest_run(self):
        base = [fixture(x) for x in (10.0, 20.0, 100.0)]
        candidate = [fixture(x) for x in (1.0, 10.0, 11.0)]
        self.assertEqual(compare(base, candidate)["build_speedup"], 2.0)
        with self.assertRaises(ValueError):
            summarize(candidate[:1])

    def test_one_bad_recall_run_is_rejected(self):
        base = [fixture(20.0) for _ in range(3)]
        candidate = [fixture(10.0) for _ in range(3)]
        candidate[2]["recall"]["recall@100"] = 0.9949
        self.assertFalse(compare(base, candidate)["gates"]["recall"])
        candidate[2]["recall"]["recall@100"] = 0.995
        self.assertTrue(compare(base, candidate)["gates"]["recall"])
        candidate[2]["batch_query"]["10"]["recall"][1] = 0.994
        self.assertFalse(compare(base, candidate)["development_pass"])

    def test_both_topk_throughput_gates_apply(self):
        base = [fixture(20.0) for _ in range(3)]
        candidate = [fixture(10.0, qps=90.0) for _ in range(3)]
        self.assertTrue(compare(base, candidate)["development_pass"])
        slower = copy.deepcopy(candidate)
        for run in slower:
            run["batch_query"]["100"]["qps"] = 89.9
        self.assertFalse(compare(base, slower)["gates"]["batch_query"])


if __name__ == "__main__":
    unittest.main()
