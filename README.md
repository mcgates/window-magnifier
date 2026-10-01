# Window Magnifier

![App icon](icon.svg)

A live magnifier in a separate, movable and resizable window for **KDE Plasma on
Wayland**. Your desktop stays at its normal size.

## Features

- Follow the mouse or drag to pan a fixed area.
- Magnification from 1× to 20×, with optional smoothing.
- Freeze the view and remember your preferences.
- Ctrl+Meta+Shift+M: show/hide; Ctrl+Meta+Shift+F: freeze/resume.
- Reconnect when sharing ends or the desktop resumes after an interruption.

Screen access uses KDE's ScreenCast portal and PipeWire. Mouse tracking and
shortcuts use a temporary KWin script that is unloaded when the app closes.
No recording is saved or uploaded. If the captured area overlaps the magnifier,
the app holds its previous image to avoid recursive mirrors. It shares one
monitor at a time and holds the view when the pointer leaves that monitor.

## Install on Ubuntu/Kubuntu

Download the `.deb` from Releases and install it:

```sh
sudo apt install ./window-magnifier_0.1.0_all.deb
```

Search for **Window Magnifier** in your app menu. Click **Choose screen**, select
your monitor, and click **Share**. Requires a KDE Plasma Wayland session.
The initial version has been tested on Ubuntu 26.04.1 / Plasma 6.6.6.
Other Ubuntu versions need their dependency compatibility checked before use.

## Run from source

Install these packages on Ubuntu:

```sh
sudo apt install python3-pyqt6 python3-gi python3-dbus gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-base gstreamer1.0-pipewire xdg-desktop-portal-kde
sh run.sh
```

## Build the Ubuntu package

```sh
python3 build_deb.py
```

The package is written to `dist/`. Installation does not require bundling Ubuntu
libraries: the package manager installs the declared runtime dependencies.

## Development status

This is an early KDE-specific release. It has not been tested on every distribution
or monitor arrangement. The app was developed with AI assistance, including code,
documentation and icon design. Maintainers should review and test changes before
publishing releases.

License: MIT. See [LICENSE](LICENSE).

## Tests

Run `QT_QPA_PLATFORM=offscreen python3 -m unittest discover` after installing dependencies.
