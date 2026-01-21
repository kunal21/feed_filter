import os
import asyncio
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
import imagehash
import pytesseract
from PIL import Image
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import AsyncOpenAI
from contextlib import asynccontextmanager

# Load environment variables
load_dotenv()

# OpenAI client (initialized if API key is present)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
FRAMES_DIR = DATA_DIR / "frames"
DB_PATH = DATA_DIR / "feed_filter.db"

# Create directories
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)

# Perceptual hash threshold for deduplication
HASH_THRESHOLD = 5


async def init_db():
    """Initialize SQLite database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE,
                frame_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id INTEGER,
                frame_path TEXT NOT NULL,
                frame_hash TEXT,
                ocr_text TEXT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bookmarked BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (recording_id) REFERENCES recordings(id)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_text ON posts(ocr_text)
        """)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Feed Filter API", lifespan=lifespan)

# CORS for extension and dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "feed_filter"}


@app.post("/upload")
async def upload_video(video: UploadFile = File(...)):
    """Upload a video recording for processing."""
    if not video.filename.endswith(('.webm', '.mp4', '.mkv')):
        raise HTTPException(400, "Invalid video format")

    # Save the video
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recording_{timestamp}.webm"
    filepath = UPLOADS_DIR / filename

    with open(filepath, "wb") as f:
        content = await video.read()
        f.write(content)

    # Add to database
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO recordings (filename) VALUES (?)",
            (filename,)
        )
        recording_id = cursor.lastrowid
        await db.commit()

    # Start background processing
    asyncio.create_task(process_video(recording_id, filepath))

    return {"status": "uploaded", "filename": filename, "recording_id": recording_id}


