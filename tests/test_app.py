import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from unittest.mock import Mock, patch
import pytest
from pydantic import ValidationError
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt, QPoint, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from ixl_assistant.solver import Solution, solve
from ixl_assistant.app import MainWindow, SolveTask, STYLE
from ixl_assistant.capture import RegionSelector


@pytest.fixture(scope='session')
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(STYLE)
    return application


@pytest.fixture
def window(app):
    widget = MainWindow(enable_hotkey=False)
    widget.image = QImage(320, 160, QImage.Format.Format_RGB888)
    widget.image.fill(Qt.GlobalColor.white)
    yield widget
    widget.busy = False
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def result(status='solved'):
    return Solution(status=status, question='2 + 2', answer='4' if status == 'solved' else 'Capture all choices', steps=['Add two and two.'], check='4 − 2 = 2')


def test_structured_validation():
    with pytest.raises(ValidationError):
        Solution(status='solved', question='x', answer='4', steps=[], check='')
    assert result('recapture').status == 'recapture'


def test_api_image_and_mode():
    with patch('ixl_assistant.solver.OpenAI') as client:
        client.return_value.responses.parse.return_value.output_parsed = result()
        assert solve(b'png', 'fake-test-key', 'gpt-4.1-mini', True).answer == '4'
        args = client.return_value.responses.parse.call_args.kwargs
        assert args['input'][1]['content'][1]['image_url'] == 'data:image/png;base64,cG5n'
        assert '4–7' in args['input'][1]['content'][0]['text']
        client.return_value.close.assert_called_once()


def test_empty_api_result():
    with patch('ixl_assistant.solver.OpenAI') as client:
        client.return_value.responses.parse.return_value.output_parsed = None
        with pytest.raises(ValueError):
            solve(b'png', 'fake', 'model', False)
        client.return_value.close.assert_called_once()


def test_history_copy_clear(window, app):
    for _ in range(12):
        window.solved(result())
    assert len(window.history) == 10
    window.show_history(1)
    window.copy_answer()
    assert QApplication.clipboard().text() == '4'
    # Qt's offscreen clipboard must release its MIME data before app teardown.
    QApplication.clipboard().clear()
    window.clear_history()
    assert window.image is None and not window.history
    assert not window.copy.isEnabled()


def test_recapture_and_failure(window):
    window.solved(result('recapture'))
    assert not window.copy.isEnabled()
    assert 'recapture' in window.status.text()
    window.set_busy(True)
    assert not window.capture_button.isEnabled()
    window.failed('Offline')
    assert window.retry.isEnabled()
    assert not window.busy
    assert window.steps.text() == 'Offline'


def test_worker_failure_is_sanitized(app):
    worker = SolveTask(b'png', 'fake', 'model', False)
    errors = []
    worker.signals.failed.connect(errors.append)
    with patch('ixl_assistant.app.solve', side_effect=RuntimeError('SECRET')):
        worker.run()
    assert len(errors) == 1 and 'SECRET' not in errors[0]
    assert worker.args == ()


def test_crop_at_scaled_resolution(app):
    screen = app.primaryScreen()
    image = QImage(screen.geometry().width()*2, screen.geometry().height()*2, QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.white)
    selector = RegionSelector(screen, image)
    selected = []
    selector.selected.connect(selected.append)
    selector.show()
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, pos=QPoint(120, 100))
    assert len(selected) == 1
    assert selected[0].width() == 202
    assert selected[0].height() == 142
    selector.close()
    selector.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_escape_cancels(app):
    selector = RegionSelector(app.primaryScreen(), QImage(100, 100, QImage.Format.Format_RGB888))
    cancelled = []
    selector.cancelled.connect(lambda: cancelled.append(True))
    QTest.keyClick(selector, Qt.Key.Key_Escape)
    assert cancelled == [True]
    selector.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_key_storage_failure_keeps_request_local(window):
    with patch('ixl_assistant.app.load_key', side_effect=RuntimeError()):
        window.analyze()
    assert not window.busy
    assert 'API key' in window.status.text()


def test_background_analysis_end_to_end(window, app):
    import time
    with patch('ixl_assistant.app.load_key', return_value='fake'), patch('ixl_assistant.app.solve', return_value=result()):
        window.analyze()
        assert window.busy
        deadline = time.monotonic() + 5
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        window.pool.waitForDone(1000)
        assert not window.busy
        assert window.answer.text() == '4'
        assert len(window.history) == 1
        assert window.copy.isEnabled()


def test_popup_controls(window):
    window.toggle_compact(True)
    assert window.preview.isHidden()
    assert window.compact.text() == 'Full view'
    window.toggle_compact(False)
    assert not window.preview.isHidden()
    window.toggle_pin(False)
    assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    window.toggle_pin(True)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
