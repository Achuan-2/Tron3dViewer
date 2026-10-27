"""Make Qt's Arial text editable through an installed font in PDF editors.

Only Qt's two-byte Identity-H TrueType output is converted. Fonts or characters
that cannot be represented safely in WinAnsi keep their embedded Unicode font.
"""

from struct import error as StructError, unpack_from

from pypdf import PageObject, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject, ByteStringObject, ContentStream, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)


_ARIAL_FACES = {"ArialMT", "Arial-BoldMT", "Arial-ItalicMT", "Arial-BoldItalicMT"}


def _postscript_name(font_data: bytes) -> str | None:
    """Read name ID 6 from the embedded TrueType program, not a Qt alias."""
    table_count = unpack_from(">H", font_data, 4)[0]
    for index in range(table_count):
        tag, _, offset, length = unpack_from(">4sIII", font_data, 12 + index * 16)
        if tag != b"name":
            continue
        table = font_data[offset:offset + length]
        _, count, strings_offset = unpack_from(">HHH", table)
        for record in range(count):
            platform, _, _, name_id, size, start = unpack_from(">HHHHHH", table, 6 + record * 12)
            if name_id == 6 and platform in (0, 1, 3):
                value = table[strings_offset + start:strings_offset + start + size]
                name = value.decode("mac_roman" if platform == 1 else "utf-16-be")
                if name in _ARIAL_FACES:
                    return name
    return None


def _qt_unicode_map(font: DictionaryObject, writer: PdfWriter) -> dict[int, str]:
    """Read Qt's two-byte CMap using pypdf's public content-stream parser.

    This deliberately supports only bfchar and bfrange mappings. An unfamiliar
    CMap is left embedded rather than guessed or parsed through a private API.
    """
    mapping = {}
    for operands, operator in ContentStream(font["/ToUnicode"], writer).operations:
        if operator == b"endcodespacerange":
            if len(operands) != 2 or any(len(value.original_bytes) != 2 for value in operands):
                raise ValueError("Expected Qt's two-byte character codes")
        elif operator == b"endbfchar":
            for index in range(0, len(operands), 2):
                source, target = operands[index:index + 2]
                mapping[int.from_bytes(source.original_bytes, "big")] = target.original_bytes.decode("utf-16-be")
        elif operator == b"endbfrange":
            for index in range(0, len(operands), 3):
                first, last, target = operands[index:index + 3]
                first = int.from_bytes(first.original_bytes, "big")
                last = int.from_bytes(last.original_bytes, "big")
                if not 0 <= first <= last <= 65535:
                    raise ValueError("Invalid Qt character range")
                if isinstance(target, ArrayObject):
                    if len(target) != last - first + 1:
                        raise ValueError("Incomplete Qt character range")
                    values = [value.original_bytes for value in target]
                else:
                    value = target.original_bytes
                    start = int.from_bytes(value, "big")
                    values = [(start + offset).to_bytes(len(value), "big") for offset in range(last - first + 1)]
                mapping.update((first + offset, value.decode("utf-16-be")) for offset, value in enumerate(values))
        elif operator in (b"usecmap", b"endcidchar", b"endcidrange"):
            raise ValueError("Unsupported Qt character mapping")
    if not mapping:
        raise ValueError("Missing Qt Unicode mapping")
    return mapping


