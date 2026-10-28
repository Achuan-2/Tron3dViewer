import html
import unittest

from PySide6.QtWidgets import QApplication

from tron3dviewer import __version__
from tron3dviewer.about import AUTHOR_URL, DONATION_URL, GITHUB_URL, AboutDialog
from tron3dviewer.i18n import set_language


class AboutDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        set_language("zh_CN")
        self.addCleanup(set_language, "zh_CN")

    def test_about_contains_project_links_and_local_reward_qr(self):
        dialog = AboutDialog()
        self.addCleanup(dialog.close)

        self.assertIn(__version__, dialog.windowTitle() + "".join(label.text() for label in dialog.findChildren(type(dialog.author_label))))
        self.assertIn(AUTHOR_URL, dialog.author_label.text())
        self.assertIn(GITHUB_URL, dialog.github_label.text())
        self.assertIn(html.escape(DONATION_URL, quote=True), dialog.donation_link.text())
        self.assertTrue(dialog.author_label.openExternalLinks())
        self.assertTrue(dialog.github_label.openExternalLinks())
        self.assertTrue(dialog.donation_link.openExternalLinks())
        self.assertFalse(dialog.qr_pixmap.isNull())
        self.assertFalse(dialog.qr_label.pixmap().isNull())

    def test_about_uses_english_translation(self):
        set_language("en")
        dialog = AboutDialog()
        self.addCleanup(dialog.close)

        self.assertEqual(dialog.windowTitle(), "About Tron 3D viewer")
        self.assertIn("Author", dialog.author_label.text())
        self.assertIn("Other ways to support", dialog.donation_link.text())


if __name__ == "__main__":
    unittest.main()
