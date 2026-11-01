"""Bounded Win32 control actions for the real native-dialog GUI regression.

Only windows belonging to --pid are inspected or controlled. No global input is sent.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import re
import struct
import sys
import time
import zlib

if os.name != "nt":
    raise SystemExit("This helper requires Windows.")

U = C.WinDLL("user32", use_last_error=True)
G = C.WinDLL("gdi32", use_last_error=True)
K = C.WinDLL("kernel32", use_last_error=True)
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [CALLBACK, W.LPARAM]
U.EnumChildWindows.argtypes = [W.HWND, CALLBACK, W.LPARAM]
U.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
U.IsWindowVisible.argtypes = U.IsWindowEnabled.argtypes = [W.HWND]
U.GetDlgCtrlID.argtypes = [W.HWND]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetParent.argtypes, U.GetParent.restype = [W.HWND], W.HWND
U.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t)]
U.SendMessageTimeoutW.restype = C.c_ssize_t
U.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
U.IsIconic.argtypes = [W.HWND]
U.ShowWindowAsync.argtypes = [W.HWND, C.c_int]
U.RedrawWindow.argtypes = [W.HWND, C.c_void_p, W.HANDLE, W.UINT]
U.GetWindowDC.argtypes, U.GetWindowDC.restype = [W.HWND], W.HDC
U.ReleaseDC.argtypes = [W.HWND, W.HDC]
U.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
G.CreateCompatibleDC.argtypes, G.CreateCompatibleDC.restype = [W.HDC], W.HDC
G.CreateCompatibleBitmap.argtypes, G.CreateCompatibleBitmap.restype = [W.HDC, C.c_int, C.c_int], W.HBITMAP
G.SelectObject.argtypes, G.SelectObject.restype = [W.HDC, W.HGDIOBJ], W.HGDIOBJ
G.DeleteObject.argtypes, G.DeleteDC.argtypes = [W.HGDIOBJ], [W.HDC]
G.BitBlt.argtypes = [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]
G.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]


class ProcessEntry(C.Structure):
    _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
                ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                ("parent_pid", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD), ("exe", W.WCHAR * 260)]


K.CreateToolhelp32Snapshot.argtypes, K.CreateToolhelp32Snapshot.restype = [W.DWORD, W.DWORD], W.HANDLE
K.Process32FirstW.argtypes = K.Process32NextW.argtypes = [W.HANDLE, C.POINTER(ProcessEntry)]
K.CloseHandle.argtypes = [W.HANDLE]
K.OpenProcess.argtypes, K.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
K.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
K.WaitForSingleObject.argtypes, K.WaitForSingleObject.restype = [W.HANDLE, W.DWORD], W.DWORD


def processes():
    snapshot = K.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (None, C.c_void_p(-1).value):
        raise C.WinError(C.get_last_error())
    try:
        entry = ProcessEntry(size=C.sizeof(ProcessEntry))
        found = []
        more = K.Process32FirstW(snapshot, C.byref(entry))
        while more:
            found.append({"pid": entry.pid, "parentPid": entry.parent_pid, "exe": entry.exe})
            more = K.Process32NextW(snapshot, C.byref(entry))
        if C.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise C.WinError(C.get_last_error())
        return found
    finally:
        K.CloseHandle(snapshot)


def terminate_child(parent_pid, child_pid):
    child = next((item for item in processes() if item["pid"] == child_pid), None)
    if child is None or child["parentPid"] != parent_pid or child_pid == parent_pid:
        raise ValueError(f"PID {child_pid} is not a current direct child of owned PID {parent_pid}.")
    process = K.OpenProcess(0x00100001, False, child_pid)  # SYNCHRONIZE | PROCESS_TERMINATE
    if not process:
        raise C.WinError(C.get_last_error())
    try:
        if not K.TerminateProcess(process, 1):
            raise C.WinError(C.get_last_error())
        if K.WaitForSingleObject(process, 2000) != 0:
            raise RuntimeError(f"Owned child PID {child_pid} did not exit within 2 seconds.")
        return {"ok": True, "child": child, "terminated": True}
    finally:
        K.CloseHandle(process)


def handles(parent=None):
    found = []
    callback = CALLBACK(lambda hwnd, _: found.append(int(hwnd)) or True)
    if parent is None:
        U.EnumWindows(callback, 0)
    else:
        U.EnumChildWindows(parent, callback, 0)
    return found


def pid(hwnd):
    value = W.DWORD()
    U.GetWindowThreadProcessId(hwnd, C.byref(value))
    return value.value


def send(hwnd, message, wparam=0, lparam=0, timeout=1000):
    result = C.c_size_t()
    if not U.SendMessageTimeoutW(hwnd, message, wparam, lparam, 0x0002, timeout, C.byref(result)):
        raise RuntimeError(f"Window {hwnd} did not acknowledge message {message} within {timeout} ms.")
    return result.value


def info(hwnd, control=False):
    name, text = C.create_unicode_buffer(256), C.create_unicode_buffer(4096)
    U.GetClassNameW(hwnd, name, len(name))
    if control:
        try:
            send(hwnd, 0x000D, len(text), C.cast(text, C.c_void_p).value, 150)
        except RuntimeError:
            pass
    else:
        U.GetWindowTextW(hwnd, text, len(text))
    return {"hwnd": hwnd, "pid": pid(hwnd), "class": name.value, "text": text.value,
            "id": U.GetDlgCtrlID(hwnd), "parent": int(U.GetParent(hwnd) or 0),
            "visible": bool(U.IsWindowVisible(hwnd)), "enabled": bool(U.IsWindowEnabled(hwnd))}


def windows(process, title=None, dialogs=False):
    return [item for item in (info(hwnd) for hwnd in handles() if pid(hwnd) == process and U.IsWindowVisible(hwnd))
            if (title is None or re.search(title, item["text"])) and (not dialogs or item["class"] == "#32770")]


def wait_window(process, title, timeout, dialogs=True):
    deadline = time.monotonic() + timeout
    while True:
        found = windows(process, title, dialogs)
        if found:
            # EnumWindows is in Z order: a nested confirmation appears before its parent dialog.
            return found[0]
        if time.monotonic() >= deadline:
            raise RuntimeError(f"No visible {'dialog' if dialogs else 'window'} matching {title!r} for PID {process} after {timeout:g} s; owned windows: {windows(process)}")
        time.sleep(0.1)


def children(window, process):
    return [info(hwnd, True) for hwnd in handles(window["hwnd"]) if pid(hwnd) == process]


def choose(items, class_name, control_id=None, text=None):
    matched = [item for item in items if item["visible"] and item["enabled"] and item["class"].lower() == class_name.lower()
               and (control_id is None or item["id"] == control_id)
               and (text is None or re.search(text, item["text"].replace("&", "")))]
    if len(matched) != 1:
        raise RuntimeError(f"Expected one visible enabled {class_name} control (ID={control_id}, text={text!r}); found {matched}")
    return matched[0]


def filename_field(items):
    edits = [item for item in items if item["visible"] and item["enabled"] and item["class"].lower() == "edit"]
    primary = [item for item in edits if item["id"] == 1001]
    if primary:
        return choose(primary, "Edit", 1001)
    by_handle = {item["hwnd"]: item for item in items}
    fallback = [item for item in edits if item["id"] == 1148
                and by_handle.get(item["parent"], {}).get("class") == "ComboBox"
                and by_handle[item["parent"]]["id"] == 1148]
    return choose(fallback, "Edit", 1148)


def post(hwnd, message):
    if not U.PostMessageW(hwnd, message, 0, 0):
        raise C.WinError(C.get_last_error())


def validate_capture_size(title, width, height, client_width, client_height):
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise RuntimeError(f"Invalid window bounds: {width}x{height}")
    if title == "Kinemeld" and (client_width < 640 or client_height < 400):
        raise RuntimeError(f"Kinemeld capture has no meaningful client area: {client_width}x{client_height}")


def repaint(window):
    # Queue invalidation without UPDATENOW, then bound each UI-thread paint acknowledgement.
    if not U.RedrawWindow(window["hwnd"], None, None, 0x0001 | 0x0080):
        raise C.WinError(C.get_last_error())
    deadline = time.monotonic() + 3
    painted = 0
    for hwnd in [window["hwnd"], *handles(window["hwnd"])]:
        if pid(hwnd) != window["pid"] or not U.IsWindowVisible(hwnd):
            continue
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise RuntimeError("Owned-window paint acknowledgements exceeded 3 seconds.")
        send(hwnd, 0x000F, timeout=min(250, remaining))  # WM_PAINT
        painted += 1
    send(window["hwnd"], 0x0000, timeout=250)  # WM_NULL: complete the final UI-thread barrier.
    return painted


def screenshot(window, destination):
    restored = bool(U.IsIconic(window["hwnd"]))
    if restored and not U.ShowWindowAsync(window["hwnd"], 9):  # SW_RESTORE
        raise C.WinError(C.get_last_error())
    deadline = time.monotonic() + 3
    while True:
        rect, client = W.RECT(), W.RECT()
        if not U.GetWindowRect(window["hwnd"], C.byref(rect)) or not U.GetClientRect(window["hwnd"], C.byref(client)):
            raise C.WinError(C.get_last_error())
        ready = not U.IsIconic(window["hwnd"]) and (window["text"] != "Kinemeld" or (client.right >= 640 and client.bottom >= 400))
        if ready or not restored:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("The owned window did not restore to a meaningful size within 3 seconds.")
        time.sleep(0.05)
    width, height = rect.right - rect.left, rect.bottom - rect.top
    validate_capture_size(window["text"], width, height, client.right, client.bottom)
    painted = repaint(window)
    source = U.GetWindowDC(window["hwnd"])
    memory = G.CreateCompatibleDC(source)
    bitmap = G.CreateCompatibleBitmap(source, width, height)
    if not source or not memory or not bitmap:
        if bitmap: G.DeleteObject(bitmap)
        if memory: G.DeleteDC(memory)
        if source: U.ReleaseDC(window["hwnd"], source)
        raise C.WinError(C.get_last_error())
    previous = G.SelectObject(memory, bitmap)
    method = "PrintWindow"
    try:
        if not U.PrintWindow(window["hwnd"], memory, 2):
            method = "BitBlt"
            if not G.BitBlt(memory, 0, 0, width, height, source, 0, 0, 0x00CC0020):
                raise C.WinError(C.get_last_error())
        G.SelectObject(memory, previous)
        pixels = C.create_string_buffer(width * height * 4)
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(pixels), 0, 0, 0, 0)
        bitmap_info = C.create_string_buffer(header)
        if G.GetDIBits(source, bitmap, 0, height, pixels, bitmap_info, 0) != height:
            raise C.WinError(C.get_last_error())
        raw = pixels.raw
        rows = []
        for y in range(height):
            bgra = raw[y * width * 4:(y + 1) * width * 4]
            rgb = bytearray(width * 3)
            rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
            rows.append(b"\0" + rgb)
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
        path = Path(destination).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        return {"path": str(path), "width": width, "height": height, "clientWidth": client.right, "clientHeight": client.bottom, "restored": restored, "paintedWindows": painted, "method": method}
    finally:
        G.SelectObject(memory, previous)
        G.DeleteObject(bitmap)
        G.DeleteDC(memory)
        U.ReleaseDC(window["hwnd"], source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--self-check", action="store_true")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list")
    commands.add_parser("children")
    commands.add_parser("terminate-child").add_argument("--child-pid", type=int, required=True)
    for name in ("wait", "file", "cancel", "button", "close", "screenshot"):
        command = commands.add_parser(name)
        command.add_argument("--title", required=name != "close", default="^Kinemeld$")
        command.add_argument("--timeout", type=float, default=15)
        if name == "file": command.add_argument("--path", required=True)
        if name == "screenshot": command.add_argument("--out", required=True)
        if name == "button":
            selector = command.add_mutually_exclusive_group(required=True)
            selector.add_argument("--id", type=int)
            selector.add_argument("--text")
    args = parser.parse_args()
    if args.self_check:
        item = {"hwnd": 1, "class": "Edit", "id": 1001, "parent": 0, "text": "name", "visible": True, "enabled": True}
        assert filename_field([item]) == item
        try: filename_field([item, dict(item, hwnd=2)])
        except RuntimeError: pass
        else: raise AssertionError("Ambiguous file-name fields must be rejected.")
        combo = dict(item, hwnd=2, id=1148, **{"class": "ComboBox"})
        nested = dict(item, id=1148, parent=2)
        assert filename_field([nested, combo]) == nested
        try: filename_field([nested, dict(combo, id=1001)])
        except RuntimeError: pass
        else: raise AssertionError("An unrelated edit must not be treated as the filename.")
        validate_capture_size("Confirm Save As", 350, 130, 334, 92)
        validate_capture_size("Kinemeld", 800, 600, 784, 562)
        try: validate_capture_size("Kinemeld", 160, 28, 144, 0)
        except RuntimeError: pass
        else: raise AssertionError("A minimized caption strip must not qualify as an app screenshot.")
        assert C.sizeof(W.HWND) == C.sizeof(C.c_void_p)
        assert any(item["pid"] == os.getpid() for item in processes())
        return {"ok": True, "pointerBits": C.sizeof(W.HWND) * 8, "windows": windows(args.pid or os.getpid())}
    if not args.pid or args.pid <= 0 or not args.command:
        parser.error("--pid and a command are required")
    if args.command == "list":
        return {"ok": True, "windows": [dict(item, children=children(item, args.pid)) for item in windows(args.pid)]}
    if args.command == "children":
        return {"ok": True, "children": [item for item in processes() if item["parentPid"] == args.pid]}
    if args.command == "terminate-child":
        return terminate_child(args.pid, args.child_pid)
    if not 0 <= args.timeout <= 15:
        parser.error("--timeout must be between 0 and 15 seconds")
    window = wait_window(args.pid, args.title, args.timeout, dialogs=args.command not in ("close", "screenshot"))
    result = {"ok": True, "window": window}
    if args.command == "wait": return result
    if args.command == "screenshot": return dict(result, image=screenshot(window, args.out))
    if args.command == "close":
        post(window["hwnd"], 0x0010)
        return result
    controls = children(window, args.pid)
    if args.command == "file":
        if not args.path or "\0" in args.path: raise ValueError("A nonempty file path without NUL is required.")
        field = filename_field(controls)
        value = C.create_unicode_buffer(args.path)
        if not send(field["hwnd"], 0x000C, 0, C.cast(value, C.c_void_p).value):
            raise RuntimeError("The file-name field rejected WM_SETTEXT.")
        if info(field["hwnd"], True)["text"] != args.path:
            raise RuntimeError("The file-name field did not retain the requested path.")
        result["field"] = field
        button = choose(controls, "Button", 1)
    elif args.command == "cancel":
        button = choose(controls, "Button", 2)
    else:
        button = choose(controls, "Button", args.id, args.text)
    post(button["hwnd"], 0x00F5)
    return dict(result, button=button)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
