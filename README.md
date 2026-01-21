# Feed Filter

Screen record any webpage, extract content via OCR, and interact with it later using AI-powered chat and search.

## Features

- **Screen Recording**: Record any browser tab (LinkedIn, Twitter, news sites, etc.)
- **OCR Extraction**: Automatically extract text from captured frames using Tesseract
- **AI Chat (Extension)**: Chat with any webpage in real-time - ask questions about the page content
- **AI Chat (Dashboard)**: Ask questions about your recorded content - summarize posts, find topics, search intelligently
- **Smart Deduplication**: Perceptual hashing removes duplicate frames automatically
- **Local-first**: Everything runs on your machine - no data sent to external servers (except optional OpenAI API)

## Architecture

```
Chrome Extension → Records any browser tab
        │         → AI Chat: Ask questions about current page
        ↓
Backend (Python) → FFmpeg extracts frames
                 → Deduplicates similar frames (perceptual hashing)
                 → Tesseract OCR extracts text
                 → Stores in SQLite
        ↓
Dashboard → View all captured posts
          → Text search
          → AI Chat: Ask questions about recorded content
          → AI Search (semantic search with Ollama)
          → Bookmark/delete posts
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

### 3. Ollama (for local AI - optional)
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Then pull a model
ollama pull llama3.2
ollama serve
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

# (Optional) Configure OpenAI for faster AI responses
# Create .env file with:
# OPENAI_API_KEY=your-key-here
# USE_OPENAI=true

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

```bash
cd dashboard
python3 -m http.server 8080
# Open http://localhost:8080
```

## Usage

### Recording Any Page

1. Navigate to any webpage in Chrome
2. Click the Feed Filter extension icon
3. Click "Start Recording"
4. Scroll through the page content
5. Click "Stop & Upload"
6. Wait for processing (check dashboard)

### AI Chat (Extension)

1. On any webpage, click the extension icon
2. Go to the "AI Chat" tab
3. Ask questions about the current page content
4. Note: Works on pages that expose their DOM (may not work on heavily protected sites like LinkedIn)

### AI Chat (Dashboard)

1. Open the dashboard at `http://localhost:8080`
2. Click the "AI Chat" button
3. Ask questions about your recorded content:
   - "Summarize all posts"
   - "What are the main topics?"
   - "Find job-related posts"
   - "Show me posts about AI"

### Filtering & Search

1. **Text search**: Type keywords in the search box, press Enter
2. **AI search**: Type a question like "posts about AI startups", click "AI Search"
3. **Bookmark**: Save interesting posts for later
4. **Delete**: Remove irrelevant posts

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload video recording |
| GET | `/posts` | List posts (with filters) |
| GET | `/posts/{id}` | Get single post |
| POST | `/posts/{id}/bookmark` | Toggle bookmark |
| DELETE | `/posts/{id}` | Delete post |
| GET | `/recordings` | List all recordings |
| POST | `/search/semantic` | AI-powered semantic search |
| POST | `/chat` | Chat about a webpage (extension) |
| POST | `/chat/posts` | Chat about recorded posts (dashboard) |
| GET | `/stats` | Get statistics |

## Configuration

### Using OpenAI (faster, requires API key)

Create `backend/.env`:
```
OPENAI_API_KEY=sk-your-key-here
USE_OPENAI=true
```

### Using Ollama (free, local, slower)

Set in `backend/.env`:
```
USE_OPENAI=false
```

Make sure Ollama is running: `ollama serve`

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

**AI Chat not working on some pages**
- Some sites (like LinkedIn) protect their DOM from being read
- Use screen recording for these sites, then chat via the dashboard

**Poor OCR quality**
- Try scrolling slower to capture cleaner frames
- High-contrast text works best

## Cost

**$0 per session** with local setup:
- Tesseract OCR: Free, open source
- Ollama: Free, local LLM
- FFmpeg: Free, open source
- SQLite: Free, built into Python

**Optional**: OpenAI API for faster responses (~$0.01-0.05 per chat)

## File Structure

```
feed_filter/
├── extension/           # Chrome extension
│   ├── manifest.json
│   ├── background.js    # Service worker
│   ├── offscreen.js     # Recording handler
│   ├── popup.html/js    # Extension UI with Record & AI Chat tabs
│   └── icons/
├── backend/             # Python FastAPI backend
│   ├── main.py
│   ├── requirements.txt
│   ├── .env             # API keys (create this)
│   └── data/            # Created at runtime
│       ├── uploads/     # Raw video files
│       ├── frames/      # Extracted frames
│       └── feed_filter.db
└── dashboard/           # Web UI
    └── index.html       # Dashboard with AI Chat panel
```
