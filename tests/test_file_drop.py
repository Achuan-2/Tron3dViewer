from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
import tifffile

from tron3d.main_window import MainWindow


class FileDropTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.volume_view.canvas.close)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def drop(self, urls):
        mime = QMimeData()
        mime.setUrls(urls)
        enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.window, enter)
        QApplication.sendEvent(self.window, drop)
        QApplication.processEvents()
        return enter, drop

    def test_supported_local_files_open_once(self):
        for suffix in ('.ims', '.tif', '.TIFF'):
            with self.subTest(suffix=suffix):
                path = self.directory / ('中文 图像' + suffix)
                path.touch()
                with patch.object(self.window, 'open_volume') as load:
                    enter, drop = self.drop([QUrl.fromLocalFile(str(path))])
                    self.assertTrue(enter.isAccepted())
                    self.assertTrue(drop.isAccepted())
                    load.assert_called_once_with(str(path))

    def test_directories_remote_and_unsupported_files_are_rejected(self):
        invalid = self.directory / 'image.png'
        invalid.touch()
        with patch.object(self.window, 'open_volume') as load:
            enter, drop = self.drop([
                QUrl.fromLocalFile(str(self.directory)), QUrl.fromLocalFile(str(invalid)),
                QUrl.fromLocalFile(str(self.directory / 'missing.tif')),
                QUrl('https://example.com/image.tif'),
            ])
            self.assertFalse(enter.isAccepted())
            self.assertFalse(drop.isAccepted())
            load.assert_not_called()

    def test_drop_loads_tiff_and_updates_calibration(self):
        source = self.directory / 'stack.tif'
        pixels = np.arange(5 * 6 * 7, dtype=np.uint16).reshape(5, 6, 7)
        tifffile.imwrite(source, pixels, photometric='minisblack', metadata={'axes': 'ZYX'})
        with patch('tron3d.main_window.QMessageBox.critical') as error:
            self.drop([QUrl.fromLocalFile(str(source))])
            error.assert_not_called()
        self.assertEqual(self.window.data.source, source)
        np.testing.assert_array_equal(self.window.data.channels[0], pixels)
        self.assertEqual([spin.value() for spin in self.window.spatial_spins], [7, 6, 5])


if __name__ == '__main__':
    unittest.main()
