import importlib.util
import unittest
from dataclasses import replace

import numpy as np
from cleanplate.engine import Background, Settings, matte


@unittest.skipUnless(importlib.util.find_spec('cv2'), 'OpenCV desktop dependency required')
class SegmentationTests(unittest.TestCase):
    def test_recovers_solid_subject_patch_matching_reference_without_filling_real_gap(self):
        plate = np.full((160, 180, 3), 210, np.uint8)
        plate[70:83, 80:93] = [75, 45, 30]
        frame = np.full_like(plate, 210)
        frame[30:140, 35:145] = [75, 45, 30]
        frame[40:65, 50:70] = 210  # Genuine opening, not a hole to fill.
        bg = Background.from_frames([plate])
        settings = Settings(threshold=12, softness=10, feather=0, refine_radius=10)
        original, _ = matte(frame, bg, settings)
        result, _ = matte(frame, bg, replace(settings, refine_foreground=True))
        self.assertEqual(original[76, 85], 0)
        self.assertEqual(result[76, 85], 1)
        self.assertEqual(result[50, 60], 0)
        self.assertEqual(result[10, 10], 0)
        self.assertEqual(result[100, 100], 1)

    def test_no_reliable_seed_keeps_difference_result_and_is_stateless(self):
        plate = np.full((80, 100, 3), 90, np.uint8)
        bg = Background.from_frames([plate])
        settings = Settings(feather=0)
        for frame in [plate.copy(), plate+30, plate+150]:
            expected, _ = matte(frame, bg, settings)
            actual, _ = matte(frame, bg, replace(settings, refine_foreground=True))
            np.testing.assert_array_equal(actual, expected)
        frame = plate.copy()
        frame[20:60, 20:70] = [220, 20, 20]
        settings.refine_foreground = True
        first, _ = matte(frame, bg, settings)
        matte(plate, bg, settings)
        second, _ = matte(frame, bg, settings)
        np.testing.assert_array_equal(first, second)

    def test_small_holes_preserves_large_openings_and_boundary_background(self):
        from cleanplate.segmentation import fill_small_holes
        alpha = np.ones((100, 100), np.float32)
        alpha[10:13, 10:13] = 0
        alpha[30:60, 30:60] = 0
        alpha[0:2, 70:73] = 0
        original = alpha.copy()
        result = fill_small_holes(alpha, 20)
        self.assertEqual(result[11, 11], 1)
        self.assertEqual(result[40, 40], 0)
        self.assertEqual(result[1, 71], 0)
        np.testing.assert_array_equal(alpha, original)
        np.testing.assert_array_equal(fill_small_holes(alpha, 0), alpha)

    def test_noise_does_not_exhaust_background_seeds(self):
        # Every background pixel exceeds the strict .65*threshold cutoff. A
        # safely eroded seed within the user tolerance still permits recovery.
        plate = np.full((160, 180, 3), 210, np.uint8)
        plate[70:83, 80:93] = [75, 45, 30]
        frame = np.full_like(plate, 219)
        frame[30:140, 35:145] = [75, 45, 30]
        settings = Settings(threshold=12, softness=10, feather=0, refine_radius=10,
                            refine_foreground=True)
        alpha, _ = matte(frame, Background.from_frames([plate]), settings)
        self.assertEqual(alpha[76, 85], 1)
        self.assertEqual(alpha[10, 10], 0)

    def test_multiple_objects_retained_unless_largest_requested(self):
        plate = np.full((160, 180, 3), 210, np.uint8)
        frame = plate.copy()
        frame[20:110, 20:70] = [80, 30, 30]
        frame[40:80, 110:145] = [20, 20, 80]
        bg = Background.from_frames([plate])
        settings = Settings(refine_foreground=True, feather=0, refine_radius=10)
        alpha, _ = matte(frame, bg, settings)
        self.assertEqual(alpha[60, 120], 1)
        alpha, _ = matte(frame, bg, replace(settings, keep_largest=True))
        self.assertEqual(alpha[60, 120], 0)
        self.assertEqual(alpha[60, 40], 1)

    def test_new_settings_validate_and_round_trip(self):
        import json
        settings = Settings(refine_foreground=True, edge_refinement=3, hole_area=600)
        self.assertEqual(Settings(**json.loads(json.dumps(settings.to_dict()))), settings)
        for field, value in [('refine_foreground', 1), ('edge_refinement', -1),
                             ('refine_radius', 0), ('hole_area', .1)]:
            with self.assertRaises(ValueError):
                replace(settings, **{field: value}).validate()


if __name__ == '__main__':
    unittest.main()
