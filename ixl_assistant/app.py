"""Focus desktop UI. All widgets stay on the GUI thread."""
import sys
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import (Qt, Signal, QObject, QRunnable, QThreadPool, QTimer,
                            QBuffer, QIODevice, QSettings)
from PySide6.QtGui import QCursor, QPixmap, QCloseEvent
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QDialog, QLineEdit, QFormLayout, QMessageBox,
    QSlider, QProgressBar, QScrollArea, QFrame, QSizeGrip)

from .capture import capture_monitor, RegionSelector
from .solver import solve, Solution
from .storage import load_key, save_key

STYLE = """
QWidget { background: #101725; color: #e9eef8; font-family: 'Segoe UI'; font-size: 13px; }
QFrame#card { background: #182235; border: 1px solid #293950; border-radius: 14px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 19px; font-weight: 700; color: #7eb6ff; }
QLabel#answer { font-size: 25px; font-weight: 700; color: #f4f8ff; }
QLabel#muted { color: #9aacc6; }
QPushButton { background: #23324a; border: 1px solid #354866; border-radius: 8px; padding: 9px 12px; }
QPushButton:hover { background: #304766; border-color: #639fff; }
QPushButton:disabled { color: #697c98; background: #1a2537; }
QPushButton#primary { background: #3479ec; border-color: #5798ff; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #438af9; }
QComboBox, QLineEdit { background: #1b283e; border: 1px solid #354866; border-radius: 7px; padding: 8px; }
QProgressBar { border: none; background: #1d2c43; max-height: 4px; border-radius: 2px; }
QProgressBar::chunk { background: #5798ff; }
QSlider::groove:horizontal { height: 4px; background: #354866; }
QSlider::handle:horizontal { background: #7eb6ff; width: 12px; margin: -4px 0; border-radius: 6px; }
QScrollArea { border: none; }
"""


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class SolveTask(QRunnable):
    def __init__(self, png, key, model, detailed):
        super().__init__()
        self.args = (png, key, model, detailed)
        self.signals = Signals()

    def run(self):
        from openai import AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError, BadRequestError
        try:
            self.signals.done.emit(solve(*self.args))
        except AuthenticationError:
            self.signals.failed.emit("Your API key was rejected. Update it in Settings.")
        except RateLimitError:
            self.signals.failed.emit("API quota or rate limit reached. Check your OpenAI billing and try again shortly.")
        except (APIConnectionError, APITimeoutError):
            self.signals.failed.emit("Could not reach OpenAI. Check your connection, then use Retry.")
        except BadRequestError:
            self.signals.failed.emit("The API rejected this request. Check model access in Settings or capture a smaller region.")
        except Exception:
            # Never display raw SDK errors: they may contain request content.
            self.signals.failed.emit("No complete solution was received. Retry or recapture the full question.")
        finally:
            self.args = ()


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Focus settings")
        self.setMinimumWidth(410)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Connect your OpenAI account", "brand"))
        layout.addWidget(label("Selected screenshots are sent to OpenAI when you capture. API usage is billed separately. Keys are stored in Windows Credential Manager.", "muted"))
        form = QFormLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Enter your API key")
        self.storage_ok = True
        try:
            self.key.setText(load_key())
        except Exception:
            self.storage_ok = False
            layout.addWidget(label("Secure credential storage is unavailable. No key will be saved in plaintext."))
        self.model = QLineEdit(parent.settings.value("model", "gpt-4.1-mini"))
        form.addRow("API key", self.key)
        form.addRow("Vision model", self.model)
        layout.addLayout(form)
        layout.addWidget(label("Default: gpt-4.1-mini. Use a vision model that supports structured Responses output. AI answers can be wrong; review the explanation.", "muted"))
        button = QPushButton("Save settings")
        button.setObjectName("primary")
        button.clicked.connect(self.save)
        layout.addWidget(button)

    def save(self):
        if not self.model.text().strip():
            QMessageBox.warning(self, "Model required", "Enter a vision model name.")
            return
        try:
            if not self.storage_ok:
                raise RuntimeError()
            save_key(self.key.text())
        except Exception:
            QMessageBox.warning(self, "Secure storage unavailable", "Could not save your key securely. Ensure Windows Credential Manager is available.")
            return
        self.parent().settings.setValue("model", self.model.text().strip())
        self.accept()


@dataclass
class HistoryEntry:
    title: str
    image: object
    solution: Solution


class HotkeyBridge(QObject):
    capture = Signal()


