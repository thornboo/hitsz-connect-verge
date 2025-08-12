import gc

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication, QMainWindow, QMessageBox
from PySide6.QtGui import QIcon, QAction
from platform import system
from common import resources


def create_tray_menu(window: QMainWindow, tray_icon):
    """Creates and configures the system tray menu."""
    menu = QMenu()

    show_action = menu.addAction("打开面板")
    show_action.triggered.connect(window.show)
    show_action.triggered.connect(window.raise_)

    connect_action = QAction("系统代理", menu)
    connect_action.setCheckable(True)
    connect_action.triggered.connect(window.connect_button.setChecked)
    window.connect_button.toggled.connect(connect_action.setChecked)
    menu.addAction(connect_action)

    menu.addSeparator()
    quit_action = menu.addAction("退出")
    quit_action.triggered.connect(window.quit_app)

    tray_icon.setContextMenu(menu)
    tray_icon.activated.connect(lambda reason: tray_icon_activated(reason, window))


def tray_icon_activated(reason, window):
    """Handles tray icon activation events (e.g., double-click)."""
    if reason == QSystemTrayIcon.DoubleClick:
        window.show()
        window.activateWindow()


def handle_close_event(window, event, tray_icon):
    """Handles the main window's close event."""
    if tray_icon.isVisible():
        window.hide()
        event.ignore()
    else:
        # If the connection is active, confirm before quitting.
        if hasattr(window, 'is_connected') and window.is_connected():
            reply = QMessageBox.question(
                window,
                "确认退出",
                "当前程序已连接，是否退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        
        # Proceed with quitting the application.
        quit_app(window, tray_icon)


def quit_app(window, tray_icon):
    """Stops the connection and quits the application gracefully."""
    from PySide6.QtCore import QTimer

    # Stop the worker thread
    window.stop_connection()

    # Define the final cleanup actions
    def final_quit():
        window.deleteLater()
        tray_icon.deleteLater()
        gc.collect()
        QApplication.quit()

    # Give the thread a moment to finish before quitting.
    # This helps prevent the "QThread: Destroyed while thread is still running" error.
    QTimer.singleShot(100, final_quit)



def init_tray_icon(window):
    """Initializes the system tray icon and menu."""
    tray_icon = QSystemTrayIcon(window)

    # Set the icon based on the operating system.
    if system() == "Windows":
        icon_path = ":/icons/icon.ico"
    elif system() == "Darwin":
        # Use a template image for macOS that adapts to the menu bar theme.
        icon_path = ":/icons/menu-icon.svg"
        icon = QIcon(icon_path)
        icon.setIsMask(True)
        tray_icon.setIcon(icon)
        create_tray_menu(window, tray_icon)
        tray_icon.show()
        return tray_icon
    else:  # Linux
        icon_path = ":/icons/icon.png"

    tray_icon.setIcon(QIcon(icon_path))
    create_tray_menu(window, tray_icon)
    tray_icon.show()
    return tray_icon
