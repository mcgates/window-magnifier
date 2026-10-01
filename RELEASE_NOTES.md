# Window Magnifier 0.1.0 — initial preview

A separate live magnifier window for KDE Plasma on Wayland.

Includes mouse tracking, magnification up to 20×, dragging to pan, freeze,
smoothing, saved preferences and global show/hide and freeze shortcuts.

Download the Ubuntu package, install it with `sudo apt install ./window-magnifier_0.1.0_all.deb`,
then open Window Magnifier and choose a screen to share.

The native application was tested on Ubuntu 26.04.1 with Plasma 6.6.6.
The Debian package was built and its extracted application tested without
performing a system package installation. Compatibility with other distributions
and desktop environments has not been established.

Known limits: one shared monitor at a time; KDE-specific tracking and shortcuts;
the view holds when its capture area overlaps its own window. Screen sharing
must be granted through KDE's sharing dialog.
