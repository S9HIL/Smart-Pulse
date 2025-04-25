/**
 * Dashboard JavaScript for Automation Hub
 * Handles the main dashboard functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Check services status
    checkServicesStatus();
    
    // Set up interval to check status
    setInterval(checkServicesStatus, 30000); // Every 30 seconds
    
    // Add event listeners to service cards
    document.querySelectorAll('.service-card').forEach(card => {
        card.addEventListener('click', function() {
            const serviceUrl = this.getAttribute('data-url');
            if (serviceUrl) {
                window.location.href = serviceUrl;
            }
        });
    });
});

/**
 * Check the status of all automation services
 */
function checkServicesStatus() {
    fetch('/status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateServiceStatus('whatsapp', data.services.whatsapp);
            } else {
                console.error('Error fetching service status:', data.message);
            }
        })
        .catch(error => {
            console.error('Error checking services status:', error);
        });
}

/**
 * Update the UI status for a service
 * @param {string} service - The service name
 * @param {object} status - The status object
 */
function updateServiceStatus(service, status) {
    const statusEl = document.querySelector(`.${service}-status`);
    const indicatorEl = document.querySelector(`.${service}-indicator`);
    const phoneEl = document.querySelector(`.${service}-phone`);
    
    if (!statusEl || !indicatorEl) return;
    
    // Remove all status classes
    indicatorEl.classList.remove('status-connected', 'status-disconnected', 'status-connecting');
    
    if (service === 'whatsapp') {
        if (status.running) {
            if (status.status === 'connected') {
                statusEl.textContent = 'Connected';
                indicatorEl.classList.add('status-connected');
                
                if (phoneEl && status.phone) {
                    phoneEl.textContent = status.phone;
                    phoneEl.parentElement.classList.remove('d-none');
                } else if (phoneEl) {
                    phoneEl.parentElement.classList.add('d-none');
                }
            } else if (status.status === 'connecting' || status.status === 'open') {
                statusEl.textContent = 'Connecting...';
                indicatorEl.classList.add('status-connecting');
                
                if (phoneEl) {
                    phoneEl.parentElement.classList.add('d-none');
                }
            } else {
                statusEl.textContent = 'Not Connected';
                indicatorEl.classList.add('status-disconnected');
                
                if (phoneEl) {
                    phoneEl.parentElement.classList.add('d-none');
                }
            }
        } else {
            statusEl.textContent = 'Service Offline';
            indicatorEl.classList.add('status-disconnected');
            
            if (phoneEl) {
                phoneEl.parentElement.classList.add('d-none');
            }
        }
    }
}

/**
 * Show loading spinner
 * @param {string} message - Optional message to display
 */
function showSpinner(message = 'Loading...') {
    // Remove existing spinner if any
    hideSpinner();
    
    // Create spinner overlay
    const overlay = document.createElement('div');
    overlay.className = 'spinner-overlay';
    overlay.id = 'spinner-overlay';
    
    const spinnerHtml = `
        <div class="spinner-container">
            <div class="spinner-border text-light" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p>${message}</p>
        </div>
    `;
    
    overlay.innerHTML = spinnerHtml;
    document.body.appendChild(overlay);
}

/**
 * Hide loading spinner
 */
function hideSpinner() {
    const existing = document.getElementById('spinner-overlay');
    if (existing) {
        existing.remove();
    }
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of toast (success, danger, warning, info)
 */
function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.id = toastId;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    const toastHtml = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toast.innerHTML = toastHtml;
    toastContainer.appendChild(toast);
    
    // Initialize and show the toast
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    
    bsToast.show();
    
    // Remove the toast after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}
