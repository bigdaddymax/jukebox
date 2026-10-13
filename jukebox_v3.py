import subprocess
import os
import time
import glob
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from gpiozero import Button

# --- Налаштування шляхів та порту ---
HOME_DIR = "/home/pi/movies"
WEB_PORT = 8080

# --- Призначення 4 кнопок (BCM 16, 20, 21, 26) ---
PIN_DIR_NEXT = 16   # Наступна папка
PIN_DIR_PREV = 20   # Попередня папка
PIN_VID_NEXT = 21   # Наступне відео
PIN_VID_PREV = 26   # Попереднє відео

# --- Глобальний стан ---
current_dir_index = 0
current_video_index = 0

switch_requested = False
current_proc = None
state_lock = threading.Lock()


def prepare_screen():
    os.system('setterm -foreground black -cursor off')
    os.system('clear')


def stop_all():
    global current_proc
    if current_proc and current_proc.poll() is None:
        try:
            current_proc.terminate()
            current_proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            current_proc.kill()
    current_proc = None

    subprocess.run(["sudo", "killall", "-9", "mpv"], 
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.2)


def get_directories():
    if not os.path.exists(HOME_DIR):
        return []
    dirs = [
        d for d in os.listdir(HOME_DIR) 
        if os.path.isdir(os.path.join(HOME_DIR, d)) and not d.startswith('.')
    ]
    return sorted(dirs)


def get_playlist(folder_name):
    folder_path = os.path.join(HOME_DIR, folder_name)
    if not os.path.exists(folder_path):
        return []
    return sorted(
        glob.glob(os.path.join(folder_path, "*.mp4")) +
        glob.glob(os.path.join(folder_path, "*.mkv"))
    )


