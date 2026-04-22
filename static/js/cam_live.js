let lastConnectionTime = 0;
let connectionFadeTimeout = null;

// Fetch camera error messages every 2 seconds.
async function updateCameraError() {
  try {
    const response = await fetch('/camera_error');
    if (response.ok) {
      const data = await response.json();
      const errorDisplay = document.getElementById('error-display');
      const connectionDisplay = document.getElementById('connection-display');
      const reconnectDisplay = document.getElementById('reconnect-display');

      if (data.error && data.error.trim() !== '') {
        errorDisplay.textContent = 'Error: ' + data.error;
        errorDisplay.classList.add('show');
      } else {
        errorDisplay.classList.remove('show');
      }

      // Handle reconnect message (show when camera not connected)
      if (data.reconnect_message && data.reconnect_message.trim() !== '') {
        reconnectDisplay.textContent = data.reconnect_message;
        reconnectDisplay.classList.add('show');
      } else {
        reconnectDisplay.classList.remove('show');
      }

      // Handle connection message: use timestamp to detect new events
      if (data.connection_message && data.connection_time && data.connection_time !== lastConnectionTime) {
        lastConnectionTime = data.connection_time;
        connectionDisplay.textContent = data.connection_message;
        connectionDisplay.classList.remove('fade-out');
        connectionDisplay.classList.add('show');

        // Clear previous timeout if any
        if (connectionFadeTimeout) {
          clearTimeout(connectionFadeTimeout);
        }

        // Fade out after 3 seconds
        connectionFadeTimeout = setTimeout(() => {
          connectionDisplay.classList.add('fade-out');
        }, 3000);
      }
    }
  } catch (e) {
    console.error('Failed to fetch camera error:', e);
  }
}

// Update on page load and then every 2 seconds.
updateCameraError();
setInterval(updateCameraError, 2000);
