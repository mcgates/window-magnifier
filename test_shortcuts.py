import os,sys,unittest
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from magnifier import Magnifier,QApplication,Gst
class ShortcutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  Gst.init(None)
  cls.app=QApplication.instance() or QApplication([])
 def test_visibility_and_freeze_preserve_view(self):
  w=Magnifier(demo=True)
  w.show()
  old=w.image
  w.toggle_visibility()
  self.assertFalse(w.isVisible())
  w.toggle_visibility()
  self.assertTrue(w.isVisible())
  w.toggle_freeze()
  self.assertTrue(w.pause.isChecked())
  w.toggle_freeze()
  self.assertFalse(w.pause.isChecked())
  self.assertIs(w.image,old)
  w.close()
if __name__=='__main__': unittest.main()
