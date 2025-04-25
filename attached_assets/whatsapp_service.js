/**
 * Simple WhatsApp Service
 * This service handles WhatsApp connections and message sending
 */

const { default: makeWASocket, useMultiFileAuthState, Browsers, makeInMemoryStore, DisconnectReason } = require('@whiskeysockets/baileys');
const { v4: uuidv4 } = require('uuid');
const express = require('express');
const cors = require('cors');
const path = require('path');
const pino = require('pino');
const fs = require('fs');
const QRCode = require('qrcode');

// Create express app
const app = express();
const port = process.env.PORT || 8000;

// Configure middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cors()); // Enable CORS for all routes

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

    // Create socket for this session
    const newSock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        browser: Browsers.ubuntu('Chrome'),
        logger: pino({ level: 'silent' }),
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
    newSock.ev.on('connection.update', (update) => {
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
            if (qr) {
                qrData = qr;
                logger.info(`QR code received: ${qr.slice(0, 20)}...`);
            }

            if (connection) {
                logger.info(`Connection update: ${connection}`);
                connectionStatus = connection;
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
        
        // Wait for the connection to be ready
        await new Promise(resolve => setTimeout(resolve, 1000));

        // Add retry mechanism for improved reliability
        let retries = 5; // Increased retries
        let success = false;
        let lastError = null;
        let code = null;
        
        while (retries > 0 && !success) {
            try {
                // Request pairing code from the current socket (will be the sessionId one)
                code = await sock.requestPairingCode(formattedPhone);
                if (code) {
                    success = true;
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
                    await new Promise(resolve => setTimeout(resolve, 2000));
                }
            }
        }
        
        if (!success) {
            throw lastError || new Error('Failed to get pairing code after retries');
        }
        
        logger.info(`Pairing code generated: ${code}`);
        
        pairingCode = code;
        
        return {
            success: true,
            pairingCode: code,
            check_connection: true,
            sessionId: sessionId
        };
    } catch (error) {
        logger.error(`Error generating pairing code: ${error.message}`);
        return {
            success: false,
            message: error.message
        };
    }
}

// Store message logs
function addMessageLog(to, message, success, errorMsg = null) {
    // Add message to log with timestamp
    messageLog.push({
        timestamp: new Date(),
        to: to,
        message: message,
        success: success,
        error: errorMsg
    });
    
    // Keep log size manageable - keep only the latest 1000 messages
    if (messageLog.length > 1000) {
        messageLog.shift(); // Remove oldest entry
    }
}

// Send a message to a specific number
async function sendMessage(to, message) {
    try {
        if (!sock) {
            throw new Error('WhatsApp connection not established');
        }

        if (connectionStatus !== 'connected') {
            throw new Error('WhatsApp not connected');
        }

        // Parse phone number
        let recipient = to.toString().replace(/[^0-9]/g, '');
        
        // For Indian numbers, if it's 10 digits, add '91' prefix
        // Valid Indian mobile numbers start with 6, 7, 8, or 9
        if (recipient.length === 10 && /^[6-9]/.test(recipient)) {
            recipient = '91' + recipient;
            logger.info(`Added country code to Indian recipient: ${recipient}`);
        }
        
        // Format the phone number with WhatsApp jid suffix
        const waJid = `${recipient}@s.whatsapp.net`;

        // Add retry mechanism for improved reliability
        let retries = 3;
        let success = false;
        let lastError = null;
        
        while (retries > 0 && !success) {
            try {
                // Send the message
                await sock.sendMessage(waJid, { text: message });
                success = true;
            } catch (err) {
                lastError = err;
                logger.warn(`Retry sending to ${recipient}, ${retries} attempts left: ${err.message}`);
                retries--;
                // Wait a short time before retrying
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }
        
        if (!success) {
            const errorMsg = lastError ? lastError.message : 'Failed to send message after retries';
            addMessageLog(recipient, message, false, errorMsg);
            throw lastError || new Error('Failed to send message after retries');
        }
        
        logger.info(`Message sent to ${recipient}`);
        addMessageLog(recipient, message, true);
        
        return {
            success: true,
            to: recipient,
            message: 'Message sent successfully'
        };
    } catch (error) {
        logger.error(`Error sending message to ${to}: ${error.message}`);
        addMessageLog(to, message, false, error.message);
        return {
            success: false,
            to: to,
            message: error.message
        };
    }
}

// Send multiple messages to multiple recipients
async function sendBulkMessages(taskId, targets, messages, delay = 5, loopMode = false, maxLoops = 0) {
    try {
        if (!sock) {
            throw new Error('WhatsApp connection not established');
        }

        if (connectionStatus !== 'connected') {
            throw new Error('WhatsApp not connected');
        }

        // Calculate total messages
        const baseTotal = targets.length * messages.length;
        let totalMessages = baseTotal;
        
        // If loop mode is enabled and maxLoops is specified (not 0), multiply by maxLoops
        // If loop mode is enabled and maxLoops is 0 (infinite), we'll still show the total for one loop
        if (loopMode && maxLoops > 0) {
            totalMessages = baseTotal * maxLoops;
        }
        
        // Create task data
        activeTasks[taskId] = {
            id: taskId,
            status: 'running',
            total: totalMessages,
            sent: 0,
            failed: 0,
            remaining: totalMessages,
            targets: targets,
            messages: messages,
            delay: delay,
            active: true,
            errors: [],
            loopMode: loopMode,
            currentLoop: 1,
            maxLoops: maxLoops,
            baseTotal: baseTotal
        };

        // Start sending messages in a separate thread
        sendMessagesInBackground(taskId);
        
        return {
            success: true,
            taskId: taskId,
            message: `Started sending ${totalMessages} messages with task ID ${taskId}${loopMode ? ' in loop mode' : ''}`
        };
    } catch (error) {
        logger.error(`Error starting bulk messages: ${error.message}`);
        
        // Update task status if it exists
        if (activeTasks[taskId]) {
            activeTasks[taskId].status = 'error';
            activeTasks[taskId].active = false;
            activeTasks[taskId].errors.push(error.message);
        }
        
        return {
            success: false,
            taskId: taskId,
            message: error.message
        };
    }
}

// Send messages in background
async function sendMessagesInBackground(taskId) {
    try {
        const task = activeTasks[taskId];
        if (!task) {
            logger.error(`Task ${taskId} not found`);
            return;
        }

        const { targets, messages, delay, loopMode, maxLoops } = task;
        
        // Log start of task
        logger.info(`Starting to send messages for task ${taskId}`);
        logger.info(`Number of targets: ${targets.length}, Number of messages: ${messages.length}`);
        logger.info(`Delay between messages: ${delay} seconds, Loop mode: ${loopMode}, Max loops: ${maxLoops}`);
        
        // Handle looping
        let continueLooping = true;
        while (continueLooping) {
            // Send messages one by one - first loop through ALL targets for EACH message
            for (const message of messages) {
                if (!task.active) {
                    logger.info(`Task ${taskId} stopped`);
                    continueLooping = false;
                    break;
                }
                
                logger.info(`Processing message: "${message.substring(0, 30)}${message.length > 30 ? '...' : ''}"`);
                
                for (const target of targets) {
                    if (!task.active) {
                        logger.info(`Task ${taskId} stopped`);
                        continueLooping = false;
                        break;
                    }
                    
                    // Log the current message being sent
                    logger.info(`Sending message to ${target}: "${message.substring(0, 30)}${message.length > 30 ? '...' : ''}"`);
                    
                    // Send message
                    const result = await sendMessage(target, message);
                    
                    // Update task status
                    if (result.success) {
                        task.sent++;
                        logger.info(`Message successfully sent to ${target}`);
                    } else {
                        task.failed++;
                        task.errors.push(`Error sending to ${target}: ${result.message}`);
                        logger.error(`Error sending to ${target}: ${result.message}`);
                    }
                    
                    task.remaining--;
                    
                    // Update progress
                    let progress;
                    
                    // For infinite looping, show progress within the current loop
                    if (loopMode && maxLoops === 0) {
                        const currentLoopTotal = targets.length * messages.length;
                        const currentLoopProgress = (task.sent + task.failed) % currentLoopTotal;
                        progress = Math.round((currentLoopProgress / currentLoopTotal) * 100);
                        logger.info(`Task ${taskId} progress: ${progress}% (${currentLoopProgress}/${currentLoopTotal} in current loop, total sent: ${task.sent})`);
                    } else {
                        progress = Math.round((task.sent + task.failed) / task.total * 100);
                        logger.info(`Task ${taskId} progress: ${progress}% (${task.sent}/${task.total} sent)`);
                    }
                    
                    // Wait for delay - this is crucial for proper message timing
                    if (task.active) {
                        // Always wait for the full delay time between messages
                        logger.info(`Waiting for ${delay} seconds before sending next message...`);
                        await new Promise(resolve => setTimeout(resolve, delay * 1000));
                    }
                }
            }
            
            // Check if we should continue looping
            if (loopMode) {
                logger.info(`Loop ${task.currentLoop} completed for task ${taskId}`);
                
                // Check if we've reached the max loops (if specified)
                if (maxLoops > 0 && task.currentLoop >= maxLoops) {
                    logger.info(`Reached maximum loops (${maxLoops}) for task ${taskId}`);
                    continueLooping = false;
                } else {
                    // Increment loop counter
                    task.currentLoop++;
                    
                    // Add a longer delay between loops (3x the message delay)
                    await new Promise(resolve => setTimeout(resolve, delay * 3 * 1000));
                    
                    logger.info(`Starting loop ${task.currentLoop} for task ${taskId}`);
                }
            } else {
                // Not in loop mode, exit after one run
                continueLooping = false;
            }
        }
        
        // Update task status
        if (task.active) {
            task.status = 'completed';
            task.active = false;
            logger.info(`Task ${taskId} completed`);
        }
    } catch (error) {
        logger.error(`Error in background task ${taskId}: ${error.message}`);
        
        // Update task status
        const task = activeTasks[taskId];
        if (task) {
            task.status = 'error';
            task.active = false;
            task.errors.push(error.message);
        }
    }
}

// Stop a task
function stopTask(taskId) {
    try {
        const task = activeTasks[taskId];
        if (!task) {
            return {
                success: false,
                message: `Task ${taskId} not found`
            };
        }
        
        // Stop the task
        task.active = false;
        task.status = 'stopped';
        logger.info(`Task ${taskId} stopped`);
        
        return {
            success: true,
            message: `Task ${taskId} stopped`
        };
    } catch (error) {
        logger.error(`Error stopping task ${taskId}: ${error.message}`);
        return {
            success: false,
            message: error.message
        };
    }
}

// Restart a task
function restartTask(taskId) {
    try {
        const task = activeTasks[taskId];
        if (!task) {
            return {
                success: false,
                message: `Task ${taskId} not found`
            };
        }
        
        // Only restart if it was stopped
        if (task.status !== 'stopped') {
            return {
                success: false,
                message: `Task ${taskId} is not stopped (current status: ${task.status})`
            };
        }
        
        // Reset task status
        task.active = true;
        task.status = 'running';
        logger.info(`Task ${taskId} restarted`);
        
        // Start sending messages again
        sendMessagesInBackground(taskId);
        
        return {
            success: true,
            message: `Task ${taskId} restarted`
        };
    } catch (error) {
        logger.error(`Error restarting task ${taskId}: ${error.message}`);
        return {
            success: false,
            message: error.message
        };
    }
}

// Logout from WhatsApp
async function logoutWhatsApp() {
    try {
        if (!sock) {
            return {
                success: true,
                message: 'Already logged out'
            };
        }
        
        // Log out
        await sock.logout();
        sock = null;
        connectionStatus = 'disconnected';
        connectedPhoneNumber = null;
        qrData = null;
        
        logger.info('Logged out from WhatsApp');
        
        return {
            success: true,
            message: 'Logged out successfully'
        };
    } catch (error) {
        logger.error(`Error logging out: ${error.message}`);
        return {
            success: false,
            message: error.message
        };
    }
}

// Define API endpoints
// Get service status
app.get('/status', (req, res) => {
    try {
        const status = {
            success: true,
            status: connectionStatus,
            phoneNumber: connectedPhoneNumber,
            qrAvailable: !!qrData,
            pairingCode: pairingCode
        };
        
        res.json(status);
    } catch (error) {
        logger.error(`Error getting status: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Request pairing code
app.post('/request-pairing-code', async (req, res) => {
    try {
        const { phoneNumber } = req.body;
        
        if (!phoneNumber) {
            return res.status(400).json({
                success: false,
                message: 'Phone number is required'
            });
        }
        
        // First check if we are already connected and the phone number matches
        if (connectionStatus === 'connected' && connectedPhoneNumber) {
            // Compare the given phone number with the connected one, after cleaning
            let formattedPhone = phoneNumber.toString().replace(/[^0-9]/g, '');
            let currentPhone = connectedPhoneNumber.toString().replace(/[^0-9]/g, '');
            
            // If the phone numbers match, return already connected status
            if (formattedPhone === currentPhone) {
                logger.info(`Already connected with phone number: ${currentPhone}`);
                return res.json({
                    success: true,
                    already_connected: true,
                    phone_number: connectedPhoneNumber
                });
            }
        }
        
        // Not already connected, continue with pairing code request
        const result = await requestPairingCode(phoneNumber);
        
        // Check auth_info folder again to see if we have files that could indicate a previous connection
        const authFiles = fs.readdirSync(AUTH_DIR);
        const hasCredFile = authFiles.some(file => file.includes('creds.json'));
        
        // If we have found credential files, suggest checking connection status
        if (hasCredFile) {
            result.check_connection = true;
        }
        
        res.json(result);
    } catch (error) {
        logger.error(`Error requesting pairing code: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Send a message
app.post('/send-message', async (req, res) => {
    try {
        const { to, message } = req.body;
        
        if (!to || !message) {
            return res.status(400).json({
                success: false,
                message: 'Recipient and message are required'
            });
        }
        
        const result = await sendMessage(to, message);
        res.json(result);
    } catch (error) {
        logger.error(`Error sending message: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Send multiple messages
app.post('/send-messages', async (req, res) => {
    try {
        const { taskId, targets, messages, delay, loopMode, maxLoops, messageFile } = req.body;
        
        // Check if we have direct messages or need to read from a file
        let messageArray = messages;
        
        logger.info(`Received send-messages request with:
            - taskId: ${taskId}
            - targets: ${JSON.stringify(targets).substring(0, 100)}...
            - messages: ${messageArray ? JSON.stringify(messageArray).substring(0, 100) + '...' : 'None (using file)'}
            - delay: ${delay}
            - loopMode: ${loopMode}
            - maxLoops: ${maxLoops}
            - messageFile: ${messageFile || 'None'}`);
        
        // If messageFile exists, read messages from it
        if (messageFile) {
            try {
                // Check if file exists
                if (fs.existsSync(messageFile)) {
                    // Read file content
                    const fileContent = fs.readFileSync(messageFile, 'utf8');
                    
                    // Split by lines and filter empty lines
                    messageArray = fileContent.split('\n')
                        .map(line => line.trim())
                        .filter(line => line.length > 0);
                    
                    logger.info(`Read ${messageArray.length} messages from file: ${messageFile}`);
                    logger.info(`First few messages: ${JSON.stringify(messageArray.slice(0, 3))}${messageArray.length > 3 ? ' (and more)' : ''}`);
                } else {
                    return res.status(400).json({
                        success: false,
                        message: `Message file not found: ${messageFile}`
                    });
                }
            } catch (fileError) {
                logger.error(`Error reading message file: ${fileError.message}`);
                return res.status(400).json({
                    success: false,
                    message: `Error reading message file: ${fileError.message}`
                });
            }
        }
        
        if (!targets || !targets.length || !messageArray || !messageArray.length) {
            return res.status(400).json({
                success: false,
                message: 'Recipients and messages are required'
            });
        }
        
        // Generate task ID if not provided
        const id = taskId || uuidv4();
        
        // Set default delay to 10 seconds if not specified
        const delayValue = delay || 10;
        
        // Set loop mode and max loops
        // Default to loop mode enabled and infinite loops (maxLoops = 0) unless explicitly disabled
        const useLoopMode = loopMode !== false && loopMode !== 'false';
        const loops = maxLoops ? parseInt(maxLoops) : 0;
        
        const result = await sendBulkMessages(id, targets, messageArray, delayValue, useLoopMode, loops);
        res.json(result);
    } catch (error) {
        logger.error(`Error sending bulk messages: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Get task status
app.get('/task-status/:taskId', (req, res) => {
    try {
        const { taskId } = req.params;
        
        const task = activeTasks[taskId];
        if (!task) {
            return res.status(404).json({
                success: false,
                message: `Task ${taskId} not found`
            });
        }
        
        let progress;
        
        // For infinite looping, calculate progress within the current loop
        if (task.loopMode && task.maxLoops === 0) {
            const currentLoopTotal = task.baseTotal;
            const currentLoopProgress = (task.sent + task.failed) % currentLoopTotal;
            progress = Math.round((currentLoopProgress / currentLoopTotal) * 100);
        } else {
            progress = Math.round((task.sent + task.failed) / task.total * 100);
        }
        
        // Get the latest message logs related to this task
        const taskMessages = messageLog
            .filter(log => task.targets.includes(log.to))
            .map(log => ({
                timestamp: new Date(log.timestamp).toLocaleTimeString(),
                to: log.to,
                message: log.message,
                success: log.success,
                error: log.error
            }))
            .slice(-50); // Limit to last 50 messages to avoid huge payloads
            
        res.json({
            success: true,
            task: {
                id: taskId,
                status: task.status,
                active: task.active,
                total: task.total,
                sent: task.sent,
                failed: task.failed,
                remaining: task.remaining,
                progress: progress,
                errors: task.errors,
                loopMode: task.loopMode,
                currentLoop: task.currentLoop,
                maxLoops: task.maxLoops,
                loopProgress: task.loopMode ? `Loop ${task.currentLoop}${task.maxLoops > 0 ? ` of ${task.maxLoops}` : ''}` : null,
                messageLogs: taskMessages
            }
        });
    } catch (error) {
        logger.error(`Error getting task status: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Stop a task
app.post('/stop-task/:taskId', (req, res) => {
    try {
        const { taskId } = req.params;
        
        const result = stopTask(taskId);
        res.json(result);
    } catch (error) {
        logger.error(`Error stopping task: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Restart a task
app.post('/restart-task/:taskId', (req, res) => {
    try {
        const { taskId } = req.params;
        
        const result = restartTask(taskId);
        res.json(result);
    } catch (error) {
        logger.error(`Error restarting task: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Get message logs
app.get('/message-logs', (req, res) => {
    try {
        // Return only successful messages
        const successfulMessages = messageLog.filter(msg => msg.success);
        
        res.json({
            success: true,
            messages: successfulMessages
        });
    } catch (error) {
        logger.error(`Error getting message logs: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Delete a task completely
app.delete('/delete-task/:taskId', (req, res) => {
    try {
        const { taskId } = req.params;
        
        // First stop the task if it's running
        if (activeTasks[taskId] && activeTasks[taskId].active) {
            stopTask(taskId);
        }
        
        // Delete the task from memory
        if (activeTasks[taskId]) {
            delete activeTasks[taskId];
            logger.info(`Task ${taskId} deleted completely`);
            
            return res.json({
                success: true,
                message: `Task ${taskId} deleted completely`
            });
        } else {
            return res.status(404).json({
                success: false,
                message: `Task ${taskId} not found`
            });
        }
    } catch (error) {
        logger.error(`Error deleting task: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Logout from WhatsApp
app.post('/logout', async (req, res) => {
    try {
        const result = await logoutWhatsApp();
        res.json(result);
    } catch (error) {
        logger.error(`Error logging out: ${error.message}`);
        res.status(500).json({
            success: false,
            message: error.message
        });
    }
});

// Start server
app.listen(port, () => {
    logger.info(`Simple WhatsApp service running on port ${port}`);
    // Initialize connection
    connectToWhatsApp();
});

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

module.exports = app;