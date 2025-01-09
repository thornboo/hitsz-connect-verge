import keyring
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QLineEdit, QCheckBox, QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget
)
from PySide6.QtCore import QThread, Signal
import subprocess
import platform
import shlex
# Add this import at the top with other imports
from subprocess import CREATE_NO_WINDOW

# Proxy management (Windows-specific)
def set_proxy(enable, server=None, port=None):
    if platform.system() == "Windows":
        import winreg as reg
        import ctypes
        
        internet_settings = reg.OpenKey(reg.HKEY_CURRENT_USER,
                                        r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
                                        0, reg.KEY_ALL_ACCESS)
        reg.SetValueEx(internet_settings, 'ProxyEnable', 0, reg.REG_DWORD, 1 if enable else 0)
        if enable and server and port:
            proxy = f"{server}:{port}"
            reg.SetValueEx(internet_settings, 'ProxyServer', 0, reg.REG_SZ, proxy)
        ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)
        ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)
        reg.CloseKey(internet_settings)

# Worker Thread for Running Commands
class CommandWorker(QThread):
    output = Signal(str)
    finished = Signal()

    def __init__(self, command_args, proxy_enabled):
        super().__init__()
        self.command_args = command_args
        self.proxy_enabled = proxy_enabled
        self.process = None

    def run(self):
        if self.proxy_enabled:
            set_proxy(True, server="127.0.0.1", port=1081)
        
        self.process = subprocess.Popen(
            self.command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            creationflags=CREATE_NO_WINDOW  # Add this line to hide console
        )
        for line in self.process.stdout:
            self.output.emit(line)
        self.process.wait()
        
        if self.proxy_enabled:
            set_proxy(False)
        
        self.finished.emit()

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()

# Main Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HITSZ Connect Verge")

        self.service_name = "zju-connect"  # Identifier for keyring
        self.username_key = "username"    # Key for storing username
        self.password_key = "password"    # Key for storing password
        
        self.worker = None
        self.setup_ui()
        self.load_credentials()

    def setup_ui(self):
        # Layouts
        layout = QVBoxLayout()
        
        # Account and Password
        layout.addWidget(QLabel("账号："))
        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("密码："))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        self.show_password_cb = QCheckBox("显示密码")
        self.show_password_cb.stateChanged.connect(self.toggle_password_visibility)
        layout.addWidget(self.show_password_cb)

        self.remember_cb = QCheckBox("记住密码")
        layout.addWidget(self.remember_cb)
        
        # Server and DNS
        layout.addWidget(QLabel("SSL VPN 服务端地址："))
        self.server_input = QLineEdit("vpn.hitsz.edu.cn")
        layout.addWidget(self.server_input)

        layout.addWidget(QLabel("DNS 服务器地址："))
        self.dns_input = QLineEdit("10.248.98.30")
        layout.addWidget(self.dns_input)
        
        # Proxy Control
        self.proxy_cb = QCheckBox("自动配置代理")
        self.proxy_cb.setChecked(True)
        layout.addWidget(self.proxy_cb)

        # Buttons
        button_layout = QHBoxLayout()
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self.start_connection)
        self.connect_button.clicked.connect(self.save_credentials)
        button_layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.clicked.connect(self.stop_connection)
        button_layout.addWidget(self.disconnect_button)

        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.stop_connection) 
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)
        layout.addLayout(button_layout)

        # Status and Output
        self.status_label = QLabel("状态: 已停止")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("运行信息："))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)

        # Set main widget
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def toggle_password_visibility(self):
        if self.show_password_cb.isChecked():
            self.password_input.setEchoMode(QLineEdit.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)

    def load_credentials(self):
        """Load stored credentials from keyring."""
        saved_username = keyring.get_password(self.service_name, self.username_key)
        saved_password = keyring.get_password(self.service_name, self.password_key)
        if saved_username:
            self.username_input.setText(saved_username)
        if saved_password:
            self.password_input.setText(saved_password)
            self.remember_cb.setChecked(True)

    def save_credentials(self):
        """Save credentials to keyring if 'Remember Password' is checked."""
        username = self.username_input.text()
        password = self.password_input.text()

        if self.remember_cb.isChecked():
            keyring.set_password(self.service_name, self.username_key, username)
            keyring.set_password(self.service_name, self.password_key, password)
        else:
            # Remove credentials if the user unchecks the remember box
            keyring.delete_password(self.service_name, self.username_key)
            keyring.delete_password(self.service_name, self.password_key)

        # self.status_label.setText("状态: 凭据已保存" if self.remember_cb.isChecked() else "状态: 凭据未保存")

    def start_connection(self):
        if self.worker and self.worker.isRunning():
            self.status_label.setText("状态: 正在运行")
            return

        username = self.username_input.text()
        password = self.password_input.text()
        server_address = self.server_input.text()
        dns_server_address = self.dns_input.text()

        import os, sys
        if getattr(sys, 'frozen', False):
            # Running as bundled exe
            base_path = sys._MEIPASS
        else:
            # Running as script
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        command = os.path.join(base_path, "zju-connect.exe")
        command_args = [
            command, "-server", shlex.quote(server_address),
            "-zju-dns-server", shlex.quote(dns_server_address),
            "-username", shlex.quote(username), "-password", shlex.quote(password)
        ]
        
        self.worker = CommandWorker(command_args, self.proxy_cb.isChecked())
        self.worker.output.connect(self.append_output)
        self.worker.finished.connect(self.on_connection_finished)
        self.worker.start()

        self.status_label.setText("状态: 正在运行")

    def stop_connection(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
            self.worker = None

        self.status_label.setText("状态: 已停止")

    def append_output(self, text):
        self.output_text.append(text)

    def on_connection_finished(self):
        self.worker = None
        self.status_label.setText("状态: 已停止")

# Run the application
if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
