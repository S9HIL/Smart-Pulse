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

// Create logger
const logger = pino({
    transport: {
        target: 'pino-pretty',
        options: {
            colorize: true,
        },
    },
});

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
                
                // Send QR code to parent process
                sendToParent({
                    type: 'qr_code',
                    qrData: qr
                });
            }

            if (connection) {
                logger.info(`Connection update: ${connection}`);
                connectionStatus = connection;
                
                // Send connection status to parent process
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
                        
                        // Send connection status to parent process
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
                        
                        // Send connection status to parent process
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
            throw lastError || new Error('Failed to request pairing code after multiple retries');
        }
        
        logger.info(`Received pairing code: ${code}`);
        pairingCode = code;
        
        // Send pairing code to parent process
        sendToParent({
            type: 'pairing_code',
            code: code,
            phoneNumber: formattedPhone
        });
        
        return code;
    } catch (err) {
        logger.error(`Error requesting pairing code: ${err.message}`);
        throw err;
    }
}

// Send a WhatsApp message to a user or group
async function sendMessage(target, message, isGroup = false, options = {}) {
    const messageId = options.messageId || uuidv4();
    
    try {
        if (!sock) {
            throw new Error('WhatsApp is not connected');
        }
        
        // Validate target
        if (!target) {
            throw new Error('Target phone number or group ID is required');
        }
        
        // Format phone number if this is a user (not a group)
        let recipient = target;
        if (!isGroup) {
            // Clean the phone number, remove any non-numeric characters
            recipient = target.toString().replace(/[^0-9]/g, '');
            
            // For 10-digit Indian numbers, add the country code
            if (recipient.length === 10 && /^[6-9]/.test(recipient)) {
                recipient = '91' + recipient;
            }
            
            // Add suffix for WhatsApp ID
            recipient = `${recipient}@s.whatsapp.net`;
        } else {
            // Format group ID
            recipient = `${recipient}@g.us`;
        }
        
        logger.info(`Sending message to ${isGroup ? 'group' : 'user'}: ${recipient}`);
        
        // Create message object
        const msg = {
            text: message
        };
        
        // Send message
        const result = await sock.sendMessage(recipient, msg);
        
        // Log success
        logger.info(`Message sent successfully: ${messageId}`);
        
        // Send status to parent process
        sendToParent({
            type: 'message_status',
            messageId: messageId,
            status: 'sent',
            recipient: recipient
        });
        
        return { success: true, messageId, result };
    } catch (err) {
        logger.error(`Error sending message: ${err.message}`);
        
        // Send error status to parent process
        sendToParent({
            type: 'message_status',
            messageId: messageId,
            status: 'failed',
            error: err.message
        });
        
        return { success: false, messageId, error: err.message };
    }
}

// Send message to parent process
function sendToParent(data) {
    try {
        if (process.send) {
            // If running as a child process, use process.send
            process.send(data);
        } else {
            // Otherwise, write to stdout as JSON
            console.log(JSON.stringify(data));
        }
    } catch (err) {
        // Fallback to console
        console.log(JSON.stringify(data));
    }
}

// STDIN command processor for integration with Python
async function processStdin() {
    const readline = require('readline');
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        terminal: false
    });
    
    rl.on('line', async (line) => {
        try {
            // Parse the JSON command
            const command = JSON.parse(line);
            
            // Process command
            switch (command.action) {
                case 'connect':
                    // Connect to WhatsApp
                    await connectToWhatsApp(
                        command.sessionId,
                        command.phoneNumber,
                        command.forceNew || false
                    );
                    break;
                    
                case 'requestPairingCode':
                    // Request a pairing code
                    await requestPairingCode(command.phoneNumber);
                    break;
                    
                case 'sendMessage':
                    // Send a message
                    await sendMessage(
                        command.to,
                        command.message,
                        command.isGroup || false,
                        { messageId: command.messageId }
                    );
                    break;
                    
                case 'status':
                    // Get current status
                    sendToParent({
                        type: 'status',
                        status: connectionStatus,
                        phoneNumber: connectedPhoneNumber,
                        hasQR: !!qrData,
                        hasPairingCode: !!pairingCode
                    });
                    break;
                    
                default:
                    logger.warn(`Unknown command: ${command.action}`);
            }
        } catch (err) {
            logger.error(`Error processing command: ${err.message}`);
            sendToParent({
                type: 'error',
                error: err.message
            });
        }
    });
    
    // Handle stdin closing
    rl.on('close', () => {
        logger.info('STDIN closed, exiting...');
        process.exit(0);
    });
}

// Initialize
(async () => {
    try {
        // Start processing stdin for commands
        processStdin();
        
        // Send initial status
        sendToParent({
            type: 'status',
            status: 'initializing'
        });
        
        logger.info('WhatsApp service ready to process commands');
    } catch (err) {
        logger.error(`Error initializing WhatsApp service: ${err.message}`);
        process.exit(1);
    }
})();
