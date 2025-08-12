import subprocess
import os
import signal
import time
from platform import system

from PySide6.QtCore import QThread, Signal
from .process_utils import run_quiet

# Platform-specific imports
if system() == "Windows":
    import winreg as reg
    import ctypes
    from subprocess import CREATE_NO_WINDOW


def get_proxy_settings(window):
    """Extracts proxy settings from the main window's configuration."""
    http_host, http_port = "127.0.0.1", None
    socks_host, socks_port = "127.0.0.1", None

    if hasattr(window, "http_bind") and window.http_bind:
        try:
            http_port = int(window.http_bind)
        except (ValueError, TypeError):
            pass

    if hasattr(window, "socks_bind") and window.socks_bind:
        try:
            socks_port = int(window.socks_bind)
        except (ValueError, TypeError):
            pass

    return http_host, http_port, socks_host, socks_port


class CommandWorker(QThread):
    """
    A QThread worker that runs an external command, captures its output,
    and manages system proxy settings.
    """
    output = Signal(str)
    finished = Signal()

    def __init__(self, command_args, proxy_enabled, window=None):
        super().__init__()
        self.command_args = command_args
        self.proxy_enabled = proxy_enabled
        self.window = window
        self.process = None
        self._should_stop = False
        self._proxy_handlers = {
            "Windows": set_windows_proxy,
            "Darwin": set_macos_proxy,
            "Linux": set_linux_proxy,
        }

    def run(self):
        """The main execution method of the thread."""
        try:
            if self._should_stop:
                return

            self._set_system_proxy(enable=True)

            if self._should_stop:
                return

            # Start the subprocess
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "universal_newlines": True,
                "encoding": "utf-8",
                "creationflags": CREATE_NO_WINDOW if system() == "Windows" else 0,
            }
            if system() != "Windows":
                popen_kwargs["preexec_fn"] = os.setsid  # Create a new process group

            self.process = subprocess.Popen(self.command_args, **popen_kwargs)

            # Read output lines until the process terminates or is stopped
            while not self._should_stop and self.process.poll() is None:
                line = self.process.stdout.readline()
                if line:
                    self.output.emit(line)
                else:
                    # Avoid busy-waiting if the stream is empty
                    time.sleep(0.05)
            
            # Read any remaining output after the loop
            if self.process:
                if remaining_output := self.process.stdout.read():
                    self.output.emit(remaining_output)

                if (exit_code := self.process.wait()) != 0:
                    self.output.emit(f"Process exited with code: {exit_code}\n")

        except FileNotFoundError:
            self.output.emit(f"Error: Command not found at {self.command_args[0]}\n")
        except Exception as e:
            self.output.emit(f"An unexpected error occurred: {e}\n")
        finally:
            self._set_system_proxy(enable=False)
            # Ensure the finished signal is always emitted for cleanup
            if not self.isInterruptionRequested():
                self.finished.emit()

    def stop(self):
        """Requests the thread and its subprocess to stop gracefully."""
        self._should_stop = True
        self.requestInterruption()

        if not self.process:
            return

        try:
            # Terminate the process group/tree
            if system() == "Windows":
                # /T terminates the process and any child processes.
                run_quiet(
                    ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                    timeout=3,
                )
            else:
                # On Unix, terminate the entire process group.
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGTERM)
                self.process.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            # If graceful termination fails, force kill
            try:
                if system() == "Windows":
                     run_quiet(["taskkill", "/F", "/T", "/PID", str(self.process.pid)])
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except Exception:
                pass # Ignore errors on final kill attempt
        except Exception as e:
            self.output.emit(f"Error during process termination: {e}\n")
        finally:
            self.process = None

    def _set_system_proxy(self, enable: bool):
        """Enables or disables the system proxy if configured to do so."""
        if not self.proxy_enabled or not self.window:
            return

        proxy_handler = self._proxy_handlers.get(system())
        if not proxy_handler:
            return

        try:
            if enable:
                settings = get_proxy_settings(self.window)
                proxy_handler(True, *settings)
            else:
                proxy_handler(False)
        except Exception as e:
            self.output.emit(f"Failed to {{'set' if enable else 'unset'}} proxy: {{e}}\n")


def set_windows_proxy(enable, http_host=None, http_port=None, socks_host=None, socks_port=None):
    """Configures system-wide proxy settings on Windows via the registry."""
    if system() != "Windows":
        return

    INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, reg.KEY_ALL_ACCESS) as key:
            reg.SetValueEx(key, "ProxyEnable", 0, reg.REG_DWORD, 1 if enable else 0)
            if enable and http_host and http_port:
                proxy_server = f"{http_host}:{http_port}"
                reg.SetValueEx(key, "ProxyServer", 0, reg.REG_SZ, proxy_server)

        # Notify the system that settings have changed
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception as e:
        print(f"Failed to set Windows proxy: {e}")


def set_macos_proxy(enable, http_host=None, http_port=None, socks_host=None, socks_port=None):
    """Configures proxy settings on macOS for all active network services."""
    if system() != "Darwin":
        return

    try:
        services_output = subprocess.check_output(["networksetup", "-listallnetworkservices"]).decode()
        services = [s for s in services_output.split("\n")[1:] if s and not s.startswith("*")]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    for service in services:
        try:
            if enable:
                if http_host and http_port:
                    run_quiet(["networksetup", "-setwebproxy", service, http_host, str(http_port)])
                    run_quiet(["networksetup", "-setsecurewebproxy", service, http_host, str(http_port)])
                if socks_host and socks_port:
                    run_quiet(["networksetup", "-setsocksfirewallproxy", service, socks_host, str(socks_port)])
            else:
                run_quiet(["networksetup", "-setwebproxystate", service, "off"])
                run_quiet(["networksetup", "-setsecurewebproxystate", service, "off"])
                run_quiet(["networksetup", "-setsocksfirewallproxystate", service, "off"])
        except Exception:
            # Ignore errors for individual services (e.g., inactive ones)
            continue


def set_linux_proxy(enable, http_host=None, http_port=None, socks_host=None, socks_port=None):
    """Configures proxy settings for GNOME-based desktop environments on Linux."""
    if system() != "Linux":
        return

    try:
        if enable:
            run_quiet(["gsettings", "set", "org.gnome.system.proxy", "mode", "manual"])
            if http_host and http_port:
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.http", "host", http_host])
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.http", "port", str(http_port)])
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.https", "host", http_host])
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.https", "port", str(http_port)])
            if socks_host and socks_port:
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.socks", "host", socks_host])
                run_quiet(["gsettings", "set", "org.gnome.system.proxy.socks", "port", str(socks_port)])
        else:
            run_quiet(["gsettings", "set", "org.gnome.system.proxy", "mode", "none"])
    except Exception as e:
        print(f"Failed to set Linux (GNOME) proxy: {e}")