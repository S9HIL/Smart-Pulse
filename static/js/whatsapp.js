/**
 * WhatsApp automation JavaScript
 * Handles WhatsApp connection and messaging functionality
 */

let qrCheckInterval = null;
let statusCheckInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize components
    initializeWhatsApp();
    
    // Add event listeners
    const connectBtn = document.getElementById('connect-whatsapp');
    if (connectBtn) {
        connectBtn.addEventListener('click', connectWhatsApp);
    }
    
    const disconnectBtn = document.getElementById('disconnect-whatsapp');
    if (disconnectBtn) {
        disconnectBtn.addEventListener('click', disconnectWhatsApp);
    }
    
    const pairingCodeBtn = document.getElementById('request-pairing-code');
    if (pairingCodeBtn) {
        pairingCodeBtn.addEventListener('click', requestPairingCode);
    }
    
    const sendMessageForm = document.getElementById('send-message-form');
    if (sendMessageForm) {
        sendMessageForm.addEventListener('submit', sendMessages);
    }
});

/**
 * Initialize WhatsApp components and check status
 */
function initializeWhatsApp() {
    checkWhatsAppStatus();
    
    // Start status check interval
    statusCheckInterval = setInterval(checkWhatsAppStatus, 5000);
}

/**
 * Check WhatsApp connection status
 */
function checkWhatsAppStatus(callback) {
    fetch('/whatsapp/status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateWhatsAppStatus(data);
                
                // If we have QR and it's not already visible, fetch and display it
                if (data.hasQR && document.getElementById('qr-display') && !document.getElementById('qr-display').src) {
                    fetchAndDisplayQR();
                }
                
                // If a callback was provided, call it with the status
                if (typeof callback === 'function') {
                    callback(data.status);
                }
            }
        })
        .catch(error => {
            console.error('Error checking WhatsApp status:', error);
            // Call callback with error if provided
            if (typeof callback === 'function') {
                callback('error');
            }
        });
}

/**
 * Update WhatsApp status UI
 * @param {object} data - Status data
 */
function updateWhatsAppStatus(data) {
    const statusEl = document.getElementById('whatsapp-status');
    const phoneEl = document.getElementById('whatsapp-phone');
    const connectBtn = document.getElementById('connect-whatsapp');
    const disconnectBtn = document.getElementById('disconnect-whatsapp');
    const qrSection = document.getElementById('qr-section');
    const pairingSection = document.getElementById('pairing-section');
    const messageForm = document.getElementById('message-form-section');
    
    if (statusEl) {
        // Update status indicator
        const statusClass = getStatusClass(data.status);
        statusEl.textContent = formatStatus(data.status);
        statusEl.className = `badge ${statusClass}`;
    }
    
    if (phoneEl) {
        // Update phone number display
        if (data.phoneNumber) {
            phoneEl.textContent = data.phoneNumber;
            phoneEl.parentElement.classList.remove('d-none');
        } else {
            phoneEl.parentElement.classList.add('d-none');
        }
    }
    
    // Update button states
    if (connectBtn && disconnectBtn) {
        if (data.status === 'connected') {
            connectBtn.classList.add('d-none');
            disconnectBtn.classList.remove('d-none');
        } else if (['disconnected', 'error'].includes(data.status)) {
            connectBtn.classList.remove('d-none');
            disconnectBtn.classList.add('d-none');
        }
    }
    
    // Show/hide sections based on status
    if (qrSection && pairingSection && messageForm) {
        if (data.status === 'connected') {
            qrSection.classList.add('d-none');
            pairingSection.classList.add('d-none');
            messageForm.classList.remove('d-none');
        } else if (['connecting', 'open'].includes(data.status)) {
            qrSection.classList.remove('d-none');
            pairingSection.classList.remove('d-none');
            messageForm.classList.add('d-none');
        } else {
            qrSection.classList.add('d-none');
            pairingSection.classList.add('d-none');
            messageForm.classList.add('d-none');
        }
    }
}

/**
 * Format status string for display
 * @param {string} status - Status code
 * @returns {string} Formatted status
 */
function formatStatus(status) {
    switch (status) {
        case 'connected': return 'Connected';
        case 'connecting': return 'Connecting';
        case 'open': return 'Waiting for scan';
        case 'disconnected': return 'Disconnected';
        case 'error': return 'Error';
        default: return status.charAt(0).toUpperCase() + status.slice(1);
    }
}

/**
 * Get Bootstrap badge class for status
 * @param {string} status - Status code
 * @returns {string} Bootstrap badge class
 */
function getStatusClass(status) {
    switch (status) {
        case 'connected': return 'bg-success';
        case 'connecting': 
        case 'open': return 'bg-warning';
        case 'disconnected': 
        case 'error': return 'bg-danger';
        default: return 'bg-secondary';
    }
}

/**
 * Connect to WhatsApp
 */
