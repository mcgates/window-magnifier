#!/usr/bin/env python3
"""Window magnifier for KDE Wayland: portal capture, PipeWire, KWin tracking."""
import os
import sys
import uuid
import tempfile
import threading
import time
from pathlib import Path
import json

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo, GLib
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QSettings, QSize
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QCheckBox, QDoubleSpinBox,
                            QLabel)

APP_ID = os.environ.get('FLATPAK_ID', 'local.WindowMagnifier')
PORTAL = 'org.freedesktop.portal.Desktop'
SCREENCAST = 'org.freedesktop.portal.ScreenCast'
REQUEST = 'org.freedesktop.portal.Request'


def crop_rect(center, view_size, zoom, frame_size):
    """A bounded source rectangle; one logical screen pixel maps to zoom pixels."""
    fw, fh = frame_size
    w, h = min(fw, view_size[0] / zoom), min(fh, view_size[1] / zoom)
    x = min(max(0, center[0] - w / 2), fw - w)
    y = min(max(0, center[1] - h / 2), fh - h)
    return QRectF(x, y, w, h)


class CursorBridge(dbus.service.Object):
    def __init__(self, bus, owner):
        self.owner = owner
        self.name = dbus.service.BusName(f'{APP_ID}.i{owner.instance}', bus)
        super().__init__(bus, '/Cursor')

    @dbus.service.method('local.WindowMagnifier', in_signature='', out_signature='s')
    def State(self):
        return json.dumps({'status': self.owner.status.text(),
            'tracking': self.owner.tracking_available, 'cursor': self.owner.cursor,
            'window': str(self.owner.window_rect), 'live_frame': self.owner.image is not None})

    @dbus.service.method('local.WindowMagnifier', in_signature='', out_signature='')
    def ToggleVisibility(self):
        self.owner.toggle_visibility()

    @dbus.service.method('local.WindowMagnifier', in_signature='', out_signature='')
    def ToggleFreeze(self):
        self.owner.toggle_freeze()

    @dbus.service.method('local.WindowMagnifier', in_signature='', out_signature='')
    def Capture(self):
        self.owner.connect_capture()

    @dbus.service.method('local.WindowMagnifier', in_signature='', out_signature='')
    def Quit(self):
        self.owner.close()

    @dbus.service.method('local.WindowMagnifier', in_signature='s', out_signature='')
    def Position(self, payload):
        data = json.loads(str(payload))
        self.owner.cursor = tuple(data['cursor'])
        self.owner.window_rect = QRectF(*data['window']) if data.get('window') else None
        self.owner.tracking_available = True