def generate_thumbnail_if_missing(video_path):
    base, _ = os.path.splitext(video_path)
    thumb_path = base + ".jpg"
    
    if not os.path.exists(thumb_path):
        cmd = [
            "ffmpeg", "-ss", "00:00:03", "-i", video_path,
            "-vframes", "1", "-q:v", "3", "-vf", "scale=320:-1",
            thumb_path, "-y"
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass


# --- Обробники навігації ---

def action_dir_next():
    global current_dir_index, current_video_index, switch_requested
    with state_lock:
        dir_list = get_directories()
        if not dir_list:
            return
        print("\n[EVENT] -> Наступна папка (BCM 16)")
        stop_all()
        current_dir_index = (current_dir_index + 1) % len(dir_list)
        current_video_index = 0
        switch_requested = True


def action_dir_prev():
    global current_dir_index, current_video_index, switch_requested
    with state_lock:
        dir_list = get_directories()
        if not dir_list:
            return
        print("\n[EVENT] <- Попередня папка (BCM 20)")
        stop_all()
        current_dir_index = (current_dir_index - 1) % len(dir_list)
        current_video_index = 0
        switch_requested = True


def action_vid_next():
    global current_video_index, switch_requested
    with state_lock:
        dir_list = get_directories()
        if not dir_list or current_dir_index >= len(dir_list):
            return
        folder = dir_list[current_dir_index]
        playlist = get_playlist(folder)
        if not playlist:
            return
        print("\n[EVENT] >> Наступне відео (BCM 21)")
        stop_all()
        current_video_index = (current_video_index + 1) % len(playlist)
        switch_requested = True


def action_vid_prev():
    global current_video_index, switch_requested
    with state_lock:
        dir_list = get_directories()
        if not dir_list or current_dir_index >= len(dir_list):
            return
        folder = dir_list[current_dir_index]
        playlist = get_playlist(folder)
        if not playlist:
            return
        print("\n[EVENT] << Попереднє відео (BCM 26)")
        stop_all()
        current_video_index = (current_video_index - 1) % len(playlist)
        switch_requested = True


# --- Вебсервер ---

class JukeboxWebHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global current_dir_index, current_video_index, switch_requested
        
        parsed_path = urlparse(self.path)
        query = parse_qs(parsed_path.query)

        if parsed_path.path == '/thumb':
            img_path = query.get('path', [None])[0]
            if img_path and os.path.exists(img_path) and img_path.startswith(HOME_DIR):
                try:
                    with open(img_path, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception:
                    pass
            self.send_response(404)
            self.end_headers()
            return

        if parsed_path.path == '/status':
            import json
            with state_lock:
                dir_list = get_directories()
                current_folder = dir_list[current_dir_index] if dir_list and current_dir_index < len(dir_list) else ""
                playlist = get_playlist(current_folder) if current_folder else []
                current_file_path = playlist[current_video_index] if playlist and current_video_index < len(playlist) else ""
                current_file_name = os.path.basename(current_file_path) if current_file_path else "Нічого не грає"
                
                base, _ = os.path.splitext(current_file_path)
                thumb_p = base + ".jpg" if current_file_path else ""
                has_thumb = os.path.exists(thumb_p)

            status_data = {
                "folder": current_folder,
                "file": current_file_name,
                "thumb": f"/thumb?path={thumb_p}" if has_thumb else "",
                "index": current_video_index + 1,
                "total": len(playlist)
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
            return

        if parsed_path.path == '/play':
            target_folder = query.get('folder', [None])[0]
            target_file = query.get('file', [None])[0]

            with state_lock:
                dir_list = get_directories()
                if target_folder in dir_list:
                    playlist = get_playlist(target_folder)
                    full_target_path = os.path.join(HOME_DIR, target_folder, target_file)
                    if full_target_path in playlist:
                        print(f"\n[WEB EVENT] Запуск через веб: {target_folder}/{target_file}")
                        stop_all()
                        current_dir_index = dir_list.index(target_folder)
                        current_video_index = playlist.index(full_target_path)
                        switch_requested = True

            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

        dir_list = get_directories()
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Raspberry Pi Jukebox</title>
            <style>
                body { font-family: Arial, sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
                h1 { color: #ffffff; text-align: center; margin-top: 5px; }
                
                .now-playing { background: #1f1b24; border: 2px solid #bb86fc; border-radius: 10px; padding: 15px; margin-bottom: 25px; display: flex; align-items: center; gap: 15px; box-shadow: 0 4px 10px rgba(187,134,252,0.2); }
                .np-thumb { width: 120px; height: 75px; background: #000; border-radius: 4px; overflow: hidden; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
                .np-thumb img { width: 100%; height: 100%; object-fit: cover; }
                .np-info h2 { margin: 0 0 5px 0; font-size: 18px; color: #bb86fc; }
                .np-info p { margin: 0; font-size: 14px; color: #b0bec5; word-break: break-word; }

                .folder { background: #1e1e1e; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
                h3 { margin-top: 0; color: #4CAF50; border-bottom: 1px solid #333; padding-bottom: 8px; }
                
                .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; padding: 0; list-style: none; }
                .card { background: #2c2c2c; border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; transition: 0.2s; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
                .card:hover { transform: translateY(-3px); background: #3700b3; }
                .card a { color: #fff; text-decoration: none; display: flex; flex-direction: column; height: 100%; }
                .thumb-container { width: 100%; height: 110px; background: #000; position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center; }
                .thumb-container img { width: 100%; height: 100%; object-fit: cover; }
                .no-thumb { color: #777; font-size: 12px; }
                .title { padding: 10px; font-size: 13px; word-break: break-word; flex-grow: 1; }
            </style>
        </head>
        <body>
            <h1>🎬 Jukebox Control</h1>

            <div class="now-playing" id="np-block">
                <div class="np-thumb" id="np-thumb-box"><span>Завантаження...</span></div>
                <div class="np-info">
                    <h2>▶ Зараз грає</h2>
                    <p id="np-details">Отримання даних...</p>
                </div>
            </div>
        """

        if not dir_list:
            html += "<p>Папок не знайдено.</p>"
        else:
            for folder in dir_list:
                html += f"<div class='folder'><h3>📁 {folder}</h3><ul class='grid'>"
                playlist = get_playlist(folder)
                if not playlist:
                    html += "<li style='color: #777;'>Папка порожня</li>"
                else:
                    for file_path in playlist:
                        file_name = os.path.basename(file_path)
                        base, _ = os.path.splitext(file_path)
                        thumb_path = base + ".jpg"
                        
                        if not os.path.exists(thumb_path):
                            generate_thumbnail_if_missing(file_path)

                        html += "<li class='card'>"
                        html += f"<a href='/play?folder={folder}&file={file_name}'>"
                        html += "<div class='thumb-container'>"
                        if os.path.exists(thumb_path):
                            html += f"<img src='/thumb?path={thumb_path}' loading='lazy'>"
                        else:
                            html += "<span class='no-thumb'>▶ Video</span>"
                        html += f"</div><div class='title'>{file_name}</div></a>"
                        html += "</li>"
                html += "</ul></div>"

        html += """
            <script>
                function updateStatus() {
                    fetch('/status')
                        .then(response => response.json())
                        .then(data => {
                            let details = `<b>Папка:</b> ${data.folder.toUpperCase()} &nbsp;|&nbsp; <b>Файл:</b> ${data.file} (${data.index}/${data.total})`;
                            document.getElementById('np-details').innerHTML = details;
                            
                            let thumbBox = document.getElementById('np-thumb-box');
                            if (data.thumb) {
                                thumbBox.innerHTML = `<img src="${data.thumb}">`;
                            } else {
                                thumbBox.innerHTML = `<span class="no-thumb">Video</span>`;
                            }
                        })
                        .catch(err => console.log('Помилка оновлення статусу'));
                }
                setInterval(updateStatus, 2500);
                updateStatus();
            </script>
        </body></html>
        """
        self.wfile.write(html.encode('utf-8'))


def start_web_server():
    server = HTTPServer(('0.0.0.0', WEB_PORT), JukeboxWebHandler)
    server.serve_forever()


# --- Ініціалізація кнопок ---
prepare_screen()

btn_dir_next = Button(PIN_DIR_NEXT, pull_up=True, bounce_time=0.3)
btn_dir_next.when_pressed = action_dir_next

btn_dir_prev = Button(PIN_DIR_PREV, pull_up=True, bounce_time=0.3)
btn_dir_prev.when_pressed = action_dir_prev

btn_vid_next = Button(PIN_VID_NEXT, pull_up=True, bounce_time=0.3)
btn_vid_next.when_pressed = action_vid_next

btn_vid_prev = Button(PIN_VID_PREV, pull_up=True, bounce_time=0.3)
btn_vid_prev.when_pressed = action_vid_prev

print(f"Ініціалізовано 4 кнопки (BCM 16, 20, 21, 26)")

web_thread = threading.Thread(target=start_web_server, daemon=True)
web_thread.start()
print(f"Вебсервер запущено на порту {WEB_PORT}")


def run_video(folder_name, path, total_videos):
    global switch_requested, current_proc
    
    if not os.path.exists(path):
        print(f"Помилка: Файл {path} не знайдено")
        time.sleep(1)
        return False

    osd_message = f"Папка: {folder_name.upper()} ({current_video_index + 1}/{total_videos})"

    cmd = [
        "mpv",
        "--fullscreen",
        "--no-terminal",
        "--quiet",
        "--vo=gpu",
        "--gpu-context=drm",
        "--hwdec=auto",
        "--ao=null",
        f"--osd-msg1={osd_message}",
        "--osd-duration=2500",
        "--osd-font-size=35",
        "--osd-align-x=left",
        "--osd-align-y=top",
        path
    ]
    
    print(f"Відтворення [{folder_name.upper()}]: {os.path.basename(path)}")
    
    with state_lock:
        switch_requested = False
        current_proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=None  
        )

    start_time = time.time()
    time.sleep(0.8)

    while True:
        with state_lock:
            if switch_requested:
                if current_proc and current_proc.poll() is None:
                    current_proc.terminate()
                    try:
                        current_proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        current_proc.kill()
                current_proc = None
                return True

            if current_proc and current_proc.poll() is not None:
                exit_code = current_proc.poll()
                run_duration = time.time() - start_time
                current_proc = None

                if run_duration < 1.5:
                    print(f"[ПОПЕРЕДЖЕННЯ] mpv завершився занадто швидко (код {exit_code}). Пауза 2 сек...")
                    time.sleep(2)
                
                return False

        time.sleep(0.1)


# --- Головний цикл ---
try:
    stop_all()
    print("\nСистема готова. Запуск відтворення...")
    
    while True:
        with state_lock:
            dir_list = get_directories()
        
        if not dir_list:
            print(f"Увага: Не знайдено піддиректорій у {HOME_DIR}. Очікування...")
            time.sleep(3)
            continue

        with state_lock:
            if current_dir_index >= len(dir_list):
                current_dir_index = 0
            folder = dir_list[current_dir_index]
            playlist = get_playlist(folder)
        
        if not playlist:
            print(f"Порожня папка: {folder}. Перехід далі...")
            with state_lock:
                current_dir_index = (current_dir_index + 1) % len(dir_list)
                current_video_index = 0
            time.sleep(1)
            continue

        with state_lock:
            if current_video_index >= len(playlist):
                current_video_index = 0
            current_file = playlist[current_video_index]
            total_vids = len(playlist)

        interrupted = run_video(folder, current_file, total_vids)
        
        if not interrupted:
            with state_lock:
                current_video_index += 1
                if current_video_index >= len(playlist):
                    current_video_index = 0
                    dir_list = get_directories()
                    if dir_list:
                        current_dir_index = (current_dir_index + 1) % len(dir_list)

except KeyboardInterrupt:
    stop_all()
    print("\nВимкнення...")
