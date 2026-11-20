"""Process memory (RSS) in MB, stdlib only (Ticket-04 soak test).

Linux:   /proc/self/statm (current resident pages)
macOS:   mach task_info via ctypes (current resident size); falls back to resource.ru_maxrss (peak)
Windows: GetProcessMemoryInfo via ctypes (WorkingSetSize)
Returns 0.0 if nothing works (the caller should treat that as "unknown").
"""
import os
import sys


def _linux():
    with open("/proc/self/statm", "rb") as f:
        pages = int(f.read().split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE")


def _macos():
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

        class MachTaskBasicInfo(ctypes.Structure):
            _fields_ = [("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
                        ("resident_size_max", ctypes.c_uint64), ("user_time", ctypes.c_uint64 * 1),
                        ("system_time", ctypes.c_uint64 * 1), ("policy", ctypes.c_int32),
                        ("suspend_count", ctypes.c_int32)]

        MACH_TASK_BASIC_INFO = 20
        info = MachTaskBasicInfo()
        count = ctypes.c_uint32(ctypes.sizeof(info) // 4)
        libc.mach_task_self.restype = ctypes.c_uint32
        libc.task_info.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_uint32)]
        rc = libc.task_info(libc.mach_task_self(), MACH_TASK_BASIC_INFO, ctypes.byref(info),
                            ctypes.byref(count))
        if rc == 0 and info.resident_size > 0:
            return int(info.resident_size)
    except Exception:
        pass
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)     # bytes on macOS


def _windows():
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return int(pmc.WorkingSetSize)


def rss_bytes():
    try:
        if sys.platform.startswith("linux"):
            return _linux()
        if sys.platform == "darwin":
            return _macos()
        if sys.platform in ("win32", "cygwin"):
            return _windows()
    except Exception:
        pass
    try:                                     # other POSIX: peak RSS (KB on Linux/BSD)
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:
        return 0


def rss_mb():
    """Resident memory of this process in MB (1 MB = 1024*1024 bytes), 1 decimal."""
    return round(rss_bytes() / (1024 * 1024), 1)


if __name__ == "__main__":
    print(rss_mb())
