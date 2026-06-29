import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKING_API_SCRIPTS = [
    ROOT / "src" / "stage1" / "sp500_metrics.py",
    ROOT / "src" / "stage1" / "enrich_for_analysis.py",
    ROOT / "src" / "stage2" / "sp500_daily_prices.py",
]


class ApiSecurityTests(unittest.TestCase):
    def test_working_code_uses_stable_fmp_api(self):
        for path in WORKING_API_SCRIPTS:
            with self.subTest(path=path.name):
                source = path.read_text()
                self.assertIn("https://financialmodelingprep.com/stable", source)
                self.assertNotIn("https://financialmodelingprep.com/api/v3", source)

    def test_api_key_is_not_added_to_query_parameters(self):
        for path in WORKING_API_SCRIPTS:
            with self.subTest(path=path.name):
                source = path.read_text()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                        continue
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if not any(isinstance(target, ast.Name) and target.id == "params" for target in targets):
                        continue
                    value = node.value
                    names = {item.id for item in ast.walk(value) if isinstance(item, ast.Name)}
                    strings = {item.value for item in ast.walk(value) if isinstance(item, ast.Constant) and isinstance(item.value, str)}
                    self.assertNotIn("API_KEY", names)
                    self.assertNotIn("apikey", strings)


if __name__ == "__main__":
    unittest.main()
