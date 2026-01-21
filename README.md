# Feed Filter

Screen record your LinkedIn feed, extract posts via OCR, and filter them later with AI-powered search.

## Architecture

```
Chrome Extension → Records LinkedIn tab
        ↓
Backend (Python) → FFmpeg extracts frames
                 → Deduplicates similar frames
                 → Tesseract OCR extracts text
                 → Stores in SQLite
        ↓
Dashboard → View all posts
          → Text search
          → AI search (Ollama)
          → Bookmark/delete
```

## Prerequisites

Install these before running:

### 1. FFmpeg
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### 2. Tesseract OCR
```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr

# Windows
# Download from https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. Ollama (for AI search)
```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Then pull a model
ollama pull llama3.2
```

### 4. Python 3.10+
```bash
# Check version
python3 --version
```

## Setup

### 1. Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
```

Backend runs at `http://localhost:8000`

### 2. Chrome Extension

1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `extension` folder

### 3. Dashboard

Just open `dashboard/index.html` in a browser, or serve it:

```bash
cd dashboard
python3 -m http.server 3000
# Open http://localhost:3000
```

## Usage

### Recording

1. Go to LinkedIn in Chrome
2. Click the Feed Filter extension icon
3. Click "Start Recording"
4. Scroll through your feed (10 min recommended)
5. Click "Stop & Upload"
6. Wait for processing (check dashboard)

### Filtering

1. Open the dashboard
2. **Text search**: Type keywords, press Enter
3. **AI search**: Type a question like "posts about AI startups", click "AI Search"
4. **Bookmark**: Save interesting posts for later
5. **Delete**: Remove irrelevant posts

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload video recording |
| GET | `/posts` | List posts (with filters) |
| GET | `/posts/{id}` | Get single post |
| POST | `/posts/{id}/bookmark` | Toggle bookmark |
| DELETE | `/posts/{id}` | Delete post |
| GET | `/recordings` | List all recordings |
| POST | `/search/semantic` | AI-powered search |
| GET | `/stats` | Get statistics |

## Troubleshooting

**"FFmpeg not found"**
- Make sure FFmpeg is in your PATH
- Try running `ffmpeg -version` in terminal

**"Tesseract not found"**
- Install Tesseract and ensure it's in PATH
- On macOS: `brew install tesseract`

**"Ollama not running"**
- Start Ollama: `ollama serve`
- Pull a model: `ollama pull llama3.2`

**Extension won't record**
- Make sure you're on a regular tab (not chrome:// pages)
- Reload the extension after changes

**Poor OCR quality**
- LinkedIn's text is usually clear, but compressed video may affect quality
- Try scrolling slower to capture cleaner frames

## Cost

**$0 per session** - Everything runs locally:
- Tesseract OCR: Free, open source
- Ollama: Free, local LLM
- FFmpeg: Free, open source
- SQLite: Free, built into Python

## File Structure

```
feed_filter/
├── extension/           # Chrome extension
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   └── icons/
├── backend/            # Python backend
│   ├── main.py
│   ├── requirements.txt
│   └── data/           # Created at runtime
│       ├── uploads/    # Raw video files
│       ├── frames/     # Extracted frames
│       └── feed_filter.db
└── dashboard/          # Web UI
    └── index.html
```
