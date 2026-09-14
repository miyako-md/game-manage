"""Atomic credential storage, encrypted for the current Windows user with DPAPI.

On other platforms AES-GCM uses a separate owner-only local key file. The key
must be backed up together with the ciphertext. No secrets are logged.
"""
import ctypes
import json
import os
import tempfile
from pathlib import Path


class CredentialStoreError(Exception):
    pass


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                         ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise CredentialStoreError('本地凭据无法解密或保存，请使用原 Windows 用户重新登录')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class CredentialStore:
    def __init__(self, path):
        self.path = Path(path)

    def _key(self, create=False):
        key_path = self.path.with_suffix(self.path.suffix + '.key')
        if create and not key_path.exists():
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as file:
                    file.write(os.urandom(32))
        return key_path.read_bytes()

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_bytes()
            if raw.startswith(b'DPAPI1\n') and os.name == 'nt':
                plain = _dpapi(raw[7:], decrypt=True)
            elif raw.startswith(b'AESGCM1\n'):
                from Crypto.Cipher import AES
                nonce, tag, body = raw[8:24], raw[24:40], raw[40:]
                plain = AES.new(self._key(), AES.MODE_GCM, nonce=nonce).decrypt_and_verify(body, tag)
            else:
                raise ValueError('unsupported store')
            data = json.loads(plain)
            if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
                raise ValueError('invalid store')
            return data
        except Exception:
            raise CredentialStoreError('本地凭据文件无法读取，请检查文件及当前系统用户') from None

    def save(self, accounts: dict) -> None:
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            plain = json.dumps(accounts, ensure_ascii=False).encode('utf-8')
            if os.name == 'nt':
                sealed = b'DPAPI1\n' + _dpapi(plain)
            else:
                from Crypto.Cipher import AES
                cipher = AES.new(self._key(create=True), AES.MODE_GCM)
                body, tag = cipher.encrypt_and_digest(plain)
                sealed = b'AESGCM1\n' + cipher.nonce + tag + body
            fd, temp = tempfile.mkstemp(dir=self.path.parent, prefix='.credentials-')
            with os.fdopen(fd, 'wb') as file:
                file.write(sealed)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.path)
        except Exception:
            raise CredentialStoreError('本地凭据保存失败，原登录状态已保留') from None
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)
