from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMessageBox,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QPen, QBrush
from PySide6.QtCore import Qt
from utils.tray_utils import handle_close_event, quit_app, init_tray_icon
from utils.credential_utils import save_credentials
from utils.password_utils import toggle_password_visibility
from views.menu_utils import setup_menubar, check_for_updates
from utils.config_utils import load_settings
from common.version import get_version

VERSION = get_version()


class StatusIndicator(QWidget):
    """A widget that displays a colored dot or a busy spinner to show status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.color = Qt.red  # Default: Not Connected
        self.busy = False
        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(60)
        self._spinner_timer.timeout.connect(self._advance_spinner)

    def set_status(self, connected: bool):
        """Sets the indicator to a solid connected or disconnected state."""
        self.busy = False
        self._spinner_timer.stop()
        self.color = Qt.green if connected else Qt.red
        self.update()

    def set_busy(self, busy: bool):
        """Enables or disables the busy spinner animation."""
        self.busy = busy
        if busy:
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
        self.update()

    def _advance_spinner(self):
        """Advances the spinner animation by one step."""
        self._spinner_angle = (self._spinner_angle + 45) % 360
        self.update()

    def paintEvent(self, event):
        """Paints the status indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.busy:
            pen = QPen(self.color, 1)
            brush = QBrush(self.color)
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawEllipse(1, 1, 10, 10)
        else:
            bg_pen = QPen(Qt.lightGray, 1)
            painter.setPen(bg_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(2, 2, 8, 8)

            arc_pen = QPen(self.color, 2)
            painter.setPen(arc_pen)
            start_angle = int(self._spinner_angle * 16)
            span_angle = int(90 * 16)
            painter.drawArc(2, 2, 8, 8, start_angle, span_angle)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HITSZ Connect Verge")
        self.setMinimumSize(300, 450)

        self.worker = None
        self.version = VERSION
        self.load_settings()
        setup_menubar(self, self.version)
        self.setup_ui()
        self.tray_icon = init_tray_icon(self)

        if self.connect_startup:
            QTimer.singleShot(5000, lambda: self.connect_button.setChecked(True))

        if self.check_update:
            self.check_updates_startup()

    def setup_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel("用户名"))
        self.username_input = QLineEdit()
        self.username_input.setText(self.username)
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("密码"))
        self.password_input = QLineEdit()
        self.password_input.setText(self.password)
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        self.show_password_cb = QCheckBox("显示密码")
        self.show_password_cb.stateChanged.connect(
            lambda state: toggle_password_visibility(self.password_input, state)
        )
        layout.addWidget(self.show_password_cb)

        self.remember_cb = QCheckBox("记住密码")
        self.remember_cb.setChecked(self.remember)
        self.remember_cb.stateChanged.connect(self.save_credentials)
        layout.addWidget(self.remember_cb)

        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("运行信息"))
        status_layout.addStretch()

        status_container = QHBoxLayout()
        status_container.setSpacing(8)

        self.status_indicator = StatusIndicator()
        status_container.addWidget(self.status_indicator)

        self.status_label = QLabel("状态: 未连接")
        status_container.addWidget(self.status_label)

        status_wrapper = QWidget()
        status_wrapper.setLayout(status_container)
        status_layout.addWidget(status_wrapper)
        layout.addLayout(status_layout)

        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumBlockCount(3000)
        layout.addWidget(self.output_text)

        button_layout = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.connect_button.setCheckable(True)
        self.connect_button.toggled.connect(self.on_connect_toggled)
        self.connect_button.toggled.connect(self.save_credentials)
        button_layout.addWidget(self.connect_button)

        button_layout.addStretch()

        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.quit_app)
        button_layout.addWidget(self.exit_button)
        layout.addLayout(button_layout)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def closeEvent(self, event):
        handle_close_event(self, event, self.tray_icon)

    def is_connected(self):
        """Checks if the application is currently in a connected state."""
        return self.connect_button.isChecked() and "正在运行" in self.status_label.text()

    def quit_app(self):
        """Quits the application, showing a confirmation dialog if connected."""
        if self.is_connected():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "当前程序已连接，是否退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.stop_connection()
        quit_app(self, self.tray_icon)

    def save_credentials(self):
        save_credentials(self)

    def start_connection(self):
        """Initiates the connection process with visual feedback."""
        self.update_status("状态: 正在连接", connected=False, busy=True)
        self._start_worker()

    def stop_connection(self):
        """Stops the connection process with visual feedback."""
        self.update_status("状态: 正在断开", connected=True, busy=True)
        self._stop_worker()

    def _start_worker(self):
        """Starts the background connection worker."""
        from utils.connection_utils import start_connection
        start_connection(self)

    def _stop_worker(self):
        """Stops the background connection worker."""
        from utils.connection_utils import stop_connection
        stop_connection(self)

    def load_settings(self):
        load_settings(self)

    def check_updates_startup(self):
        check_for_updates(self, self.version, startup=True)

    def update_status(self, text: str, connected: bool, busy: bool = False):
        """Updates the status label and indicator."""
        self.status_label.setText(text)
        self.status_indicator.color = Qt.green if connected else Qt.red
        self.status_indicator.set_busy(busy)

    def on_connect_toggled(self, checked: bool):
        """Handles the connect/disconnect button toggle."""
        if checked:
            self.connect_button.setText("断开")
            self.start_connection()
        else:
            self.connect_button.setText("连接")
            self.stop_connection()