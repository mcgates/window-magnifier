import os, sys, unittest, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magnifier import crop_rect, Magnifier, Gst, QApplication

class MagnifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gst.init(None)
        cls.app = QApplication.instance() or QApplication([])

    def test_crop_edges_and_zoom(self):
        rect = crop_rect((0, 0), (600, 300), 3, (1920, 1080))
        self.assertEqual((rect.x(),rect.y(),rect.width(),rect.height()),(0,0,200,100))
        rect = crop_rect((9999,9999),(600,300),3,(1920,1080))
        self.assertEqual((rect.x(),rect.y()),(1720,980))
        rect = crop_rect((-300,-300),(600,300),1,(80,60))
        self.assertEqual((rect.x(),rect.y(),rect.width(),rect.height()),(0,0,80,60))

    def test_live_frame_conversion_and_freeze(self):
        window = Magnifier(demo=True)
        window.image = None
        pipeline = Gst.parse_launch('videotestsrc pattern=red num-buffers=3 ! video/x-raw,format=BGRA,width=640,height=480 ! appsink name=frames emit-signals=true sync=false')
        sink = pipeline.get_by_name('frames')
        sink.connect('new-sample',window.new_sample)
        pipeline.set_state(Gst.State.PLAYING)
        deadline = time.monotonic()+3
        while time.monotonic()<deadline and window.latest is None:
            time.sleep(.01)
        self.assertIsNotNone(window.latest)
        window.tick()
        self.assertEqual(window.image.size().width(),640)
        color=window.image.pixelColor(50,50)
        self.assertGreater(color.red(),240)
        self.assertLess(color.blue(),10)
        old=window.image
        window.pause.setChecked(True)
        window.latest=old.copy()
        window.tick()
        self.assertIs(window.image,old)
        pipeline.set_state(Gst.State.NULL)
        window.close()

if __name__=='__main__': unittest.main()
