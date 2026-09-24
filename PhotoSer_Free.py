# ==============================================================================
# PhotoSer — Сервер локальной передачи файлов (с настраиваемой PIN-авторизацией)
# Copyright (C) 2026 JemikiVa
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# ==============================================================================

import os
import sys
import time
import socket
import urllib.request
import urllib.error
import threading
import logging
import uuid
import platform
import json
import secrets
import random
import subprocess
import shlex
from typing import Optional, List
from io import BytesIO

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

import flask
from flask import (
    Flask,
    render_template_string,
    request,
    jsonify,
    send_from_directory,
    make_response,
)

# Попытка импорта WSGI сервера Waitress для стабильной работы
try:
    from waitress import serve

    HAS_WAITRESS = True
except ImportError:
    HAS_WAITRESS = False

# Попытка импорта qrcode и zeroconf для расширенной функциональности
try:
    import qrcode

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from PIL import ImageTk

    HAS_IMAGETK = True
except ImportError:
    HAS_IMAGETK = False

try:
    from zeroconf import ServiceInfo, Zeroconf

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem

    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ==============================================================================
# НАСТРОЙКИ И ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# ==============================================================================

def get_app_dir() -> str:
    """Возвращает абсолютный путь к директории исполняемого файла (.exe) или скрипта."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))


APP_DIR = get_app_dir()

LICENSE_INFO = "GPLv3 (GNU General Public License v3)"
COPYRIGHT_INFO = "Copyright (C) 2026 JemikiVa"

DEFAULT_PORT = 51773
PORT_CANDIDATES = [51773, 51774, 51775, 8080, 8888, 5000]
UDP_PORT = 9999
SERVICE_TYPE = "_photoser._tcp.local."

RECEIVED_FOLDER_NAMES = {
    'ru': 'Полученные файлы',
    'en': 'Received files',
    'lv': 'Saņemtie faili',
    'de': 'Empfangene Dateien',
}

LOG_FILE = os.path.join(os.path.expanduser("~"), "photoser_app.log")
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), "photoser_settings.json")
ICON_FILE = os.path.join(APP_DIR, "photoser_app_icon.ico")

UPLOAD_FOLDER = ""
LAST_SESSION_FOLDER = ""
notify_callback = None
app_server_name = 'PhotoSer'

# Глобальная ссылка для предотвращения сборки мусора мьютекса
single_instance_mutex = None

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

config_lock = threading.RLock()
current_port = DEFAULT_PORT
app_language = 'ru'
udp_stop_event = threading.Event()

zeroconf_instance: Optional[Zeroconf] = None
zeroconf_info: Optional[ServiceInfo] = None

# Глобальные настройки PIN-авторизации
pin_enabled = True
current_pin = "1234"
active_sessions = set()

# ==============================================================================
# ПРЕДОТВРАЩЕНИЕ ЗАПУСКА ДВУХ КОПИЙ (SINGLE INSTANCE)
# ==============================================================================

def check_single_instance() -> bool:
    """Возвращает True, если это единственный экземпляр. Возвращает False, если программа уже запущена."""
    global single_instance_mutex
    system = platform.system()

    if system == 'Windows':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex_name = "Global\\PhotoSer_SingleInstance_Mutex"
        single_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if last_error == 183:
            return False
        return True
    else:
        import fcntl
        lock_file_path = os.path.join('/tmp', 'photoser_app.lock')
        try:
            single_instance_mutex = open(lock_file_path, 'w')
            fcntl.lockf(single_instance_mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            return False

# ==============================================================================
# ЛОКАЛИЗОВАННЫЕ ДАННЫЕ О ЛИЦЕНЗИЯХ ДЛЯ ОКНА ABOUT
# ==============================================================================

THIRD_PARTY_LICENSES = {
    'ru': ('СТОРОННИЕ КОМПОНЕНТЫ\n\n1. Flask\n   Лицензия: BSD-3-Clause\n\n2. Werkzeug\n   Лицензия: BSD-3-Clause\n\n3. Waitress\n   Лицензия: Zope Public License 2.1 (ZPL-2.1)\n\n4. qrcode\n   Лицензия: BSD-3-Clause\n\n5. Pillow\n   Лицензия: HPND / MIT-CMU\n\n6. zeroconf\n   Лицензия: GNU LGPL 2.1 или более поздняя\n\n7. pystray\n   Лицензия: GNU LGPL 3.0 или более поздняя\n\n8. Tcl/Tk\n   Лицензия: Tcl/Tk License\n\nПолные сведения: THIRD-PARTY-NOTICES.txt'),
    'en': ('THIRD-PARTY COMPONENTS\n\n1. Flask\n   License: BSD-3-Clause\n\n2. Werkzeug\n   License: BSD-3-Clause\n\n3. Waitress\n   License: Zope Public License 2.1 (ZPL-2.1)\n\n4. qrcode\n   License: BSD-3-Clause\n\n5. Pillow\n   License: HPND / MIT-CMU\n\n6. zeroconf\n   License: GNU LGPL 2.1 or later\n\n7. pystray\n   License: GNU LGPL 3.0 or later\n\n8. Tcl/Tk\n   License: Tcl/Tk License\n\nFull details: THIRD-PARTY-NOTICES.txt'),
    'lv': ('TREŠO PUŠU KOMPONENTES\n\n1. Flask\n   Licence: BSD-3-Clause\n\n2. Werkzeug\n   Licence: BSD-3-Clause\n\n3. Waitress\n   Licence: Zope Public License 2.1 (ZPL-2.1)\n\n4. qrcode\n   Licence: BSD-3-Clause\n\n5. Pillow\n   Licence: HPND / MIT-CMU\n\n6. zeroconf\n   Licence: GNU LGPL 2.1 vai jaunāka\n\n7. pystray\n   Licence: GNU LGPL 3.0 vai jaunāka\n\n8. Tcl/Tk\n   Licence: Tcl/Tk License\n\nPilna informācija: THIRD-PARTY-NOTICES.txt'),
    'de': ('DRITTANBIETER-KOMPONENTEN\n\n1. Flask\n   Lizenz: BSD-3-Clause\n\n2. Werkzeug\n   Lizenz: BSD-3-Clause\n\n3. Waitress\n   Lizenz: Zope Public License 2.1 (ZPL-2.1)\n\n4. qrcode\n   Lizenz: BSD-3-Clause\n\n5. Pillow\n   Lizenz: HPND / MIT-CMU\n\n6. zeroconf\n   Lizenz: GNU LGPL 2.1 oder später\n\n7. pystray\n   Lizenz: GNU LGPL 3.0 oder später\n\n8. Tcl/Tk\n   Lizenz: Tcl/Tk License\n\nVollständige Angaben: THIRD-PARTY-NOTICES.txt'),
}

ABOUT_LICENSE_NOTICE = {
    'ru': ('О ПРОГРАММЕ\n\nPhotoSer v1.0\nCopyright (C) 2026 JemikiVa\n\nPhotoSer распространяется по GNU General Public License v3 (GPLv3).\n\nПрограмма предоставляется БЕЗ КАКИХ-ЛИБО ГАРАНТИЙ в пределах, разрешённых GPLv3.\n\nПолный текст лицензии должен поставляться вместе с релизом.\nОфициальный текст: https://www.gnu.org/licenses/gpl-3.0.txt'),
    'en': ('ABOUT PHOTOSER\n\nPhotoSer v1.0\nCopyright (C) 2026 JemikiVa\n\nPhotoSer is distributed under the GNU General Public License v3 (GPLv3).\n\nThe program is provided WITHOUT ANY WARRANTY to the extent permitted by the GPLv3.\n\nThe complete license text should accompany the release.\nOfficial text: https://www.gnu.org/licenses/gpl-3.0.txt'),
    'lv': ('PAR PROGRAMMU\n\nPhotoSer v1.0\nAutortiesības (C) 2026 JemikiVa\n\nPhotoSer tiek izplatīts saskaņā ar GNU General Public License v3 (GPLv3).\n\nProgramma tiek nodrošināta BEZ JEBKĀDAS GARANTIJAS, ciktāl to pieļauj GPLv3.\n\nPilnam licences tekstam jābūt pieejamam kopā ar laidienu.\nOficiālais teksts: https://www.gnu.org/licenses/gpl-3.0.txt'),
    'de': ('ÜBER PHOTOSER\n\nPhotoSer v1.0\nCopyright (C) 2026 JemikiVa\n\nPhotoSer wird unter der GNU General Public License v3 (GPLv3) verteilt.\n\nDas Programm wird OHNE JEDE GARANTIE bereitgestellt, soweit dies nach GPLv3 zulässig ist.\n\nDer vollständige Lizenztext sollte dem Release beiliegen.\nOffizieller Text: https://www.gnu.org/licenses/gpl-3.0.txt'),
}

# ==============================================================================
# HTML / WEB UI (локализация + PIN-код)
# ==============================================================================

WEB_STRINGS = {
    'ru': {
        'html_lang': 'ru',
        'title': 'PhotoSer — Передача файлов',
        'heading': 'PhotoSer',
        'subtitle': 'Выберите файлы на устройстве для отправки на ПК.',
        'btn_select': 'Выберите файлы',
        'no_files': 'Файлы не выбраны',
        'one_file': 'Выбран файл: {name}',
        'many_files': 'Выбрано файлов: {n}',
        'btn_upload': 'Загрузить файлы',
        'list_title': 'Загруженные файлы на сервере:',
        'list_loading': 'Загрузка списка...',
        'list_empty': 'Папка пуста',
        'list_error': 'Ошибка загрузки списка',
        'ok': 'Успешно загружено!',
        'err_upload': 'Ошибка передачи файлов.',
        'err_size': 'Превышен лимит передачи: максимум 2 ГБ.',
        'err_connection': 'Ошибка подключения к компьютеру или сети.',
        'err_session': 'Не удалось создать сессию авторизации. Повторите вход.',
        'err_net': 'Произошла ошибка сети.',
        'footer': 'PhotoSer • Copyright © 2026 JemikiVa • Лицензия GNU GPLv3',
        'pin_title': 'Ввод ПИН-кода',
        'pin_subtitle': 'Введите ПИН-код, установленный на ПК:',
        'btn_verify': 'Войти',
        'err_pin': 'Неверный ПИН-код!'
    },
    'en': {
        'html_lang': 'en',
        'title': 'PhotoSer — File Transfer',
        'heading': 'PhotoSer',
        'subtitle': 'Select files on this device to send them to the PC.',
        'btn_select': 'Select files',
        'no_files': 'No files selected',
        'one_file': 'Selected file: {name}',
        'many_files': 'Files selected: {n}',
        'btn_upload': 'Upload files',
        'list_title': 'Files uploaded to the server:',
        'list_loading': 'Loading list...',
        'list_empty': 'Folder is empty',
        'list_error': 'Failed to load list',
        'ok': 'Upload successful!',
        'err_upload': 'File transfer error.',
        'err_size': 'Transfer limit exceeded: maximum 2 GB.',
        'err_connection': 'Connection error to the computer or network.',
        'err_session': 'Authorization session could not be created. Please try again.',
        'err_net': 'Network error.',
        'footer': 'PhotoSer • Copyright © 2026 JemikiVa • GNU GPLv3 License',
        'pin_title': 'Enter PIN Code',
        'pin_subtitle': 'Enter the PIN code set on your PC:',
        'btn_verify': 'Connect',
        'err_pin': 'Invalid PIN code!'
    },
    'lv': {
        'html_lang': 'lv',
        'title': 'PhotoSer — Failu pārsūtīšana',
        'heading': 'PhotoSer',
        'subtitle': 'Izvēlieties failus ierīcē, lai nosūtītu tos uz datoru.',
        'btn_select': 'Izvēlēties failus',
        'no_files': 'Faili nav izvēlēti',
        'one_file': 'Izvēlēts fails: {name}',
        'many_files': 'Izvēlēti faili: {n}',
        'btn_upload': 'Augšupielādēt',
        'list_title': 'Serverī augšupielādētie faili:',
        'list_loading': 'Ielādē sarakstu...',
        'list_empty': 'Mape ir tukša',
        'list_error': 'Neizdevās ielādēt sarakstu',
        'ok': 'Veiksmīgi augšupielādēts!',
        'err_upload': 'Failu pārsūtīšanas kļūda.',
        'err_size': 'Pārsūtīšanas limits pārsniegts: maksimums 2 GB.',
        'err_connection': 'Savienojuma kļūda ar datoru vai tīklu.',
        'err_session': 'Neizdevās izveidot autorizācijas sesiju. Mēģiniet vēlreiz.',
        'err_net': 'Tīkla kļūda.',
        'footer': 'PhotoSer • Autortiesības © 2026 Jemiki • GNU GPLv3 licence',
        'pin_title': 'Ievadiet PIN kodu',
        'pin_subtitle': 'Ievadiet PIN kodu, kas iestatīts datorā:',
        'btn_verify': 'Pieslēgties',
        'err_pin': 'Nepareizs PIN kods!'
    },
    'de': {
        'html_lang': 'de',
        'title': 'PhotoSer — Dateiübertragung',
        'heading': 'PhotoSer',
        'subtitle': 'Wählen Sie Dateien auf diesem Gerät, um sie an den PC zu senden.',
        'btn_select': 'Dateien auswählen',
        'no_files': 'Keine Dateien ausgewählt',
        'one_file': 'Ausgewählte Datei: {name}',
        'many_files': 'Dateien ausgewählt: {n}',
        'btn_upload': 'Hochladen',
        'list_title': 'Auf dem Server gespeicherte Dateien:',
        'list_loading': 'Liste wird geladen...',
        'list_empty': 'Ordner ist leer',
        'list_error': 'Liste konnte nicht geladen werden',
        'ok': 'Erfolgreich hochgeladen!',
        'err_upload': 'Fehler bei der Dateiübertragung.',
        'err_size': 'Übertragungsgrenze überschritten: maximal 2 GB.',
        'err_connection': 'Verbindungsfehler zum Computer oder Netzwerk.',
        'err_session': 'Autorisierungssitzung konnte nicht erstellt werden. Bitte erneut versuchen.',
        'err_net': 'Netzwerkfehler.',
        'footer': 'PhotoSer • Copyright © 2026 JemikiVa • GNU-GPLv3-Lizenz',
        'pin_title': 'PIN-Code eingeben',
        'pin_subtitle': 'Geben Sie den auf dem PC festgelegten PIN-Code ein:',
        'btn_verify': 'Verbinden',
        'err_pin': 'Ungültiger PIN-Code!'
    }
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="{{ html_lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        :root {
            --bg-color: #f4f6f9;
            --card-bg: #ffffff;
            --primary: #0066cc;
            --primary-hover: #0052a3;
            --text: #333333;
            --border: #e0e0e0;
            --success: #28a745;
            --danger: #dc3545;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text);
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 600px;
            background: var(--card-bg);
            padding: 24px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        h1 { font-size: 1.5rem; margin-top: 0; margin-bottom: 8px; color: var(--primary); }
        p { color: #666; font-size: 0.95rem; margin-bottom: 20px; }

        .pin-box { text-align: center; padding: 20px 0; }
        .pin-input {
            font-size: 1.8rem;
            letter-spacing: 6px;
            text-align: center;
            width: 200px;
            padding: 10px;
            border: 2px solid var(--border);
            border-radius: 8px;
            margin-bottom: 15px;
            outline: none;
        }
        .pin-input:focus { border-color: var(--primary); }
        .btn-pin {
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 12px 30px;
            font-size: 1rem;
            font-weight: bold;
            border-radius: 6px;
            cursor: pointer;
        }
        .pin-error { color: var(--danger); font-size: 0.9rem; margin-top: 10px; display: none; }

        .upload-box {
            border: 2px dashed var(--border);
            border-radius: 8px;
            padding: 30px 20px;
            text-align: center;
            background: #fafafa;
            margin-bottom: 20px;
        }
        .file-input-hidden { display: none; }
        .btn-select {
            display: inline-block;
            background-color: var(--primary);
            color: #fff;
            padding: 12px 24px;
            font-size: 1rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
        }
        .btn-select:hover { background-color: var(--primary-hover); }
        #file-status { margin-top: 12px; font-size: 0.9rem; color: #555; word-break: break-all; }
        .progress-bar-container {
            width: 100%; background-color: #e9ecef; border-radius: 4px; height: 10px;
            overflow: hidden; display: none; margin-top: 15px;
        }
        .progress-bar { width: 0%; height: 100%; background-color: var(--success); transition: width 0.2s; }
        .btn-upload {
            width: 100%; background-color: var(--success); color: white; border: none;
            padding: 12px; font-size: 1rem; font-weight: bold; border-radius: 6px;
            cursor: pointer; display: none;
        }
        .btn-upload:disabled { background-color: #ccc; cursor: not-allowed; }
        footer {
            margin-top: 25px; text-align: center; font-size: 0.8rem; color: #888;
            border-top: 1px dashed var(--border); padding-top: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{ heading }}</h1>

        <div id="pin-screen" class="pin-box" style="display: {% if authenticated %}none{% else %}block{% endif %};">
            <h3>{{ pin_title }}</h3>
            <p>{{ pin_subtitle }}</p>
            <input type="password" id="pin-code" class="pin-input" placeholder="••••" autocomplete="off" onkeydown="if(event.key==='Enter') verifyPin()">
            <br>
            <button class="btn-pin" onclick="verifyPin()">{{ btn_verify }}</button>
            <div id="pin-err" class="pin-error">{{ err_pin }}</div>
        </div>

        <div id="main-screen" style="display: {% if authenticated %}block{% else %}none{% endif %};">
            <p>{{ subtitle }}</p>

            <div class="upload-box">
                <label for="file-input" class="btn-select">{{ btn_select }}</label>
                <input type="file" id="file-input" class="file-input-hidden" multiple onchange="handleFileSelection(this.files)">
                <div id="file-status">{{ no_files }}</div>
                <div class="progress-bar-container" id="progress-container">
                    <div class="progress-bar" id="progress-bar"></div>
                </div>
            </div>

            <button id="upload-btn" class="btn-upload" onclick="uploadFiles()">{{ btn_upload }}</button>

        </div>

        <footer>{{ footer }}</footer>
    </div>

    <script>
        const I18N = {
            no_files: {{ no_files|tojson }},
            one_file: {{ one_file|tojson }},
            many_files: {{ many_files|tojson }},
            ok: {{ ok|tojson }},
            err_upload: {{ err_upload|tojson }},
            err_size: {{ err_size|tojson }},
            err_connection: {{ err_connection|tojson }},
            err_pin: {{ err_pin|tojson }},
            err_session: {{ err_session|tojson }},
            err_net: {{ err_net|tojson }},
            list_empty: {{ list_empty|tojson }},
            list_error: {{ list_error|tojson }},
            list_loading: {{ list_loading|tojson }}
        };
        let selectedFiles = [];

        function verifyPin() {
            const pin = document.getElementById('pin-code').value;
            const errEl = document.getElementById('pin-err');
            errEl.style.display = 'none';

            fetch('/api/verify_pin', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({pin: pin})
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'ok') {
                    document.getElementById('pin-screen').style.display = 'none';
                    document.getElementById('main-screen').style.display = 'block';
                } else {
                    errEl.style.display = 'block';
                }
            })
            .catch(() => {
                errEl.style.display = 'block';
            });
        }

        function handleFileSelection(files) {
            selectedFiles = Array.from(files);
            const statusEl = document.getElementById('file-status');
            const uploadBtn = document.getElementById('upload-btn');
            if (selectedFiles.length === 0) {
                statusEl.textContent = I18N.no_files;
                uploadBtn.style.display = 'none';
            } else if (selectedFiles.length === 1) {
                statusEl.textContent = I18N.one_file.replace('{name}', selectedFiles[0].name);
                uploadBtn.style.display = 'block';
            } else {
                statusEl.textContent = I18N.many_files.replace('{n}', selectedFiles.length);
                uploadBtn.style.display = 'block';
            }
        }


        function uploadFiles() {
            if (selectedFiles.length === 0) return;

            const maxTransferSize = 2 * 1024 * 1024 * 1024;
            const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
            if (totalSize > maxTransferSize) {
                statusEl.textContent = I18N.err_size;
                return;
            }

            const formData = new FormData();
            for (let i = 0; i < selectedFiles.length; i++) {
                formData.append('files', selectedFiles[i]);
            }
            const xhr = new XMLHttpRequest();
            const uploadBtn = document.getElementById('upload-btn');
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            const statusEl = document.getElementById('file-status');
            uploadBtn.disabled = true;
            progressContainer.style.display = 'block';
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    progressBar.style.width = Math.round((e.loaded / e.total) * 100) + '%';
                }
            });
            xhr.addEventListener('load', () => {
                if (xhr.status === 200) {
                    statusEl.textContent = I18N.ok;
                    document.getElementById('file-input').value = '';
                    selectedFiles = [];
                    setTimeout(() => {
                        uploadBtn.style.display = 'none';
                        uploadBtn.disabled = false;
                        progressContainer.style.display = 'none';
                        progressBar.style.width = '0%';
                        statusEl.textContent = I18N.no_files;
                    }, 2000);
                } else if (xhr.status === 401) {
                    location.reload();
                } else if (xhr.status === 413) {
                    statusEl.textContent = I18N.err_size;
                    uploadBtn.disabled = false;
                } else {
                    statusEl.textContent = I18N.err_upload;
                    uploadBtn.disabled = false;
                }
            });
            xhr.addEventListener('error', () => {
                statusEl.textContent = I18N.err_connection;
                uploadBtn.disabled = false;
            });
            xhr.open('POST', '/upload', true);
            xhr.send(formData);
        }

        {% if authenticated %}
        {% endif %}
    </script>
</body>
</html>
"""


