import importlib.util
import unittest
import numpy as np
from cleanplate.engine import Background, Settings, matte


@unittest.skipUnless(importlib.util.find_spec('cv2'), 'Install desktop requirements to test OpenCV features')
class AlignmentTests(unittest.TestCase):
    def test_feature_alignment_with_occluding_subject(self):
        import cv2
        from cleanplate.alignment import estimate_alignment
        rng=np.random.default_rng(42)
        source=rng.integers(20,230,(512,512,3),dtype=np.uint8)
        source=cv2.GaussianBlur(source,(3,3),.7)
        matrix=cv2.getRotationMatrix2D((255.5,255.5),1.8,.96)
        matrix[:,2]+=[4,-5]
        target=cv2.warpAffine(source,matrix,(512,512))
        target[190:330,180:330]=30
        transform,count=estimate_alignment(source,target)
        self.assertGreater(count,10)
        self.assertAlmostEqual(transform['scale'],96,delta=.4)
        self.assertAlmostEqual(transform['rotation'],-1.8,delta=.4)
        self.assertAlmostEqual(transform['offset_x'],4,delta=1)
        self.assertAlmostEqual(transform['offset_y'],-5,delta=1)

    def test_empty_scene_rejects_unreliable_alignment(self):
        from cleanplate.alignment import estimate_alignment
        blank=np.zeros((120,120,3),np.uint8)
        with self.assertRaises(ValueError):
            estimate_alignment(blank,blank)

    def test_optional_largest_component_and_fill(self):
        plate=np.zeros((80,80,3),np.uint8)
        frame=plate.copy()
        frame[15:65,15:65]=220
        frame[30:35,30:35]=0
        frame[4:7,4:7]=220
        bg=Background.from_frames([plate])
        alpha,_=matte(frame,bg,Settings(feather=0,keep_largest=True,fill_holes=True))
        self.assertEqual(alpha[32,32],1)
        self.assertEqual(alpha[5,5],0)
        self.assertEqual(alpha[20,20],1)


if __name__=='__main__':
    unittest.main()
