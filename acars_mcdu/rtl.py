"""Enumeración de dongles RTL-SDR vía librtlsdr (ctypes, sin abrir el device)."""

import ctypes
import ctypes.util


def devices():
    """[{index, name, manufacturer, product, serial, label}] o [] si no hay lib."""
    path = ctypes.util.find_library("rtlsdr") or "librtlsdr.so.0"
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        return []
    try:
        lib.rtlsdr_get_device_count.restype = ctypes.c_uint32
        lib.rtlsdr_get_device_name.restype = ctypes.c_char_p
        lib.rtlsdr_get_device_name.argtypes = [ctypes.c_uint32]
        lib.rtlsdr_get_device_usb_strings.argtypes = [
            ctypes.c_uint32, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
        n = int(lib.rtlsdr_get_device_count())
    except AttributeError:
        return []

    out = []
    for i in range(n):
        name = (lib.rtlsdr_get_device_name(i) or b"").decode("utf-8", "replace")
        man = ctypes.create_string_buffer(256)
        prod = ctypes.create_string_buffer(256)
        ser = ctypes.create_string_buffer(256)
        try:
            lib.rtlsdr_get_device_usb_strings(i, man, prod, ser)
        except Exception:
            pass
        d = {
            "index": i,
            "name": name,
            "manufacturer": man.value.decode("utf-8", "replace"),
            "product": prod.value.decode("utf-8", "replace"),
            "serial": ser.value.decode("utf-8", "replace"),
        }
        bits = [b for b in (d["product"] or name, d["serial"]) if b]
        d["label"] = f"#{i}  " + "  ·  ".join(bits)
        out.append(d)
    return out
