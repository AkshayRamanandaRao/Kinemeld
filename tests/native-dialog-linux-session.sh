#!/usr/bin/env bash
set -euo pipefail
# This entire desktop/D-Bus session belongs to this test, including its native portal windows.
export KINEMELD_PRIVATE_GUI_SESSION=1
export XDG_CURRENT_DESKTOP=GNOME
export GTK_MODULES=atk-bridge
export NO_AT_BRIDGE=0
export WEBKIT_DISABLE_DMABUF_RENDERER=1
export LIBGL_ALWAYS_SOFTWARE=1
export GDK_BACKEND=x11
unset WAYLAND_DISPLAY
session_root="$(mktemp -d)"
cleanup() {
  local status=$?
  trap - EXIT
  kill "${wm_pid:-}" 2>/dev/null || true
  # The private document portal leaves a FUSE mount after the tested app exits.
  if mountpoint -q "$session_root/runtime/doc"; then
    if ! fusermount3 -u "$session_root/runtime/doc"; then
      fusermount3 -uz "$session_root/runtime/doc" || exit "$((status == 0 ? 1 : status))"
    fi
    if mountpoint -q "$session_root/runtime/doc"; then
      exit "$((status == 0 ? 1 : status))"
    fi
  fi
  rm -rf -- "$session_root"
  exit "$status"
}
trap cleanup EXIT
export XDG_CONFIG_HOME="$session_root/config"
export XDG_DATA_HOME="$session_root/data"
export XDG_CACHE_HOME="$session_root/cache"
export XDG_RUNTIME_DIR="$session_root/runtime"
mkdir -m 700 "$XDG_RUNTIME_DIR"
mkdir -p "$XDG_CONFIG_HOME/xdg-desktop-portal"
printf '[preferred]\ndefault=gtk\n' > "$XDG_CONFIG_HOME/xdg-desktop-portal/portals.conf"
dbus-update-activation-environment DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME GDK_BACKEND GTK_MODULES NO_AT_BRIDGE
openbox > "$session_root/openbox.log" 2>&1 &
wm_pid=$!
/usr/bin/python3 tests/native-dialog-platform.py --exe "$1" --solver-config "$2"
