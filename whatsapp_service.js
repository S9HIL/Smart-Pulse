/**
 * Simple WhatsApp Service
 * This service handles WhatsApp connections and message sending
 * 
 * Non-server version: Communicates only through stdin/stdout
 */

const { default: makeWASocket, useMultiFileAuthState, Browsers, DisconnectReason } = require('@whiskeysockets/baileys');
const { v4: uuidv4 } = require('uuid');
const path = require('path');
const pino = require('pino');
const fs = require('fs');
const QRCode = require('qrcode');

// Setup directories
const BASE_AUTH_DIR = path.join(process.cwd(), 'temp_auth_info');
if (!fs.existsSync(BASE_AUTH_DIR)) {
    fs.mkdirSync(BASE_AUTH_DIR, { recursive: true });
}

// For backward compatibility
const AUTH_DIR = path.join(process.cwd(), 'auth_info');
if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
}

// Create logger
const logger = pino({
    transport: {
        target: 'pino-pretty',
        options: {
            colorize: true,
        },
    },
});

// WhatsApp connection (using multiple sockets for multi-session)
let sock = null;
let activeSessions = {}; // Store active WhatsApp sessions by session ID
let currentSessionId = null; // Current active session ID
let connectionStatus = "disconnected";
let connectedPhoneNumber = null;
let qrData = null;
let pairingCode = null;

// Store for active tasks and message logs
const activeTasks = {};
const messageLog = [];

// Generate a unique session ID for each WhatsApp session
function generateSessionId(phoneNumber) {
    const timestamp = Date.now();
    return `session_${phoneNumber}_${timestamp}`;
}

