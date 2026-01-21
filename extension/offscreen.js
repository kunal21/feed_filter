let mediaRecorder = null;
let recordedChunks = [];
let mediaStream = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only handle messages targeted at offscreen
  if (message.target !== 'offscreen') {
    return false;
  }

  if (message.action === 'startCapture') {
    startCapture(message.streamId).then(sendResponse);
    return true;
  }

  if (message.action === 'stopCapture') {
    stopCapture(message.backendUrl).then(sendResponse);
    return true;
  }

  return false;
});

async function startCapture(streamId) {
  try {
    // Get media stream using the stream ID
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId
        }
      }
    });

    // Setup MediaRecorder
    recordedChunks = [];
    mediaRecorder = new MediaRecorder(mediaStream, {
      mimeType: 'video/webm;codecs=vp9'
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };

    // Start recording with 1-second chunks
    mediaRecorder.start(1000);

    console.log('Recording started');
    return { success: true };
  } catch (error) {
    console.error('Start capture error:', error);
    return { success: false, error: error.message };
  }
}

async function stopCapture(backendUrl) {
  return new Promise((resolve) => {
    if (!mediaRecorder || mediaRecorder.state === 'inactive') {
      resolve({ success: false, error: 'No active recording' });
      return;
    }

    mediaRecorder.onstop = async () => {
      // Stop all tracks
      if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
      }

      // Create blob from recorded chunks
      const blob = new Blob(recordedChunks, { type: 'video/webm' });
      console.log('Recording stopped, blob size:', blob.size);

      // Upload to backend
      const result = await uploadRecording(blob, backendUrl);
      resolve(result);
    };

    mediaRecorder.stop();
  });
}

async function uploadRecording(blob, backendUrl) {
  const url = backendUrl.replace(/\/$/, '');

  try {
    const formData = new FormData();
    formData.append('video', blob, `recording_${Date.now()}.webm`);

    const response = await fetch(`${url}/upload`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }

    const result = await response.json();
    console.log('Upload successful:', result);
    return { success: true, ...result };
  } catch (error) {
    console.error('Upload error:', error);

    // Save locally as fallback
    const downloadUrl = URL.createObjectURL(blob);
    chrome.runtime.sendMessage({
      action: 'downloadFallback',
      url: downloadUrl,
      filename: `linkedin_recording_${Date.now()}.webm`
    });

    return { success: false, error: error.message, savedLocally: true };
  }
}