def check_auth() -> bool:
    if not pin_enabled:
        return True
    session_token = request.cookies.get('photoser_session')
    return session_token in active_sessions

def build_web_html(lang: Optional[str] = None) -> str:
    global app_language
    code = lang or app_language or 'ru'
    if code not in WEB_STRINGS:
        code = 'ru'
    ctx = dict(WEB_STRINGS[code])
    ctx['server_name'] = app_server_name or 'PhotoSer'
    ctx['heading'] = ctx['server_name']
    ctx['title'] = f"PhotoSer — {ctx['server_name']}"
    ctx['authenticated'] = check_auth()
    return render_template_string(HTML_TEMPLATE, **ctx)


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def make_safe_filename(original_name: str) -> str:
    name = os.path.basename(original_name or '').strip().replace('\x00', '')
    name = name.replace('/', '_').replace('\\', '_').replace('..', '_')
    for ch in '<>:"|?*':
        name = name.replace(ch, '_')
    name = name.strip(' .')
    if not name:
        name = 'file'

    _root, ext = os.path.splitext(name)
    if not _root:
        _root = 'file'
    if len(_root) > 80:
        _root = _root[:80]

    unique_suffix = uuid.uuid4().hex[:8]
    return f"{_root}_{unique_suffix}{ext}"


