import unittest
import numpy as np
from cleanplate.engine import Settings, Background, matte, composite, checker_preview


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.plate = np.full((64, 80, 3), [40, 80, 100], np.uint8)
        self.frame = self.plate.copy()
        self.frame[16:48, 25:55] = [210, 40, 20]
        self.bg = Background.from_frames([self.plate])
        self.settings = Settings(feather=0)

    def test_background_transparent_subject_opaque(self):
        alpha, _ = matte(self.frame, self.bg, self.settings)
        self.assertEqual(float(alpha[0, 0]), 0)
        self.assertTrue(np.all(alpha[16:48, 25:55] == 1))
        rgba = composite(self.frame, alpha, self.settings)
        np.testing.assert_array_equal(rgba[0, 0], [0, 0, 0, 0])
        np.testing.assert_array_equal(rgba[32, 40], [210, 40, 20, 255])

    def test_statistical_noise(self):
        frames = [np.full((20, 20, 3), level, np.uint8) for level in (80, 100, 120)]
        bg = Background.from_frames(frames)
        np.testing.assert_allclose(bg.mean, 100)
        np.testing.assert_allclose(bg.deviation, 20)
        alpha, _ = matte(frames[-1], bg, Settings(threshold=1, softness=1, feather=0))
        self.assertFalse(alpha.any())

    def test_alignment_and_unknown_area(self):
        plate = np.zeros((64, 80, 3), np.uint8)
        plate[:, 20:40] = 180
        frame = np.zeros_like(plate)
        frame[:, 23:43] = 180
        bg = Background.from_frames([plate])
        alpha, _ = matte(frame, bg, Settings(offset_x=3, feather=0))
        self.assertEqual(float(alpha[:, 5:].sum()), 0)
        self.assertTrue(np.all(alpha[:, :3] == 1))

    def test_softness_and_determinism(self):
        first = matte(self.frame, self.bg, self.settings)[0]
        matte(self.plate, self.bg, self.settings)
        second = matte(self.frame, self.bg, self.settings)[0]
        np.testing.assert_array_equal(first, second)
        plate = np.zeros((4, 4, 3), np.uint8)
        a, _ = matte(plate + 30, Background.from_frames([plate]),
                     Settings(threshold=20, softness=20, feather=0))
        np.testing.assert_allclose(a, .5, atol=.003)

    def test_effects_extend_alpha_without_wrapping(self):
        alpha, _ = matte(self.frame, self.bg, self.settings)
        output = composite(self.frame, alpha, Settings(outline=4, shadow=.6, glow=.5))
        self.assertGreater(int(output[32, 23, 3]), 0)
        np.testing.assert_array_equal(output[32, 40, :3], self.frame[32, 40])
        from cleanplate.engine import _shift
        point = np.zeros((10, 10), np.float32)
        point[9, 9] = 1
        self.assertEqual(float(_shift(point, 2, 2).sum()), 0)
        self.assertEqual(checker_preview(output).shape, self.frame.shape)

    def test_bad_resolution_and_settings_rejected(self):
        with self.assertRaises(ValueError):
            matte(self.frame[:10], self.bg, self.settings)
        for settings in [Settings(scale=0), Settings(softness=0), Settings(threshold=float('nan')),
                         Settings(outline=1.5), Settings(outline_color='invalid')]:
            with self.assertRaises(ValueError):
                settings.validate()

    def test_effect_switches_remove_all_styling_even_with_nonzero_values(self):
        from dataclasses import replace
        alpha, _ = matte(self.frame, self.bg, self.settings)
        enabled = Settings(outline=6, shadow=.8, glow=.9, outline_color='#56d4ed')
        disabled = replace(enabled, outline_enabled=False, shadow_enabled=False, glow_enabled=False)
        result = composite(self.frame, alpha, disabled)
        np.testing.assert_array_equal(result, composite(self.frame, alpha, Settings()))
        np.testing.assert_array_equal(result[..., 3], np.uint8(alpha * 255))
        self.assertGreater(composite(self.frame, alpha, enabled)[32, 22, 3], 0)
        # Project serialization preserves explicit OFF, including nonzero stored values.
        import json
        restored = Settings(**json.loads(json.dumps(disabled.to_dict())))
        np.testing.assert_array_equal(result, composite(self.frame, alpha, restored))

    def test_each_switch_is_independent(self):
        from dataclasses import replace
        alpha, _ = matte(self.frame, self.bg, self.settings)
        for name in ('outline', 'shadow', 'glow'):
            configured = Settings(outline=5, shadow=.8, glow=.8,
                                  outline_enabled=False, shadow_enabled=False, glow_enabled=False)
            toggled = replace(configured, **{name + '_enabled': True})
            expected = Settings(**{name: getattr(configured, name)})
            np.testing.assert_array_equal(composite(self.frame, alpha, toggled),
                                          composite(self.frame, alpha, expected))

    def test_light_compensation_with_large_dark_subject(self):
        from cleanplate.engine import compensate_light
        ramp = np.linspace(100, 170, 160, dtype=np.float32)
        plate = np.broadcast_to(ramp[None, :, None], (120, 160, 3)).copy()
        frame = np.clip(plate*1.1+40, 0, 255)
        frame[:, :110] = 20
        calibrated = compensate_light(frame, plate, np.ones((120,160), dtype=bool))
        np.testing.assert_allclose(calibrated[:, 115:], frame[:, 115:], atol=1)

    def test_flatten_alpha_on_custom_background(self):
        from cleanplate.engine import flatten_rgba
        rgba = np.array([[[200,100,50,0],[200,100,50,255],[200,100,50,128]]], np.uint8)
        output = flatten_rgba(rgba, '#00ff00')
        np.testing.assert_array_equal(output[0,0], [0,255,0])
        np.testing.assert_array_equal(output[0,1], [200,100,50])
        np.testing.assert_allclose(output[0,2], [100,177,25], atol=1)


if __name__ == '__main__':
    unittest.main()
