import unittest

from classes.DataClasses import SignaturePlacement
from classes.PdfSigner import PdfSigner


class TestPdfSignerFontSize(unittest.TestCase):
    def test_build_text_lines_scales_with_placeholder_height(self):
        large_box = SignaturePlacement(page_number=0, x=10, y=20, width=120, height=60)
        small_box = SignaturePlacement(page_number=0, x=10, y=20, width=120, height=24)

        large_lines = PdfSigner._build_text_lines("Alice Example", "I reviewed this document", large_box)
        small_lines = PdfSigner._build_text_lines("Alice Example", "I reviewed this document", small_box)

        self.assertGreater(large_lines[0][2], small_lines[0][2])
        self.assertGreaterEqual(large_lines[0][2], 6)
        self.assertLessEqual(small_lines[0][2], 6)

        total_height = (len(large_lines) * large_lines[0][2]) + ((len(large_lines) - 1) * max(0.5, large_lines[0][2] * 0.2))
        self.assertLessEqual(total_height, large_box.height)


if __name__ == "__main__":
    unittest.main()