async def process_video(recording_id: int, video_path: Path):
    """Extract frames, deduplicate, and OCR."""
    print(f"Processing recording {recording_id}: {video_path}")

    # Create frame directory for this recording
    recording_frames_dir = FRAMES_DIR / str(recording_id)
    recording_frames_dir.mkdir(exist_ok=True)

    # Extract frames using ffmpeg (1 frame per second)
    try:
        subprocess.run([
            "ffmpeg", "-i", str(video_path),
            "-vf", "fps=1",
            "-q:v", "2",
            str(recording_frames_dir / "frame_%04d.jpg")
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        return
    except FileNotFoundError:
        print("FFmpeg not found. Please install ffmpeg.")
        return

    # Get all extracted frames
    frames = sorted(recording_frames_dir.glob("frame_*.jpg"))
    print(f"Extracted {len(frames)} frames")

    # Deduplicate and OCR
    seen_hashes = []
    unique_count = 0

    async with aiosqlite.connect(DB_PATH) as db:
        for frame_path in frames:
            try:
                img = Image.open(frame_path)

                # Compute perceptual hash
                phash = imagehash.phash(img)

                # Check if similar frame already seen
                is_duplicate = False
                for seen_hash in seen_hashes:
                    if phash - seen_hash < HASH_THRESHOLD:
                        is_duplicate = True
                        break

                if is_duplicate:
                    # Remove duplicate frame
                    frame_path.unlink()
                    continue

                seen_hashes.append(phash)
                unique_count += 1

                # OCR the frame
                try:
                    ocr_text = pytesseract.image_to_string(img)
                    ocr_text = ocr_text.strip()
                except Exception as e:
                    print(f"OCR error on {frame_path}: {e}")
                    ocr_text = ""

                # Store in database
                await db.execute(
                    """INSERT INTO posts (recording_id, frame_path, frame_hash, ocr_text)
                       VALUES (?, ?, ?, ?)""",
                    (recording_id, str(frame_path), str(phash), ocr_text)
                )

            except Exception as e:
                print(f"Error processing {frame_path}: {e}")

        # Mark recording as processed
        await db.execute(
            "UPDATE recordings SET processed = TRUE, frame_count = ? WHERE id = ?",
            (unique_count, recording_id)
        )
        await db.commit()

    print(f"Recording {recording_id} processed: {unique_count} unique frames")


@app.get("/posts")
async def get_posts(
    search: Optional[str] = None,
    bookmarked: Optional[bool] = None,
    recording_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Get posts with optional filtering."""
    query = "SELECT * FROM posts WHERE 1=1"
    params = []

    if search:
        query += " AND ocr_text LIKE ?"
        params.append(f"%{search}%")

    if bookmarked is not None:
        query += " AND bookmarked = ?"
        params.append(bookmarked)

    if recording_id is not None:
        query += " AND recording_id = ?"
        params.append(recording_id)

    query += " ORDER BY extracted_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        posts = [dict(row) for row in rows]

    return {"posts": posts, "count": len(posts)}


@app.get("/posts/{post_id}")
async def get_post(post_id: int):
    """Get a single post by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(404, "Post not found")

        return dict(row)


@app.post("/posts/{post_id}/bookmark")
async def toggle_bookmark(post_id: int):
    """Toggle bookmark status for a post."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE posts SET bookmarked = NOT bookmarked WHERE id = ?",
            (post_id,)
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT bookmarked FROM posts WHERE id = ?",
            (post_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(404, "Post not found")

        return {"bookmarked": bool(row[0])}


@app.delete("/posts/{post_id}")
async def delete_post(post_id: int):
    """Delete a post."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Get frame path first
        cursor = await db.execute(
            "SELECT frame_path FROM posts WHERE id = ?",
            (post_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(404, "Post not found")

        # Delete frame file
        frame_path = Path(row[0])
        if frame_path.exists():
            frame_path.unlink()

        # Delete from database
        await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        await db.commit()

    return {"status": "deleted"}


@app.get("/recordings")
async def get_recordings():
    """Get all recordings."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM recordings ORDER BY uploaded_at DESC"
        )
        rows = await cursor.fetchall()

        return {"recordings": [dict(row) for row in rows]}


@app.get("/frame/{recording_id}/{frame_name}")
async def get_frame(recording_id: int, frame_name: str):
    """Serve a frame image."""
    frame_path = FRAMES_DIR / str(recording_id) / frame_name

    if not frame_path.exists():
        raise HTTPException(404, "Frame not found")

    return FileResponse(frame_path, media_type="image/jpeg")


@app.post("/search/semantic")
async def semantic_search(query: str, limit: int = 20):
    """
    Use Ollama to semantically search posts.
    Analyzes each post individually for better relevance scoring.
    """
    import httpx

    # Get all posts with text
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, ocr_text, frame_path FROM posts WHERE ocr_text != '' ORDER BY extracted_at DESC LIMIT 100"
        )
        rows = await cursor.fetchall()
        posts = [dict(row) for row in rows]

    if not posts:
        return {"posts": [], "count": 0}

    # Score each post individually for better accuracy
    scored_posts = []

    async with httpx.AsyncClient() as client:
        for post in posts:
            text = post['ocr_text'][:500]  # Use more text for better understanding

            prompt = f"""Rate how relevant this LinkedIn post is to the query "{query}".
Score from 0-10 where:
- 0 = completely irrelevant
- 5 = somewhat related
- 10 = highly relevant

Post content:
{text}

Reply with ONLY a number 0-10, nothing else:"""

            try:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama3.2",
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": 5,
                            "temperature": 0.1
                        }
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("response", "").strip()
                    # Extract first number from response
                    score = 0
                    for char in answer:
                        if char.isdigit():
                            score = int(char)
                            if len(answer) > 1 and answer[0] == '1' and answer[1] == '0':
                                score = 10
                            break

                    if score >= 5:  # Only include posts with score 5+
                        scored_posts.append((score, post))

            except Exception as e:
                print(f"Error scoring post {post['id']}: {e}")
                continue

    # Sort by score descending
    scored_posts.sort(key=lambda x: x[0], reverse=True)

    # Get full post data for top results
    result_posts = []
    for score, post in scored_posts[:limit]:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM posts WHERE id = ?",
                (post['id'],)
            )
            row = await cursor.fetchone()
            if row:
                post_dict = dict(row)
                post_dict['relevance_score'] = score
                result_posts.append(post_dict)

    return {"posts": result_posts, "count": len(result_posts)}


@app.post("/analyze")
async def analyze_post(post_id: int, question: str):
    """
    Ask a question about a specific post using Ollama.
    """
    import httpx

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM posts WHERE id = ?",
            (post_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(404, "Post not found")

        post = dict(row)

    prompt = f"""Analyze this LinkedIn post and answer the question.

POST CONTENT:
{post['ocr_text']}

QUESTION: {question}

Answer concisely:"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 200
                    }
                },
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            answer = result.get("response", "").strip()

            return {"answer": answer, "post_id": post_id}

    except httpx.ConnectError:
        raise HTTPException(503, "Ollama not running. Start it with: ollama serve")
    except Exception as e:
        raise HTTPException(500, f"Ollama error: {str(e)}")


class ChatRequest(BaseModel):
    page_title: str
    page_url: str
    page_content: str
    question: str


class PostsChatRequest(BaseModel):
    posts_content: str
    question: str


async def call_openai(messages: list, max_tokens: int = 500) -> str:
    """Call OpenAI API."""
    if not openai_client:
        raise HTTPException(503, "OpenAI API key not configured")

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


async def call_ollama(prompt: str, max_tokens: int = 500) -> str:
    """Call Ollama API."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens
                }
            },
            timeout=120.0
        )
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip()


@app.post("/chat")
async def chat_with_page(request: ChatRequest):
    """
    Proxy endpoint for the extension to chat about a webpage.
    Uses OpenAI if USE_OPENAI=true, otherwise Ollama.
    """
    page_title = request.page_title
    page_url = request.page_url
    page_content = request.page_content
    question = request.question

    # Truncate content if too long
    if len(page_content) > 12000:
        page_content = page_content[:12000] + "... [truncated]"

    system_prompt = "You are a helpful assistant analyzing a webpage. Be concise and direct."

    user_content = f"""PAGE TITLE: {page_title}
PAGE URL: {page_url}

PAGE CONTENT:
{page_content}

USER QUESTION: {question}

Provide a helpful, concise answer based on the page content above:"""

    try:
        if USE_OPENAI and openai_client:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            answer = await call_openai(messages, max_tokens=500)
        else:
            prompt = f"{system_prompt}\n\n{user_content}"
            answer = await call_ollama(prompt, max_tokens=500)

        return {"answer": answer}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"AI error: {str(e)}")


@app.post("/chat/posts")
async def chat_with_posts(request: PostsChatRequest):
    """
    Chat endpoint for the dashboard to ask questions about captured posts.
    Uses OpenAI if USE_OPENAI=true, otherwise Ollama.
    """
    posts_content = request.posts_content
    question = request.question

    # Truncate content if too long
    if len(posts_content) > 15000:
        posts_content = posts_content[:15000] + "... [truncated]"

    system_prompt = """You are a helpful assistant analyzing LinkedIn posts that were captured via screen recording and OCR.
The posts may have some OCR errors or formatting issues. Do your best to understand the content and provide helpful answers.
Be concise and direct. When summarizing or listing posts, use clear formatting with bullet points."""

    user_content = f"""CAPTURED LINKEDIN POSTS:
{posts_content}

USER QUESTION: {question}

Provide a helpful, concise answer based on the posts above:"""

    try:
        if USE_OPENAI and openai_client:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            answer = await call_openai(messages, max_tokens=800)
        else:
            prompt = f"{system_prompt}\n\n{user_content}"
            answer = await call_ollama(prompt, max_tokens=800)

        return {"answer": answer}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"AI error: {str(e)}")


@app.get("/stats")
async def get_stats():
    """Get overall statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM recordings")
        recordings_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM posts")
        posts_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM posts WHERE bookmarked = TRUE")
        bookmarked_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM recordings WHERE processed = FALSE"
        )
        processing_count = (await cursor.fetchone())[0]

    return {
        "recordings": recordings_count,
        "posts": posts_count,
        "bookmarked": bookmarked_count,
        "processing": processing_count
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