function connectWhatsApp() {
    const phoneNumber = document.getElementById('phone-number').value;
    
    if (!phoneNumber) {
        showToast('Please enter a phone number', 'warning');
        return;
    }
    
    // Check if we have a pairing code
    const pairingCodeEl = document.getElementById('pairing-code-display');
    const pairingCode = pairingCodeEl ? pairingCodeEl.textContent.trim() : '';
    const usePairingCode = pairingCode !== '';
    
    showSpinner('Connecting to WhatsApp...');
    
    const formData = new FormData();
    formData.append('phone_number', phoneNumber);
    formData.append('use_pairing_code', usePairingCode ? 'true' : 'false');
    if (usePairingCode) {
        formData.append('pairing_code', pairingCode);
    }
    
    fetch('/whatsapp/connect', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();
        
        if (data.success) {
            showToast('WhatsApp connection initiated', 'success');
            
            // If we're using a pairing code, it's a direct connection attempt
            if (usePairingCode) {
                showToast('Attempting to authenticate with pairing code. Please wait...', 'info');
                
                // Hide pairing code after use
                if (document.getElementById('pairing-code-container')) {
                    document.getElementById('pairing-code-container').classList.add('d-none');
                }
                
                // Start frequent status checks to detect connection
                let connectionAttempts = 0;
                const maxAttempts = 30;
                const connectionCheckInterval = setInterval(() => {
                    connectionAttempts++;
                    
                    // Check connection status more frequently
                    checkWhatsAppStatus((status) => {
                        if (status === 'connected') {
                            clearInterval(connectionCheckInterval);
                            showToast('Successfully connected to WhatsApp!', 'success');
                        } else if (connectionAttempts >= maxAttempts) {
                            clearInterval(connectionCheckInterval);
                            showToast('Connection attempt timed out. Please try again.', 'warning');
                        }
                    });
                }, 2000);
                
            } else {
                // Start checking for QR code for non-pairing code flow
                checkForQRCode();
            }
        } else {
            showToast(`Failed to connect: ${data.message}`, 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showToast(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Disconnect from WhatsApp
 */
function disconnectWhatsApp() {
    showSpinner('Disconnecting from WhatsApp...');
    
    fetch('/whatsapp/disconnect', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();
        
        if (data.success) {
            showToast('Disconnected from WhatsApp', 'info');
            
            // Reset QR code
            const qrImage = document.getElementById('qr-display');
            if (qrImage) {
                qrImage.src = '';
            }
            
            // Clear intervals
            clearInterval(qrCheckInterval);
            qrCheckInterval = null;
        } else {
            showToast(`Failed to disconnect: ${data.message}`, 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showToast(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Start checking for QR code
 */
function checkForQRCode() {
    // Clear existing interval
    if (qrCheckInterval) {
        clearInterval(qrCheckInterval);
    }
    
    // Fetch QR code immediately
    fetchAndDisplayQR();
    
    // Set interval to check for QR code
    qrCheckInterval = setInterval(fetchAndDisplayQR, 5000);
}

/**
 * Fetch and display QR code
 */
function fetchAndDisplayQR() {
    fetch('/whatsapp/qr_code')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.qrCode) {
                // Generate QR code image
                const qrImage = document.getElementById('qr-display');
                if (qrImage) {
                    qrImage.src = `data:image/png;base64,${data.qrCode}`;
                    document.getElementById('qr-container').classList.remove('d-none');
                    document.getElementById('qr-instructions').classList.remove('d-none');
                }
            }
        })
        .catch(error => {
            console.error('Error fetching QR code:', error);
        });
}

/**
 * Request a pairing code for WhatsApp
 */
function requestPairingCode() {
    const phoneNumber = document.getElementById('phone-number').value;
    
    if (!phoneNumber) {
        showToast('Please enter a phone number', 'warning');
        return;
    }
    
    showSpinner('Requesting pairing code...');
    
    const formData = new FormData();
    formData.append('phone_number', phoneNumber);
    
    fetch('/whatsapp/pairing_code', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();
        
        if (data.success && data.pairingCode) {
            // Display pairing code
            const pairingCodeEl = document.getElementById('pairing-code-display');
            pairingCodeEl.textContent = data.pairingCode;
            document.getElementById('pairing-code-container').classList.remove('d-none');
            
            showToast('Pairing code generated successfully', 'success');
        } else {
            showToast(`Failed to get pairing code: ${data.message}`, 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showToast(`Error: ${error.message}`, 'danger');
    });
}

/**
 * Send WhatsApp messages
 * @param {Event} event - Form submit event
 */
function sendMessages(event) {
    event.preventDefault();
    
    const form = event.target;
    const recipients = form.querySelector('#recipients').value;
    const messageInput = form.querySelector('#message');
    const messageFileInput = form.querySelector('#message-file');
    const delay = form.querySelector('#delay').value;
    
    // Validate inputs
    if (!recipients) {
        showToast('Please enter at least one recipient', 'warning');
        return;
    }
    
    if (!messageInput.value && (!messageFileInput.files || messageFileInput.files.length === 0)) {
        showToast('Please enter a message or upload a message file', 'warning');
        return;
    }
    
    showSpinner('Starting message sending...');
    
    const formData = new FormData(form);
    
    fetch('/whatsapp/send_messages', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideSpinner();
        
        if (data.success) {
            showToast('Message sending started', 'success');
            
            // Reset form
            form.reset();
            
            // Redirect to messages page
            window.location.href = `/whatsapp/messages/${data.batch_id}`;
        } else {
            showToast(`Failed to send messages: ${data.message}`, 'danger');
        }
    })
    .catch(error => {
        hideSpinner();
        showToast(`Error: ${error.message}`, 'danger');
    });
}
