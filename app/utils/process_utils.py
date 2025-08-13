import subprocess
from platform import system


def run_quiet(
    args,
    *,
    capture_output: bool = False,
    text: bool = True,
    timeout: float | None = None,
    check: bool = False,
):
    """
    Runs a subprocess without creating a console window on Windows.

    This function mirrors a subset of the `subprocess.run` signature
    and is used to suppress console pop-ups for background tasks.
    On non-Windows platforms, it behaves identically to `subprocess.run`.
    """
    kwargs = {
        "capture_output": capture_output,
        "text": text,
        "timeout": timeout,
        "check": check,
    }

    if system() == "Windows":
        # The CREATE_NO_WINDOW flag prevents the console window from appearing.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        # startupinfo is also required to properly hide the window.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo

    return subprocess.run(args, **kwargs)