def _prepare_arial(font: DictionaryObject, writer: PdfWriter) -> tuple[dict[int, int], DictionaryObject] | None:
    if font.get("/Subtype") != "/Type0" or font.get("/Encoding") != "/Identity-H":
        return None
    descendant = font["/DescendantFonts"][0].get_object()
    if descendant.get("/Subtype") != "/CIDFontType2":
        return None
    descriptor = descendant["/FontDescriptor"].get_object()
    name = _postscript_name(descriptor["/FontFile2"].get_data())
    if name is None:
        return None

    encoded = {}
    for cid, text in _qt_unicode_map(font, writer).items():
        value = text.encode("cp1252")
        if len(value) != 1:
            return None
        encoded[cid] = value[0]

    cid_widths = {}
    width_data = descendant.get("/W", [])
    index = 0
    while index < len(width_data):
        first, values = int(width_data[index]), width_data[index + 1]
        if isinstance(values, ArrayObject):
            cid_widths.update((first + offset, width) for offset, width in enumerate(values))
            index += 2
        else:
            cid_widths.update((cid, width_data[index + 2]) for cid in range(first, int(values) + 1))
            index += 3
    widths = ArrayObject(NumberObject(0) for _ in range(256))
    for cid, code in encoded.items():
        widths[code] = cid_widths.get(cid, descendant.get("/DW", NumberObject(1000)))

    # Clone shared descriptors: another page may still use the original CID font.
    descriptor = DictionaryObject(descriptor)
    for key in ("/FontFile", "/FontFile2", "/FontFile3", "/CIDSet"):
        descriptor.pop(key, None)
    descriptor[NameObject("/FontName")] = NameObject("/" + name)
    descriptor[NameObject("/Flags")] = NumberObject((int(descriptor.get("/Flags", 0)) & ~4) | 32)
    replacement = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/TrueType"),
        NameObject("/BaseFont"): NameObject("/" + name),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        NameObject("/FirstChar"): NumberObject(0),
        NameObject("/LastChar"): NumberObject(255),
        NameObject("/Widths"): widths,
        NameObject("/FontDescriptor"): descriptor,
    })
    return encoded, replacement


def use_system_arial(page: PageObject, writer: PdfWriter) -> None:
    """Convert each eligible Arial font atomically; leave other fonts intact."""
    fonts = page["/Resources"].get("/Font", {})
    candidates = {}
    for name, reference in fonts.items():
        try:
            prepared = _prepare_arial(reference.get_object(), writer)
        except (KeyError, IndexError, AttributeError, TypeError, ValueError, OverflowError, StructError, PdfReadError):
            # Unsupported Unicode, missing font data or unfamiliar Qt output.
            continue
        if prepared is not None:
            candidates[name] = prepared
    if not candidates:
        return

    content = ContentStream(page.get_contents(), writer)
    replacements = {name: [] for name in candidates}
    rejected = set()
    current_font = None
    saved_fonts = []
    for operands, operator in content.operations:
        if operator == b"Tf":
            current_font = operands[0]
        elif operator == b"q":
            saved_fonts.append(current_font)
        elif operator == b"Q":
            current_font = saved_fonts.pop() if saved_fonts else None
        elif operator in (b"Tj", b"'", b'"', b"TJ") and current_font in candidates and current_font not in rejected:
            codes, _ = candidates[current_font]

            def encode(value):
                source = value.original_bytes
                if len(source) % 2:
                    raise ValueError("Incomplete Qt character code")
                return ByteStringObject(bytes(codes[int.from_bytes(source[i:i + 2], "big")]
                                              for i in range(0, len(source), 2)))

            try:
                if operator == b"TJ":
                    # Preserve fractional kerning values instead of rounding to integers.
                    value = ArrayObject(encode(item) if isinstance(item, (str, bytes)) else item for item in operands[0])
                else:
                    value = encode(operands[-1])
            except (KeyError, ValueError):
                rejected.add(current_font)
                continue
            replacements[current_font].append((operands, value))

    converted = {name for name in candidates if name not in rejected and replacements[name]}
    if not converted:
        return
    # Font resources can also be shared across pages. Replace only this page's
    # dictionary; never change the original embedded font or its descriptor.
    resources = DictionaryObject(page["/Resources"])
    fonts = DictionaryObject(fonts)
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    for name in converted:
        _, font = candidates[name]
        font[NameObject("/FontDescriptor")] = writer._add_object(font["/FontDescriptor"])
        fonts[name] = writer._add_object(font)
        for operands, value in replacements[name]:
            operands[-1] = value
    # replace_contents() rewrites the old indirect stream in place, which can
    # also change pages that share it. Allocate a new stream for this page.
    stream = DecodedStreamObject()
    stream.set_data(content.get_data())
    page[NameObject("/Contents")] = writer._add_object(stream)
