from PySide6.QtWidgets import (
    QMainWindow,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QPen, QBrush
from PySide6.QtCore import Qt
from utils.tray_utils import handle_close_event, quit_app, init_tray_icon
from utils.credential_utils import save_credentials
from utils.connection_utils import start_connection, stop_connection
from utils.password_utils import toggle_password_visibility
from views.menu_utils import setup_menubar, check_for_updates
from utils.config_utils import load_settings
from common.version import get_version

VERSION = get_version()


class StatusIndicator(QWidget):
    """状态指示器组件，显示彩色圆点"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.color = Qt.red  # 默认红色（未连接）

    def set_status(self, connected: bool):
        """设置连接状态"""
        self.color = Qt.green if connected else Qt.red
        self.update()  # 触发重绘

    def paintEvent(self, event):
        """绘制圆点"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # 抗锯齿

        # 设置画笔和画刷
        pen = QPen(self.color, 1)
        brush = QBrush(self.color)
        painter.setPen(pen)
        painter.setBrush(brush)

        # 绘制圆点
        painter.drawEllipse(1, 1, 10, 10)


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
        # Layouts
        layout = QVBoxLayout()

        # Account and Password
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
            lambda checked: toggle_password_visibility(self.password_input, checked)
        )
        layout.addWidget(self.show_password_cb)

        self.remember_cb = QCheckBox("记住密码")
        self.remember_cb.setChecked(self.remember)
        self.remember_cb.stateChanged.connect(self.save_credentials)
        layout.addWidget(self.remember_cb)

        # Status and Output
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("运行信息"))
        layout.addLayout(status_layout)
        status_layout.addStretch()

        # 创建状态指示器和标签的容器
        status_container = QHBoxLayout()
        status_container.setSpacing(8)  # 设置间距

        # 添加状态指示器
        self.status_indicator = StatusIndicator()
        status_container.addWidget(self.status_indicator)

        # 添加状态标签
        self.status_label = QLabel("状态: 未连接")
        status_container.addWidget(self.status_label)

        # 创建包装容器并添加到主布局
        status_wrapper = QWidget()
        status_wrapper.setLayout(status_container)
        status_layout.addWidget(status_wrapper)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)

        # 优化日志显示性能
        # QTextEdit没有setMaximumBlockCount，改为禁用撤销/重做来减少内存使用
        self.output_text.setUndoRedoEnabled(False)  # 禁用撤销/重做功能，减少内存使用

        layout.addWidget(self.output_text)

        # Buttons
        button_layout = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.connect_button.setCheckable(True)
        self.connect_button.toggled.connect(
            lambda: (
                self.start_connection()
                if self.connect_button.isChecked()
                else self.stop_connection()
            )
        )
        self.connect_button.toggled.connect(
            lambda: (
                self.connect_button.setText("断开")
                if self.connect_button.isChecked()
                else self.connect_button.setText("连接")
            )
        )
        self.connect_button.toggled.connect(self.save_credentials)
        button_layout.addWidget(self.connect_button)

        button_layout.addStretch()

        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.stop_connection)
        self.exit_button.clicked.connect(self.quit_app)
        button_layout.addWidget(self.exit_button)
        layout.addLayout(button_layout)

        # Set main widget
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def closeEvent(self, event):
        handle_close_event(self, event, self.tray_icon)

    def quit_app(self):
        # Ensure connection is stopped before quitting
        self.stop_connection()
        quit_app(self, self.tray_icon)

    def save_credentials(self):
        save_credentials(self)

    def start_connection(self):
        start_connection(self)

    def stop_connection(self):
        stop_connection(self)

    def load_settings(self):
        load_settings(self)

    def check_updates_startup(self):
        check_for_updates(self, self.version, startup=True)

    def update_status(self, text: str, connected: bool = False):
        """更新状态文本和指示器"""
        self.status_label.setText(text)
        self.status_indicator.set_status(connected)
