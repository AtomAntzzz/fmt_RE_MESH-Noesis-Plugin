"""Bounded binary reads; independent of the plugin host."""

import hashlib
import struct


def sha256_bytes(data):
	return hashlib.sha256(data).hexdigest()


def checked_range(data, start, size, label, error_type=ValueError):
	end = start + size
	if start < 0 or size < 0 or end < start or end > len(data):
		raise error_type("offset-out-of-bounds:" + label)
	return (start, end)


def read_scalar(data, offset, fmt, label, error_type=ValueError):
	checked_range(data, offset, struct.calcsize(fmt), label, error_type)
	return struct.unpack_from(fmt, data, offset)[0]


def read_utf16z(data, offset, limit, label, error_type=ValueError):
	if offset % 2 or offset < 0 or offset >= limit or limit > len(data):
		raise error_type(label + "-out-of-bounds")
	end = offset
	while end + 2 <= limit and data[end:end + 2] != b"\0\0":
		end += 2
	if end + 2 > limit:
		raise error_type(label + "-unterminated")
	try:
		value = data[offset:end].decode("utf-16le")
	except UnicodeDecodeError:
		raise error_type(label + "-invalid-utf16")
	if not value:
		raise error_type(label + "-empty")
	return value


def ranges_overlap(left, right):
	return left[0] < right[1] and right[0] < left[1]




def readUIntAt(bs, readAt):
	pos = bs.tell()
	bs.seek(readAt)
	value = bs.readUInt()
	bs.seek(pos)
	return value

def readUShortAt(bs, tell):
	pos = bs.tell()
	bs.seek(tell)
	out = bs.readUShort()
	bs.seek(pos)
	return out

def readUByteAt(bs, tell):
	pos = bs.tell()
	bs.seek(tell)
	out = bs.readUByte()
	bs.seek(pos)
	return out

def ReadUnicodeString(bs):
	numZeroes = 0
	resultString = ""
	while(numZeroes < 2):
		c = bs.readUByte()
		if c == 0:
			numZeroes+=1
			continue
		else:
			numZeroes = 0
		resultString += chr(c)
	return resultString

def readUnicodeStringAt(bs, tell):
	string = []
	pos = bs.tell()
	bs.seek(tell)
	while(readUShortAt(bs, bs.tell()) != 0):
		string.append(bs.readByte())
		bs.seek(1,1)
	bs.seek(pos)
	buff = struct.pack("<" + 'b'*len(string), *string)
	return str(buff, 'utf-8')

# Murmur3 hash algorithm, credit to Darkness for adapting this.
def hash(key, getUnsigned=False):

	seed = 0xffffffff
	key = bytearray(key, 'utf8')

	def fmix(h):
		h ^= h >> 16
		h = (h * 0x85ebca6b) & 0xFFFFFFFF
		h ^= h >> 13
		h = (h * 0xc2b2ae35) & 0xFFFFFFFF
		h ^= h >> 16
		return h

	length = len(key)
	nblocks = int(length / 4)

	h1 = seed

	c1 = 0xcc9e2d51
	c2 = 0x1b873593

	for block_start in range(0, nblocks * 4, 4):
		k1 = key[block_start + 3] << 24 | \
			 key[block_start + 2] << 16 | \
			 key[block_start + 1] << 8 | \
			 key[block_start + 0]

		k1 = (c1 * k1) & 0xFFFFFFFF
		k1 = (k1 << 15 | k1 >> 17) & 0xFFFFFFFF
		k1 = (c2 * k1) & 0xFFFFFFFF

		h1 ^= k1
		h1 = (h1 << 13 | h1 >> 19) & 0xFFFFFFFF
		h1 = (h1 * 5 + 0xe6546b64) & 0xFFFFFFFF

	tail_index = nblocks * 4
	k1 = 0
	tail_size = length & 3

	if tail_size >= 3:
		k1 ^= key[tail_index + 2] << 16
	if tail_size >= 2:
		k1 ^= key[tail_index + 1] << 8
	if tail_size >= 1:
		k1 ^= key[tail_index + 0]

	if tail_size > 0:
		k1 = (k1 * c1) & 0xFFFFFFFF
		k1 = (k1 << 15 | k1 >> 17) & 0xFFFFFFFF
		k1 = (k1 * c2) & 0xFFFFFFFF
		h1 ^= k1

	unsigned_val = fmix(h1 ^ length)
	if getUnsigned or unsigned_val & 0x80000000 == 0:
		return unsigned_val
	else:
		return -((unsigned_val ^ 0xFFFFFFFF) + 1)

def hash_wide(key, getUnsigned=False):
    key_temp = ''
    for char in key:
        key_temp += char + '\x00'
    return hash(key_temp, getUnsigned)