// Initialize WhatsApp connection (supports multi-session)
async function connectToWhatsApp(sessionId = null, phoneNumber = null, forceNewSession = false) {
    logger.info(`Initializing WhatsApp connection ${sessionId ? `for session ${sessionId}` : ''}`);

    // Generate a new session ID if none provided
    if (!sessionId && phoneNumber) {
        sessionId = generateSessionId(phoneNumber);
        logger.info(`Generated new session ID: ${sessionId}`);
    }

    // Use default session directory if no session ID specified
    let authDir = AUTH_DIR;
    
    // If specific session ID is provided, use that directory
    if (sessionId) {
        authDir = path.join(BASE_AUTH_DIR, sessionId);
        if (!fs.existsSync(authDir)) {
            fs.mkdirSync(authDir, { recursive: true });
            logger.info(`Created new session directory: ${authDir}`);
        }
    }
    
    // Force new session by clearing any existing auth files if requested
    if (forceNewSession && fs.existsSync(authDir)) {
        logger.info(`Forcing new session, clearing existing auth files in ${authDir}`);
        const authFiles = fs.readdirSync(authDir);
        for (const file of authFiles) {
            try {
                fs.unlinkSync(path.join(authDir, file));
            } catch (err) {
                logger.warn(`Failed to delete file ${file}: ${err.message}`);
            }
        }
    }

    // Get auth state for this session
    const { state, saveCreds } = await useMultiFileAuthState(authDir);
    
    // Check if we have auth files that indicate a previous connection
    const authFiles = fs.readdirSync(authDir);
    const hasAuthInfo = authFiles.some(file => file.includes('creds') || file.includes('auth_info'));
    
    // Use existing auth files if available to maintain session
    if (hasAuthInfo && !forceNewSession) {
        logger.info(`Found existing WhatsApp auth files in ${authDir}, will try to re-use them`);
    }

    // Create socket for this session with improved configuration
    const newSock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        browser: Browsers.ubuntu('Chrome'),
        logger: pino({ level: 'warn' }), // Increase log level for debugging
        connectTimeoutMs: 60000, // Longer timeout for connection
        defaultQueryTimeoutMs: 60000, // Longer timeout for queries
        emitOwnEvents: true, // Make sure we emit our own events
        retryRequestDelayMs: 2000, // Wait 2 seconds before retrying requests
    });
    
    // If session ID is provided, store in active sessions
    if (sessionId) {
        activeSessions[sessionId] = {
            socket: newSock,
            status: 'connecting',
            phoneNumber: phoneNumber,
            authDir: authDir
        };
        currentSessionId = sessionId;
        
        // Set the global socket to this one
        sock = newSock;
    } else {
        // For backward compatibility, use as global socket
        sock = newSock;
    }

    // Save credentials when updated
    newSock.ev.on('creds.update', saveCreds);

    // Handle connection updates
    newSock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        // First, update the session-specific status if this is a session-based connection
        if (sessionId && activeSessions[sessionId]) {
            if (connection) {
                activeSessions[sessionId].status = connection;
            }
            
            if (qr) {
                activeSessions[sessionId].qrCode = qr;
            }
            
            if (connection === 'open' && newSock.user) {
                activeSessions[sessionId].phoneNumber = newSock.user.id.split(':')[0];
            }
        }
        
        // If this is the current active socket, update global status
        if (!sessionId || (sessionId && sessionId === currentSessionId)) {
            // QR code functionality removed as per requirements
            if (qr) {
                logger.info(`QR code received but not used (functionality removed)`);
            }

            if (connection) {
                logger.info(`Connection update: ${connection}`);
                connectionStatus = connection;
                
                // Send connection update to parent
                sendToParent({
                    type: 'connection_update',
                    status: connection,
                    phoneNumber: connectedPhoneNumber
                });
            }

            if (connection === 'close') {
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                
                logger.info(`Connection closed with status code: ${statusCode}`);
                
                if (shouldReconnect) {
                    logger.info('Attempting to reconnect...');
                    // Implement exponential backoff for reconnection attempts
                    setTimeout(() => {
                        logger.info('Reconnecting to WhatsApp...');
                        // Reconnect with the same session ID if available
                        connectToWhatsApp(sessionId, phoneNumber);
                    }, 3000); // Wait 3 seconds before reconnecting
                } else {
                    logger.info('Connection closed. You are logged out.');
                    
                    // Update global status if this is the current active socket
                    if (!sessionId || (sessionId && sessionId === currentSessionId)) {
                        connectionStatus = "disconnected";
                        connectedPhoneNumber = null;
                        qrData = null;
                        pairingCode = null;
                        
                        // Send connection update to parent
                        sendToParent({
                            type: 'connection_update',
                            status: 'disconnected',
                            phoneNumber: null
                        });
                    }
                    
                    // Remove from active sessions if this is a session-based connection
                    if (sessionId) {
                        delete activeSessions[sessionId];
                        
                        // If this was the current session, set to null
                        if (currentSessionId === sessionId) {
                            currentSessionId = null;
                            
                            // Find any other active session to use as current
                            const otherSessions = Object.keys(activeSessions);
                            if (otherSessions.length > 0) {
                                currentSessionId = otherSessions[0];
                                sock = activeSessions[currentSessionId].socket;
                                connectionStatus = activeSessions[currentSessionId].status;
                                connectedPhoneNumber = activeSessions[currentSessionId].phoneNumber;
                                logger.info(`Switched to session ${currentSessionId}`);
                            } else {
                                sock = null;
                            }
                        }
                    }
                    
                    // Clear any active tasks
                    for (const taskId in activeTasks) {
                        if (activeTasks[taskId].active) {
                            activeTasks[taskId].active = false;
                            activeTasks[taskId].status = 'error';
                            activeTasks[taskId].errors.push('WhatsApp disconnected');
                        }
                    }
                }
            } else if (connection === 'open') {
                logger.info('WhatsApp connection established!');
                
                // Update global status if this is the current active socket
                if (!sessionId || (sessionId && sessionId === currentSessionId)) {
                    connectionStatus = "connected";
                    
                    // Clear QR code and pairing code as they are no longer needed
                    qrData = null;
                    pairingCode = null;
                }
                
                // Get connected phone number
                if (newSock && newSock.user) {
                    const connectedPhone = newSock.user.id.split(':')[0];
                    
                    // Update session data
                    if (sessionId) {
                        activeSessions[sessionId].phoneNumber = connectedPhone;
                        activeSessions[sessionId].status = 'connected';
                    }
                    
                    // Update global phone number if this is the current active socket
                    if (!sessionId || (sessionId && sessionId === currentSessionId)) {
                        connectedPhoneNumber = connectedPhone;
                        
                        // Send connection update to parent
                        sendToParent({
                            type: 'connection_update',
                            status: 'connected',
                            phoneNumber: connectedPhone
                        });
                    }
                    
                    logger.info(`Connected with phone number: ${connectedPhone}`);
                }
            }
        }
    });

    // Return the socket
    return newSock;
}

