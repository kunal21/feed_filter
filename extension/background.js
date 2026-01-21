// Recording state
let isRecording = false;
let recordingTabId = null;
let startTime = null;

// Handle messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Ignore messages meant for offscreen document
  if (message.target === 'offscreen') {
    return false;
  }

  if (message.action === 'getStatus') {
    sendResponse({
      isRecording,
      recordingTabId,
      startTime,
      elapsed: startTime ? Math.floor((Date.now() - startTime) / 1000) : 0
    });
    return true;
  }

  if (message.action === 'startRecording') {
    startRecording(message.tabId).then(sendResponse);
    return true;
  }

  if (message.action === 'stopRecording') {
    stopRecording(message.backendUrl).then(sendResponse);
    return true;
  }

  return false;
});

async function startRecording(tabId) {
  if (isRecording) {
    return { success: false, error: 'Already recording' };
  }

  try {
    // Get media stream ID for the tab
    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId
    });

    // Create offscreen document for recording
    await createOffscreenDocument();

    // Send stream ID to offscreen document to start recording
    const response = await chrome.runtime.sendMessage({
      action: 'startCapture',
      target: 'offscreen',
      streamId: streamId
    });

    if (response.success) {
      isRecording = true;
      recordingTabId = tabId;
      startTime = Date.now();

      // Update badge
      chrome.action.setBadgeText({ text: 'REC' });
      chrome.action.setBadgeBackgroundColor({ color: '#e74c3c' });
    }

    return response;
  } catch (error) {
    console.error('Start recording error:', error);
    return { success: false, error: error.message };
  }
}

async function stopRecording(backendUrl) {
  if (!isRecording) {
    return { success: false, error: 'Not recording' };
  }

  try {
    const response = await chrome.runtime.sendMessage({
      action: 'stopCapture',
      target: 'offscreen',
      backendUrl: backendUrl
    });

    isRecording = false;
    recordingTabId = null;
    startTime = null;

    // Clear badge
    chrome.action.setBadgeText({ text: '' });

    // Close offscreen document
    await closeOffscreenDocument();

    return response;
  } catch (error) {
    console.error('Stop recording error:', error);
    return { success: false, error: error.message };
  }
}

async function createOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT']
  });

  if (existingContexts.length > 0) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['USER_MEDIA'],
    justification: 'Recording tab video for feed filtering'
  });
}

async function closeOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT']
  });

  if (existingContexts.length > 0) {
    await chrome.offscreen.closeDocument();
  }
}
