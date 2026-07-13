#!/usr/bin/env python3
import pathlib
import struct
import sys


def u2(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def u4(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def cp_utf8(cp, index):
    value = cp[index]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return None


def parse_constant_pool(data):
    cp_count = u2(data, 8)
    cp = [None] * cp_count
    offset = 10
    i = 1
    while i < cp_count:
        tag = data[offset]
        offset += 1
        if tag == 1:
            length = u2(data, offset)
            offset += 2
            cp[i] = data[offset:offset + length]
            offset += length
        elif tag in (3, 4):
            offset += 4
        elif tag in (5, 6):
            offset += 8
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            offset += 2
        elif tag in (9, 10, 11, 12, 18):
            offset += 4
        elif tag == 15:
            offset += 3
        else:
            raise ValueError("unsupported constant pool tag %d at cp index %d" % (tag, i))
        i += 1
    return cp, offset


def copy_attributes(data, offset, cp):
    count = u2(data, offset)
    offset += 2
    kept = []
    removed = 0
    for _ in range(count):
        start = offset
        name_index = u2(data, offset)
        length = u4(data, offset + 2)
        offset += 6 + length
        if cp_utf8(cp, name_index) == "MethodParameters":
            removed += 1
        else:
            kept.append(data[start:offset])
    out = bytearray(struct.pack(">H", len(kept)))
    for attr in kept:
        out.extend(attr)
    return bytes(out), offset, removed


def copy_members(data, offset, cp):
    count = u2(data, offset)
    offset += 2
    out = bytearray(struct.pack(">H", count))
    removed = 0
    for _ in range(count):
        out.extend(data[offset:offset + 6])
        offset += 6
        attrs, offset, attr_removed = copy_attributes(data, offset, cp)
        out.extend(attrs)
        removed += attr_removed
    return bytes(out), offset, removed


def strip_file(path):
    data = path.read_bytes()
    if data[:4] != b"\xca\xfe\xba\xbe":
        return 0
    cp, offset = parse_constant_pool(data)
    out = bytearray(data[:offset])

    out.extend(data[offset:offset + 6])
    offset += 6

    interface_count = u2(data, offset)
    interface_bytes = 2 + interface_count * 2
    out.extend(data[offset:offset + interface_bytes])
    offset += interface_bytes

    fields, offset, removed_fields = copy_members(data, offset, cp)
    methods, offset, removed_methods = copy_members(data, offset, cp)
    attrs, offset, removed_class = copy_attributes(data, offset, cp)
    out.extend(fields)
    out.extend(methods)
    out.extend(attrs)
    if offset != len(data):
        raise ValueError("trailing class data in %s" % path)
    removed = removed_fields + removed_methods + removed_class
    if removed:
        path.write_bytes(bytes(out))
    return removed


def main():
    root = pathlib.Path(sys.argv[1])
    total = 0
    for path in root.rglob("*.class"):
        total += strip_file(path)
    print("stripped MethodParameters attributes:", total)


if __name__ == "__main__":
    main()