class View(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMinimumSize(360, 220)
        self.drag = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#15191f'))
        image = self.owner.image
        if image is None:
            p.setPen(QColor('#e5e9ef'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       'Choose a screen to start magnifying.\nDrag to pan • Scroll to change magnification')
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.owner.smooth.isChecked())
        source = self.owner.source_rect()
        p.drawImage(QRectF(self.rect()), image, source)

    def wheelEvent(self, event):
        z = self.owner.zoom.value()
        self.owner.zoom.setValue(z * (1.25 if event.angleDelta().y() > 0 else 0.8))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.follow.setChecked(False)
            self.drag = event.position()

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            delta = event.position() - self.drag
            self.drag = event.position()
            z = self.owner.zoom.value()
            c = self.owner.center
            self.owner.center = (c[0] - delta.x() / z, c[1] - delta.y() / z)
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag = None


class Magnifier(QMainWindow):
    def __init__(self, demo=False, settings=None):
        super().__init__()
        self.settings = None if demo else (settings if settings is not None else
            QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      'WindowMagnifier', 'settings'))
        self.instance = uuid.uuid4().hex
        self.title = f'Window Magnifier [{self.instance[:6]}]'
        self.setWindowTitle(self.title)
        self.resize(660, 430)
        self.bus = None
        self.session = None
        self.pipeline = None
        self.remote_fd = None
        self.pending = []
        self.receivers = []
        self.script_name = None
        self.script_file = None
        self.image = None
        self.latest = None
        self.lock = threading.Lock()
        self.cursor = None
        self.window_rect = None
        self.tracking_available = False
        self.center = (0, 0)
        self.position = (0, 0)
        self.logical_size = None
        self.last_tick = time.time()
        self.capture_started_at = None
        self.received_frame = False
        panel = QWidget()
        layout = QVBoxLayout(panel)
        bar = QHBoxLayout()
        self.choose = QPushButton('Choose screen')
        self.choose.clicked.connect(self.connect_capture)
        bar.addWidget(self.choose)
        bar.addWidget(QLabel('Magnification'))
        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(1, 20)
        self.zoom.setSingleStep(0.5)
        self.zoom.setValue(3)
        self.zoom.setSuffix('×')
        bar.addWidget(self.zoom)
        self.follow = QCheckBox('Follow mouse')
        self.follow.setChecked(True)
        bar.addWidget(self.follow)
        self.pause = QCheckBox('Freeze')
        bar.addWidget(self.pause)
        self.smooth = QCheckBox('Smooth')
        bar.addWidget(self.smooth)
        layout.addLayout(bar)
        self.view = View(self)
        layout.addWidget(self.view, 1)
        self.status = QLabel('Choose a screen. The desktop stays at its normal size.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setCentralWidget(panel)
        self.zoom.valueChanged.connect(lambda _: self.view.update())
        self.smooth.toggled.connect(lambda _: self.view.update())
        if self.settings is not None:
            size = self.settings.value('window_size', QSize(660, 430), type=QSize)
            self.resize(size.expandedTo(QSize(580, 320)))
            self.zoom.setValue(self.settings.value('magnification', 3.0, type=float))
            self.follow.setChecked(self.settings.value('follow_mouse', True, type=bool))
            self.smooth.setChecked(self.settings.value('smooth', False, type=bool))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_settings)
        self.zoom.valueChanged.connect(self.schedule_save)
        self.follow.toggled.connect(self.schedule_save)
        self.smooth.toggled.connect(self.schedule_save)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        if demo:
            self.follow.setChecked(False)
            self.choose.setEnabled(False)
            self.image = QImage(1200, 800, QImage.Format.Format_RGB32)
            self.image.fill(QColor('#f4f5f7'))
            p = QPainter(self.image)
            p.setPen(QColor('#13213a'))
            font = p.font()
            font.setPixelSize(18)
            p.setFont(font)
            for y in range(30, 800, 35):
                p.drawText(25, y, 'Live magnification in a separate window — 0123456789')
            p.end()
            self.center = (320, 160)
            self.status.setText('Demo image • Drag to pan • Scroll to magnify')
        else:
            try:
                self.bus = dbus.SessionBus()
                self.portal = dbus.Interface(self.bus.get_object(PORTAL, '/org/freedesktop/portal/desktop'), SCREENCAST)
                self.bridge = CursorBridge(self.bus, self)
                self.start_tracker()
            except Exception as exc:
                self.status.setText(f'Desktop connection failed: {exc}')
                self.choose.setEnabled(False)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def toggle_freeze(self):
        self.pause.setChecked(not self.pause.isChecked())
        self.status.setText('Frozen • Press Ctrl+Meta+Shift+F to resume.'
                            if self.pause.isChecked() else 'Resuming live view…')

    def schedule_save(self, *args):
        if self.settings is not None:
            self.save_timer.start(300)

    def save_settings(self):
        if self.settings is None:
            return
        self.settings.setValue('window_size', self.size())
        self.settings.setValue('magnification', self.zoom.value())
        # A missing KWin connection must not overwrite the user's preference.
        if self.follow.isEnabled():
            self.settings.setValue('follow_mouse', self.follow.isChecked())
        self.settings.setValue('smooth', self.smooth.isChecked())
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            self.status.setText('Could not save preferences. Check your configuration folder permissions.')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'save_timer'):
            self.schedule_save()

    def start_tracker(self):
        try:
            script = '''function sendPosition() {
 var found = null;
 var windows = workspace.stackingOrder;
 for (var i=0; i<windows.length; i++) {
  if (windows[i].caption === TITLE) {
   var r=windows[i].frameGeometry;
   found=[r.x,r.y,r.width,r.height];
  }
 }
 var p=workspace.cursorPos;
 callDBus(SERVICE, '/Cursor', 'local.WindowMagnifier', 'Position',
          JSON.stringify({cursor:[p.x,p.y],window:found}));
}
registerShortcut('WindowMagnifierToggle', 'Window Magnifier: Show or hide',
                 'Ctrl+Meta+Shift+M', function() {
 callDBus(SERVICE, '/Cursor', 'local.WindowMagnifier', 'ToggleVisibility');
});
registerShortcut('WindowMagnifierFreeze', 'Window Magnifier: Freeze or resume',
                 'Ctrl+Meta+Shift+F', function() {
 callDBus(SERVICE, '/Cursor', 'local.WindowMagnifier', 'ToggleFreeze');
});
workspace.cursorPosChanged.connect(sendPosition);
workspace.windowAdded.connect(sendPosition);
sendPosition();
'''.replace('TITLE', json.dumps(self.title)).replace('SERVICE', json.dumps(self.bridge.name.get_name()))
            # KWin is outside the sandbox and needs the host-visible cache path.
            runtime = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'window-magnifier/kwin-scripts'
            runtime.mkdir(parents=True, exist_ok=True)
            f = tempfile.NamedTemporaryFile(mode='w', suffix='.js', prefix='window-magnifier-', dir=runtime, delete=False)
            f.write(script)
            f.close()
            self.script_file = f.name
            scripting = dbus.Interface(self.bus.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
            self.script_name = f'window-magnifier-{self.instance}'
            ident = scripting.loadScript(f.name, self.script_name, signature='ss')
            obj = self.bus.get_object('org.kde.KWin', f'/Scripting/Script{ident}')
            dbus.Interface(obj, 'org.kde.kwin.Script').run()
        except Exception as exc:
            self.follow.setChecked(False)
            self.follow.setEnabled(False)
            self.status.setText(f'Mouse tracking unavailable; drag to pan. {exc}')

    def request(self, method, args, options, callback):
        token = 'r' + uuid.uuid4().hex
        options['handle_token'] = dbus.String(token)
        sender = self.bus.get_unique_name()[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        holder = []
        def response(code, results):
            holder[0].remove()
            if holder[0] in self.receivers:
                self.receivers.remove(holder[0])
            if path in self.pending:
                self.pending.remove(path)
            if code:
                self.stop_capture()
                self.choose.setEnabled(True)
                self.status.setText('Screen sharing cancelled. Choose a screen to try again.')
                return
            try:
                callback(results)
            except Exception as exc:
                self.capture_error(str(exc))
        holder.append(self.bus.add_signal_receiver(response, signal_name='Response',
                      dbus_interface=REQUEST, bus_name=PORTAL, path=path))
        self.receivers.append(holder[0])
        self.pending.append(path)
        try:
            getattr(self.portal, method)(*args, dbus.Dictionary(options, signature='sv'))
        except Exception:
            holder[0].remove()
            self.receivers.remove(holder[0])
            self.pending.remove(path)
            raise

    def connect_capture(self):
        self.stop_capture()
        self.image = None
        self.view.update()
        self.pause.setChecked(False)
        self.choose.setText('Choose screen')
        self.choose.setEnabled(False)
        self.status.setText('Select the monitor you want to magnify in the sharing dialog…')
        try:
            self.request('CreateSession', [], {'session_handle_token': dbus.String('s' + uuid.uuid4().hex)}, self.created)
        except Exception as exc:
            self.capture_error(str(exc))

    def created(self, result):
        self.session = str(result['session_handle'])
        self.session_receiver = self.bus.add_signal_receiver(self.session_closed,
            signal_name='Closed', dbus_interface='org.freedesktop.portal.Session',
            bus_name=PORTAL, path=self.session)
        self.request('SelectSources', [dbus.ObjectPath(self.session)],
                     {'types': dbus.UInt32(1), 'multiple': dbus.Boolean(False),
                      'cursor_mode': dbus.UInt32(2)}, self.selected)

    def selected(self, result):
        self.request('Start', [dbus.ObjectPath(self.session), ''], {}, self.started)

    def started(self, result):
        streams = result.get('streams', [])
        if not streams:
            raise RuntimeError('The portal returned no screen stream.')
        node, properties = streams[0]
        self.position = tuple(map(int, properties.get('position', (0, 0))))
        size = properties.get('size')
        self.logical_size = tuple(map(int, size)) if size else None
        self.remote_fd = self.portal.OpenPipeWireRemote(dbus.ObjectPath(self.session),
                                                       dbus.Dictionary({}, signature='sv')).take()
        self.pipeline = Gst.Pipeline.new('magnifier')
        source = Gst.ElementFactory.make('pipewiresrc', 'capture')
        convert = Gst.ElementFactory.make('videoconvert', 'convert')
        caps = Gst.ElementFactory.make('capsfilter', 'format')
        sink = Gst.ElementFactory.make('appsink', 'frames')
        if any(e is None for e in (source, convert, caps, sink)):
            raise RuntimeError('Missing GStreamer PipeWire/video plugins.')
        source.set_property('fd', self.remote_fd)
        serial = properties.get('pipewire-serial')
        if serial is not None and source.find_property('target-object'):
            source.set_property('target-object', str(serial))
        else:
            source.set_property('path', str(node))
        source.set_property('do-timestamp', True)
        caps.set_property('caps', Gst.Caps.from_string('video/x-raw,format=BGRA'))
        sink.set_property('emit-signals', True)
        sink.set_property('max-buffers', 1)
        sink.set_property('drop', True)
        sink.set_property('sync', False)
        sink.connect('new-sample', self.new_sample)
        for element in (source, convert, caps, sink):
            self.pipeline.add(element)
        if not (source.link(convert) and convert.link(caps) and caps.link(sink)):
            raise RuntimeError('Unable to link the capture pipeline.')
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Unable to start screen capture.')
        self.capture_started_at = time.time()
        self.received_frame = False
        self.choose.setEnabled(True)
        self.status.setText('Waiting for the first live frame…')

    def new_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        ok, mapped = buffer.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR
        try:
            image = QImage(mapped.data, info.width, info.height, info.stride[0],
                           QImage.Format.Format_ARGB32).copy()
            with self.lock:
                self.latest = image
        finally:
            buffer.unmap(mapped)
        return Gst.FlowReturn.OK

    def source_rect(self):
        return crop_rect(self.center, (self.view.width(), self.view.height()),
                         self.zoom.value(), (self.image.width(), self.image.height()))

    def check_capture_health(self, now):
        gap = now - self.last_tick
        self.last_tick = now
        if not self.pipeline:
            return True
        if gap > 10:
            self.capture_error('Desktop resumed or capture was interrupted. Click Reconnect screen to continue.')
            return False
        if (not self.received_frame and self.capture_started_at is not None
                and now - self.capture_started_at > 15):
            self.capture_error('No video arrived from the shared screen. Click Reconnect screen to try again.')
            return False
        return True

    def tick(self):
        if not self.check_capture_health(time.time()):
            return
        context = GLib.MainContext.default()
        for _ in range(30):
            if not context.pending():
                break
            context.iteration(False)
        if self.pipeline:
            bus = self.pipeline.get_bus()
            msg = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg:
                error = msg.parse_error()[0].message if msg.type == Gst.MessageType.ERROR else 'Screen sharing ended.'
                self.capture_error(error)
                return
        with self.lock:
            frame = self.latest
            self.latest = None
        if frame is None:
            return
        self.received_frame = True
        if self.pause.isChecked():
            self.status.setText('Frozen • Uncheck Freeze to resume.')
            return
        logical = self.logical_size or (frame.width(), frame.height())
        sx, sy = frame.width() / logical[0], frame.height() / logical[1]
        candidate = self.center
        if self.follow.isChecked() and self.cursor:
            x, y = self.cursor[0] - self.position[0], self.cursor[1] - self.position[1]
            if not (0 <= x < logical[0] and 0 <= y < logical[1]):
                self.status.setText('Pointer is outside the shared screen • Holding the view.')
                return
            candidate = (x * sx, y * sy)
        elif self.image is None:
            candidate = (frame.width() / 2, frame.height() / 2)
        rect = crop_rect(candidate, (self.view.width(), self.view.height()), self.zoom.value(),
                         (frame.width(), frame.height()))
        logical_rect = QRectF(rect.x() / sx + self.position[0], rect.y() / sy + self.position[1],
                              rect.width() / sx, rect.height() / sy)
        if self.window_rect and logical_rect.intersects(self.window_rect) and self.image is not None:
            self.status.setText('Holding the view: move the pointer away from this window to avoid mirrors.')
            return
        self.center = candidate
        self.image = frame
        self.status.setText('Live • ' + ('Following mouse' if self.follow.isChecked() and self.tracking_available
                            else 'Drag to pan') + ' • Scroll to change magnification')
        self.view.update()

    def session_closed(self, *args):
        self.capture_error('Screen sharing ended. Choose a screen to reconnect.')

    def capture_error(self, message):
        self.stop_capture()
        self.image = None
        self.view.update()
        self.choose.setText('Reconnect screen')
        self.choose.setEnabled(True)
        self.status.setText(message)

    def stop_capture(self):
        self.capture_started_at = None
        self.received_frame = False
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self.remote_fd is not None:
            os.close(self.remote_fd)
            self.remote_fd = None
        if hasattr(self, 'session_receiver'):
            self.session_receiver.remove()
            del self.session_receiver
        if self.session:
            session, self.session = self.session, None
            try:
                dbus.Interface(self.bus.get_object(PORTAL, session), 'org.freedesktop.portal.Session').Close()
            except dbus.DBusException:
                pass
        for path in self.pending:
            try:
                dbus.Interface(self.bus.get_object(PORTAL, path), REQUEST).Close()
            except dbus.DBusException:
                pass
        self.pending.clear()
        for receiver in self.receivers:
            receiver.remove()
        self.receivers.clear()
        with self.lock:
            self.latest = None

    def closeEvent(self, event):
        self.save_timer.stop()
        self.save_settings()
        self.timer.stop()
        self.stop_capture()
        if self.script_name:
            try:
                dbus.Interface(self.bus.get_object('org.kde.KWin', '/Scripting'),
                               'org.kde.kwin.Scripting').unloadScript(self.script_name)
            except dbus.DBusException:
                pass
        if self.script_file:
            Path(self.script_file).unlink(missing_ok=True)
        event.accept()


def main():
    DBusGMainLoop(set_as_default=True)
    Gst.init(None)
    app = QApplication(sys.argv)
    app.setApplicationName('Window Magnifier')
    if os.environ.get('FLATPAK_ID'):
        app.setDesktopFileName(APP_ID)
    window = Magnifier(demo='--demo' in sys.argv)
    window.show()
    if '--screenshot' in sys.argv:
        filename = sys.argv[sys.argv.index('--screenshot') + 1]
        def screenshot():
            window.grab().save(filename)
            window.close()
        QTimer.singleShot(300, screenshot)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