def find_available_port(host: str, candidates: List[int]) -> int:
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return 0


# ==============================================================================
# МЕХАНИЗМЫ ОБНАРУЖЕНИЯ (UDP BROADCAST & ZEROCONF / MDNS)
# ==============================================================================

def udp_broadcast_worker(stop_event: threading.Event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while not stop_event.is_set():
        with config_lock:
            port = current_port
        message = f"PHOTOSER_DISCOVERY:{port}".encode('utf-8')
        try:
            sock.sendto(message, ('<broadcast>', UDP_PORT))
        except Exception as e:
            logging.error(f"Ошибка отправки UDP broadcast: {e}")

        for _ in range(30):
            if stop_event.is_set():
                break
            time.sleep(0.1)
    sock.close()


def register_mdns(ip: str, port: int, server_name: str = 'PhotoSer'):
    global zeroconf_instance, zeroconf_info
    if not HAS_ZEROCONF:
        return
    try:
        zeroconf_instance = Zeroconf()
        safe_name = ''.join(ch if ch.isalnum() or ch in (' ', '-', '_') else '_' for ch in (server_name or 'PhotoSer')).strip() or 'PhotoSer'
        safe_name = safe_name[:48]
        zeroconf_info = ServiceInfo(
            SERVICE_TYPE,
            f"{safe_name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties={'version': '1.0', 'license': 'GPLv3', 'author': 'JemikiVa', 'server_name': server_name.encode('utf-8')},
        )
        zeroconf_instance.register_service(zeroconf_info)
        logging.info(f"mDNS сервис зарегистрирован: {SERVICE_TYPE} на порту {port}, имя сервера: {server_name}")
    except Exception as e:
        logging.error(f"Ошибка регистрации mDNS: {e}")


def unregister_mdns():
    global zeroconf_instance, zeroconf_info
    if zeroconf_instance and zeroconf_info:
        try:
            zeroconf_instance.unregister_service(zeroconf_info)
            zeroconf_instance.close()
            logging.info("mDNS сервис остановлен.")
        except Exception as e:
            logging.error(f"Ошибка остановки mDNS: {e}")
        zeroconf_instance = None
        zeroconf_info = None


# ==============================================================================
# FLASK СЕРВЕР И API
# ==============================================================================

app = Flask(__name__)
MAX_TRANSFER_SIZE = 2 * 1024 * 1024 * 1024  # 2 GiB
app.config['MAX_CONTENT_LENGTH'] = MAX_TRANSFER_SIZE


@app.route('/')
def index():
    return build_web_html()


@app.route('/api/verify_pin', methods=['POST'])
def api_verify_pin():
    if not pin_enabled:
        return jsonify({'status': 'ok'})

    data = request.get_json() or {}
    user_pin = str(data.get('pin', '')).strip()
    if user_pin == current_pin:
        token = secrets.token_hex(16)
        active_sessions.add(token)
        resp = make_response(jsonify({'status': 'ok'}))
        resp.set_cookie('photoser_session', token, max_age=86400, httponly=True)
        return resp
    return jsonify({'status': 'error', 'message': 'Invalid PIN'}), 401

@app.route('/api/session')
def api_session():
    return jsonify({'authenticated': check_auth()})

@app.route('/api/health')
def api_health():
    return jsonify({'service': 'PhotoSer', 'status': 'ok', 'port': current_port}), 200


@app.route('/api/lang')
def api_lang():
    return jsonify({'lang': app_language})


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'Transfer limit exceeded: maximum 2 GB'}), 413


@app.route('/upload', methods=['POST'])
def upload_file():
    if not check_auth():
        return jsonify({'error': 'Необходима авторизация'}), 401

    if 'files' not in request.files:
        return jsonify({'error': 'Файлы не найдены в запросе'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'Пустой список файлов'}), 400

    session_dir = make_session_folder()
    saved_files = []

    for file in files:
        if file and file.filename:
            safe_name = make_safe_filename(file.filename)
            save_path = os.path.join(session_dir, safe_name)
            file.save(save_path)
            saved_files.append(safe_name)
            logging.info(f"Файл сохранен: {save_path}")

    count = len(saved_files)
    if count and notify_callback:
        try:
            notify_callback(count, session_dir)
        except Exception as e:
            logging.error(f"Уведомление: {e}")

    return jsonify({
        'message': 'Загрузка успешна',
        'files': saved_files,
        'session': os.path.basename(session_dir),
        'path': session_dir
    }), 200


# Public Free edition is intentionally one-way: phone -> computer.

# ==============================================================================
# ЛОКАЛИЗАЦИЯ GUI + НАСТРОЙКИ + АВТОЗАПУСК + ИКОНКА
# ==============================================================================

