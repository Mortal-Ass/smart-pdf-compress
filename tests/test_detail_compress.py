"""Run with python -m unittest discover -s tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz
from PIL import ImageChops, ImageStat
from detail_compress import bitmap, detail_candidate, parse_regions


class DetailCompressionTest(unittest.TestCase):
    def test_rotation_crop_and_regions(self):
        with fitz.open() as source, TemporaryDirectory() as temp:
            for angle in (0, 90, 180, 270):
                page = source.new_page(width=260, height=190)
                page.draw_rect(fitz.Rect(70, 30, 120, 85), fill=(1, 0, 0))
                page.set_cropbox(fitz.Rect(30, 20, 230, 170))
                page.set_rotation(angle)
            path = Path(temp) / "result.pdf"
            regions = parse_regions("1:5,5,50,80;2:15,10,60,90", 4)
            detail_candidate(source, path, 1048576, {2}, regions, lambda *a, **k: None)
            self.assertLessEqual(path.stat().st_size, 1048576)
            with fitz.open(path) as result:
                for page, reference in zip(result, source, strict=True):
                    self.assertEqual(page.rotation, reference.rotation)
                    self.assertEqual(page.cropbox, reference.cropbox)
                    diff = ImageChops.difference(bitmap(page, 72)[0], bitmap(reference, 72)[0])
                    self.assertLess(max(ImageStat.Stat(diff).mean), 4)
