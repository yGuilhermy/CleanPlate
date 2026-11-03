import importlib.util
import unittest

import numpy as np

from cleanplate.edges import refine_alpha


@unittest.skipUnless(importlib.util.find_spec('cv2'), 'Install desktop requirements to test edge refinement')
class EdgeRefinementTests(unittest.TestCase):
    def test_zero_radius_keeps_sub_byte_precision_and_does_not_alias(self):
        alpha = np.linspace(0, 1, 1000, dtype=np.float32).reshape(20, 50)
        frame = np.full(alpha.shape + (3,), 120, np.uint8)
        result = refine_alpha(frame, alpha, 0)
        np.testing.assert_array_equal(result, alpha)
        self.assertEqual(result.dtype, np.float32)
        self.assertFalse(np.shares_memory(result, alpha))

    def test_rgb_edge_preserved_better_than_uniform_blur(self):
        import cv2
        frame = np.zeros((64, 96, 3), np.uint8)
        frame[:, :48] = [180, 50, 20]
        frame[:, 48:] = [20, 50, 180]
        # Both colors have identical grayscale luminance in a mean-RGB model.
        alpha = np.zeros((64, 96), np.float32)
        alpha[:, 48:] = 1
        result = refine_alpha(frame, alpha, 5)
        blurred = cv2.GaussianBlur(alpha, (0, 0), 5)
        self.assertLess(float(result[32, 47]), .02)
        self.assertGreater(float(result[32, 48]), .98)
        self.assertLess(float(np.mean(abs(result-alpha))), float(np.mean(abs(blurred-alpha))))
        np.testing.assert_array_equal(result[:, :35], 0)
        np.testing.assert_array_equal(result[:, 61:], 1)

    def test_constant_guide_has_no_singularities(self):
        frame = np.full((32, 40, 3), 120, np.uint8)
        alpha = np.zeros((32, 40), np.float32)
        alpha[:, 20:] = 1
        result = refine_alpha(frame, alpha, 3)
        self.assertTrue(np.isfinite(result).all())
        self.assertGreater(float(result[16, 19]), 0)
        self.assertLess(float(result[16, 20]), 1)
        self.assertGreaterEqual(float(result.min()), 0)
        self.assertLessEqual(float(result.max()), 1)

    def test_solid_masks_are_exact(self):
        frame = np.random.default_rng(3).integers(0, 256, (29, 37, 3), dtype=np.uint8)
        for value in (0, 1):
            alpha = np.full(frame.shape[:2], value, np.float32)
            np.testing.assert_array_equal(refine_alpha(frame, alpha, 9), alpha)

    def test_tiny_frames_and_fractional_radius(self):
        for shape in [(1, 1), (1, 4), (4, 1), (2, 3)]:
            frame = np.full(shape + (3,), 80, np.uint8)
            alpha = np.full(shape, .12345, np.float32)
            result = refine_alpha(frame, alpha, .5)
            self.assertEqual(result.shape, shape)
            np.testing.assert_allclose(result, alpha, atol=1e-5)

    def test_coarse_coefficients_are_evaluated_on_full_resolution_edge(self):
        frame = np.full((800, 32, 3), 20, np.uint8)
        frame[401:] = 220
        alpha = np.zeros((800, 32), np.float32)
        alpha[401:] = 1
        result = refine_alpha(frame, alpha, 4)
        self.assertEqual(result.shape, alpha.shape)
        self.assertLess(float(result[400, 16]), .03)
        self.assertGreater(float(result[401, 16]), .97)
        np.testing.assert_array_equal(result[:390], 0)
        np.testing.assert_array_equal(result[412:], 1)

    def test_invalid_inputs_rejected(self):
        frame = np.zeros((4, 5, 3), np.uint8)
        alpha = np.zeros((4, 5), np.float32)
        for radius in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                refine_alpha(frame, alpha, radius)
        with self.assertRaises(ValueError):
            refine_alpha(frame[:3], alpha, 1)
        with self.assertRaises(ValueError):
            refine_alpha(frame, alpha + np.nan, 1)


if __name__ == '__main__':
    unittest.main()
