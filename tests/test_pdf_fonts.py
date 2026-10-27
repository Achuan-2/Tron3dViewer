from io import BytesIO
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, ContentStream, DecodedStreamObject, FloatObject, NameObject,
)
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF
from PySide6.QtGui import QFont, QFontInfo, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

from tron3d.pdf_fonts import use_system_arial


class PdfFontCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if QFontInfo(QFont("Arial")).family() != "Arial":
            raise unittest.SkipTest("Arial must be installed to check system-font export")

    def make_pdf(self, runs):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        device = QPdfWriter(buffer)
        painter = QPainter(device)
        for index, (family, text) in enumerate(runs):
            painter.setFont(family if isinstance(family, QFont) else QFont(family, 12))
            painter.drawText(QPointF(100, 300 + index * 300), text)
        painter.end()
        buffer.close()
        return PdfWriter(clone_from=BytesIO(bytes(data)))

    def reopen(self, writer):
        output = BytesIO()
        writer.write(output)
        return PdfReader(BytesIO(output.getvalue()))

    def test_western_text_has_real_font_name_and_round_trips(self):
        text = "100 µm; café; €; ×; °"
        writer = self.make_pdf([("Arial", text)])
        use_system_arial(writer.pages[0], writer)
        page = self.reopen(writer).pages[0]
        self.assertEqual(page.extract_text(), text)
        font = next(iter(page["/Resources"]["/Font"].values())).get_object()
        self.assertEqual(font["/BaseFont"], "/ArialMT")
        self.assertEqual(font["/Encoding"], "/WinAnsiEncoding")
        self.assertEqual(font["/FontDescriptor"]["/FontName"], "/ArialMT")
        self.assertNotIn("/FontFile2", font["/FontDescriptor"])

    def test_unicode_keeps_original_embedded_font(self):
        for text in ("100 μm", "−100", "测试", "X 测试 100 µm"):
            with self.subTest(text=text):
                writer = self.make_pdf([("Arial", text)])
                page = writer.pages[0]
                before = page.extract_text()
                use_system_arial(page, writer)
                page = self.reopen(writer).pages[0]
                self.assertEqual(page.extract_text(), before)
                self.assertIn(text.replace(" ", ""), before.replace(" ", "").replace("\n", ""))
                embedded = [font.get_object() for font in page["/Resources"]["/Font"].values()
                            if font.get_object()["/Subtype"] == "/Type0"]
                self.assertTrue(embedded)
                for font in embedded:
                    descriptor = font["/DescendantFonts"][0].get_object()["/FontDescriptor"]
                    self.assertIn("/FontFile2", descriptor)

    def test_arial_styles_keep_their_real_names(self):
        for bold, italic, name in ((True, False, "Arial-BoldMT"), (False, True, "Arial-ItalicMT"),
                                   (True, True, "Arial-BoldItalicMT")):
            with self.subTest(name=name):
                font = QFont("Arial", 12)
                font.setBold(bold)
                font.setItalic(italic)
                writer = self.make_pdf([(font, "Arial 100 µm")])
                use_system_arial(writer.pages[0], writer)
                page = self.reopen(writer).pages[0]
                font = next(iter(page["/Resources"]["/Font"].values())).get_object()
                self.assertEqual(font["/BaseFont"], "/" + name)
                self.assertEqual(page.extract_text(), "Arial 100 µm")

    def test_explicit_and_contiguous_unicode_mappings(self):
        for entries in (b"3 beginbfchar <0001> <0041> <0002> <0042> <0003> <0043> endbfchar",
                        b"1 beginbfrange <0001> <0003> <0041> endbfrange"):
            with self.subTest(entries=entries):
                writer = self.make_pdf([("Arial", "ABC")])
                page = writer.pages[0]
                font = next(iter(page["/Resources"]["/Font"].values())).get_object()
                cmap = DecodedStreamObject()
                cmap.set_data(b"1 begincodespacerange <0000> <FFFF> endcodespacerange\n" + entries)
                font[NameObject("/ToUnicode")] = cmap
                use_system_arial(page, writer)
                page = self.reopen(writer).pages[0]
                font = next(iter(page["/Resources"]["/Font"].values())).get_object()
                self.assertEqual(font["/Subtype"], "/TrueType")
                self.assertEqual(page.extract_text(), "ABC")

    def test_each_font_uses_its_own_encoding(self):
        writer = self.make_pdf([("Arial", "Arial 100 µm"), ("Times New Roman", "Times 250"),
                                ("Arial", "X 测试")])
        page = writer.pages[0]
        before = page.extract_text()
        original_fonts = {name: reference.get_object() for name, reference in page["/Resources"]["/Font"].items()}
        use_system_arial(page, writer)
        page = self.reopen(writer).pages[0]
        self.assertEqual(page.extract_text(), before)
        converted = 0
        for name, reference in page["/Resources"]["/Font"].items():
            font = reference.get_object()
            if font["/Subtype"] == "/TrueType":
                self.assertEqual(font["/BaseFont"], "/ArialMT")
                converted += 1
            else:
                self.assertEqual(font["/BaseFont"], original_fonts[name]["/BaseFont"])
                self.assertIn("/FontFile2", font["/DescendantFonts"][0].get_object()["/FontDescriptor"])
        self.assertEqual(converted, 1)

    def test_shared_page_resources_are_not_mutated(self):
        writer = self.make_pdf([("Arial", "100 µm")])
        original = writer.pages[0]
        duplicate = writer.add_blank_page(width=float(original.mediabox.width), height=float(original.mediabox.height))
        duplicate[NameObject("/Resources")] = original["/Resources"]
        duplicate[NameObject("/Contents")] = original.raw_get("/Contents")
        use_system_arial(original, writer)
        self.assertEqual(next(iter(duplicate["/Resources"]["/Font"].values())).get_object()["/Subtype"], "/Type0")
        use_system_arial(duplicate, writer)
        for page in self.reopen(writer).pages:
            self.assertEqual(page.extract_text(), "100 µm")
            self.assertEqual(next(iter(page["/Resources"]["/Font"].values())).get_object()["/Subtype"], "/TrueType")

    def test_fractional_kerning_is_preserved(self):
        writer = self.make_pdf([("Arial", "Arial")])
        page = writer.pages[0]
        content = ContentStream(page.get_contents(), writer)
        for index, (operands, operator) in enumerate(content.operations):
            if operator == b"Tj":
                content.operations[index] = ([ArrayObject([operands[0], FloatObject(-12.75)])], b"TJ")
                break
        else:
            self.fail("Qt did not emit text")
        page.replace_contents(content)
        use_system_arial(page, writer)
        page = self.reopen(writer).pages[0]
        values = [value for operands, operator in ContentStream(page.get_contents(), writer).operations
                  if operator == b"TJ" for value in operands[0] if isinstance(value, FloatObject)]
        self.assertIn(-12.75, values)
        self.assertEqual(page.extract_text(), "Arial")

    def test_saved_font_state_and_all_text_operators(self):
        writer = self.make_pdf([("Arial", "Arial"), ("Times New Roman", "Times")])
        page = writer.pages[0]
        names = list(page["/Resources"]["/Font"])
        content = ContentStream(page.get_contents(), writer)
        chunks = []
        current_font = None
        for operands, operator in content.operations:
            if operator == b"Tf":
                current_font = operands[0]
            elif operator == b"Tj" and current_font == names[0]:
                chunks.append(operands[0].original_bytes)
        source = b"".join(chunks)
        font_size = FloatObject(12)
        content.operations = [
            ([], b"BT"), ([names[0], font_size], b"Tf"), ([], b"q"),
            ([names[1], font_size], b"Tf"), ([], b"Q"),
            ([ByteStringObject(source)], b"Tj"), ([ByteStringObject(source)], b"'"),
            ([FloatObject(0), FloatObject(0), ByteStringObject(source)], b'"'),
            ([ArrayObject([ByteStringObject(source), FloatObject(1.5)])], b"TJ"), ([], b"ET"),
        ]
        page.replace_contents(content)
        use_system_arial(page, writer)
        reader = self.reopen(writer)
        parsed = ContentStream(reader.pages[0].get_contents(), reader)
        for operands, operator in parsed.operations:
            if operator in (b"Tj", b"'", b'"'):
                self.assertEqual(operands[-1].original_bytes, b"Arial")
            elif operator == b"TJ":
                self.assertEqual(operands[0][0].original_bytes, b"Arial")

    def test_unmapped_glyph_keeps_whole_font_unchanged(self):
        writer = self.make_pdf([("Arial", "100 µm")])
        page = writer.pages[0]
        content = ContentStream(page.get_contents(), writer)
        index = next(i for i, (_, operator) in enumerate(content.operations) if operator == b"Tj")
        content.operations.insert(index + 1, ([ByteStringObject(b"\xff\xff")], b"Tj"))
        page.replace_contents(content)
        before = page.get_contents().get_data()
        use_system_arial(page, writer)
        self.assertEqual(page.get_contents().get_data(), before)
        font = next(iter(page["/Resources"]["/Font"].values())).get_object()
        self.assertIn("/FontFile2", font["/DescendantFonts"][0].get_object()["/FontDescriptor"])

    def test_unfamiliar_cmap_keeps_embedded_font(self):
        writer = self.make_pdf([("Arial", "Arial")])
        page = writer.pages[0]
        font = next(iter(page["/Resources"]["/Font"].values())).get_object()
        cmap = DecodedStreamObject()
        cmap.set_data(b"/Other-CMap usecmap")
        font[NameObject("/ToUnicode")] = cmap
        before = page.get_contents().get_data()
        use_system_arial(page, writer)
        self.assertEqual(page.get_contents().get_data(), before)
        self.assertEqual(font["/Subtype"], "/Type0")


if __name__ == "__main__":
    unittest.main()
