// ==================== Recording Tab ====================
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusBox = document.getElementById('statusBox');
const statusText = document.getElementById('statusText');
const timer = document.getElementById('timer');
const uploadStatus = document.getElementById('uploadStatus');
const backendUrlInput = document.getElementById('backendUrl');

let timerInterval = null;

// Load saved backend URL
chrome.storage.local.get(['backendUrl'], (result) => {
  if (result.backendUrl) {
    backendUrlInput.value = result.backendUrl;
  }
});

// Save backend URL on change
backendUrlInput.addEventListener('change', () => {
  chrome.storage.local.set({ backendUrl: backendUrlInput.value });
});

// Check current recording status on popup open
async function checkStatus() {
  const response = await chrome.runtime.sendMessage({ action: 'getStatus' });

  if (response && response.isRecording) {
    showRecordingState(response.elapsed);
    startTimerFromElapsed(response.elapsed);
  } else {
    showIdleState();
  }
}

function showRecordingState(elapsed = 0) {
  startBtn.style.display = 'none';
  stopBtn.style.display = 'block';
  statusBox.className = 'status recording';
  statusText.textContent = 'Recording...';
  timer.style.display = 'block';
  updateTimerDisplay(elapsed);
}

function showIdleState() {
  startBtn.style.display = 'block';
  stopBtn.style.display = 'none';
  statusBox.className = 'status idle';
  statusText.textContent = 'Ready to record';
  timer.style.display = 'none';
  timer.textContent = '00:00';
  clearInterval(timerInterval);
}

function updateTimerDisplay(seconds) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
  const secs = (seconds % 60).toString().padStart(2, '0');
  timer.textContent = `${minutes}:${secs}`;
}

function startTimerFromElapsed(elapsed) {
  let seconds = elapsed;
  updateTimerDisplay(seconds);

  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    seconds++;
    updateTimerDisplay(seconds);
  }, 1000);
}

startBtn.addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab) {
      uploadStatus.textContent = 'Error: No active tab';
      uploadStatus.className = 'upload-status error';
      return;
    }

    uploadStatus.textContent = 'Starting...';
    uploadStatus.className = 'upload-status uploading';

    const response = await chrome.runtime.sendMessage({
      action: 'startRecording',
      tabId: tab.id
    });

    if (response.success) {
      showRecordingState();
      startTimerFromElapsed(0);
      uploadStatus.textContent = 'Recording! You can close this popup.';
      uploadStatus.className = 'upload-status success';
    } else {
      uploadStatus.textContent = `Error: ${response.error}`;
      uploadStatus.className = 'upload-status error';
    }
  } catch (error) {
    console.error('Start error:', error);
    uploadStatus.textContent = `Error: ${error.message}`;
    uploadStatus.className = 'upload-status error';
  }
});

stopBtn.addEventListener('click', async () => {
  try {
    clearInterval(timerInterval);
    statusText.textContent = 'Stopping...';
    uploadStatus.textContent = 'Processing & uploading...';
    uploadStatus.className = 'upload-status uploading';

    const backendUrl = backendUrlInput.value;
    const response = await chrome.runtime.sendMessage({
      action: 'stopRecording',
      backendUrl: backendUrl
    });

    showIdleState();

    if (response.success) {
      uploadStatus.textContent = `Uploaded! Processing ${response.filename}`;
      uploadStatus.className = 'upload-status success';
    } else if (response.savedLocally) {
      uploadStatus.textContent = 'Upload failed - saved locally';
      uploadStatus.className = 'upload-status error';
    } else {
      uploadStatus.textContent = `Error: ${response.error}`;
      uploadStatus.className = 'upload-status error';
    }
  } catch (error) {
    console.error('Stop error:', error);
    showIdleState();
    uploadStatus.textContent = `Error: ${error.message}`;
    uploadStatus.className = 'upload-status error';
  }
});

// ==================== Tab Navigation ====================
const tabs = document.querySelectorAll('.tab');
const tabContents = {
  record: document.getElementById('recordTab'),
  ai: document.getElementById('aiTab')
};

tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    const targetTab = tab.dataset.tab;

    // Update tab buttons
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    // Update tab content
    Object.keys(tabContents).forEach(key => {
      tabContents[key].classList.remove('active');
    });
    tabContents[targetTab].classList.add('active');

    // Load page content when switching to AI tab
    if (targetTab === 'ai' && !pageContent) {
      extractPageContent();
    }
  });
});

// ==================== AI Chat Tab ====================
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const quickActions = document.querySelectorAll('.quick-action');

let pageContent = null;
let conversationHistory = [];

// Extract page content from current tab
async function extractPageContent() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab) {
      addMessage('error', 'No active tab found');
      return;
    }

    addMessage('system', 'Reading page content...');

    // Inject script to extract page content
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        // Get main text content, excluding scripts, styles, etc.
        const elementsToRemove = document.querySelectorAll('script, style, noscript, iframe, svg, img');
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll('script, style, noscript, iframe, svg').forEach(el => el.remove());

        // Get text content
        let text = clone.innerText || clone.textContent;

        // Clean up whitespace
        text = text.replace(/\s+/g, ' ').trim();

        // Limit to ~8000 chars to fit in context
        if (text.length > 8000) {
          text = text.substring(0, 8000) + '... [truncated]';
        }

        return {
          title: document.title,
          url: window.location.href,
          content: text
        };
      }
    });

    if (results && results[0] && results[0].result) {
      pageContent = results[0].result;
      // Remove the "Reading page content..." message
      const lastMsg = chatMessages.lastElementChild;
      if (lastMsg && lastMsg.textContent.includes('Reading')) {
        lastMsg.remove();
      }
      addMessage('system', `Loaded: ${pageContent.title.substring(0, 50)}...`);
    } else {
      addMessage('error', 'Could not read page content');
    }
  } catch (error) {
    console.error('Extract error:', error);
    addMessage('error', `Error: ${error.message}`);
  }
}

function addMessage(type, content) {
  const msg = document.createElement('div');
  msg.className = `message ${type}`;
  msg.textContent = content;
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

async function sendMessage(userQuery) {
  if (!userQuery.trim()) return;

  if (!pageContent) {
    await extractPageContent();
    if (!pageContent) return;
  }

  // Add user message
  addMessage('user', userQuery);
  chatInput.value = '';

  // Add loading message
  const loadingMsg = addMessage('assistant', 'Thinking...');

  // Disable input while processing
  sendBtn.disabled = true;
  chatInput.disabled = true;

  // Get backend URL
  const backendUrl = backendUrlInput.value.replace(/\/$/, '');

  try {
    // Call backend proxy (avoids CORS issues with Ollama)
    const response = await fetch(`${backendUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page_title: pageContent.title,
        page_url: pageContent.url,
        page_content: pageContent.content,
        question: userQuery
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Error: ${response.status}`);
    }

    const data = await response.json();
    const answer = data.answer || 'No response received';

    // Update loading message with actual response
    loadingMsg.textContent = answer;

  } catch (error) {
    console.error('AI error:', error);
    loadingMsg.className = 'message error';
    loadingMsg.textContent = `Error: ${error.message}. Is backend running?`;
  }

  // Re-enable input
  sendBtn.disabled = false;
  chatInput.disabled = false;
  chatInput.focus();
}

// Event listeners for AI chat
sendBtn.addEventListener('click', () => sendMessage(chatInput.value));

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(chatInput.value);
  }
});

quickActions.forEach(btn => {
  btn.addEventListener('click', () => {
    const prompt = btn.dataset.prompt;
    sendMessage(prompt);
  });
});

// ==================== Initialize ====================
checkStatus();
