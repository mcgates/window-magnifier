import os,sys,tempfile,unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unittest.mock import patch
from magnifier import Magnifier,QSettings,QApplication,Gst
class SettingsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  Gst.init(None)
  cls.app=QApplication.instance() or QApplication([])
 def test_settings_survive_relaunch_and_tracking_failure(self):
  with tempfile.TemporaryDirectory() as folder, patch('magnifier.dbus.SessionBus',side_effect=RuntimeError('No desktop in test')):
   path=folder+'/prefs.ini'
   first=Magnifier(settings=QSettings(path,QSettings.Format.IniFormat))
   first.resize(850,560)
   first.zoom.setValue(5.5)
   first.follow.setChecked(False)
   first.smooth.setChecked(True)
   first.close()
   second=Magnifier(settings=QSettings(path,QSettings.Format.IniFormat))
   self.assertEqual(second.size().width(),850)
   self.assertEqual(second.size().height(),560)
   self.assertEqual(second.zoom.value(),5.5)
   self.assertFalse(second.follow.isChecked())
   self.assertTrue(second.smooth.isChecked())
   second.follow.setChecked(True)
   second.save_settings()
   second.follow.setEnabled(False)
   second.follow.setChecked(False)
   second.close()
   settings=QSettings(path,QSettings.Format.IniFormat)
   self.assertTrue(settings.value('follow_mouse',type=bool))
if __name__=='__main__': unittest.main()
