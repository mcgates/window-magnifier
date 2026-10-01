import os,sys,unittest
from unittest.mock import Mock
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from magnifier import Magnifier,QApplication,Gst
class RecoveryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  Gst.init(None)
  cls.app=QApplication.instance() or QApplication([])
 def test_resume_discards_stale_capture(self):
  w=Magnifier(demo=True)
  pipeline=Mock()
  w.pipeline=pipeline
  w.last_tick=100
  self.assertFalse(w.check_capture_health(115))
  self.assertIsNone(w.pipeline)
  self.assertIsNone(w.image)
  self.assertEqual(w.choose.text(),'Reconnect screen')
  self.assertTrue(w.choose.isEnabled())
  pipeline.set_state.assert_called_with(Gst.State.NULL)
  w.close()
 def test_static_screen_is_not_mistaken_for_failure(self):
  w=Magnifier(demo=True)
  w.pipeline=Mock()
  w.capture_started_at=1
  w.received_frame=True
  w.last_tick=1000
  self.assertTrue(w.check_capture_health(1001))
  w.close()
 def test_missing_initial_frame_can_be_retried(self):
  w=Magnifier(demo=True)
  w.pipeline=Mock()
  w.capture_started_at=100
  w.last_tick=115
  self.assertFalse(w.check_capture_health(116))
  self.assertIn('No video arrived',w.status.text())
  w.close()
if __name__=='__main__': unittest.main()
