import unittest
import numpy as np
from cleanplate.engine import Background, Settings, matte, composite
from cleanplate.preview import calculate


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.plate = np.full((80, 120, 3), 40, np.uint8)
        self.frame = self.plate.copy()
        self.frame[20:60, 40:80] = [200, 60, 40]
        self.background = Background.from_frames([self.plate])
        self.settings = Settings(outline=5, outline_enabled=False,
                                 shadow=.8, shadow_enabled=False, glow=.8, glow_enabled=False)

    def test_preview_and_export_share_effect_switches(self):
        _, rgba = calculate(self.frame, self.background, self.settings, 'Recorte', 'Transparência')
        alpha, _ = matte(self.frame, self.background, self.settings)
        np.testing.assert_array_equal(rgba, composite(self.frame, alpha, self.settings))

    def test_backdrop_does_not_change_alpha(self):
        for color in ('Escuro', 'Claro', 'Verde', 'Transparência'):
            result, rgba = calculate(self.frame, self.background, self.settings, 'Recorte', color)
            self.assertEqual(int(rgba[0, 0, 3]), 0)
            self.assertGreater(int(result[0, 0].sum()), 0)

    def test_compare_and_preview_scaling(self):
        compare, _ = calculate(self.frame, self.background, self.settings, 'Comparar', 'Escuro')
        np.testing.assert_array_equal(compare[:, :60], self.frame[:, :60])
        image, rgba = calculate(self.frame, self.background, self.settings, 'Recorte', 'Escuro', limit=60)
        self.assertEqual(image.shape, (40, 60, 3))
        self.assertEqual(rgba.shape, (40, 60, 4))

    def test_refined_preview_matches_full_resolution_structure(self):
        import importlib.util
        if not importlib.util.find_spec('cv2'):
            self.skipTest('OpenCV required')
        from PIL import Image
        frame = np.full((480, 640, 3), 200, np.uint8)
        plate = frame.copy()
        frame[80:400, 160:480] = [60, 40, 20]
        frame[120:160, 200:240] = 200  # Keep this genuine large opening.
        frame[200:205, 300:305] = 200  # Optional small-hole repair.
        settings = Settings(refine_foreground=True, refine_radius=12,
                            edge_refinement=3, hole_area=100, feather=0)
        model = Background.from_frames([plate])
        _, full = calculate(frame, model, settings, 'Recorte', '#00ff00')
        _, small = calculate(frame, model, settings, 'Recorte', '#00ff00', limit=320)
        expected = np.asarray(Image.fromarray(full[..., 3]).resize((320, 240))) > 127
        actual = small[..., 3] > 127
        self.assertGreater(np.count_nonzero(expected & actual) / np.count_nonzero(expected | actual), .98)
        self.assertEqual(small[70, 110, 3], 0)
        self.assertEqual(small[101, 151, 3], 255)


if __name__ == '__main__':
    unittest.main()
