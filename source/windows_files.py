"""Windows 檔案控制代碼與網路來源標記。"""

from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import stat

if os.name == 'nt':
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    _open = _kernel.CreateFileW
    _open.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _open.restype = wintypes.HANDLE
    _close = _kernel.CloseHandle
    _close.argtypes = (wintypes.HANDLE,)
    _close.restype = wintypes.BOOL
    _get_attributes = _kernel.GetFileInformationByHandleEx
    _get_attributes.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    _get_attributes.restype = wintypes.BOOL
    _get_volume = _kernel.GetVolumeInformationByHandleW
    _get_volume.argtypes = (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                            wintypes.LPDWORD, wintypes.LPDWORD, wintypes.LPDWORD,
                            wintypes.LPWSTR, wintypes.DWORD)
    _get_volume.restype = wintypes.BOOL

    class _FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [('attributes', wintypes.DWORD), ('tag', wintypes.DWORD)]

    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _READ_DATA_AND_ATTRIBUTES = 0x81  # 目錄對應 FILE_LIST_DIRECTORY。
    _SHARE_READ = 1
    _SHARE_WRITE = 2
    _OPEN_EXISTING = 3
    _OPEN_REPARSE_POINT = 0x00200000
    _BACKUP_SEMANTICS = 0x02000000
    _FILE_ATTRIBUTE_TAG_INFO = 9
    _FILE_NAMED_STREAMS = 0x00040000

MAX_ZONE_BYTES = 64 * 1024


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _extended_path(path: Path) -> str:
    name = str(path)
    if name.startswith('\\\\?\\'):
        return name
    if name.startswith('\\\\'):
        return '\\\\?\\UNC\\' + name[2:]
    return '\\\\?\\' + name


def native_path(path: Path) -> Path:
    # 保留空間給 Windows 建立子目錄與檔案時附加的名稱。
    if os.name == 'nt' and len(str(path).encode('utf-16-le', 'surrogatepass')) // 2 >= 240:
        return Path(_extended_path(path))
    return path


@contextmanager
def _hold(path: Path, directory: bool):
    if os.name != 'nt':
        info = path.lstat()
        matches = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if is_link(info) or not matches:
            raise OSError('unexpected file type')
        yield None
        return

    # 不分享 DELETE，避免已檢查的路徑元件在使用中被移動或替換。
    # 來源檔也不分享 WRITE，讓 PDF 與來源標記維持同一個檔案。
    sharing = _SHARE_READ | (_SHARE_WRITE if directory else 0)
    handle = _open(_extended_path(path), _READ_DATA_AND_ATTRIBUTES, sharing, None,
                   _OPEN_EXISTING, _OPEN_REPARSE_POINT | _BACKUP_SEMANTICS, None)
    if handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = _FileAttributeTagInfo()
        if not _get_attributes(handle, _FILE_ATTRIBUTE_TAG_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if (info.attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or bool(info.attributes & stat.FILE_ATTRIBUTE_DIRECTORY) != directory
                or info.attributes & stat.FILE_ATTRIBUTE_DEVICE):
            raise OSError('unexpected file type')
        yield handle
    finally:
        _close(handle)


@contextmanager
def hold_path(path: Path, *, directory: bool = False):
    """從根目錄依序驗證並保留每個路徑元件，最後傳回檔案控制代碼。"""
    path = path.absolute()
    with ExitStack() as stack:
        for parent in reversed(path.parents):
            stack.enter_context(_hold(parent, True))
        yield stack.enter_context(_hold(path, directory))


def read_zone(path: Path, handle) -> bytes | None:
    if os.name != 'nt':
        return None
    flags = wintypes.DWORD()
    if not _get_volume(handle, None, 0, None, None, ctypes.byref(flags), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not flags.value & _FILE_NAMED_STREAMS:
        return None
    zone_handle = _open(_extended_path(path) + ':Zone.Identifier', _READ_DATA_AND_ATTRIBUTES,
                        _SHARE_READ, None, _OPEN_EXISTING, 0, None)
    if zone_handle == _INVALID_HANDLE:
        error = ctypes.get_last_error()
        # 來源正由控制代碼保留，只有 ERROR_FILE_NOT_FOUND 視為無此資料流。
        if error == 2:
            return None
        raise ctypes.WinError(error)
    try:
        descriptor = msvcrt.open_osfhandle(zone_handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        _close(zone_handle)
        raise
    with os.fdopen(descriptor, 'rb') as stream:
        marker = stream.read(MAX_ZONE_BYTES + 1)
    if len(marker) > MAX_ZONE_BYTES:
        raise OSError('zone identifier exceeds size limit')
    return marker


def write_zone(path: Path, marker: bytes) -> None:
    stream_path = _extended_path(path) + ':Zone.Identifier'
    with open(stream_path, 'wb') as stream:
        stream.write(marker)
    with open(stream_path, 'rb') as stream:
        if stream.read(len(marker) + 1) != marker:
            raise OSError('zone identifier verification failed')