UI_STRINGS = {
    'ru': {
        'title': 'PhotoSer — Сервер передачи файлов',
        'status_frame': ' Состояние сервера ',
        'status_starting': 'ЗАПУСК...',
        'status_running': 'РАБОТАЕТ',
        'status_error_ports': 'ОШИБКА: НЕТ СВОБОДНЫХ ПОРТОВ',
        'status_down': 'СЕРВЕР НЕДОСТУПЕН',
        'address': 'Адрес: {url}',
        'address_detect': 'Адрес: Определение...',
        'pin_enable': 'Требовать ПИН-код при подключении',
        'pin_label': 'ПИН-код:',
        'btn_gen_pin': 'Сгенерировать',
        'qr_frame': ' QR-код и доступ ',
        'qr_generating': 'Генерация QR-кода...',
        'qr_open': 'Откройте в браузере:\n{url}',
        'btn_folder': 'Открыть папку с файлами',
        'btn_logs': 'Логи',
        'btn_about': 'О программе',
        'lang_frame': ' Настройки / Settings ',
        'server_name': 'Имя сервера:',
        'server_name_hint': 'Идентификатор сервера',
        'autostart': 'Автозапуск при старте системы',
        'logs_title': 'Логи сервера',
        'logs_missing': 'Файл логов не найден.',
        'error': 'Ошибка',
        'folder_error': 'Не удалось открыть папку: {e}',
        'ports_error': 'Все выбранные порты заняты. Выберите другой порт вручную.',
        'port_label': 'Порт сервера:',
        'port_auto': 'Автоматически',
        'port_apply': 'Применить порт',
        'port_invalid': 'Введите порт от 1 до 65535.',
        'port_change_failed': 'Не удалось запустить сервер на порту {port}. Выберите другой порт.',
        'port_restart': 'Чтобы применить порт {port}, PhotoSer нужно перезапустить. Перезапустить сейчас?',
        'server_start_failed': 'Сервер не запустился на порту {port}.\nПроверьте брандмауэр Windows и занятость порта.\nПодробности записаны в журнал PhotoSer.',
        'about_title': 'О программе • PhotoSer',
        'about_license': 'Лицензия GPLv3',
        'about_third_party': 'Сторонние компоненты',
        'about_close': 'Закрыть',
        'btn_exit': 'Выход',
        'tray_show': 'Показать окно',
        'tray_exit': 'Выход',
        'tray_tip': 'PhotoSer — сервер передачи файлов',
        'btn_choose_folder': 'Папка сохранения…',
        'btn_reset_folder': 'По умолчанию',
        'folder_path': 'Папка: {path}',
        'first_run_title': 'Первый запуск PhotoSer',
        'first_run_msg': 'Укажите каталог, внутри которого будет создана папка «{name}» для входящих файлов.',
        'notify_title': 'PhotoSer — получены файлы',
        'notify_body': 'Получено файлов: {n}\nПапка: {path}',
        'notify_one': 'Получен 1 файл\nПапка: {path}',
        'shortcut_prompt_title': 'Ярлык на рабочем столе',
        'shortcut_prompt_msg': 'Хотите создать ярлык PhotoSer на рабочем столе для быстрого запуска?',
        'btn_shortcut': 'Создать ярлык на рабочем столе',
        'shortcut_created': 'Ярлык PhotoSer успешно создан на рабочем столе.',
        'shortcut_failed': 'Не удалось создать ярлык на рабочем столе. Подробности записаны в лог.',
        'already_running': 'Приложение PhotoSer уже запущено!'
    },
    'en': {
        'title': 'PhotoSer — Local File Transfer Server',
        'status_frame': ' Server status ',
        'status_starting': 'STARTING...',
        'status_running': 'RUNNING',
        'status_error_ports': 'ERROR: NO FREE PORTS',
        'status_down': 'SERVER UNAVAILABLE',
        'address': 'Address: {url}',
        'address_detect': 'Address: Detecting...',
        'pin_enable': 'Require PIN code on connection',
        'pin_label': 'PIN code:',
        'btn_gen_pin': 'Generate',
        'qr_frame': ' QR Code & Access ',
        'qr_generating': 'Generating QR code...',
        'qr_open': 'Open in browser:\n{url}',
        'btn_folder': 'Open uploads folder',
        'btn_logs': 'Logs',
        'btn_about': 'About',
        'lang_frame': ' Settings ',
        'server_name': 'Server name:',
        'server_name_hint': 'Server identifier',
        'autostart': 'Start with operating system',
        'logs_title': 'Server logs',
        'logs_missing': 'Log file not found.',
        'error': 'Error',
        'folder_error': 'Could not open folder: {e}',
        'ports_error': 'All selected ports are busy. Choose another port manually.',
        'port_label': 'Server port:',
        'port_auto': 'Automatic',
        'port_apply': 'Apply port',
        'port_invalid': 'Enter a port from 1 to 65535.',
        'port_change_failed': 'Could not start the server on port {port}. Choose another port.',
        'port_restart': 'PhotoSer must restart to apply port {port}. Restart now?',
        'server_start_failed': 'The server could not start on port {port}.\nCheck Windows Firewall and whether the port is in use.\nDetails were written to the PhotoSer log.',
        'about_title': 'About — PhotoSer',
        'about_license': 'GPLv3 License',
        'about_third_party': 'Third-party components',
        'about_close': 'Close',
        'btn_exit': 'Exit',
        'tray_show': 'Show window',
        'tray_exit': 'Exit',
        'tray_tip': 'PhotoSer — file transfer server',
        'btn_choose_folder': 'Save folder…',
        'btn_reset_folder': 'Default',
        'folder_path': 'Folder: {path}',
        'first_run_title': 'PhotoSer first run',
        'first_run_msg': 'Choose a location. A folder «{name}» will be created there for incoming files.',
        'notify_title': 'PhotoSer — files received',
        'notify_body': 'Files received: {n}\nFolder: {path}',
        'notify_one': '1 file received\nFolder: {path}',
        'shortcut_prompt_title': 'Desktop Shortcut',
        'shortcut_prompt_msg': 'Would you like to create a Desktop shortcut for PhotoSer for quick access?',
        'btn_shortcut': 'Create Desktop shortcut',
        'shortcut_created': 'The PhotoSer desktop shortcut was created successfully.',
        'shortcut_failed': 'Could not create the desktop shortcut. See the log for details.',
        'already_running': 'PhotoSer is already running!'
    },
    'lv': {
        'title': 'PhotoSer — Lokālais failu pārsūtīšanas serveris',
        'status_frame': ' Servera statuss ',
        'status_starting': 'PALAIŠANA...',
        'status_running': 'DARBOJAS',
        'status_error_ports': 'KĻŪDA: NAV BRĪVU PORTU',
        'status_down': 'SERVERIS NAV PIEEJAMS',
        'address': 'Adrese: {url}',
        'address_detect': 'Adrese: Nosaka...',
        'pin_enable': 'Pieprasīt PIN kodu pieslēdzoties',
        'pin_label': 'PIN kods:',
        'btn_gen_pin': 'Ģenerēt',
        'qr_frame': ' QR kods un piekļuve ',
        'qr_generating': 'Ģenerē QR kodu...',
        'qr_open': 'Atveriet pārlūkā:\n{url}',
        'btn_folder': 'Atvērt failu mapi',
        'btn_logs': 'Žurnāls',
        'btn_about': 'Par programmu',
        'lang_frame': ' Iestatījumi ',
        'server_name': 'Servera nosaukums:',
        'server_name_hint': 'Servera identifikators',
        'autostart': 'Palaišana līdz ar operētājsistēmu',
        'logs_title': 'Servera žurnāls',
        'logs_missing': 'Žurnāla fails nav atrasts.',
        'error': 'Kļūda',
        'folder_error': 'Neizdevās atvērt mapi: {e}',
        'ports_error': 'Visi izvēlētie porti ir aizņemti. Izvēlieties citu portu manuāli.',
        'port_label': 'Servera ports:',
        'port_auto': 'Automātiski',
        'port_apply': 'Piemērot portu',
        'port_invalid': 'Ievadiet portu no 1 līdz 65535.',
        'port_change_failed': 'Neizdevās palaist serveri portā {port}. Izvēlieties citu portu.',
        'port_restart': 'Lai piemērotu portu {port}, PhotoSer ir jārestartē. Restartēt tagad?',
        'server_start_failed': 'Serveri neizdevās palaist portā {port}.\nPārbaudiet Windows ugunsmūri un porta izmantošanu.\nDetalizēta informācija ir PhotoSer žurnālā.',
        'about_title': 'Par programmu — PhotoSer',
        'about_license': 'GPLv3 licence',
        'about_third_party': 'Trešo pušu komponentes',
        'about_close': 'Aizvērt',
        'btn_exit': 'Iziet',
        'tray_show': 'Rādīt logu',
        'tray_exit': 'Iziet',
        'tray_tip': 'PhotoSer — failu pārsūtīšanas serveris',
        'btn_choose_folder': 'Saglabāšanas mape…',
        'btn_reset_folder': 'Noklusējuma',
        'folder_path': 'Mape: {path}',
        'first_run_title': 'PhotoSer — pirmais starts',
        'first_run_msg': 'Norādiet mapi. Tajā tiks izveidota mape «{name}» ienākošajiem failiem.',
        'notify_title': 'PhotoSer — saņemti faili',
        'notify_body': 'Saņemti faili: {n}\nMape: {path}',
        'notify_one': 'Saņemts 1 fails\nMape: {path}',
        'shortcut_prompt_title': 'Darbvirsmas saīsne',
        'shortcut_prompt_msg': 'Vai vēlaties izveidot PhotoSer saīsni uz darbvirsmas ātrai piekļuvei?',
        'btn_shortcut': 'Izveidot darbvirsmas saīsni',
        'shortcut_created': 'PhotoSer darbvirsmas saīsne ir veiksmīgi izveidota.',
        'shortcut_failed': 'Neizdevās izveidot darbvirsmas saīsni. Plašāka informācija ir žurnālā.',
        'already_running': 'Lietotne PhotoSer jau darbojas!'
    },
    'de': {
        'title': 'PhotoSer — Lokaler Dateiübertragungsserver',
        'status_frame': ' Serverstatus ',
        'status_starting': 'START...',
        'status_running': 'AKTIV',
        'status_error_ports': 'FEHLER: KEINE FREIEN PORTS',
        'status_down': 'SERVER NICHT ERREICHBAR',
        'address': 'Adresse: {url}',
        'address_detect': 'Adresse: Wird ermittelt...',
        'pin_enable': 'PIN-Code bei Verbindung anfordern',
        'pin_label': 'PIN-Code:',
        'btn_gen_pin': 'Generieren',
        'qr_frame': ' QR-Code & Zugriff ',
        'qr_generating': 'QR-Code wird erzeugt...',
        'qr_open': 'Im Browser öffnen:\n{url}',
        'btn_folder': 'Upload-Ordner öffnen',
        'btn_logs': 'Protokolle',
        'btn_about': 'Über',
        'lang_frame': ' Einstellungen ',
        'server_name': 'Servername:',
        'server_name_hint': 'Serverkennung',
        'autostart': 'Mit dem Betriebssystem starten',
        'logs_title': 'Serverprotokolle',
        'logs_missing': 'Protokolldatei nicht gefunden.',
        'error': 'Fehler',
        'folder_error': 'Ordner konnte nicht geöffnet werden: {e}',
        'ports_error': 'Alle ausgewählten Ports sind belegt. Wählen Sie einen anderen Port manuell.',
        'port_label': 'Serverport:',
        'port_auto': 'Automatisch',
        'port_apply': 'Port anwenden',
        'port_invalid': 'Geben Sie einen Port von 1 bis 65535 ein.',
        'port_change_failed': 'Der Server konnte auf Port {port} nicht gestartet werden. Wählen Sie einen anderen Port.',
        'port_restart': 'PhotoSer muss neu gestartet werden, um Port {port} anzuwenden. Jetzt neu starten?',
        'server_start_failed': 'Der Server konnte auf Port {port} nicht gestartet werden.\nPrüfen Sie die Windows-Firewall und die Portbelegung.\nDetails stehen im PhotoSer-Protokoll.',
        'about_title': 'Über — PhotoSer',
        'about_license': 'GPLv3-Lizenz',
        'about_third_party': 'Drittanbieter-Komponenten',
        'about_close': 'Schließen',
        'btn_exit': 'Beenden',
        'tray_show': 'Fenster anzeigen',
        'tray_exit': 'Beenden',
        'tray_tip': 'PhotoSer — Dateiübertragungsserver',
        'btn_choose_folder': 'Speicherordner…',
        'btn_reset_folder': 'Standard',
        'folder_path': 'Ordner: {path}',
        'first_run_title': 'PhotoSer — Erster Start',
        'first_run_msg': 'Wählen Sie einen Ordner. Darin wird «{name}» für eingehende Dateien erstellt.',
        'notify_title': 'PhotoSer — Dateien empfangen',
        'notify_body': 'Dateien empfangen: {n}\nOrdner: {path}',
        'notify_one': '1 Datei empfangen\nOrdner: {path}',
        'shortcut_prompt_title': 'Desktop-Verknüpfung',
        'shortcut_prompt_msg': 'Möchten Sie eine Desktop-Verknüpfung für PhotoSer erstellen, um schnell darauf zuzugreifen?',
        'btn_shortcut': 'Desktop-Verknüpfung erstellen',
        'shortcut_created': 'Die PhotoSer-Desktop-Verknüpfung wurde erfolgreich erstellt.',
        'shortcut_failed': 'Die Desktop-Verknüpfung konnte nicht erstellt werden. Details stehen im Protokoll.',
        'already_running': 'PhotoSer läuft bereits!'
    }
}