// Request a pairing code
async function requestPairingCode(phoneNumber) {
    try {
        if (!phoneNumber) {
            throw new Error('Phone number is required');
        }

        // Parse phone number - ensure it includes country code
        let formattedPhone = phoneNumber.toString().replace(/[^0-9]/g, '');
        
        // For Indian numbers, if it's 10 digits, add '91' prefix
        // Valid Indian mobile numbers start with 6, 7, 8, or 9
        if (formattedPhone.length === 10 && /^[6-9]/.test(formattedPhone)) {
            formattedPhone = '91' + formattedPhone;
            logger.info(`Added country code to Indian number: ${formattedPhone}`);
        }
        
        logger.info(`Requesting pairing code for phone: ${formattedPhone}`);

        // Generate a session ID for this phone number
        const sessionId = generateSessionId(formattedPhone);
        
        // Always initialize a new connection when requesting pairing code
        // Force new session to prevent auth_info file conflicts
        await connectToWhatsApp(sessionId, formattedPhone, true);
        
        // Wait for the connection to be ready - increased wait time
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Add retry mechanism for improved reliability
        let retries = 5; // Increased retries
        let success = false;
        let lastError = null;
        let code = null;
        
        while (retries > 0 && !success) {
            try {
                if (!sock) {
                    throw new Error('WhatsApp socket not initialized');
                }

                // Check if socket has the requestPairingCode method
                if (typeof sock.requestPairingCode !== 'function') {
                    throw new Error('requestPairingCode method not available in current WhatsApp client');
                }

                // Request pairing code from the current socket
                logger.info(`Requesting pairing code for ${formattedPhone}, attempt ${6-retries}`);
                code = await sock.requestPairingCode(formattedPhone);
                
                if (code) {
                    success = true;
                    logger.info(`Successfully received pairing code: ${code}`);
                } else {
                    throw new Error('No pairing code returned');
                }
            } catch (err) {
                lastError = err;
                logger.warn(`Retry requesting pairing code, ${retries} attempts left: ${err.message}`);
                retries--;
                // Wait longer between retries for pairing code
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                // On failure, try to refresh the connection
                if (retries === 2) {
                    logger.info('Refreshing WhatsApp connection before retry');
                    await connectToWhatsApp(sessionId, formattedPhone, true);
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }
        }
        
        if (!success) {
            throw new Error(`Failed to get pairing code after multiple attempts: ${lastError?.message || 'Unknown error'}`);
        }
        
        logger.info(`Pairing code received: ${code}`);
        pairingCode = code;
        
        // Send event about pairing code
        sendToParent({
            type: 'pairing_code',
            code: code
        });
        
        return code;
    } catch (error) {
        logger.error(`Error requesting pairing code: ${error.message}`);
        throw error;
    }
}

// Logout from WhatsApp
async function logoutWhatsApp() {
    try {
        if (!sock) {
            logger.warn('Cannot logout: Not connected to WhatsApp');
            return { success: false, message: 'Not connected to WhatsApp' };
        }
        
        logger.info('Logging out from WhatsApp...');
        
        // First stop any active tasks
        for (const taskId in activeTasks) {
            if (activeTasks[taskId].active) {
                stopTask(taskId);
            }
        }
        
        // Logout from WhatsApp
        await sock.logout();
        
        // Clear the connection
        connectionStatus = 'disconnected';
        connectedPhoneNumber = null;
        qrData = null;
        pairingCode = null;
        
        // If we were using a session-based connection, clear it
        if (currentSessionId) {
            delete activeSessions[currentSessionId];
            currentSessionId = null;
        }
        
        logger.info('Successfully logged out from WhatsApp');
        
        return { success: true, message: 'Successfully logged out from WhatsApp' };
    } catch (error) {
        logger.error(`Error logging out from WhatsApp: ${error.message}`);
        return { success: false, message: error.message };
    }
}

// Send a message to a WhatsApp user
async function sendMessage(target, message, isGroup = false, options = {}) {
    try {
        if (!sock) {
            throw new Error('Not connected to WhatsApp');
        }
        
        if (connectionStatus !== 'connected') {
            throw new Error(`Cannot send message, connection status: ${connectionStatus}`);
        }
        
        // Process the target number if it's a phone number
        let recipient = target;
        if (!isGroup) {
            // Clean phone number
            recipient = target.toString().replace(/[^0-9]/g, '');
            
            // Add '@s.whatsapp.net' suffix for individual users
            const waJid = `${recipient}@s.whatsapp.net`;
            recipient = waJid;
        } else {
            // Add '@g.us' suffix for groups if not already present
            if (!recipient.endsWith('@g.us')) {
                recipient = `${recipient}@g.us`;
            }
        }
        
        // Check if we're actually connected
        if (!sock.user) {
            throw new Error('WhatsApp connection not fully established');
        }
        
        // Send the message
        const sentMessage = await sock.sendMessage(recipient, { text: message });
        
        // Log the sent message
        const logEntry = {
            timestamp: new Date().toISOString(),
            to: target,
            message: message.substring(0, 50) + (message.length > 50 ? '...' : ''),
            success: true,
            messageId: sentMessage.key.id
        };
        
        messageLog.push(logEntry);
        
        logger.info(`Message sent to ${target}: ${message.substring(0, 30)}${message.length > 30 ? '...' : ''}`);
        
        return {
            success: true,
            id: sentMessage.key.id,
            message: 'Message sent successfully'
        };
    } catch (error) {
        logger.error(`Error sending message to ${target}: ${error.message}`);
        
        // Log the failed message
        const logEntry = {
            timestamp: new Date().toISOString(),
            to: target,
            message: message ? message.substring(0, 50) + (message.length > 50 ? '...' : '') : 'Empty message',
            success: false,
            error: error.message
        };
        
        messageLog.push(logEntry);
        
        throw error;
    }
}

// Function to stop a task
function stopTask(taskId) {
    if (!activeTasks[taskId]) {
        logger.warn(`Cannot stop task ${taskId}: Not found`);
        return { success: false, message: `Task ${taskId} not found` };
    }
    
    logger.info(`Stopping task ${taskId}`);
    
    activeTasks[taskId].active = false;
    activeTasks[taskId].status = 'stopped';
    
    return {
        success: true,
        taskId: taskId,
        message: `Task ${taskId} stopped`
    };
}

// Function to send multiple messages to multiple recipients
async function sendBulkMessages(taskId, targets, messages, delay = 10, loopMode = false, maxLoops = 0) {
    try {
        if (!sock) {
            throw new Error('Not connected to WhatsApp');
        }
        
        if (connectionStatus !== 'connected') {
            throw new Error(`Cannot send messages, connection status: ${connectionStatus}`);
        }
        
        // Validate targets
        if (!targets || !Array.isArray(targets) || targets.length === 0) {
            throw new Error('No valid targets provided');
        }
        
        // Validate messages
        if (!messages || !Array.isArray(messages) || messages.length === 0) {
            throw new Error('No valid messages provided');
        }
        
        // Normalize delay (minimum 1 second)
        const delaySeconds = Math.max(1, Number(delay) || 10);
        
        // Generate task ID if not provided
        const id = taskId || uuidv4();
        
        // Create task object to track progress
        const task = {
            id: id,
            targets: [...targets],
            messages: [...messages],
            delay: delaySeconds,
            active: true,
            status: 'running',
            total: targets.length * messages.length,
            baseTotal: targets.length * messages.length, // Keep original total for loop tracking
            sent: 0,
            failed: 0,
            remaining: targets.length * messages.length,
            startTime: new Date(),
            lastMessageTime: null,
            errors: [],
            loopMode: loopMode === true,
            maxLoops: Number(maxLoops) || 0,
            currentLoop: 1
        };
        
        // Store task
        activeTasks[id] = task;
        
        logger.info(`Starting bulk message task ${id}: ${targets.length} targets, ${messages.length} messages, delay: ${delaySeconds}s, loop mode: ${loopMode}, max loops: ${maxLoops}`);
        
        // Start message sending in background
        sendMessages(id);
        
        return {
            success: true,
            taskId: id,
            message: `Bulk message task started with ID: ${id}`
        };
    } catch (error) {
        logger.error(`Error starting bulk messages: ${error.message}`);
        throw error;
    }
    
    // Function to send messages in background
    async function sendMessages(taskId) {
        const task = activeTasks[taskId];
        if (!task) return;
        
        // Log start of batch
        sendToParent({
            type: 'message_log',
            batchId: taskId,
            status: 'started',
            message: `Started sending ${task.total} messages to ${task.targets.length} recipients`
        });
        
        let targetIndex = 0;
        let messageIndex = 0;
        
        // Continue as long as the task is active
        while (task.active) {
            try {
                // Check if we need to restart the loop
                if (messageIndex >= task.messages.length) {
                    messageIndex = 0;
                    targetIndex++;
                }
                
                // Check if we've gone through all targets
                if (targetIndex >= task.targets.length) {
                    // If we're not in loop mode or we've reached max loops, we're done
                    if (!task.loopMode || (task.maxLoops > 0 && task.currentLoop >= task.maxLoops)) {
                        logger.info(`Task ${taskId} completed: All messages sent`);
                        task.active = false;
                        task.status = 'completed';
                        
                        // Log completion
                        sendToParent({
                            type: 'message_log',
                            batchId: taskId,
                            status: 'completed',
                            message: `Completed sending ${task.sent} messages (${task.failed} failed)`
                        });
                        
                        break;
                    }
                    
                    // Otherwise, start a new loop
                    targetIndex = 0;
                    messageIndex = 0;
                    task.currentLoop++;
                    
                    logger.info(`Task ${taskId} starting loop ${task.currentLoop}${task.maxLoops > 0 ? ` of ${task.maxLoops}` : ''}`);
                    
                    // Log new loop
                    sendToParent({
                        type: 'message_log',
                        batchId: taskId,
                        status: 'loop',
                        message: `Starting loop ${task.currentLoop}${task.maxLoops > 0 ? ` of ${task.maxLoops}` : ''}`
                    });
                }
                
                // Get current target and message
                const target = task.targets[targetIndex];
                const message = task.messages[messageIndex];
                
                // Send the message
                try {
                    await sendMessage(target, message);
                    task.sent++;
                    task.lastMessageTime = new Date();
                    
                    // Log success
                    sendToParent({
                        type: 'message_log',
                        batchId: taskId,
                        status: 'sent',
                        message: `Sent message to ${target}`,
                        target: target
                    });
                    
                } catch (err) {
                    task.failed++;
                    task.errors.push(`Error sending to ${target}: ${err.message}`);
                    
                    logger.error(`Task ${taskId}: Error sending to ${target}: ${err.message}`);
                    
                    // Log failure
                    sendToParent({
                        type: 'message_log',
                        batchId: taskId,
                        status: 'error',
                        message: `Failed to send to ${target}: ${err.message}`,
                        target: target
                    });
                }
                
                // Move to next message
                messageIndex++;
                
                // Calculate remaining messages for this loop
                const loopTotal = task.baseTotal;
                const loopSent = (targetIndex * task.messages.length) + messageIndex;
                task.remaining = loopTotal - loopSent;
                
                // Delay before next message
                await new Promise(resolve => setTimeout(resolve, task.delay * 1000));
                
                // Check if task is still active
                if (!task.active) {
                    logger.info(`Task ${taskId} stopped manually`);
                    break;
                }
                
            } catch (error) {
                logger.error(`Task ${taskId} error: ${error.message}`);
                task.errors.push(`General error: ${error.message}`);
                
                // Log error
                sendToParent({
                    type: 'message_log',
                    batchId: taskId,
                    status: 'error',
                    message: `General error: ${error.message}`
                });
                
                // Wait a bit longer after an error
                await new Promise(resolve => setTimeout(resolve, (task.delay + 5) * 1000));
            }
        }
    }
}

// Function to send data back to the parent process (Python)
function sendToParent(data) {
    if (typeof data === 'object') {
        console.log(JSON.stringify(data));
    } else {
        console.log(data);
    }
}

// Process commands from stdin (from Python)
async function processStdin() {
    process.stdin.setEncoding('utf8');
    
    process.stdin.on('data', async (data) => {
        try {
            const lines = data.trim().split('\n');
            
            for (const line of lines) {
                if (!line.trim()) continue;
                
                let command;
                try {
                    command = JSON.parse(line);
                } catch (e) {
                    logger.error(`Invalid JSON command: ${line}`);
                    continue;
                }
                
                logger.info(`Received command: ${command.command}`);
                
                if (command.command === 'connect') {
                    // Connect to WhatsApp
                    const sessionId = command.sessionId || null;
                    const phoneNumber = command.phoneNumber || null;
                    const forceNew = command.forceNew || false;
                    const usePairingCode = command.usePairingCode || false;
                    const pairingCode = command.pairingCode || null;
                    
                    logger.info(`Connecting to WhatsApp with phone: ${phoneNumber}, usePairingCode: ${usePairingCode}`);
                    
                    if (usePairingCode && pairingCode) {
                        const formattedPhone = phoneNumber.toString().replace(/[^0-9]/g, '');
                        
                        // Generate a unique session ID for this connection
                        const newSessionId = sessionId || generateSessionId(formattedPhone);
                        
                        // First we need to get the session ready for pairing code by creating a fresh connection
                        logger.info(`Initializing fresh connection for pairing code authentication`);
                        await connectToWhatsApp(newSessionId, formattedPhone, true);
                        
                        // Then we manually enter the pairing code
                        logger.info(`Using pairing code: ${pairingCode} for connection with phone: ${formattedPhone}`);
                        
                        if (sock && sock.authState && sock.authState.creds && sock.authState.creds.me) {
                            logger.info("Already authenticated, no need for pairing code");
                            // Even though we're already authenticated, ensure the connected status is properly set
                            connectionStatus = "connected";
                            
                            // Get connected phone number if available
                            if (sock.user) {
                                connectedPhoneNumber = sock.user.id.split(':')[0];
                            }
                        } else {
                            try {
                                // Wait to ensure connection is ready for pairing code - increased wait time
                                await new Promise(resolve => setTimeout(resolve, 5000));
                                
                                // Sometimes we need to wait for the connection to generate a QR or be ready for pairing
                                await sock.waitForConnectionUpdate(state => {
                                    logger.info(`Connection update received: ${JSON.stringify(state)}`);
                                    return state.connection === 'open' || Boolean(state.qr);
                                });
                                
                                // If socket has registerNewParticipant function (newer version)
                                if (sock && typeof sock.registerNewParticipant === 'function') {
                                    logger.info(`Registering with pairing code using modern method for ${formattedPhone}`);
                                    try {
                                        // Use the correct method for newer versions of the library
                                        await sock.registerNewParticipant({ phone: formattedPhone, pairingCode });
                                        logger.info("Successfully registered with pairing code");
                                    } catch (pairingError) {
                                        logger.error(`Error registering with pairing code: ${pairingError.message}`);
                                        // Try alternate method as fallback
                                        if (sock.authState && sock.authState.creds) {
                                            logger.info("Trying alternate pairing method");
                                            sock.ev.emit('pairing-code', { pairingCode });
                                        }
                                    }
                                } 
                                // Fallback for older versions
                                else if (sock.authState && sock.authState.creds) {
                                    logger.info("Using legacy pairing code method");
                                    
                                    // Try direct method first if available
                                    if (typeof sock.registrationPairingCode === 'function') {
                                        await sock.registrationPairingCode(formattedPhone, pairingCode);
                                    } else {
                                        // Use event method as last resort
                                        sock.ev.emit('pairing-code', { pairingCode, phoneNumber: formattedPhone });
                                    }
                                }
                                
                                // Wait for authentication to complete
                                logger.info("Waiting for authentication to complete...");
                                await new Promise(resolve => setTimeout(resolve, 5000));
                                
                                // Log the current connection status
                                logger.info(`Current connection status after pairing: ${connectionStatus}`);
                            } catch (err) {
                                logger.error(`Error using pairing code: ${err.message}`);
                            }
                        }
                    } else {
                        // Regular connection without pairing code
                        await connectToWhatsApp(sessionId, phoneNumber, forceNew);
                    }
                    
                    // Send back status
                    sendToParent({
                        type: 'connection_update',
                        status: connectionStatus,
                        phoneNumber: connectedPhoneNumber
                    });
                }
                else if (command.command === 'status') {
                    // Get connection status
                    sendToParent({
                        type: 'connection_update',
                        status: connectionStatus,
                        phoneNumber: connectedPhoneNumber
                    });
                }
                else if (command.command === 'logout') {
                    // Logout from WhatsApp
                    if (sock) {
                        await logoutWhatsApp();
                    }
                    
                    sendToParent({
                        type: 'connection_update',
                        status: 'disconnected'
                    });
                }
                else if (command.command === 'request_pairing_code') {
                    // Request pairing code
                    const phoneNumber = command.phoneNumber;
                    
                    if (!phoneNumber) {
                        sendToParent({
                            type: 'pairing_code_error',
                            message: 'Phone number is required'
                        });
                        continue;
                    }
                    
                    try {
                        const code = await requestPairingCode(phoneNumber);
                        
                        if (code) {
                            pairingCode = code;
                            sendToParent({
                                type: 'pairing_code',
                                code: code
                            });
                        } else {
                            sendToParent({
                                type: 'pairing_code_error',
                                message: 'Failed to get pairing code'
                            });
                        }
                    } catch (error) {
                        logger.error(`Error requesting pairing code: ${error.message}`);
                        sendToParent({
                            type: 'pairing_code_error',
                            message: error.message
                        });
                    }
                }
                else if (command.command === 'send_messages') {
                    // Send batch of messages
                    const batchId = command.batchId || uuidv4();
                    const recipients = command.recipients || [];
                    const messages = command.messages || [];
                    const delay = command.delay || 10;
                    
                    if (!recipients.length || !messages.length) {
                        sendToParent({
                            type: 'message_log',
                            batchId: batchId,
                            status: 'error',
                            message: 'Recipients and messages are required'
                        });
                        continue;
                    }
                    
                    // Send messages in background
                    sendBulkMessages(batchId, recipients, messages, delay, false, 1)
                        .then(result => {
                            logger.info(`Batch ${batchId} started: ${JSON.stringify(result)}`);
                        })
                        .catch(error => {
                            logger.error(`Error starting batch ${batchId}: ${error.message}`);
                        });
                    
                    // Send confirmation
                    sendToParent({
                        type: 'message_log',
                        batchId: batchId,
                        status: 'started',
                        message: 'Message sending started'
                    });
                }
                else if (command.command === 'stop_batch') {
                    // Stop a batch of messages
                    const batchId = command.batchId;
                    
                    if (!batchId || !activeTasks[batchId]) {
                        sendToParent({
                            type: 'message_log',
                            status: 'error',
                            message: 'Invalid batch ID'
                        });
                        continue;
                    }
                    
                    stopTask(batchId);
                    
                    sendToParent({
                        type: 'message_log',
                        batchId: batchId,
                        status: 'stopped',
                        message: 'Batch stopped'
                    });
                }
            }
        } catch (error) {
            logger.error(`Error processing command: ${error.message}`);
        }
    });
    
    process.stdin.on('end', () => {
        logger.info('stdin stream ended');
        process.exit(0);
    });
}

// Handle process exit
process.on('SIGINT', async () => {
    logger.info('Shutting down gracefully...');
    
    // Stop all active tasks
    for (const taskId in activeTasks) {
        if (activeTasks[taskId].active) {
            stopTask(taskId);
        }
    }
    
    // Logout from WhatsApp
    if (sock) {
        await logoutWhatsApp();
    }
    
    process.exit(0);
});

// Initialize
logger.info('WhatsApp service starting in stdin/stdout mode (non-server)');
processStdin();

// Initialize connection
connectToWhatsApp()
    .then(() => {
        logger.info('Initial WhatsApp connection attempt completed');
    })
    .catch(err => {
        logger.error(`Initial WhatsApp connection error: ${err.message}`);
    });