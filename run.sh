#!/bin/sh
cd "$(dirname "$0")" || exit 1
export GI_TYPELIB_PATH="$PWD/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
exec /usr/bin/python3 magnifier.py "$@"
