import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "src" / "stage2" / "make_event_returns.py"
SPEC = importlib.util.spec_from_file_location("make_event_returns", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EventReturnTests(unittest.TestCase):
    def test_event_windows_sum_log_returns(self):
        rows = []
        dates = [
            "2025-02-18", "2025-02-19", "2025-03-13", "2025-03-25",
            "2025-04-08", "2025-04-09", "2025-04-21", "2025-12-31",
        ]
        for symbol, scale in [("AAA", 1.0), ("BBB", 2.0)]:
            prices = scale * np.array([100, 110, 121, 133.1, 146.41, 161.051, 177.1561, 194.87171])
            rows.extend(
                {"symbol": symbol, "date": date, "adjClose": price}
                for date, price in zip(dates, prices)
            )

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "prices.csv"
            output_path = Path(tmp) / "events.csv"
            pd.DataFrame(rows).to_csv(input_path, index=False)
            result = MODULE.make_event_returns(input_path, output_path).set_index("symbol")

            self.assertTrue(output_path.exists())
            self.assertEqual(list(result.index), ["AAA", "BBB"])
            self.assertAlmostEqual(result.loc["AAA", "S1_Decline"], 1 * np.log(1.1))
            self.assertAlmostEqual(result.loc["AAA", "S3_Policy_Shock_Jump"], 1 * np.log(1.1))
            self.assertAlmostEqual(result.loc["AAA", "S5_Long_Term_Adjustment"], 6 * np.log(1.1))
            pd.testing.assert_series_equal(result.loc["AAA"], result.loc["BBB"], check_names=False)

    def test_missing_required_column_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.csv"
            pd.DataFrame({"symbol": ["AAA"], "date": ["2025-01-01"]}).to_csv(input_path, index=False)
            with self.assertRaisesRegex(ValueError, "adjClose"):
                MODULE.make_event_returns(input_path, Path(tmp) / "out.csv")


if __name__ == "__main__":
    unittest.main()