class MainWindow(QWidget):
    def __init__(self, enable_hotkey=True):
        super().__init__()
        self.settings = QSettings("FocusAssistant", "Focus")
        self.setWindowTitle("Focus • Screenshot assistant")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(440, 720)
        self.setMinimumSize(360, 510)
        self.busy = False
        self.selecting = False
        self.image = None
        self.solution = None
        self.history = []
        self.listener = None
        self.selector = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.bridge = HotkeyBridge(self)
        self.bridge.capture.connect(self.begin_capture)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 8)
        header = QHBoxLayout()
        header.addWidget(label("◈  Focus", "brand"))
        header.addStretch()
        settings = QPushButton("Settings")
        settings.clicked.connect(lambda: SettingsDialog(self).exec())
        header.addWidget(settings)
        outer.addLayout(header)
        outer.addWidget(label("SCREENSHOT STUDY ASSISTANT", "muted"))
        outer.addWidget(label("Capture a question. Understand the answer.", "muted"))
        controls = QHBoxLayout()
        self.pin = QPushButton("Always on top ✓")
        self.pin.setCheckable(True)
        self.pin.setChecked(True)
        self.pin.clicked.connect(self.toggle_pin)
        controls.addWidget(self.pin)
        self.compact = QPushButton("Compact view")
        self.compact.setCheckable(True)
        self.compact.clicked.connect(self.toggle_compact)
        controls.addWidget(self.compact)
        outer.addLayout(controls)
        self.capture_button = QPushButton("＋  Capture question     Ctrl + Shift + S")
        self.capture_button.setObjectName("primary")
        self.capture_button.clicked.connect(self.begin_capture)
        outer.addWidget(self.capture_button)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Concise explanation", "Detailed explanation"])
        self.mode.setCurrentIndex(int(self.settings.value("detailed", 0)))
        self.mode.currentIndexChanged.connect(lambda i: self.settings.setValue("detailed", i))
        row.addWidget(self.mode)
        self.retry = QPushButton("Retry")
        self.retry.setEnabled(False)
        self.retry.clicked.connect(self.analyze)
        row.addWidget(self.retry)
        outer.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        outer.addWidget(self.progress)
        self.status = label("Ready • Capture the question and all answer choices.", "muted")
        outer.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        self.preview = label("Your selected screenshot will appear here", "muted")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(110)
        body.addWidget(self.preview)
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.addWidget(label("ANSWER", "muted"))
        self.answer = label("Let’s work it out.", "answer")
        self.answer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.answer)
        self.steps = label("Select a clear region with the complete question to get started.")
        self.steps.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(self.steps)
        self.check = label("", "muted")
        card_layout.addWidget(self.check)
        self.copy = QPushButton("Copy answer")
        self.copy.setEnabled(False)
        self.copy.clicked.connect(self.copy_answer)
        card_layout.addWidget(self.copy)
        body.addWidget(card)
        body.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        history_row = QHBoxLayout()
        self.history_combo = QComboBox()
        self.history_combo.addItem("Recent questions • this session")
        self.history_combo.activated.connect(self.show_history)
        history_row.addWidget(self.history_combo, 1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_history)
        self.clear_button = clear
        history_row.addWidget(clear)
        outer.addLayout(history_row)
        footer = QHBoxLayout()
        footer.addWidget(label("Opacity", "muted"))
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(55, 100)
        opacity.setValue(int(self.settings.value("opacity", 100)))
        opacity.valueChanged.connect(self.set_opacity)
        self.setWindowOpacity(opacity.value()/100)
        footer.addWidget(opacity)
        footer.addWidget(QSizeGrip(self))
        outer.addLayout(footer)
        outer.addWidget(label("AI can make mistakes. Check before you submit.", "muted"))
        if enable_hotkey:
            self.install_hotkey()

    def toggle_pin(self, enabled):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.pin.setText("Always on top ✓" if enabled else "Always on top")
        self.show()

    def toggle_compact(self, enabled):
        self.preview.setVisible(not enabled)
        self.compact.setText("Full view" if enabled else "Compact view")
        self.resize(self.width(), 550 if enabled else 760)

    def welcome(self):
        try:
            configured = bool(load_key())
        except Exception:
            configured = False
        if not configured:
            SettingsDialog(self).exec()

    def install_hotkey(self):
        try:
            from pynput.keyboard import GlobalHotKeys
            self.listener = GlobalHotKeys({"<ctrl>+<shift>+s": self.bridge.capture.emit})
            self.listener.start()
        except Exception:
            self.status.setText("Global shortcut unavailable. Use Capture question.")

    def set_opacity(self, value):
        self.setWindowOpacity(value / 100)
        self.settings.setValue("opacity", value)

    def begin_capture(self):
        if self.busy or self.selecting or QApplication.activeModalWidget():
            return
        try:
            key = load_key()
        except Exception:
            key = ""
        if not key:
            self.showNormal()
            SettingsDialog(self).exec()
            return
        self.capture_screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.selecting = True
        self.hide()
        QTimer.singleShot(250, self.open_selector)

    def open_selector(self):
        try:
            image = capture_monitor(self.capture_screen)
            self.selector = RegionSelector(self.capture_screen, image)
            self.selector.selected.connect(self.accept_capture)
            self.selector.cancelled.connect(self.cancel_capture)
            self.selector.show()
            self.selector.activateWindow()
            self.selector.setFocus()
        except Exception:
            self.cancel_capture()
            self.status.setText("Screen capture failed. Check display permissions and try again.")

    def finish_selector(self):
        self.selecting = False
        if self.selector:
            self.selector.deleteLater()
            self.selector = None
        self.showNormal()
        self.raise_()

    def cancel_capture(self):
        self.finish_selector()

    def accept_capture(self, image):
        self.finish_selector()
        self.image = image
        self.update_preview()
        self.analyze()

    def update_preview(self):
        if self.image is not None:
            self.preview.setPixmap(QPixmap.fromImage(self.image).scaled(
                max(280, self.width()-60), 180, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview"):
            self.update_preview()

    def set_busy(self, busy):
        self.busy = busy
        self.progress.setVisible(busy)
        for widget in (self.capture_button, self.mode, self.history_combo, self.clear_button):
            widget.setEnabled(not busy)
        self.retry.setEnabled(not busy and self.image is not None)
        self.copy.setEnabled(not busy and self.solution is not None and self.solution.status == "solved")

    def analyze(self):
        if self.busy or self.image is None:
            return
        try:
            key = load_key()
            if not key:
                raise ValueError()
        except Exception:
            self.status.setText("Add an API key in Settings before solving.")
            return
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.image.save(buffer, "PNG")
        png = bytes(buffer.data())
        buffer.close()
        if len(png) > 18 * 1024 * 1024:
            self.status.setText("Selection is too large. Capture a smaller region.")
            return
        self.solution = None
        self.answer.setText("Working on it…")
        self.steps.setText("Reading the question and checking the result.")
        self.check.clear()
        self.status.setText("Analyzing securely with OpenAI…")
        self.set_busy(True)
        task = SolveTask(png, key, self.settings.value("model", "gpt-4.1-mini"), self.mode.currentIndex() == 1)
        task.signals.done.connect(self.solved)
        task.signals.failed.connect(self.failed)
        self.task = task
        self.pool.start(task)

    def solved(self, solution):
        self.solution = solution
        self.render_solution()
        self.set_busy(False)
        self.history.insert(0, HistoryEntry(datetime.now().strftime("%H:%M") + " · " + solution.question[:65], self.image.copy(), solution))
        self.history = self.history[:10]
        self.history_combo.clear()
        self.history_combo.addItem("Recent questions • this session")
        self.history_combo.addItems([entry.title for entry in self.history])

    def render_solution(self):
        solution = self.solution
        self.answer.setText(solution.answer)
        self.steps.setText("\n\n".join(f"{i+1}. {step}" for i, step in enumerate(solution.steps)))
        self.check.setText("Check: " + solution.check if solution.check else "")
        self.status.setText("Solution ready • review the check below." if solution.status == "solved" else "More detail needed • please recapture.")

    def failed(self, message):
        self.solution = None
        self.answer.setText("Couldn’t solve this yet")
        self.steps.setText(message)
        self.check.clear()
        self.status.setText("Try again when you’re ready.")
        self.set_busy(False)

    def show_history(self, index):
        if self.busy or index < 1 or index > len(self.history):
            return
        entry = self.history[index-1]
        self.image, self.solution = entry.image, entry.solution
        self.update_preview()
        self.render_solution()
        self.set_busy(False)

    def clear_history(self):
        if self.busy:
            return
        self.history.clear()
        self.history_combo.clear()
        self.history_combo.addItem("Recent questions • this session")
        self.image = self.solution = None
        self.preview.clear()
        self.preview.setText("Your selected screenshot will appear here")
        self.answer.setText("Let’s work it out.")
        self.steps.setText("Capture a question to get started.")
        self.check.clear()
        self.status.setText("Session history cleared.")
        self.set_busy(False)

    def copy_answer(self):
        if self.solution and self.solution.status == "solved":
            QApplication.clipboard().setText(self.solution.answer)
            self.status.setText("Answer copied to clipboard.")

    def closeEvent(self, event: QCloseEvent):
        if self.busy:
            self.status.setText("Please wait for the current request before closing.")
            event.ignore()
            return
        if self.listener:
            self.listener.stop()
        if self.selector:
            self.selector.close()
        event.accept()


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-report", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName("Focus")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    if args.smoke_report:
        def smoke_test():
            try:
                import keyring
                import mss
                import pynput.keyboard
                if window.listener is None or not window.listener.is_alive():
                    raise RuntimeError("Global keyboard listener did not start")
                if keyring.get_keyring().priority <= 0:
                    raise RuntimeError("Secure credential backend is unavailable")
                if window.grab().isNull():
                    raise RuntimeError("The application window did not render")
                window.toggle_compact(True)
                window.toggle_compact(False)
                report = {"status": "passed", "checks": ["window render", "compact toggle", "keyboard listener", "credential backend", "capture module import"]}
                code = 0
            except Exception as error:
                report = {"status": "failed", "error": str(error)}
                code = 1
            args.smoke_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            window.close()
            app.exit(code)
        QTimer.singleShot(1500, smoke_test)
    else:
        QTimer.singleShot(300, window.welcome)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
