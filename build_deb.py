#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parent
out=root/'dist'
out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
 stage=Path(tmp)
 app=stage/'usr/share/window-magnifier'
 app.mkdir(parents=True)
 shutil.copy2(root/'magnifier.py',app/'magnifier.py')
 doc=stage/'usr/share/doc/window-magnifier'
 doc.mkdir(parents=True)
 shutil.copy2(root/'LICENSE',doc/'copyright')
 for rel in ['usr/bin','usr/share/applications','usr/share/icons/hicolor/scalable/apps','DEBIAN']:
  (stage/rel).mkdir(parents=True,exist_ok=True)
 wrapper=stage/'usr/bin/window-magnifier'
 wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/window-magnifier/magnifier.py "$@"\n')
 wrapper.chmod(0o755)
 shutil.copy2(root/'icon.svg',stage/'usr/share/icons/hicolor/scalable/apps/local.window-magnifier.svg')
 (stage/'usr/share/applications/local.window-magnifier.desktop').write_text('[Desktop Entry]\nType=Application\nName=Window Magnifier\nExec=window-magnifier\nIcon=local.window-magnifier\nTerminal=false\nCategories=Utility;Accessibility;\n')
 (stage/'DEBIAN/control').write_text('Package: window-magnifier\nVersion: 0.1.0\nSection: utils\nPriority: optional\nArchitecture: all\nMaintainer: Window Magnifier contributors\nDepends: python3, python3-pyqt6, python3-gi, python3-dbus, gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-base, gstreamer1.0-pipewire, xdg-desktop-portal-kde\nDescription: Separate live magnifier window for KDE Wayland\n Magnify screen content with pointer tracking, panning and global shortcuts.\n')
 subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(out/'window-magnifier_0.1.0_all.deb')],check=True)
