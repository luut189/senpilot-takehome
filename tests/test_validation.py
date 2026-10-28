"""Pure tests runnable with pytest or stdlib unittest when PyPI is blocked."""

import unittest
from pathlib import PurePath

from senpilot.scraper.validation import CATEGORIES, normalize_matter, parse_counts, safe_filename


class ValidationTests(unittest.TestCase):
    def test_matter_case_and_whitespace(self):
        self.assertEqual(normalize_matter(" m12205 "), "M12205")

    def test_invalid_matters(self):
        for value in ("M1234", "M123456", "M１２２０５", "X12205", "M12205/M12383", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_matter(value)

    def test_counts_from_observed_button_labels(self):
        self.assertEqual(
            parse_counts(
                [
                    "Exhibits - 13",
                    "Key Documents - 6",
                    "Other Documents - 43",
                    "Transcripts - 0",
                    "Recordings - 0",
                    "Search",
                    "Related Matters",
                ]
            ),
            dict(zip(CATEGORIES, (13, 6, 43, 0, 0), strict=True)),
        )

    def test_missing_count_is_not_zero(self):
        with self.assertRaises(ValueError):
            parse_counts([f"{c} - 0" for c in CATEGORIES[:-1]])

    def test_duplicate_count_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_counts([f"{c} - 1" for c in CATEGORIES] + ["Exhibits - 1"])

    def test_unrecognized_count_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_counts([f"{c} - unknown" for c in CATEGORIES])

    def test_filename_cannot_escape_directory(self):
        for name in ("../../file.pdf", "..\\file.pdf", "/tmp/file.pdf", "a\x00b.pdf"):
            with self.subTest(name=name):
                result = safe_filename(name)
                self.assertEqual(PurePath(result).name, result)
                self.assertNotIn("\\", result)
                self.assertNotIn("\x00", result)
                self.assertTrue(result.endswith(".pdf"))

    def test_filename_length_and_extension(self):
        result = safe_filename("a" * 400 + ".pdf")
        self.assertLessEqual(len(result), 170)
        self.assertTrue(result.endswith(".pdf"))

    def test_reserved_and_empty_filenames(self):
        self.assertEqual(safe_filename("CON.pdf"), "_CON.pdf")
        self.assertEqual(safe_filename("..."), "document")


if __name__ == "__main__":
    unittest.main()
