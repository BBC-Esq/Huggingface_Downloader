"""
Development Installation Script

Sets up the development environment by installing all required dependencies.
Provides a GUI confirmation dialog and displays progress in the console.

Usage:
    python install.py
"""

import sys
import subprocess
import time
import tkinter as tk
from tkinter import messagebox

# ============================================================
# CONFIGURATION
# ============================================================
libs = [
    "pyside6",
    "huggingface_hub",
    "tqdm",
]
# ============================================================

start_time = time.time()


def enable_ansi_colors():
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        stdout_handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
        mode.value |= 0x0004
        kernel32.SetConsoleMode(stdout_handle, mode)


def tkinter_message_box(title, message, type="info", yes_no=False):
    root = tk.Tk()
    root.withdraw()
    if yes_no:
        result = messagebox.askyesno(title, message)
    elif type == "error":
        messagebox.showerror(title, message)
        result = False
    else:
        messagebox.showinfo(title, message)
        result = True
    root.destroy()
    return result


def check_python_version_and_confirm():
    major, minor = map(int, sys.version.split()[0].split('.')[:2])
    if major == 3 and minor in [11, 12, 13]:
        return tkinter_message_box(
            "Confirmation",
            f"Python version {sys.version.split()[0]} was detected, which is compatible.\n\n"
            f"Click YES to proceed with installation or NO to exit.",
            yes_no=True
        )
    else:
        tkinter_message_box(
            "Python Version Error",
            "This program requires Python 3.11, 3.12, or 3.13.\n\nExiting the installer...",
            type="error"
        )
        return False


def upgrade_pip_setuptools_wheel(max_retries=5, delay=3):
    upgrade_commands = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--no-cache-dir"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "setuptools", "--no-cache-dir"],
        [sys.executable, "-m", "pip", "install", "--upgrade", "wheel", "--no-cache-dir"]
    ]
    for command in upgrade_commands:
        package = command[5]
        for attempt in range(max_retries):
            try:
                print(f"\nAttempt {attempt + 1} of {max_retries}: Upgrading {package}...")
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=480)
                print(f"\033[92mSuccessfully upgraded {package}\033[0m")
                break
            except subprocess.CalledProcessError as e:
                print(f"Attempt {attempt + 1} failed. Error: {e.stderr.strip()}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)


def install_libraries_with_retry(libraries, max_retries=5, delay=3):
    failed_installations = []
    multiple_attempts = []

    for library in libraries:
        for attempt in range(max_retries):
            try:
                print(f"\nAttempt {attempt + 1} of {max_retries}: Installing {library}")
                command = ["uv", "pip", "install", library]
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=480)
                print(f"\033[92mSuccessfully installed {library}\033[0m")
                if attempt > 0:
                    multiple_attempts.append((library, attempt + 1))
                break
            except subprocess.CalledProcessError as e:
                print(f"Attempt {attempt + 1} failed. Error: {e.stderr.strip()}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    failed_installations.append(library)

    return failed_installations, multiple_attempts


def main():
    enable_ansi_colors()

    if not check_python_version_and_confirm():
        sys.exit(1)

    print("\033[92mInstalling uv:\033[0m")
    subprocess.run(["pip", "install", "uv"], check=True)

    print("\033[92mUpgrading pip, setuptools, and wheel:\033[0m")
    upgrade_pip_setuptools_wheel()

    print("\033[92mInstalling libraries:\033[0m")
    failed, multiple = install_libraries_with_retry(libs)

    print("\n----- Installation Summary -----")

    if failed:
        print("\033[91m\nThe following libraries failed to install:\033[0m")
        for lib in failed:
            print(f"\033[91m- {lib}\033[0m")

    if multiple:
        print("\033[93m\nThe following libraries required multiple attempts:\033[0m")
        for lib, attempts in multiple:
            print(f"\033[93m- {lib} (took {attempts} attempts)\033[0m")

    if not failed and not multiple:
        print("\033[92mAll libraries installed successfully on the first attempt.\033[0m")
    elif not failed:
        print("\033[92mAll libraries were eventually installed successfully.\033[0m")

    end_time = time.time()
    total_time = end_time - start_time
    hours, rem = divmod(total_time, 3600)
    minutes, seconds = divmod(rem, 60)
    print(f"\033[92m\nTotal installation time: {int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}\033[0m")


if __name__ == "__main__":
    main()
