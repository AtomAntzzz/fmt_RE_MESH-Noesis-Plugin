"""Gdeflate implementation bound to one plugin runtime."""

import os
import struct
from re_engine_types import (
	MaterialProfileError,
)

# Host/state/callback dependencies (resolved on use, never copied).
RUNTIME_DEPENDENCIES = (
	'__file__',
)


def bind(runtime):
	def loadGDeflateDecoder(helperPath=None):
		try:
			import ctypes
		except ImportError:
			raise MaterialProfileError("gdeflate-ctypes-unavailable")
		architecture = "x64" if struct.calcsize("P") == 8 else "x86"
		helperName = "pragmata_gdeflate_" + architecture + ".dll"
		helperPath = helperPath or os.path.join(os.path.dirname(os.path.abspath(runtime.__file__)), helperName)
		if not os.path.isfile(helperPath):
			raise MaterialProfileError("gdeflate-helper-missing:" + helperName)
		try:
			library = ctypes.CDLL(helperPath)
			abiVersion = library.pragmata_gdeflate_abi_version
			abiVersion.argtypes = []
			abiVersion.restype = ctypes.c_uint32
			decompress = library.pragmata_gdeflate_decompress
			decompress.argtypes = [
				ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
				ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
			]
			decompress.restype = ctypes.c_int
		except (AttributeError, OSError):
			raise MaterialProfileError("gdeflate-helper-load-failed")
		if abiVersion() != 1:
			raise MaterialProfileError("gdeflate-helper-abi-mismatch")
		def decode(chunk, outputSize):
			if not chunk or outputSize < 1:
				raise MaterialProfileError("gdeflate-invalid-buffer-size")
			inputBuffer = (ctypes.c_uint8 * len(chunk)).from_buffer_copy(chunk)
			outputBuffer = (ctypes.c_uint8 * outputSize)()
			if decompress(outputBuffer, outputSize, inputBuffer, len(chunk)) != 1:
				raise MaterialProfileError("gdeflate-decompression-failed")
			return ctypes.string_at(outputBuffer, outputSize)
		return decode

	return (
		loadGDeflateDecoder,
	)
