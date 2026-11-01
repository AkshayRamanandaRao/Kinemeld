#!/usr/bin/env bash
set -euo pipefail
# This entire desktop/D-Bus session belongs to this test, including its native portal windows.
export KINEMELD_PRIVATE_GUI_SESSION=1
export XDG_CURRENT_DESKTOP=GNOME
export GTK_MODULES=atk-bridge
export NO_AT_BRIDGE=0
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export LIBGL_ALWAYS_SOFTWARE=1
session_root="$(mktemp -d)"
trap 'kill "${wm_pid:-}" 2>/dev/null || true; rm -rf -- "$session_root"' EXIT
export XDG_CONFIG_HOME="$session_root/config"
mkdir -p "$XDG_CONFIG_HOME/xdg-desktop-portal"
printf '[preferred]\ndefault=gtk\n' > "$XDG_CONFIG_HOME/xdg-desktop-portal/portals.conf"
openbox > "$session_root/openbox.log" 2>&1 &
wm_pid=$!
/usr/bin/python3 tests/native-dialog-platform.py --exe "$1" --solver-config "$2"
