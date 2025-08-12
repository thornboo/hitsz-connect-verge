import os
import sys
import socket
import time
import subprocess
from platform import system
import shlex
import gc
import logging
import datetime
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QTimer
from .process_utils import run_quiet
from .set_proxy import CommandWorker

logger = logging.getLogger(__name__)


def is_port_in_use(host, port):
    """Checks if a TCP port is currently in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex((host, port)) == 0
    except Exception as e:
        logger.debug("Port check failed for %s:%s: %s", host, port, e)
        return True  # Assume in use if check fails


def get_port_process_info(port):
    """Gets information about the process using a specific port."""
    try:
        if system() == "Windows":
            result = run_quiet(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    if pid == "0":
                        return "System process"
                    tasklist_result = run_quiet(
                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    lines = tasklist_result.stdout.strip().split("\n")
                    if len(lines) > 1:
                        return lines[1].split(",")[0].strip('"')
                    return f"PID {pid}"
        else:  # Unix-like
            result = subprocess.run(
                ["lsof", "-i", f":{port}"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                return lines[1].split()[0]
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("Failed to get process info for port %s: %s", port, e)
    return None


def handle_output(window, text):
    """Queues output text for batched UI updates and detects connection success."""
    if not hasattr(window, "_log_buffer"):
        window._log_buffer = []
        window._last_flush_time = time.time()

    window._log_buffer.append(text.rstrip())

    # Flush based on buffer size or time to prevent UI lag
    if len(window._log_buffer) > 50 or time.time() - window._last_flush_time > 0.1:
        _schedule_log_flush(window)
        window._last_flush_time = time.time()

    # Detect connection success from log output
    lower_text = text.lower()
    if ("listening" in lower_text and ("socks" in lower_text or "http" in lower_text)) or \
       ("started" in lower_text and "proxy" in lower_text):
        if hasattr(window, "update_status"):
            window.update_status("状态: 正在运行", connected=True, busy=False)


def _rotate_logs_if_needed(window):
    """Rotates logs if they exceed the maximum line count."""
    MAX_LOG_LINES = 500
    KEEP_LINES = 200

    document = window.output_text.document()
    if document.blockCount() > MAX_LOG_LINES:
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, document.blockCount() - KEEP_LINES)
        cursor.removeSelectedText()
        cursor.insertText(f"--- Log rotated at {datetime.datetime.now():%H:%M:%S} ---\\n")
        window.output_text.setTextCursor(cursor)


def append_log_with_rotation(window, text):
    """Appends a single line of text to the log immediately."""
    window.output_text.appendPlainText(text)
    _rotate_logs_if_needed(window)
    # Scroll to the bottom
    scrollbar = window.output_text.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())


def _schedule_log_flush(window):
    """Schedules a batched log flush to the UI."""
    if getattr(window, "_log_flush_scheduled", False):
        return
    window._log_flush_scheduled = True

    def _flush():
        try:
            if buffer := getattr(window, "_log_buffer", []):
                chunk = "\n".join(buffer)
                window.output_text.appendPlainText(chunk)
                window._log_buffer = []
                _rotate_logs_if_needed(window)
                # Scroll to the bottom
                scrollbar = window.output_text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
        finally:
            window._log_flush_scheduled = False

    QTimer.singleShot(50, _flush)


def _check_port_conflicts(window):
    """Checks for port conflicts and returns a list of warning messages."""
    used_ports = set()
    conflicts = []

    def check(port_type, bind_value, prior_label=None):
        if not bind_value:
            return
        try:
            port = int(bind_value)
            if prior_label and port in used_ports:
                conflicts.append(f"{port_type} port {port} conflicts with {prior_label}.")
            elif is_port_in_use("127.0.0.1", port):
                process_info = get_port_process_info(port)
                details = f" (in use by {process_info})" if process_info else ""
                conflicts.append(f"{port_type} port {port} is already in use{details}.")
            used_ports.add(port)
        except ValueError:
            append_log_with_rotation(window, f"Warning: Invalid {port_type} port '{{bind_value}}'.")

    check("SOCKS5", getattr(window, 'socks_bind', None))
    check("HTTP", getattr(window, 'http_bind', None), "SOCKS5 port")
    return conflicts


def handle_connection_finished(window):
    """Handles cleanup after the connection process has finished."""
    if window.worker:
        window.worker.output.disconnect()
        window.worker.finished.disconnect()
        window.worker.deleteLater()
        window.worker = None
        gc.collect()

    if hasattr(window, "update_status"):
        window.update_status("状态: 未连接", connected=False, busy=False)
    if hasattr(window, "connect_button"):
        window.connect_button.setChecked(False)


def start_connection(window):
    """Starts the VPN connection process."""
    if window.worker and window.worker.isRunning():
        window.update_status("状态: 正在运行", connected=True, busy=False)
        return

    if conflicts := _check_port_conflicts(window):
        for conflict in conflicts:
            append_log_with_rotation(window, f"⚠️ {conflict}")
        append_log_with_rotation(window, "Attempting to connect despite conflicts. If it fails, please check port settings.")

    base_path = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
    if not getattr(sys, 'frozen', False):
        base_path = os.path.join(base_path, "..", "..")

    exe_name = "zju-connect.exe" if system() == "Windows" else "zju-connect"
    command_path = os.path.join(base_path, "app", "core", exe_name)

    if not os.path.exists(command_path):
        error_msg = f"Error: Executable not found at {command_path}"
        append_log_with_rotation(window, error_msg)
        window.update_status("状态: 启动失败", connected=False, busy=False)
        window.connect_button.setChecked(False)
        return

    if system() != "Windows":
        os.chmod(command_path, 0o755)

    args = [
        command_path,
        "-server", window.server_address,
        "-port", str(window.port),
        "-username", window.username_input.text(),
        "-password", window.password_input.text(),
        "-zju-dns-server", "auto" if window.auto_dns else window.dns_server,
        "-disable-zju-config",
        "-skip-domain-resource",
    ]
    if window.http_bind:
        args.extend(["-http-bind", f"127.0.0.1:{window.http_bind}"])
    if window.socks_bind:
        args.extend(["-socks-bind", f"127.0.0.1:{window.socks_bind}"])
    if not window.keep_alive:
        args.append("-disable-keep-alive")
    if window.debug_dump:
        args.append("-debug-dump")
    if window.disable_multi_line:
        args.append("-disable-multi-line")
    if window.cert_file:
        args.extend(["-cert-file", window.cert_file])
        if window.cert_password:
            args.extend(["-cert-password", window.cert_password])

    # Log command with masked credentials
    debug_args = list(args)
    for i, arg in enumerate(debug_args):
        if arg in ("-password", "-cert-password") and i + 1 < len(debug_args):
            debug_args[i + 1] = "********"
    append_log_with_rotation(window, f"Executing: {' '.join(shlex.quote(arg) for arg in debug_args)}")

    window.worker = CommandWorker(command_args=args, proxy_enabled=window.proxy, window=window)
    window.worker.output.connect(lambda text: handle_output(window, text))
    window.worker.finished.connect(lambda: handle_connection_finished(window))
    window.worker.start()


def stop_connection(window):
    """Stops the VPN connection process."""
    if window.worker:
        try:
            window.worker.stop()
            # Set a timer to forcefully terminate if graceful stop fails
            QTimer.singleShot(2000, lambda: window.worker.terminate() if window.worker and window.worker.isRunning() else None)
        except Exception as e:
            append_log_with_rotation(window, f"Error while stopping connection: {e}")
    # Final state is set by handle_connection_finished when the worker signals it's done