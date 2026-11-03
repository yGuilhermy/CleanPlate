import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import numpy as np
from PIL import Image
from cleanplate.engine import Settings
from cleanplate.media import (build_background, export_video, probe, read_frame,
                              run, executable, Cancelled, CREATE_FLAGS)


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.plate = np.full((64, 80, 3), [40, 80, 100], np.uint8)
        Image.fromarray(cls.plate).save(cls.root / 'plate.png')
        cls.frames = []
        for index in range(10):
            frame = cls.plate.copy()
            frame[16:48, 20 + index:40 + index] = [210, 40, 20]
            cls.frames.append(frame)
        args = [executable('ffmpeg'), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                '-s', '80x64', '-r', '10', '-i', 'pipe:0', '-f', 'lavfi', '-i',
                'sine=frequency=440:duration=1', '-c:v', 'ffv1', '-c:a', 'pcm_s16le',
                '-shortest', str(cls.root / 'source.mkv')]
        result = subprocess.run(args, input=b''.join(f.tobytes() for f in cls.frames),
                                capture_output=True, creationflags=CREATE_FLAGS)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_probe_and_seek(self):
        info = probe(self.root / 'source.mkv')
        self.assertEqual((info['width'], info['height']), (80, 64))
        np.testing.assert_array_equal(read_frame(self.root / 'source.mkv', .5), self.frames[5])

    def test_reference_take(self):
        # Explicitly use a static empty take, not the subject clip.
        empty = self.root / 'empty.mkv'
        run([executable('ffmpeg'), '-v', 'error', '-y', '-loop', '1', '-i',
             str(self.root / 'plate.png'), '-t', '1', '-r', '10', '-c:v', 'ffv1', str(empty)])
        bg = build_background(empty, duration=.8, samples=4)
        self.assertEqual(bg.samples, 4)
        np.testing.assert_allclose(bg.mean, self.plate, atol=2)

    def test_prores_alpha_audio_and_matte_export(self):
        bg = build_background(self.root / 'plate.png')
        out = self.root / 'recorte.mov'
        # Saved nonzero styling values must not leak into the exported alpha when OFF.
        settings = Settings(feather=0, outline=8, shadow=.8, glow=.8,
                            outline_enabled=False, shadow_enabled=False, glow_enabled=False)
        count = export_video(self.root / 'source.mkv', out, bg, settings)
        self.assertEqual(count, 10)
        data = json.loads(run([executable('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', str(out)]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        self.assertEqual(video['codec_name'], 'prores')
        self.assertIn('yuva', video['pix_fmt'])
        self.assertEqual(int(video['nb_frames']), 10)
        self.assertTrue(any(s['codec_type'] == 'audio' for s in data['streams']))
        raw = run([executable('ffmpeg'), '-v', 'error', '-i', str(out), '-frames:v', '1',
                   '-pix_fmt', 'rgba', '-f', 'rawvideo', 'pipe:1'])
        rgba = np.frombuffer(raw, np.uint8).reshape(64, 80, 4)
        self.assertLess(int(rgba[0, 0, 3]), 2)
        self.assertGreater(int(rgba[32, 30, 3]), 253)
        self.assertLess(int(rgba[32, 18, 3]), 2)
        mask = self.root / 'matte.mp4'
        self.assertEqual(export_video(self.root / 'source.mkv', mask, bg, Settings(feather=0), 'matte'), 10)
        frame = read_frame(mask)
        self.assertLess(int(frame[0, 0, 0]), 5)
        self.assertGreater(int(frame[32, 30, 0]), 250)

    def test_cancellation_preserves_existing_output(self):
        out = self.root / 'cancel.mov'
        out.write_bytes(b'original')
        event = threading.Event()
        def progress(_):
            event.set()
        with self.assertRaises(Cancelled):
            export_video(self.root / 'source.mkv', out, build_background(self.root / 'plate.png'),
                         Settings(), cancel=event, progress=progress)
        self.assertEqual(out.read_bytes(), b'original')
        self.assertFalse(list(self.root.glob('*.partial.*')))

    def test_solid_colors_and_audio(self):
        bg = build_background(self.root/'plate.png')
        for color, expected in [('#00ff00',[0,255,0]),('#000000',[0,0,0]),('#315b9a',[49,91,154])]:
            out = self.root / ('solid'+color[1:]+'.mp4')
            self.assertEqual(export_video(self.root/'source.mkv',out,bg,Settings(feather=0),
                'solid',background_color=color,quality=16,audio=True),10)
            np.testing.assert_allclose(read_frame(out)[0,0],expected,atol=7)
            data=json.loads(run([executable('ffprobe'),'-v','error','-show_streams','-of','json',str(out)]))
            self.assertTrue(any(s['codec_type']=='audio' for s in data['streams']))

    def test_rotated_phone_video(self):
        base = self.root/'phone-base.mp4'
        run([executable('ffmpeg'),'-v','error','-y','-i',str(self.root/'source.mkv'),
             '-c:v','libx264','-c:a','aac',str(base)])
        rotated = self.root/'rotated.mov'
        run([executable('ffmpeg'),'-v','error','-y','-display_rotation','90','-i',str(base),
             '-c','copy',str(rotated)])
        info = probe(rotated)
        self.assertEqual((info['width'],info['height']),(64,80))
        frame=read_frame(rotated,info=info)
        self.assertEqual(frame.shape,(80,64,3))
        from cleanplate.engine import Background
        plate=np.rot90(self.plate)
        out=self.root/'rotated-result.mp4'
        export_video(rotated,out,Background.from_frames([plate]),Settings(feather=0),'solid',background_color='#00ff00')
        self.assertEqual((probe(out)['width'],probe(out)['height']),(64,80))


if __name__ == '__main__':
    unittest.main()