LANG_DISPLAY = {'ru': 'Русский', 'en': 'English', 'lv': 'Latviešu', 'de': 'Deutsch'}


def generate_app_icon(path: str = ICON_FILE) -> str:
    """Генерирует фирменный .ico файл иконки приложения."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return ''

    # Отрисовка высокодетализированного изображения для иконки
    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 12
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(0, 102, 204))
    draw.ellipse([70, 70, 186, 186], outline=(255, 255, 255, 230), width=10)

    # Сохраняем в формате .ico с разным разрешением
    try:
        img.save(path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    except Exception:
        # Резервный вариант, если драйвер ICO вызовет исключение
        img.save(path, format='ICO')
    return path


def ensure_app_icon(path: str = ICON_FILE) -> str:
    if os.path.isfile(path):
        return path
    return generate_app_icon(path)


def get_desktop_dir() -> str:
    """Возвращает реальный каталог рабочего стола пользователя."""
    home = os.path.expanduser('~')
    candidates = []

    # Linux/XDG: Desktop может называться не только ~/Desktop.
    xdg_file = os.path.join(home, '.config', 'user-dirs.dirs')
    if os.path.isfile(xdg_file):
        try:
            with open(xdg_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('XDG_DESKTOP_DIR='):
                        value = line.split('=', 1)[1].strip().strip('"')
                        value = value.replace('$HOME', home)
                        if value:
                            candidates.append(os.path.expandvars(os.path.expanduser(value)))
                        break
        except Exception as e:
            logging.warning(f"Не удалось прочитать XDG desktop dir: {e}")

    candidates.extend([
        os.path.join(home, 'Desktop'),
        os.path.join(home, 'Рабочий стол'),
    ])

    # На Windows Desktop может находиться в OneDrive.
    if platform.system() == 'Windows':
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 '[Environment]::GetFolderPath("Desktop")'],
                capture_output=True, text=True, check=True,
                creationflags=0x08000000
            )
            desktop = result.stdout.strip()
            if desktop:
                candidates.insert(0, desktop)
        except Exception as e:
            logging.warning(f"Не удалось определить Windows Desktop: {e}")

    for path in candidates:
        if path and os.path.isdir(path):
            return os.path.abspath(path)

    fallback = os.path.join(home, 'Desktop')
    os.makedirs(fallback, exist_ok=True)
    return os.path.abspath(fallback)


def create_desktop_shortcut() -> bool:
    """Создаёт ярлык PhotoSer на рабочем столе пользователя."""
    system = platform.system()
    desktop_dir = get_desktop_dir()
    script_path = os.path.abspath(sys.argv[0])
    icon_path = ensure_app_icon(ICON_FILE)

    try:
        if system == 'Windows':
            shortcut_path = os.path.join(desktop_dir, 'PhotoSer.lnk')

            if script_path.lower().endswith(('.py', '.pyw')):
                target_path = sys.executable
                arguments = script_path
            else:
                target_path = script_path
                arguments = ''

            def ps_quote(value: str) -> str:
                return "'" + value.replace("'", "''") + "'"

            ps_lines = [
                "$WshShell = New-Object -ComObject WScript.Shell",
                f"$Shortcut = $WshShell.CreateShortcut({ps_quote(shortcut_path)})",
                f"$Shortcut.TargetPath = {ps_quote(target_path)}",
            ]
            if arguments:
                ps_lines.append(f"$Shortcut.Arguments = {ps_quote(arguments)}")
            ps_lines.append(f"$Shortcut.WorkingDirectory = {ps_quote(os.path.dirname(script_path))}")
            if icon_path and os.path.isfile(icon_path):
                ps_lines.append(f"$Shortcut.IconLocation = {ps_quote(icon_path)}")
            ps_lines.append("$Shortcut.Save()")

            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 "; ".join(ps_lines)],
                check=True,
                creationflags=0x08000000
            )
            logging.info(f"Ярлык Windows .lnk создан: {shortcut_path}")
            return os.path.isfile(shortcut_path)

        elif system == 'Linux':
            shortcut_path = os.path.join(desktop_dir, 'PhotoSer.desktop')
            if script_path.lower().endswith('.py'):
                exec_cmd = f"{shlex.quote(sys.executable)} {shlex.quote(script_path)}"
            else:
                exec_cmd = shlex.quote(script_path)

            content = (
                "[Desktop Entry]\n"
                "Version=1.0\n"
                "Type=Application\n"
                "Name=PhotoSer\n"
                f"Exec={exec_cmd}\n"
                f"Icon={shlex.quote(icon_path)}\n"
                "Terminal=false\n"
                "Categories=Network;Utility;\n"
            )
            with open(shortcut_path, 'w', encoding='utf-8') as f:
                f.write(content)
            os.chmod(shortcut_path, 0o755)

            try:
                subprocess.run(
                    ['gio', 'set', shortcut_path, 'metadata::trusted', 'true'],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except FileNotFoundError:
                pass

            logging.info(f"Ярлык Linux .desktop создан: {shortcut_path}")
            return os.path.isfile(shortcut_path)

        elif system == 'Darwin':
            shortcut_path = os.path.join(desktop_dir, 'PhotoSer.command')
            if script_path.lower().endswith(('.py', '.pyw')):
                command = f"exec {shlex.quote(sys.executable)} {shlex.quote(script_path)}"
            else:
                command = f"exec {shlex.quote(script_path)}"

            with open(shortcut_path, 'w', encoding='utf-8') as f:
                f.write("#!/bin/bash\n" + command + "\n")
            os.chmod(shortcut_path, 0o755)

            logging.info(f"Ярлык macOS .command создан: {shortcut_path}")
            return os.path.isfile(shortcut_path)

        logging.warning(f"Создание ярлыка не поддерживается для ОС: {system}")
        return False

    except Exception as e:
        logging.exception(f"Ошибка создания ярлыка на рабочем столе: {e}")
        return False


def load_settings() -> dict:
    defaults = {
        'language': 'ru',
        'autostart': False,
        'storage_parent': '',
        'first_run_done': False,
        'pin_enabled': True,
        'pin_code': '1234',
        'server_name': 'PhotoSer',
        'manual_port': 0
    }
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in list(defaults.keys()):
                if k in data:
                    defaults[k] = data[k]
            try:
                port = int(defaults.get('manual_port') or 0)
                defaults['manual_port'] = port if 1 <= port <= 65535 else 0
            except (TypeError, ValueError):
                defaults['manual_port'] = 0
    except Exception as e:
        logging.error(f"Ошибка чтения настроек: {e}")
    return defaults


def save_settings(settings: dict) -> None:
    """Надёжно сохраняет настройки, не оставляя повреждённый JSON при сбое записи."""
    temp_file = SETTINGS_FILE + '.tmp'
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE) or '.', exist_ok=True)
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, SETTINGS_FILE)
    except Exception as e:
        logging.error(f"Ошибка записи настроек: {e}")
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass


def received_folder_name(lang: str) -> str:
    return RECEIVED_FOLDER_NAMES.get(lang) or RECEIVED_FOLDER_NAMES['en']


def build_received_path(parent: str, lang: str) -> str:
    return os.path.join(parent, received_folder_name(lang))


def ensure_upload_folder(path: str) -> str:
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def apply_upload_folder_from_settings(settings: dict) -> str:
    global UPLOAD_FOLDER
    parent = (settings.get('storage_parent') or '').strip()
    if not parent:
        parent = os.path.expanduser('~')
    lang = settings.get('language') or 'ru'
    path = build_received_path(parent, lang)
    UPLOAD_FOLDER = ensure_upload_folder(path)
    return UPLOAD_FOLDER


def rename_received_folder_on_lang_change(old_lang: str, new_lang: str, settings: dict) -> str:
    global UPLOAD_FOLDER
    parent = (settings.get('storage_parent') or '').strip() or os.path.expanduser('~')
    old_path = build_received_path(parent, old_lang)
    new_path = build_received_path(parent, new_lang)

    if os.path.normpath(old_path) == os.path.normpath(new_path):
        UPLOAD_FOLDER = ensure_upload_folder(new_path)
        return UPLOAD_FOLDER

    if os.path.isdir(old_path) and not os.path.exists(new_path):
        try:
            os.rename(old_path, new_path)
            logging.info(f"Папка получений: {old_path} → {new_path}")
        except OSError as e:
            logging.error(f"Переименование папки получений: {e}")
            ensure_upload_folder(new_path)
    else:
        ensure_upload_folder(new_path)

    UPLOAD_FOLDER = ensure_upload_folder(new_path)
    return UPLOAD_FOLDER


def make_session_folder() -> str:
    global LAST_SESSION_FOLDER, UPLOAD_FOLDER
    ensure_upload_folder(UPLOAD_FOLDER)
    from datetime import datetime
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    session = os.path.join(UPLOAD_FOLDER, stamp)
    base, n = session, 1
    while os.path.exists(session):
        session = f"{base}_{n}"
        n += 1
    os.makedirs(session, exist_ok=True)
    LAST_SESSION_FOLDER = session
    return session


def open_path_in_os(folder: str) -> None:
    if not folder or not os.path.isdir(folder):
        return
    system = platform.system()
    try:
        if system == 'Windows':
            os.startfile(folder)
        elif system == 'Darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
    except Exception as e:
        logging.error(f"Открытие папки: {e}")


def set_autostart(enable: bool) -> None:
    script = os.path.abspath(sys.argv[0])
    system = platform.system()
    if system == 'Windows':
        cmd = f'"{sys.executable}" "{script}"' if script.endswith('.py') else f'"{script}"'
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    winreg.SetValueEx(key, "PhotoSer", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "PhotoSer")
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logging.error(f"Автозапуск Windows: {e}")
            raise
    elif system == 'Linux':
        autostart_dir = os.path.join(os.path.expanduser('~'), '.config', 'autostart')
        desktop = os.path.join(autostart_dir, 'photoser.desktop')
        if enable:
            os.makedirs(autostart_dir, exist_ok=True)
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=PhotoSer\n"
                f"Exec={sys.executable} {script}\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(desktop, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            if os.path.isfile(desktop):
                os.remove(desktop)


def is_autostart_enabled() -> bool:
    system = platform.system()
    try:
        if system == 'Windows':
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                try:
                    winreg.QueryValueEx(key, "PhotoSer")
                    return True
                except FileNotFoundError:
                    return False
        elif system == 'Linux':
            desktop = os.path.join(os.path.expanduser('~'), '.config', 'autostart', 'photoser.desktop')
            return os.path.isfile(desktop)
    except Exception:
        return False
    return False


# ==============================================================================
# GUI ПРИЛОЖЕНИЕ (TKINTER)
# ==============================================================================

class PhotoSerGUI:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.lang = self.settings.get('language', 'ru')
        if self.lang not in UI_STRINGS:
            self.lang = 'ru'

        global app_language, notify_callback, pin_enabled, current_pin, app_server_name
        app_language = self.lang
        pin_enabled = bool(self.settings.get('pin_enabled', True))
        current_pin = str(self.settings.get('pin_code', '1234'))
        app_server_name = str(self.settings.get('server_name', 'PhotoSer') or 'PhotoSer').strip()[:64] or 'PhotoSer'
        self.settings['server_name'] = app_server_name
        self.server_name_var = tk.StringVar(value=app_server_name)

        self.ip_address = get_local_ip()
        self._server_url = ""
        self._status_key = "status_starting"
        self._tray_icon = None
        self._last_notify_folder = ""
        self._discovery_started = False

        self._apply_window_icon()
        self._create_widgets()
        self.apply_language()

        self._maybe_first_run()

        notify_callback = self.on_files_received
        self.start_server_pipeline()
        self.setup_tray()

    def t(self, key: str, **kwargs) -> str:
        s = UI_STRINGS.get(self.lang, UI_STRINGS['ru']).get(key, key)
        try:
            return s.format(**kwargs) if kwargs else s
        except Exception:
            return s

    def _apply_window_icon(self):
        try:
            icon_path = ensure_app_icon(ICON_FILE)
            if not icon_path or not os.path.isfile(icon_path):
                return
            if HAS_IMAGETK:
                from PIL import Image
                img = Image.open(icon_path).resize((64, 64))
                self._icon_photo = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._icon_photo)
            else:
                try:
                    self._icon_photo = tk.PhotoImage(file=icon_path)
                    self.root.iconphoto(True, self._icon_photo)
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Иконка: {e}")

    def _create_widgets(self):
        self.root.minsize(640, 700)
        self.root.geometry("760x820")
        self.root.resizable(True, True)

        style = ttk.Style(self.root)
        try:
            style.configure('Title.TLabel', font=('Segoe UI', 20, 'bold'))
            style.configure('Subtitle.TLabel', font=('Segoe UI', 10))
            style.configure('Card.TLabelframe', padding=14)
            style.configure('Card.TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
            style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), padding=(14, 8))
        except Exception:
            pass

        outer = ttk.Frame(self.root, padding=(22, 18, 22, 18))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        header.columnconfigure(0, weight=1)
        self.lbl_app_title = ttk.Label(header, text='PhotoSer', style='Title.TLabel')
        self.lbl_app_title.grid(row=0, column=0, sticky='w')
        self.lbl_app_subtitle = ttk.Label(header, text='')
        self.lbl_app_subtitle.grid(row=1, column=0, sticky='w', pady=(3, 0))
        self.lang_combo = ttk.Combobox(header, values=[LANG_DISPLAY[k] for k in ('ru', 'en', 'lv', 'de')], state='readonly', width=15)
        self.lang_combo.set(LANG_DISPLAY.get(self.lang, 'Русский'))
        self.lang_combo.bind('<<ComboboxSelected>>', self._on_language_change)
        self.lang_combo.grid(row=0, column=1, rowspan=2, sticky='e')

        self.status_frame = ttk.LabelFrame(outer, text=' Status ', style='Card.TLabelframe')
        self.status_frame.grid(row=1, column=0, sticky='ew', pady=(0, 12))
        self.status_frame.columnconfigure(0, weight=1)
        left = ttk.Frame(self.status_frame)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        left.columnconfigure(0, weight=1)
        self.lbl_status = ttk.Label(left, text='...', font=('Segoe UI', 12, 'bold'))
        self.lbl_status.grid(row=0, column=0, sticky='w')
        self.lbl_url = ttk.Label(left, text='...', font=('Segoe UI', 11))
        self.lbl_url.grid(row=1, column=0, sticky='w', pady=(8, 0))

        port_row = ttk.Frame(left)
        port_row.grid(row=2, column=0, sticky='ew', pady=(12, 0))
        port_row.columnconfigure(2, weight=1)
        self.lbl_port = ttk.Label(port_row, text='Port:')
        self.lbl_port.grid(row=0, column=0, sticky='w')
        self.port_mode_var = tk.StringVar(value='auto' if not self.settings.get('manual_port') else str(self.settings.get('manual_port')))
        port_values = ['auto', '51773', '51774', '51775', '8080', '8888', '5000']
        self.port_combo = ttk.Combobox(port_row, textvariable=self.port_mode_var, values=port_values, width=12)
        self.port_combo.grid(row=0, column=1, sticky='w', padx=(8, 8))
        self.btn_apply_port = ttk.Button(port_row, text='Apply port', command=self.apply_port_setting)
        self.btn_apply_port.grid(row=0, column=2, sticky='w')
        self.lbl_server_name = ttk.Label(left, text='Server name:')
        self.lbl_server_name.grid(row=3, column=0, sticky='w', pady=(16, 3))
        self.server_name_entry = ttk.Entry(left, textvariable=self.server_name_var)
        self.server_name_entry.grid(row=4, column=0, sticky='ew')
        self.server_name_entry.bind('<Return>', self._on_server_name_change)
        self.server_name_entry.bind('<FocusOut>', self._on_server_name_change)

        self.qr_frame = ttk.LabelFrame(self.status_frame, text=' QR ', style='Card.TLabelframe')
        self.qr_frame.grid(row=0, column=1, rowspan=5, sticky='nsew')
        self.qr_label = ttk.Label(self.qr_frame, text='...', anchor='center')
        self.qr_label.pack(padx=12, pady=8, ipadx=10, ipady=10)

        pin_card = ttk.LabelFrame(outer, text=' PIN ', style='Card.TLabelframe')
        pin_card.grid(row=2, column=0, sticky='ew', pady=(0, 12))
        self.pin_enable_var = tk.BooleanVar(value=pin_enabled)
        self.chk_pin_enable = ttk.Checkbutton(pin_card, text='Require PIN code', variable=self.pin_enable_var, command=self._on_pin_enable_toggle)
        self.chk_pin_enable.pack(anchor='w')
        pin_row = ttk.Frame(pin_card)
        pin_row.pack(fill='x', pady=(10, 0))
        self.lbl_pin_title = ttk.Label(pin_row, text='PIN:')
        self.lbl_pin_title.pack(side='left')
        self.pin_entry_var = tk.StringVar(value=current_pin)
        self.pin_entry = ttk.Entry(pin_row, textvariable=self.pin_entry_var, width=12, font=('Segoe UI', 11, 'bold'))
        self.pin_entry.pack(side='left', padx=(8, 10))
        self.pin_entry.bind('<KeyRelease>', self._on_pin_text_change)
        self.btn_gen_pin = ttk.Button(pin_row, text='Generate', command=self.generate_random_pin)
        self.btn_gen_pin.pack(side='left')
        self._update_pin_ui_state()

        self.lang_frame = ttk.LabelFrame(outer, text=' Settings ', style='Card.TLabelframe')
        self.lang_frame.grid(row=3, column=0, sticky='ew', pady=(0, 12))
        self.lang_frame.columnconfigure(1, weight=1)
        self.autostart_var = tk.BooleanVar(value=bool(self.settings.get('autostart')) or is_autostart_enabled())
        self.chk_autostart = ttk.Checkbutton(self.lang_frame, text='Autostart', variable=self.autostart_var, command=self._on_autostart_toggle)
        self.chk_autostart.grid(row=0, column=0, sticky='w', padx=(0, 18))
        self.btn_shortcut = ttk.Button(self.lang_frame, text='Create Desktop shortcut', command=self.request_desktop_shortcut)
        self.btn_shortcut.grid(row=0, column=1, sticky='w')
        self.btn_choose_folder = ttk.Button(self.lang_frame, text='Folder…', command=self.choose_upload_folder)
        self.btn_choose_folder.grid(row=1, column=0, sticky='w', pady=(10, 0))
        self.btn_reset_folder = ttk.Button(self.lang_frame, text='Default', command=self.reset_upload_folder)
        self.btn_reset_folder.grid(row=1, column=1, sticky='w', padx=(8, 0), pady=(10, 0))
        self.lbl_folder = ttk.Label(self.lang_frame, text='', wraplength=650)
        self.lbl_folder.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(7, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, sticky='ew')
        actions.columnconfigure(0, weight=1)
        self.btn_open_folder = ttk.Button(actions, text='Folder', command=self.open_upload_folder, style='Primary.TButton')
        self.btn_open_folder.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.btn_view_logs = ttk.Button(actions, text='Logs', command=self.open_log_window)
        self.btn_view_logs.grid(row=0, column=1, padx=4)
        self.btn_about = ttk.Button(actions, text='About', command=self.show_about)
        self.btn_about.grid(row=0, column=2, padx=4)
        self.btn_exit = ttk.Button(actions, text='Exit', command=self.quit_app)
        self.btn_exit.grid(row=0, column=3, padx=(4, 0))

    def _on_pin_enable_toggle(self):
        global pin_enabled, active_sessions
        pin_enabled = bool(self.pin_enable_var.get())
        self.settings['pin_enabled'] = pin_enabled
        save_settings(self.settings)
        active_sessions.clear()
        self._update_pin_ui_state()

    def _on_pin_text_change(self, _event=None):
        global current_pin, active_sessions
        val = self.pin_entry_var.get().strip()
        if val != current_pin:
            current_pin = val
            self.settings['pin_code'] = current_pin
            save_settings(self.settings)
            active_sessions.clear()

    def generate_random_pin(self):
        new_val = str(random.randint(1000, 9999))
        self.pin_entry_var.set(new_val)
        self._on_pin_text_change()

    def _update_pin_ui_state(self):
        state = 'normal' if self.pin_enable_var.get() else 'disabled'
        self.pin_entry.configure(state=state)
        self.btn_gen_pin.configure(state=state)

    def apply_language(self):
        self.root.title(self.t('title') + f" — {self.server_name_var.get().strip() or 'PhotoSer'}")
        self.lang_frame.configure(text=self.t('lang_frame'))
        self.chk_autostart.configure(text=self.t('autostart'))
        self.lbl_server_name.configure(text=self.t('server_name'))
        self.lbl_port.configure(text=self.t('port_label'))
        self.btn_apply_port.configure(text=self.t('port_apply'))
        self.btn_shortcut.configure(text=self.t('btn_shortcut'))
        self.status_frame.configure(text=self.t('status_frame'))
        self.qr_frame.configure(text=self.t('qr_frame'))
        self.btn_open_folder.configure(text=self.t('btn_folder'))
        self.btn_view_logs.configure(text=self.t('btn_logs'))
        self.btn_about.configure(text=self.t('btn_about'))
        self.btn_exit.configure(text=self.t('btn_exit'))
        self.btn_choose_folder.configure(text=self.t('btn_choose_folder'))
        self.btn_reset_folder.configure(text=self.t('btn_reset_folder'))
        self.chk_pin_enable.configure(text=self.t('pin_enable'))
        self.lbl_pin_title.configure(text=self.t('pin_label'))
        self.btn_gen_pin.configure(text=self.t('btn_gen_pin'))
        self._update_folder_label()

        color = {'status_running': 'green', 'status_starting': 'orange'}.get(self._status_key, 'red')
        self.lbl_status.configure(text=self.t(self._status_key), foreground=color)
        if self._server_url:
            self.lbl_url.configure(text=self.t('address', url=self._server_url))
        else:
            self.lbl_url.configure(text=self.t('address_detect'))

    def _on_language_change(self, _event=None):
        global app_language
        name = self.lang_combo.get()
        inv = {v: k for k, v in LANG_DISPLAY.items()}
        code = inv.get(name, 'ru')
        old_lang = self.lang
        self.lang = code
        app_language = code
        self.settings['language'] = code
        save_settings(self.settings)
        rename_received_folder_on_lang_change(old_lang, code, self.settings)
        self.apply_language()
        if self._server_url and (not hasattr(self.qr_label, 'image') or self.qr_label.image is None):
            self.qr_label.configure(text=self.t('qr_open', url=self._server_url))

    def request_desktop_shortcut(self):
        """Создаёт ярлык только после явного запроса пользователя."""
        if create_desktop_shortcut():
            messagebox.showinfo(
                self.t('shortcut_prompt_title'),
                self.t('shortcut_created'),
                parent=self.root
            )
        else:
            messagebox.showerror(
                self.t('error'),
                self.t('shortcut_failed'),
                parent=self.root
            )

    def apply_port_setting(self):
        value = self.port_mode_var.get().strip().lower()
        if value == 'auto':
            self.settings['manual_port'] = 0
        else:
            try:
                port = int(value)
            except ValueError:
                messagebox.showerror(self.t('error'), self.t('port_invalid'), parent=self.root)
                return
            if not 1 <= port <= 65535:
                messagebox.showerror(self.t('error'), self.t('port_invalid'), parent=self.root)
                return
            self.settings['manual_port'] = port
        save_settings(self.settings)
        # Waitress cannot be stopped safely from this GUI thread. Restarting the
        # application gives the selected port a clean server instance.
        if messagebox.askyesno(self.t('error'), self.t('port_restart', port=value), parent=self.root):
            logging.info(f"Пользователь выбрал режим порта: {value}; перезапуск приложения.")
            try:
                self.root.destroy()
            finally:
                os.execl(sys.executable, sys.executable, *sys.argv)

    def _on_server_name_change(self, _event=None):
        global app_server_name
        name = self.server_name_var.get().strip()
        if not name:
            name = 'PhotoSer'
        name = name[:64]
        self.server_name_var.set(name)
        app_server_name = name
        self.settings['server_name'] = name
        save_settings(self.settings)
        self.root.title(self.t('title') + f" — {name}")
        # Обновляем имя сервиса в mDNS без перезапуска приложения.
        if self._server_url and HAS_ZEROCONF:
            try:
                unregister_mdns()
                with config_lock:
                    port = current_port
                if port:
                    register_mdns(self.ip_address, port, app_server_name)
            except Exception as e:
                logging.error(f"Обновление имени mDNS: {e}")

    def _on_autostart_toggle(self):
        enable = bool(self.autostart_var.get())
        try:
            set_autostart(enable)
            self.settings['autostart'] = enable
            save_settings(self.settings)
        except Exception as e:
            logging.error(f"Автозапуск: {e}")
            self.autostart_var.set(not enable)
            messagebox.showerror(self.t('error'), str(e))

    def hide_to_tray(self):
        self.root.withdraw()
        if HAS_TRAY and getattr(self, '_tray_icon', None):
            try:
                self._tray_icon.visible = True
            except Exception:
                pass

    def show_from_tray(self, _icon=None, _item=None):
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, _icon=None, _item=None):
        def _do():
            try:
                if getattr(self, '_tray_icon', None):
                    self._tray_icon.stop()
            except Exception:
                pass
            udp_stop_event.set()
            unregister_mdns()
            self.root.destroy()
            os._exit(0)

        try:
            self.root.after(0, _do)
        except Exception:
            _do()

    def setup_tray(self):
        if not HAS_TRAY:
            return
        try:
            from PIL import Image as PILImage
            ensure_app_icon(ICON_FILE)
            if os.path.isfile(ICON_FILE):
                image = PILImage.open(ICON_FILE)
            else:
                image = PILImage.new('RGB', (64, 64), (0, 102, 204))

            menu = pystray.Menu(
                TrayMenuItem(self.t('tray_show'), self.show_from_tray, default=True),
                TrayMenuItem(self.t('btn_folder'), self.open_last_received),
                TrayMenuItem(self.t('tray_exit'), self.quit_app)
            )
            self._tray_icon = pystray.Icon("PhotoSer", image, self.t('tray_tip'), menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception as e:
            logging.error(f"Трей: {e}")
            self._tray_icon = None

    def _update_folder_label(self):
        global UPLOAD_FOLDER
        parent = (self.settings.get('storage_parent') or '').strip() or os.path.expanduser('~')
        self.lbl_folder.configure(
            text=self.t('folder_path', path=UPLOAD_FOLDER or build_received_path(parent, self.lang))
        )

    def _maybe_first_run(self):
        if self.settings.get('first_run_done') and (self.settings.get('storage_parent') or '').strip():
            apply_upload_folder_from_settings(self.settings)
            self._update_folder_label()
            return
        self._prompt_storage_parent(first_run=True)

    def _prompt_storage_parent(self, first_run: bool = False):
        name = received_folder_name(self.lang)
        messagebox.showinfo(self.t('first_run_title'), self.t('first_run_msg', name=name), parent=self.root)
        initial = (self.settings.get('storage_parent') or '').strip() or os.path.expanduser('~')
        path = filedialog.askdirectory(parent=self.root, initialdir=initial)
        if not path:
            if first_run:
                path = os.path.expanduser('~')
            else:
                return
        self.settings['storage_parent'] = path
        self.settings['first_run_done'] = True
        save_settings(self.settings)
        apply_upload_folder_from_settings(self.settings)
        self._update_folder_label()

        if first_run:
            if messagebox.askyesno(
                self.t('shortcut_prompt_title'),
                self.t('shortcut_prompt_msg'),
                parent=self.root
            ):
                self.request_desktop_shortcut()

    def choose_upload_folder(self):
        self._prompt_storage_parent(first_run=False)

    def reset_upload_folder(self):
        self.settings['storage_parent'] = os.path.expanduser('~')
        self.settings['first_run_done'] = True
        save_settings(self.settings)
        apply_upload_folder_from_settings(self.settings)
        self._update_folder_label()

    def on_files_received(self, count: int, session_dir: str):
        self._last_notify_folder = session_dir
        if count == 1:
            body = self.t('notify_one', path=session_dir)
        else:
            body = self.t('notify_body', n=count, path=session_dir)
        title = self.t('notify_title')

        def _show():
            if self._tray_icon is not None:
                try:
                    self._tray_icon.notify(body, title)
                except Exception as e:
                    logging.error(f"tray.notify: {e}")
            self._show_clickable_toast(title, body, session_dir)

        try:
            self.root.after(0, _show)
        except Exception:
            _show()

    def _show_clickable_toast(self, title: str, body: str, folder: str):
        toast = tk.Toplevel(self.root)
        toast.title(title)
        toast.attributes('-topmost', True)
        toast.resizable(False, False)
        frm = ttk.Frame(toast, padding=12)
        frm.pack(fill='both', expand=True)
        ttk.Label(frm, text=title, font=('Helvetica', 11, 'bold')).pack(anchor='w')
        ttk.Label(frm, text=body, wraplength=320, justify='left').pack(anchor='w', pady=(6, 10))

        def open_and_close(_event=None):
            open_path_in_os(folder)
            try:
                toast.destroy()
            except Exception:
                pass

        toast.bind('<Button-1>', open_and_close)
        frm.bind('<Button-1>', open_and_close)
        for w in frm.winfo_children():
            w.bind('<Button-1>', open_and_close)

        toast.update_idletasks()
        w, h = toast.winfo_reqwidth(), toast.winfo_reqheight()
        sw, sh = toast.winfo_screenwidth(), toast.winfo_screenheight()
        toast.geometry(f"+{sw - w - 24}+{sh - h - 80}")
        toast.after(12000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def open_last_received(self, _icon=None, _item=None):
        folder = self._last_notify_folder or LAST_SESSION_FOLDER or UPLOAD_FOLDER
        open_path_in_os(folder)

    def open_upload_folder(self):
        open_path_in_os(UPLOAD_FOLDER)

    def open_log_window(self):
        log_win = tk.Toplevel(self.root)
        log_win.title(self.t('logs_title'))
        log_win.geometry("600x400")
        txt = scrolledtext.ScrolledText(log_win, wrap=tk.WORD)
        txt.pack(fill='both', expand=True, padx=5, pady=5)

        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
                    txt.insert(tk.END, f.read())
                    txt.see(tk.END)
            except Exception as e:
                txt.insert(tk.END, f"{e}")
        else:
            txt.insert(tk.END, self.t('logs_missing'))
        txt.config(state=tk.DISABLED)

    def _show_license_window(self, parent=None):
        parent = parent or self.root
        win = tk.Toplevel(parent)
        win.title(self.t('about_license'))
        win.geometry("680x420")
        win.transient(parent)
        win.grab_set()
        win.focus_set()

        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=('Consolas', 10))
        txt.pack(fill='both', expand=True, padx=8, pady=8)
        txt.insert(tk.END, ABOUT_LICENSE_NOTICE.get(self.lang, ABOUT_LICENSE_NOTICE['en']))
        txt.config(state=tk.DISABLED)

        def close_window():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()
            try:
                parent.grab_set()
                parent.focus_set()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", close_window)
        ttk.Button(win, text=self.t('about_close'), command=close_window).pack(pady=(0, 8))

    def _show_third_party_window(self, parent=None):
        parent = parent or self.root
        win = tk.Toplevel(parent)
        win.title(self.t('about_third_party'))
        win.geometry("680x500")
        win.transient(parent)
        win.grab_set()
        win.focus_set()

        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=('Consolas', 10))
        txt.pack(fill='both', expand=True, padx=8, pady=8)
        txt.insert(tk.END, THIRD_PARTY_LICENSES.get(self.lang, THIRD_PARTY_LICENSES['en']))
        txt.config(state=tk.DISABLED)

        def close_window():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()
            try:
                parent.grab_set()
                parent.focus_set()
            except tk.TclError:
                pass

        win.protocol("WM_DELETE_WINDOW", close_window)
        ttk.Button(win, text=self.t('about_close'), command=close_window).pack(pady=(0, 8))

    def show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title(self.t('about_title'))
        about_win.geometry("500x300")
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()

        frame = ttk.Frame(about_win, padding=20)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text='PhotoSer', font=('TkDefaultFont', 20, 'bold')).pack(pady=(0, 4))
        ttk.Label(frame, text='Version 1.0').pack()
        ttk.Label(frame, text='Copyright (C) 2026 JemikiVa').pack(pady=(2, 16))
        ttk.Label(frame, text='GNU General Public License v3 (GPLv3)', font=('TkDefaultFont', 11, 'bold')).pack(pady=(0, 6))
        ttk.Label(
            frame,
            text={
                'ru': 'Свободное программное обеспечение без дополнительных ограничений.',
                'en': 'Free software with no additional restrictions.',
                'lv': 'Brīva programmatūra bez papildu ierobežojumiem.',
                'de': 'Freie Software ohne zusätzliche Einschränkungen.',
            }.get(self.lang, 'Free software with no additional restrictions.'),
            justify=tk.CENTER,
            wraplength=430
        ).pack(pady=(0, 18))

        buttons = ttk.Frame(frame)
        buttons.pack(pady=4)
        ttk.Button(buttons, text=self.t('about_license'), command=lambda: self._show_license_window(about_win)).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons, text=self.t('about_third_party'), command=lambda: self._show_third_party_window(about_win)).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons, text=self.t('about_close'), command=about_win.destroy).pack(side=tk.LEFT, padx=5)

    def update_qr_code(self, url: str):
        if not HAS_QRCODE:
            self.qr_label.config(text=self.t('qr_open', url=url))
            return
        try:
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            if HAS_IMAGETK:
                photo = ImageTk.PhotoImage(img)
            else:
                buffered = BytesIO()
                img.save(buffered, format="GIF")
                photo = tk.PhotoImage(data=buffered.getvalue())

            self.qr_label.config(image=photo, text="")
            self.qr_label.image = photo
        except Exception as e:
            logging.error(f"Ошибка генерации QR-кода: {e}")
            self.qr_label.config(text=self.t('qr_open', url=url))

    def start_server_pipeline(self):
        manual_port = self.settings.get('manual_port', 0)
        try:
            manual_port = int(manual_port or 0)
        except (TypeError, ValueError):
            manual_port = 0

        if manual_port:
            target_port = manual_port if find_available_port("0.0.0.0", [manual_port]) == manual_port else 0
            if target_port == 0:
                logging.error(f"Выбранный пользователем порт {manual_port} занят или недоступен.")
        else:
            target_port = find_available_port("0.0.0.0", PORT_CANDIDATES)
            logging.info(f"Автоматический выбор порта: {target_port}")

        if target_port == 0:
            self._status_key = "status_error_ports"
            self.lbl_status.config(text=self.t('status_error_ports'), foreground="red")
            messagebox.showerror(self.t('error'), self.t('ports_error'))
            return

        with config_lock:
            global current_port
            current_port = target_port

        url = f"http://{self.ip_address}" if target_port == 80 else f"http://{self.ip_address}:{target_port}"
        self._server_url = url
        server_ready = threading.Event()
        server_failed = threading.Event()

        def run_server():
            try:
                if HAS_WAITRESS:
                    serve(app, host='0.0.0.0', port=target_port, threads=8)
                else:
                    app.run(host='0.0.0.0', port=target_port, debug=False, use_reloader=False)
            except Exception as e:
                logging.critical(f"Сбой работы HTTP сервера на порту {target_port}: {e}")
                server_failed.set()
                self.root.after(0, lambda: self._server_start_failed(str(e), target_port))

        threading.Thread(target=run_server, daemon=True, name="PhotoSer-HTTP").start()

        def wait_until_ready():
            import time as _time
            health_url = f"http://127.0.0.1:{target_port}/api/health"
            deadline = _time.monotonic() + 8.0
            while _time.monotonic() < deadline and not server_failed.is_set():
                try:
                    with urllib.request.urlopen(health_url, timeout=0.7) as response:
                        body = response.read().decode('utf-8', errors='replace')
                        if response.status == 200 and 'PhotoSer' in body and '"status":"ok"' in body.replace(' ', ''):
                            server_ready.set()
                            break
                except Exception:
                    pass
                _time.sleep(0.15)

            if server_ready.is_set():
                self.root.after(0, lambda: self._server_ready(url, target_port))
            elif not server_failed.is_set():
                logging.critical(f"HTTP сервер не подтвердил готовность на порту {target_port} за 8 секунд.")
                self.root.after(0, lambda: self._server_start_failed("health check timeout", target_port))

        threading.Thread(target=wait_until_ready, daemon=True, name="PhotoSer-HealthCheck").start()

    def _server_ready(self, url: str, target_port: int):
        self._status_key = "status_running"
        self.lbl_status.config(text=self.t('status_running'), foreground="green")
        self.lbl_url.config(text=self.t('address', url=url))
        self.update_qr_code(url)
        engine = "Waitress" if HAS_WAITRESS else "Flask"
        logging.info(f"Сервер PhotoSer ({engine}) подтверждён: {url}")
        if not getattr(self, '_discovery_started', False):
            self._discovery_started = True
            threading.Thread(target=udp_broadcast_worker, args=(udp_stop_event,), daemon=True, name="PhotoSer-UDP").start()
            register_mdns(self.ip_address, target_port, app_server_name)

    def _server_start_failed(self, reason: str, target_port: int):
        self._status_key = "status_down"
        self.lbl_status.config(text=self.t('status_down'), foreground="red")
        self.lbl_url.config(text=self.t('address', url="—"))
        self.update_qr_code("")
        logging.critical(f"PhotoSer не запустил HTTP-сервер на порту {target_port}: {reason}")
        messagebox.showerror(
            self.t('error'),
            self.t('server_start_failed', port=target_port)
        )


# ==============================================================================
# ТОЧКА ВХОДА И ЗАВЕРШЕНИЕ
# ==============================================================================

def main():
    if not check_single_instance():
        root = tk.Tk()
        root.withdraw()
        settings = load_settings()
        lang = settings.get('language', 'ru')
        msg = UI_STRINGS.get(lang, UI_STRINGS['ru']).get('already_running', 'PhotoSer is already running!')
        title = UI_STRINGS.get(lang, UI_STRINGS['ru']).get('error', 'Error')
        messagebox.showwarning(title, msg)
        root.destroy()
        sys.exit(0)

    root = tk.Tk()
    gui = PhotoSerGUI(root)

    def on_close():
        gui.hide_to_tray()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == '__main__':
    main()

