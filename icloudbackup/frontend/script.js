// Status polling interval (in milliseconds)
const STATUS_POLL_INTERVAL = 2000;
let statusPollingActive = true;

// Translation objects
const translations = {
    en: {
        title: 'iCloud Backup',
        runningTitle: 'Everything is running',
        runningMessage: 'The iCloud Backup service is active and monitoring your backups.',
        serviceActive: 'Service active',
        twoFactorTitle: 'Two-Factor Authentication',
        twoFactorMessage: 'Please enter the 6-digit verification code you received on your Apple device.',
        codeLabel: 'Verification Code:',
        verifyButton: 'Verify',
        sendingButton: 'Sending...',
        loadingStatus: 'Loading status...',
        errorExact6Digits: 'Please enter exactly 6 digits.',
        verificationSuccess: 'Verification successful!',
        verificationFailed: 'Verification failed. Please try again.',
        sendError: 'Send error: ',
        serverError: 'Server error: '
    },
    de: {
        title: 'iCloud Backup',
        runningTitle: 'Alles läuft',
        runningMessage: 'Der iCloud Backup Service ist aktiv und überwacht Ihre Backups.',
        serviceActive: 'Service aktiv',
        twoFactorTitle: 'Zwei-Faktor-Authentifizierung',
        twoFactorMessage: 'Bitte geben Sie den 6-stelligen Verifizierungscode ein, den Sie auf Ihrem Apple-Gerät erhalten haben.',
        codeLabel: 'Verifizierungscode:',
        verifyButton: 'Verifizieren',
        sendingButton: 'Wird gesendet...',
        loadingStatus: 'Lade Status...',
        errorExact6Digits: 'Bitte geben Sie genau 6 Ziffern ein.',
        verificationSuccess: 'Verifizierung erfolgreich!',
        verificationFailed: 'Verifizierung fehlgeschlagen. Bitte versuchen Sie es erneut.',
        sendError: 'Fehler beim Senden: ',
        serverError: 'Server-Fehler: '
    }
};

// Detect browser language
function detectLanguage() {
    const browserLang = navigator.language || navigator.userLanguage;
    const langCode = browserLang.toLowerCase().split('-')[0];
    
    // Support German and English, default to English
    return translations[langCode] ? langCode : 'en';
}

// Current language
let currentLang = detectLanguage();

// Get translation
function t(key) {
    return translations[currentLang][key] || translations['en'][key] || key;
}

// Update all text elements with translations
function updateLanguage() {
    document.title = t('title');
    document.getElementById('mainTitle').textContent = t('title');
    document.getElementById('runningTitle').textContent = t('runningTitle');
    document.getElementById('runningMessage').textContent = t('runningMessage');
    document.getElementById('serviceActiveText').textContent = t('serviceActive');
    document.getElementById('twoFactorTitle').textContent = t('twoFactorTitle');
    document.getElementById('twoFactorMessage').textContent = t('twoFactorMessage');
    document.getElementById('codeLabel').textContent = t('codeLabel');
    document.getElementById('submitBtn').textContent = t('verifyButton');
    document.getElementById('loadingText').textContent = t('loadingStatus');
}

// Check current status from backend
async function checkStatus() {
    try {
        const response = await fetch('status');
        if (!response.ok) {
            throw new Error('Status check failed');
        }
        const data = await response.json();
        updateView(data);
    } catch (error) {
        console.error('Error checking status:', error);
        // Keep showing current view on error
    }
}

// Update the displayed view based on status
function updateView(status) {
    const loadingView = document.getElementById('loadingStatus');
    const runningView = document.getElementById('runningStatus');
    const verificationView = document.getElementById('verificationView');
    
    // Hide loading screen
    loadingView.style.display = 'none';
    
    if (status.requires_2fa) {
        // Show 2FA input
        runningView.style.display = 'none';
        verificationView.style.display = 'block';
        
        // Auto-focus on code input
        const codeInput = document.getElementById('code');
        if (codeInput && document.activeElement !== codeInput) {
            codeInput.focus();
        }
    } else {
        // Show running status
        verificationView.style.display = 'none';
        runningView.style.display = 'block';
    }
}

// Submit verification code
function submitForm() {
    const codeInput = document.getElementById('code');
    const messageDiv = document.getElementById('message');
    const submitButton = document.getElementById('submitBtn');
    
    // Clean the input - remove all spaces, dashes and other non-digits
    const cleanCode = codeInput.value.trim().replace(/\D/g, '');
    
    // Hide any previous message
    messageDiv.style.display = 'none';
    
    // Validate: must be exactly 6 digits
    if (cleanCode.length !== 6) {
        messageDiv.className = 'error-message';
        messageDiv.textContent = t('errorExact6Digits');
        messageDiv.style.display = 'block';
        return;
    }
    
    // Disable button during submission
    submitButton.disabled = true;
    submitButton.textContent = t('sendingButton');
    
    // Send the code
    const formData = new FormData();
    formData.append('code', cleanCode);
    
    // Use relative path for Ingress compatibility
    const sendCodeUrl = 'send_code';
    
    console.log('Sending code to:', sendCodeUrl, 'from', window.location.href);
    
    fetch(sendCodeUrl, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(t('serverError') + response.status);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            messageDiv.className = 'success-message';
            messageDiv.textContent = t('verificationSuccess');
            codeInput.value = '';
            
            // Re-check status after successful verification
            setTimeout(checkStatus, 1000);
        } else {
            messageDiv.className = 'error-message';
            messageDiv.textContent = t('verificationFailed');
            submitButton.disabled = false;
            submitButton.textContent = t('verifyButton');
        }
        messageDiv.style.display = 'block';
    })
    .catch((error) => {
        messageDiv.className = 'error-message';
        messageDiv.textContent = t('sendError') + error.message;
        messageDiv.style.display = 'block';
        submitButton.disabled = false;
        submitButton.textContent = t('verifyButton');
    });
}

// Start status polling
function startStatusPolling() {
    checkStatus(); // Initial check
    
    // Poll for status updates
    setInterval(() => {
        if (statusPollingActive) {
            checkStatus();
        }
    }, STATUS_POLL_INTERVAL);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Set language
    updateLanguage();
    
    // Start status polling
    startStatusPolling();
    
    // Allow Enter key to submit
    const codeInput = document.getElementById('code');
    if (codeInput) {
        codeInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                submitForm();
            }
        });
    }
});
