import webbrowser

from PySide6.QtWidgets import QMessageBox, QMainWindow, QMenuBar
from PySide6.QtGui import QGuiApplication, QKeySequence
from .advanced_panel import AdvancedSettingsDialog
from platform import system
from services.update_service import UpdateService
from utils.connection_utils import append_log_with_rotation

if system() == "Darwin":
    from utils.macos_utils import hide_dock_icon

update_service = UpdateService()


def setup_menubar(window: QMainWindow, version):
    """Set up the main window menu bar."""
    if system() == "Darwin":
        menubar = QMenuBar(window)
        menubar.setNativeMenuBar(not window.hide_dock_icon)
        window.setMenuBar(menubar)
    else:
        menubar = window.menuBar()

    # Settings Menu
    settings_menu = menubar.addMenu("设置")
    window.advanced_action = settings_menu.addAction("高级设置")
    window.advanced_action.setShortcut(QKeySequence.Preferences)
    window.advanced_action.triggered.connect(lambda: show_advanced_settings(window))

    # Help Menu
    help_menu = menubar.addMenu("帮助")
    help_menu.addAction("复制日志").triggered.connect(lambda: copy_log(window))
    help_menu.addAction("清空日志").triggered.connect(lambda: clear_log(window))
    help_menu.addSeparator()
    help_menu.addAction("检查更新").triggered.connect(
        lambda: check_for_updates(window, version)
    )
    help_menu.addAction("关于").triggered.connect(lambda: show_about(window, version))


def show_about(window, version):
    """Show the about dialog."""
    about_text = f"""<p style="font-size: 15pt;">HITSZ Connect Verge</p>
    <p style="font-size: 10pt;">Version: {version}</p>
    <p style="font-size: 10pt;">Repository: <a href="https://github.com/kowyo/hitsz-connect-verge">github.com/kowyo/hitsz-connect-verge</a></p>
    <p style="font-size: 10pt;">Author: <a href="https://github.com/kowyo">Kowyo</a></p>"""
    QMessageBox.about(window, "关于 HITSZ Connect Verge", about_text)


def copy_log(window):
    """Copy the application log to the clipboard."""
    QGuiApplication.clipboard().setText(window.output_text.toPlainText())
    QMessageBox.information(window, "复制日志", "日志已复制到剪贴板")


def clear_log(window):
    """Clear the application log with user confirmation."""
    reply = QMessageBox.question(
        window,
        "清空日志",
        "确定要清空所有日志吗？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply == QMessageBox.Yes:
        window.output_text.clear()
        window.output_text.appendPlainText("Log cleared by user.")


def check_for_updates(parent, current_version, startup=False):
    """
    Check for updates and notify the user.

    Args:
        parent: The parent widget for dialogs.
        current_version: The current application version string.
        startup: If True, notifications are less intrusive.
    """
    signals = update_service.check_for_updates(current_version)

    def on_update_available(latest_version):
        if startup:
            append_log_with_rotation(
                parent, f"New version {latest_version} is available."
            )
            return

        reply = QMessageBox.question(
            parent,
            "检查更新",
            f"发现新版本 {latest_version}，是否前往下载？",
        )
        if reply == QMessageBox.Yes:
            webbrowser.open(
                "https://github.com/kowyo/hitsz-connect-verge/releases/latest"
            )

    def on_up_to_date():
        if not startup:
            QMessageBox.information(parent, "检查更新", "当前已是最新版本")
        else:
            append_log_with_rotation(parent, "Application is up to date.")

    def on_error(error_msg):
        message = "检查更新失败，请检查网络连接"
        if not startup:
            QMessageBox.critical(parent, "检查更新失败", message)
        else:
            append_log_with_rotation(parent, message)

    signals.update_available.connect(on_update_available)
    signals.up_to_date.connect(on_up_to_date)
    signals.error.connect(on_error)


def show_advanced_settings(window):
    """Show the advanced settings dialog and apply changes if saved."""
    dialog = AdvancedSettingsDialog(window)
    dialog.set_settings(
        window.server_address,
        window.port,
        window.dns_server,
        window.proxy,
        window.connect_startup,
        window.silent_mode,
        window.check_update,
        window.hide_dock_icon,
        window.keep_alive,
        window.debug_dump,
        window.disable_multi_line,
        window.http_bind,
        window.socks_bind,
        window.auto_dns,
        window.cert_file,
        window.cert_password,
    )

    if dialog.exec():
        settings = dialog.get_settings()
        window.server_address = settings["server"]
        window.port = settings["port"]
        window.dns_server = settings["dns"]
        window.auto_dns = settings["auto_dns"]
        window.proxy = settings["proxy"]
        window.connect_startup = settings["connect_startup"]
        window.silent_mode = settings["silent_mode"]
        window.check_update = settings["check_update"]
        window.hide_dock_icon = settings.get("hide_dock_icon", False)
        window.keep_alive = settings["keep_alive"]
        window.debug_dump = settings["debug_dump"]
        window.disable_multi_line = settings["disable_multi_line"]
        window.http_bind = settings["http_bind"]
        window.socks_bind = settings["socks_bind"]
        window.cert_file = settings["cert_file"]
        window.cert_password = settings["cert_password"]

        if system() == "Darwin":
            hide_dock_icon(window.hide_dock_icon)

        window.save_credentials()
        QMessageBox.information(window, "设置", "高级设置已更新")
