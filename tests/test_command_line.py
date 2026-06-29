import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class CommandLineTests(unittest.TestCase):
    def test_python_scripts_show_help_without_api_key(self):
        scripts = [
            ROOT / "src" / "stage1" / "sp500_metrics.py",
            ROOT / "src" / "stage1" / "enrich_for_analysis.py",
            ROOT / "src" / "stage2" / "sp500_daily_prices.py",
            ROOT / "src" / "stage2" / "make_event_returns.py",
        ]
        env = os.environ.copy()
        env.pop("FMP_API_KEY", None)
        for script in scripts:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
