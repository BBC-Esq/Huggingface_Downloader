import sys
import os
import subprocess
import threading
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QScrollArea,
    QFileDialog, QMessageBox, QDialog, QGroupBox, QFrame,
    QProgressBar
)
from PySide6.QtCore import Qt, Signal, QObject, QSettings
from huggingface_hub import HfApi, hf_hub_download, login, whoami, list_repo_tree
from huggingface_hub.hf_api import RepoFile
from tqdm.auto import tqdm

ORGANIZATION = "HFDownloader"
APPLICATION = "HFModelDownloader"

SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def authenticate_with_token(token):
    try:
        login(token=token, add_to_git_credential=False)
        return True
    except Exception:
        return False


def get_current_user():
    try:
        user_info = whoami()
        return user_info.get('name', user_info.get('fullname', 'Unknown'))
    except Exception:
        return None


def get_repo_files_with_sizes(repo_id, token=None):
    api = HfApi(token=token)
    tree = api.list_repo_tree(repo_id, recursive=True)
    files = []
    for item in tree:
        if isinstance(item, RepoFile):
            files.append((item.path, item.size or 0))
    return files


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    else:
        return f"{size_bytes / 1024 ** 3:.2f} GB"


class DownloadSignals(QObject):
    success = Signal(str, str)
    error = Signal(str, list)
    file_progress = Signal(int, int, str, object, object)
    byte_progress = Signal(object, object)
    cancelled = Signal()


class FetchSignals(QObject):
    success = Signal(list)
    error = Signal(str)


class AuthSignals(QObject):
    done = Signal(str)


class ProgressTqdm(tqdm):
    def __init__(self, *args, signal=None, **kwargs):
        self._signal = signal
        kwargs.pop("name", None)
        # Always redirect tqdm output to devnull in the GUI app,
        # since sys.stderr may be None (e.g. pythonw.exe on Windows)
        if kwargs.get("file") is None or sys.stderr is None:
            kwargs["file"] = open(os.devnull, "w")
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        super().update(n)
        if self._signal and self.total:
            self._signal.emit(int(self.n), int(self.total))

    def close(self):
        if self._signal and self.total:
            self._signal.emit(int(self.total), int(self.total))
        super().close()


class HFDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hugging Face Model Downloader")
        self.setMinimumSize(900, 600)
        self.settings = QSettings(ORGANIZATION, APPLICATION)
        self.token = None
        self.download_dir = str(Path.home() / "Documents")
        self.file_checkboxes = []
        self.file_sizes = {}
        self.cancel_requested = False
        self.is_fetching = False
        self.is_downloading = False
        self.signals = DownloadSignals()
        self.signals.success.connect(self._on_download_success)
        self.signals.error.connect(self._on_download_error)
        self.signals.file_progress.connect(self._on_file_progress)
        self.signals.byte_progress.connect(self._on_byte_progress)
        self.signals.cancelled.connect(self._on_download_cancelled)
        self.fetch_signals = FetchSignals()
        self.fetch_signals.success.connect(self._on_fetch_success)
        self.fetch_signals.error.connect(self._on_fetch_error)
        self.auth_signals = AuthSignals()
        self.auth_signals.done.connect(self._on_auth_done)
        self._build_menu()
        self._build_ui()
        self._load_settings()

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Settings", self._show_settings)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        left_layout.addWidget(QLabel("Repository ID:"))
        self.repo_entry = QLineEdit()
        self.repo_entry.setPlaceholderText("e.g. meta-llama/Llama-2-7b")
        left_layout.addWidget(self.repo_entry)

        left_layout.addWidget(QLabel("Download Location:"))
        dir_row = QHBoxLayout()
        self.dir_entry = QLineEdit(self.download_dir)
        dir_row.addWidget(self.dir_entry)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        left_layout.addLayout(dir_row)

        self.fetch_btn = QPushButton("Fetch Files")
        self.fetch_btn.clicked.connect(self._fetch_files)
        left_layout.addWidget(self.fetch_btn)

        left_layout.addStretch()
        main_layout.addWidget(left, stretch=1)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(sep)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        right_layout.addWidget(QLabel("Available Files:"))

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        placeholder = QWidget()
        QVBoxLayout(placeholder)
        self.scroll_area.setWidget(placeholder)
        right_layout.addWidget(self.scroll_area)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        right_layout.addWidget(self.progress_label)

        self.file_progress_bar = QProgressBar()
        self.file_progress_bar.setVisible(False)
        self.file_progress_bar.setTextVisible(True)
        self.file_progress_bar.setFormat("File: %v / %m bytes")
        right_layout.addWidget(self.file_progress_bar)

        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setVisible(False)
        self.overall_progress_bar.setTextVisible(True)
        self.overall_progress_bar.setFormat("Overall: %p%")
        right_layout.addWidget(self.overall_progress_bar)

        btn_row = QHBoxLayout()
        self.toggle_btn = QPushButton("Deselect All")
        self.toggle_btn.clicked.connect(self._toggle_all)
        self.toggle_btn.setEnabled(False)
        btn_row.addWidget(self.toggle_btn)

        self.dl_btn = QPushButton("Download Selected")
        self.dl_btn.clicked.connect(self._download)
        self.dl_btn.setEnabled(False)
        btn_row.addWidget(self.dl_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.setVisible(False)
        btn_row.addWidget(self.cancel_btn)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self._open_download_folder)
        self.open_folder_btn.setVisible(False)
        btn_row.addWidget(self.open_folder_btn)

        right_layout.addLayout(btn_row)

        main_layout.addWidget(right, stretch=2)

        self.statusBar().showMessage("Not logged in")

    def _load_settings(self):
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        saved_dir = self.settings.value("download/directory")
        if saved_dir and os.path.isdir(saved_dir):
            self.download_dir = saved_dir
            self.dir_entry.setText(saved_dir)

        saved_token = self.settings.value("auth/token")
        if saved_token:
            self.token = saved_token
            self.statusBar().showMessage("Validating saved token...")
            threading.Thread(target=self._validate_token_async, args=(saved_token,), daemon=True).start()

    def _validate_token_async(self, token):
        if authenticate_with_token(token):
            user = get_current_user()
            msg = f"Logged in as {user}" if user else "Token loaded"
            self.auth_signals.done.emit(msg)
        else:
            self.auth_signals.done.emit("")

    def _on_auth_done(self, msg):
        if msg:
            self.statusBar().showMessage(msg)
        else:
            self.statusBar().showMessage("Saved token invalid")
            self.token = None

    def _save_settings(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("download/directory", self.dir_entry.text())
        if self.token:
            self.settings.setValue("auth/token", self.token)
        else:
            self.settings.remove("auth/token")

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def _show_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumWidth(480)
        layout = QVBoxLayout(dlg)

        grp = QGroupBox("HuggingFace Authentication")
        grp_layout = QVBoxLayout(grp)

        status_lbl = QLabel(f"Status: {self.statusBar().currentMessage()}")
        grp_layout.addWidget(status_lbl)

        grp_layout.addWidget(QLabel("Access Token:"))
        token_input = QLineEdit()
        token_input.setEchoMode(QLineEdit.Password)
        token_input.setPlaceholderText("Enter your HuggingFace access token")
        if self.token:
            token_input.setText(self.token)
        grp_layout.addWidget(token_input)

        show_cb = QCheckBox("Show token")
        show_cb.toggled.connect(
            lambda on: token_input.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        grp_layout.addWidget(show_cb)

        row = QHBoxLayout()

        def do_save():
            t = token_input.text().strip()
            if not t:
                QMessageBox.warning(dlg, "Warning", "Token cannot be empty")
                return
            if authenticate_with_token(t):
                self.token = t
                self.settings.setValue("auth/token", t)
                user = get_current_user()
                msg = f"Logged in as {user}" if user else "Logged in"
                self.statusBar().showMessage(msg)
                status_lbl.setText(f"Status: {msg}")
                QMessageBox.information(dlg, "Success", msg)
            else:
                QMessageBox.critical(dlg, "Error", "Invalid token")

        def do_logout():
            self.token = None
            self.settings.remove("auth/token")
            self.statusBar().showMessage("Not logged in")
            status_lbl.setText("Status: Not logged in")
            token_input.clear()
            QMessageBox.information(dlg, "Success", "Token cleared")

        save_btn = QPushButton("Save && Login")
        save_btn.clicked.connect(do_save)
        row.addWidget(save_btn)

        logout_btn = QPushButton("Logout / Clear Token")
        logout_btn.clicked.connect(do_logout)
        row.addWidget(logout_btn)

        grp_layout.addLayout(row)
        layout.addWidget(grp)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Download Location", self.download_dir)
        if d:
            self.download_dir = d
            self.dir_entry.setText(d)
            self.settings.setValue("download/directory", d)

    def _set_controls_busy(self, busy):
        self.fetch_btn.setEnabled(not busy)
        self.repo_entry.setEnabled(not busy)
        if not busy and self.file_checkboxes:
            self.toggle_btn.setEnabled(True)
            self.dl_btn.setEnabled(True)
        elif busy:
            self.toggle_btn.setEnabled(False)
            self.dl_btn.setEnabled(False)

    def _fetch_files(self):
        repo_id = self.repo_entry.text().strip()
        if not repo_id:
            QMessageBox.critical(self, "Error", "Repository ID cannot be empty")
            return

        if self.is_fetching or self.is_downloading:
            return

        self.is_fetching = True
        self._set_controls_busy(True)
        self.open_folder_btn.setVisible(False)
        self.statusBar().showMessage(f"Fetching file list from {repo_id}...")

        def worker():
            try:
                files = get_repo_files_with_sizes(repo_id, token=self.token)
                self.fetch_signals.success.emit(files)
            except Exception as e:
                self.fetch_signals.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_success(self, files):
        self.is_fetching = False
        self.file_checkboxes.clear()
        self.file_sizes.clear()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignTop)

        for name, size in files:
            label = f"{name}  ({format_size(size)})"
            cb = QCheckBox(label)
            cb.setProperty("filename", name)
            cb.setChecked(True)
            cb.toggled.connect(self._update_toggle_text)
            content_layout.addWidget(cb)
            self.file_checkboxes.append(cb)
            self.file_sizes[name] = size

        self.scroll_area.setWidget(content)
        self._set_controls_busy(False)
        self.toggle_btn.setText("Deselect All")
        self.statusBar().showMessage(f"Found {len(files)} files")

    def _on_fetch_error(self, error_msg):
        self.is_fetching = False
        self._set_controls_busy(False)
        self.statusBar().showMessage("Fetch failed")
        QMessageBox.critical(self, "Error", f"Failed to get repository files: {error_msg}")

    def _update_toggle_text(self):
        if not self.file_checkboxes:
            return
        all_on = all(cb.isChecked() for cb in self.file_checkboxes)
        self.toggle_btn.setText("Deselect All" if all_on else "Select All")

    def _toggle_all(self):
        if not self.file_checkboxes:
            return
        all_on = all(cb.isChecked() for cb in self.file_checkboxes)
        new_state = not all_on
        for cb in self.file_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(new_state)
            cb.blockSignals(False)
        self.toggle_btn.setText("Deselect All" if new_state else "Select All")

    def _download(self):
        repo_id = self.repo_entry.text().strip()
        selected = [cb.property("filename") for cb in self.file_checkboxes if cb.isChecked()]
        if not selected:
            QMessageBox.warning(self, "Warning", "No files selected")
            return

        repo_name = repo_id.split('/')[-1]
        local_dir = Path(self.dir_entry.text()) / repo_name
        os.makedirs(local_dir, exist_ok=True)

        self.last_download_dir = str(local_dir)
        self.is_downloading = True
        self.cancel_requested = False
        self._set_controls_busy(True)
        self.cancel_btn.setVisible(True)
        self.open_folder_btn.setVisible(False)

        total_bytes = sum(self.file_sizes.get(f, 0) for f in selected)
        self.overall_bytes_completed = 0
        self.overall_total_bytes = total_bytes

        self.progress_label.setVisible(True)
        self.file_progress_bar.setVisible(True)
        self.overall_progress_bar.setVisible(True)
        self.overall_progress_bar.setMaximum(100)
        self.overall_progress_bar.setValue(0)
        self.file_progress_bar.setMaximum(100)
        self.file_progress_bar.setValue(0)
        self.progress_label.setText(f"Starting download of {len(selected)} files...")

        self.statusBar().showMessage(f"Downloading {len(selected)} files ({format_size(total_bytes)})...")

        def worker():
            succeeded = []
            failed = []
            for i, filename in enumerate(selected):
                if self.cancel_requested:
                    self.signals.cancelled.emit()
                    return

                file_size = self.file_sizes.get(filename, 0)
                self.signals.file_progress.emit(i + 1, len(selected), filename, 0, file_size)

                try:
                    def make_tqdm_class(signal):
                        class BoundProgressTqdm(ProgressTqdm):
                            def __init__(self, *args, **kwargs):
                                kwargs['signal'] = signal
                                super().__init__(*args, **kwargs)
                        return BoundProgressTqdm

                    hf_hub_download(
                        repo_id,
                        filename=filename,
                        local_dir=str(local_dir),
                        token=self.token,
                        tqdm_class=make_tqdm_class(self.signals.byte_progress),
                    )
                    succeeded.append(filename)
                except Exception as e:
                    failed.append((filename, str(e)))

                self.overall_bytes_completed += file_size

            if failed:
                failed_names = [f"{name}: {err}" for name, err in failed]
                self.signals.error.emit(
                    f"{len(succeeded)} of {len(selected)} files downloaded. {len(failed)} failed.",
                    failed_names
                )
            else:
                self.signals.success.emit(
                    f"Downloaded {len(succeeded)} files to {local_dir}",
                    str(local_dir)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_file_progress(self, current_file, total_files, filename, bytes_done, bytes_total):
        short_name = filename.split('/')[-1]
        self.progress_label.setText(
            f"File {current_file}/{total_files}: {short_name} ({format_size(bytes_total)})"
        )
        self.file_progress_bar.setValue(0)
        self.file_progress_bar.setFormat(f"File: {short_name} - %p%")

    def _on_byte_progress(self, bytes_done, bytes_total):
        if bytes_total > 0:
            pct = int(bytes_done * 100 / bytes_total)
            self.file_progress_bar.setValue(pct)
            self.file_progress_bar.setFormat(
                f"File: {format_size(bytes_done)} / {format_size(bytes_total)} - {pct}%"
            )

        if self.overall_total_bytes > 0:
            overall_done = self.overall_bytes_completed + bytes_done
            overall_pct = int(overall_done * 100 / self.overall_total_bytes)
            overall_pct = min(overall_pct, 100)
            self.overall_progress_bar.setValue(overall_pct)
            self.overall_progress_bar.setFormat(
                f"Overall: {format_size(overall_done)} / {format_size(self.overall_total_bytes)} - {overall_pct}%"
            )

    def _cancel_download(self):
        self.cancel_requested = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")
        self.statusBar().showMessage("Cancelling download...")

    def _on_download_cancelled(self):
        self.is_downloading = False
        self._set_controls_busy(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Cancel")
        self._hide_progress()
        self.statusBar().showMessage("Download cancelled")
        QMessageBox.information(self, "Cancelled", "Download was cancelled. Files already downloaded are kept.")

    def _on_download_success(self, msg, folder_path):
        self.is_downloading = False
        self._set_controls_busy(False)
        self.cancel_btn.setVisible(False)
        self._hide_progress()
        self.open_folder_btn.setVisible(True)
        self.statusBar().showMessage("Download complete")
        QMessageBox.information(self, "Success", msg)

    def _on_download_error(self, msg, failed_details):
        self.is_downloading = False
        self._set_controls_busy(False)
        self.cancel_btn.setVisible(False)
        self._hide_progress()
        self.open_folder_btn.setVisible(True)
        self.statusBar().showMessage("Download completed with errors")
        detail_text = "\n".join(failed_details)
        QMessageBox.warning(
            self, "Download Errors",
            f"{msg}\n\nFailed files:\n{detail_text}"
        )

    def _hide_progress(self):
        self.progress_label.setVisible(False)
        self.file_progress_bar.setVisible(False)
        self.overall_progress_bar.setVisible(False)

    def _open_download_folder(self):
        folder = getattr(self, 'last_download_dir', self.dir_entry.text())
        if os.path.isdir(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder], creationflags=0)
            else:
                subprocess.Popen(["xdg-open", folder])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = HFDownloaderApp()
    window.show()
    sys.exit(app.exec())