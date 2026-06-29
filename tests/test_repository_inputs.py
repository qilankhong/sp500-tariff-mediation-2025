import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class RepositoryInputTests(unittest.TestCase):
    def test_frozen_universe_has_503_unique_symbols(self):
        symbols = (ROOT / "data" / "reference" / "sp500_2025_symbols.txt").read_text().splitlines()
        self.assertEqual(len(symbols), 503)
        self.assertEqual(len(set(symbols)), 503)
        self.assertTrue(all(symbol and symbol == symbol.upper() for symbol in symbols))

    def test_real_environment_file_is_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".env", gitignore)
        self.assertEqual(
            (ROOT / ".env.example").read_text().split("=", 1)[-1].strip(),
            "replace_with_your_fmp_api_key",
        )


if __name__ == "__main__":
    unittest.main()
