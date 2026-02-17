# Hugging Face Model Downloader

A desktop application for browsing and downloading files from Hugging Face repositories. Built with PySide6 and the Hugging Face Hub API.

<img width="903" height="633" alt="image" src="https://github.com/user-attachments/assets/0a9a7004-69be-4612-a01e-f43216718c1d" />

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
