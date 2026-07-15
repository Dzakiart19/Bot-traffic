import os
import time
import threading
import datetime
import urllib.request
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

try:
    from core.bot_engine import (run_bot, DEFAULT_TARGET,
                                  DEFAULT_TIMEOUT, DEFAULT_STAY_TIME)
    _BOT_AVAILABLE = True
except Exception as _import_err:
    _BOT_AVAILABLE = False
    DEFAULT_TARGET    = "https://dramacina--dzeckart.replit.app"
    DEFAULT_TIMEOUT   = 30
    DEFAULT_STAY_TIME = 5
    def run_bot(*a, **kw):
        pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'bot-monitor-secret'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

# ── Uptime tracking ──────────────────────────────────────────
server_start_time = datetime.datetime.utcnow()
bot_start_time    = None

# ── Bot state ────────────────────────────────────────────────
stats = {'tried': 0, 'success': 0, 'failed': 0,
         'running': False, 'round': 0, 'current_proxy': '-'}
log_buffer = []
MAX_LOGS   = 1000


def emit_log(message):
    log_buffer.append(message)
    if len(log_buffer) > MAX_LOGS:
        log_buffer.pop(0)
    socketio.emit('log', {
        'message': message,
        'stats': dict(stats),
        'bot_start_time': bot_start_time.isoformat() if bot_start_time else None,
    }, namespace='/')


def _run_bot():
    global bot_start_time
    bot_start_time = datetime.datetime.utcnow()
    stats.update({'tried': 0, 'success': 0, 'failed': 0,
                  'running': True, 'round': 0, 'current_proxy': '-'})
    emit_log(f"[START] Target: {DEFAULT_TARGET} | Timeout: {DEFAULT_TIMEOUT}s | Stay: {DEFAULT_STAY_TIME}s")
    run_bot(
        target_url=DEFAULT_TARGET,
        timeout=DEFAULT_TIMEOUT,
        stay_time=DEFAULT_STAY_TIME,
        log_fn=emit_log,
        stop_event=None,
        stats=stats,
    )


# Auto-start bot thread (gracefully skipped if engine unavailable)
if _BOT_AVAILABLE:
    _bot_thread = threading.Thread(target=_run_bot, daemon=True)
    _bot_thread.start()
else:
    stats['running'] = False


# ── Routes ───────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html',
                           default_target=DEFAULT_TARGET,
                           server_start=server_start_time.isoformat())


@app.route('/ping')
def ping():
    """Endpoint for cron job to keep the server alive."""
    uptime_s = int((datetime.datetime.utcnow() - server_start_time).total_seconds())
    return jsonify({
        'status': 'ok',
        'bot_running': stats.get('running', False),
        'uptime_seconds': uptime_s,
    })


@app.route('/api/status')
def api_status():
    return jsonify({
        'stats': dict(stats),
        'logs': log_buffer[-200:],
        'server_start_time': server_start_time.isoformat(),
        'bot_start_time': bot_start_time.isoformat() if bot_start_time else None,
    })


# ── Socket.IO ────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    emit('init', {
        'stats': dict(stats),
        'logs': log_buffer[-200:],
        'server_start_time': server_start_time.isoformat(),
        'bot_start_time': bot_start_time.isoformat() if bot_start_time else None,
    })


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
