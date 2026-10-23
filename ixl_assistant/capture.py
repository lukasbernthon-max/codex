"""Capture one native-resolution monitor, then select in Qt logical coordinates."""
import mss
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


def capture_monitor(screen):
    # Qt screen order can differ from MSS. Match physical origin using Windows DPI.
    ratio = screen.devicePixelRatio()
    geometry = screen.geometry()
    with mss.mss() as grabber:
        monitors = grabber.monitors[1:]
        if not monitors:
            raise RuntimeError("No monitor is available for capture.")
        # On Windows Qt's origin is physical, but its dimensions are logical.
        target = min(monitors, key=lambda m:
                     abs(m["left"] - geometry.x()) + abs(m["top"] - geometry.y()) +
                     abs(m["width"] - round(geometry.width() * ratio)))
        shot = grabber.grab(target)
        return QImage(shot.rgb, shot.width, shot.height,
                      shot.width * 3, QImage.Format.Format_RGB888).copy()


class RegionSelector(QWidget):
    selected = Signal(QImage)
    cancelled = Signal()

    def __init__(self, screen, image):
        super().__init__()
        self.image = image
        self.origin = None
        self.selection = QRect()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(self.rect(), self.image)
        painter.fillRect(self.rect(), QColor(5, 10, 24, 150))
        if not self.selection.isEmpty():
            painter.save()
            painter.setClipRect(self.selection)
            painter.drawImage(self.rect(), self.image)
            painter.restore()
            painter.setPen(QPen(QColor("#5da5ff"), 2))
            painter.drawRect(self.selection)
        painter.setPen(QColor("white"))
        painter.drawText(24, 36, "Drag around the complete question  •  Esc to cancel")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.origin is None:
            return
        self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
        if self.selection.width() < 20 or self.selection.height() < 20:
            self.origin = None
            self.selection = QRect()
            self.update()
            return
        sx, sy = self.image.width() / self.width(), self.image.height() / self.height()
        r = self.selection
        crop = self.image.copy(QRect(round(r.x()*sx), round(r.y()*sy),
                                    round(r.width()*sx), round(r.height()*sy)))
        self.close()
        self.selected.emit(crop)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.cancelled.emit()
