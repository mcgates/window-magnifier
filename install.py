#!/usr/bin/env python3
"""Install or remove Window Magnifier under a user's local prefix."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

FILES = ['icon.svg', 'magnifier.py', 'run.sh', 'README.md', 'LICENSE', 'install.py', 'install.sh']
MARKER = '.window-magnifier-install.json'


def install(prefix, uninstall=False):
    source = Path(__file__).resolve().parent
    destination = prefix / 'share/window-magnifier'
    applications = prefix / 'share/applications'
    shortcut = applications / 'local.window-magnifier.desktop'
    if uninstall:
        marker = destination / MARKER
        if not marker.is_file():
            raise RuntimeError('No managed installation found at this prefix.')
        manifest = json.loads(marker.read_text())
        for name in manifest['files']:
            path = destination / name
            if not path.resolve().is_relative_to(destination.resolve()):
                raise RuntimeError('Invalid installation manifest.')
            path.unlink(missing_ok=True)
        marker.unlink()
        for folder in sorted(destination.rglob('*'), reverse=True):
            if folder.is_dir():
                try:
                    folder.rmdir()
                except OSError:
                    pass
        try:
            destination.rmdir()
        except OSError:
            pass
        if shortcut.exists() and str(destination / 'run.sh') in shortcut.read_text():
            shortcut.unlink()
        print('Removed Window Magnifier. Saved settings were preserved.')
    else:
        missing = [name for name in FILES if not (source / name).is_file()]
        if missing:
            raise RuntimeError('Incomplete package: ' + ', '.join(missing))
        if destination.exists() and not (destination / MARKER).exists():
            raise RuntimeError('Destination already exists without an installation marker.')
        for name in FILES:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if (source / name).resolve() != target.resolve():
                shutil.copy2(source / name, target)
        (destination / 'run.sh').chmod(0o755)
        (destination / 'install.sh').chmod(0o755)
        (destination / MARKER).write_text(json.dumps({'files': FILES}, indent=2) + '\n')
        # Exec is parsed by the desktop launcher, not by a shell.
        executable = str(destination / 'run.sh')
        executable = executable.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
        applications.mkdir(parents=True, exist_ok=True)
        shortcut.write_text('[Desktop Entry]\nType=Application\nName=Window Magnifier\n'
            'Comment=Magnify a screen area in a separate window\n'
            f'Exec="{executable}"\nIcon={destination / "icon.svg"}\nTerminal=false\nCategories=Utility;Accessibility;\n')
        print('Installed:', destination)
        print('Search for Window Magnifier in your app menu.')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(applications)], check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.local')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    try:
        install(args.prefix.expanduser().resolve(), args.uninstall)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
