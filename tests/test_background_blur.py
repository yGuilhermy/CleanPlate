import unittest
from dataclasses import replace
import numpy as np
from cleanplate.engine import Background, Settings, matte, composite, blurred_background
from cleanplate.preview import calculate


class BackgroundBlurTests(unittest.TestCase):
    def setUp(self):
        yy, xx = np.indices((100, 160))
        self.plate = np.repeat(np.uint8(((xx//4+yy//4)%2)*180+30)[...,None],3,axis=2)
        self.frame = self.plate.copy()
        self.frame[25:75,55:105] = [220,40,20]
        self.bg = Background.from_frames([self.plate])
        self.settings = Settings(feather=0, background_blur=8)

    def test_subject_sharp_background_smooth_and_no_subject_ghost(self):
        alpha,_ = matte(self.frame,self.bg,self.settings)
        rgba = composite(self.frame,alpha,self.settings)
        result = blurred_background(self.frame,rgba,self.bg,self.settings)
        np.testing.assert_array_equal(result[35:65,65:95],self.frame[35:65,65:95])
        self.assertLess(result[:20,:40].std(),self.frame[:20,:40].std()/5)
        self.assertLess(abs(int(result[50,53,0])-int(result[50,53,1])),2)
        zero = blurred_background(self.frame,rgba,self.bg,replace(self.settings,background_blur=0))
        np.testing.assert_array_equal(zero,self.frame)

    def test_preview_uses_same_composition_and_blur_validation(self):
        result,rgba = calculate(self.frame,self.bg,self.settings,'Recorte','Desfocado')
        np.testing.assert_array_equal(result,blurred_background(self.frame,rgba,self.bg,self.settings))
        for radius in [-1,101,float('nan')]:
            with self.assertRaises(ValueError):
                replace(self.settings,background_blur=radius).validate()


if __name__=='__main__': unittest.main()
