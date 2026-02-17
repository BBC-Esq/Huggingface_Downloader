# Hugging Face Model Downloader

A desktop application for browsing and downloading files from Hugging Face repositories. Built with PySide6 and the Hugging Face Hub API.

## Features

- **Browse repository files** with file sizes displayed for each entry
- **Selective downloads** — check or uncheck individual files before downloading
- **Accurate progress tracking** with per-file and overall progress bars showing bytes transferred
- **Cancel downloads** mid-operation; files already completed are kept
- **Partial failure resilience** — if some files fail, successfully downloaded files are preserved and you're told exactly which files failed and why
- **Open download folder** directly from the app after downloads complete
- **HuggingFace token authentication** for accessing gated/private repositories, with credentials saved between sessions
- **Non-blocking UI** — file fetching, downloads, and token validation all run in background threads

## Screenshot

![HF Model Downloader](https://github.com/user-attachments/assets/placeholder)

## Requirements

- Python 3.11, 3.12, or 3.13
- Windows, macOS, or Linux

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. Enter a repository ID (e.g. `meta-llama/Llama-2-7b`)
2. Click **Fetch Files** to retrieve the file list
3. Select or deselect files as needed
4. Choose a download location
5. Click **Download Selected**

### Accessing Gated or Private Repositories

Some repositories on Hugging Face require authentication. To access them:

1. Create an access token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. In the app, go to **File > Settings**
3. Paste your token and click **Save & Login**

Your token is saved locally between sessions.

## License

MIT
