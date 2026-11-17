import unittest
import struct
from etiquetas import render_label, escpos


def black_bounds(image):
    from PIL import ImageOps
    return ImageOps.invert(image.convert('L')).getbbox()


class GeometryTests(unittest.TestCase):
    def test_pitch_and_white_gap(self):
        label = render_label(58, 30, 'Café', 10, gap='2,5')
        self.assertEqual(label.size, (384, 260))
        self.assertIsNone(black_bounds(label.crop((0, 240, 384, 260))))
        data = escpos(label)
        pos, height = 5, 0
        while pos < len(data):
            self.assertEqual(data[pos:pos + 4], b'\x1dv0\x00')
            width_bytes, rows = struct.unpack('<HH', data[pos + 4:pos + 8])
            pos += 8 + width_bytes * rows
            height += rows
        self.assertEqual(height, 260)
        self.assertEqual(pos, len(data))

    def test_offset_moves_ink_without_changing_pitch(self):
        images = [render_label(58, 30, 'Texto', 10, gap=2, offset=offset) for offset in (-2, 0, 2)]
        self.assertTrue(all(im.size == (384, 256) for im in images))
        bounds = [black_bounds(im) for im in images]
        self.assertEqual(bounds[1][1] - bounds[0][1], 16)
        self.assertEqual(bounds[2][1] - bounds[1][1], 16)

    def test_clipping_and_invalid_geometry_are_rejected(self):
        for kwargs in ({'gap': -1}, {'gap': 21}, {'offset': 20}, {'offset': -20}, {'offset': 'nan'}):
            with self.assertRaises(ValueError):
                render_label(58, 30, 'Texto', 10, **kwargs)


if __name__ == '__main__':
    unittest.main()
