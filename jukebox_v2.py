import subprocess
import os
import time
import glob
from gpiozero import Button

# --- Налаштування шляхів та папок ---
HOME_DIR = "/home/pi/movies"
DIR_LIST = ['bandura', 'tour', 'tech', 'history', 'music']

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


def get_playlist(folder_name):
    """Отримання відсортованого списку файлів у папці"""
    folder_path = os.path.join(HOME_DIR, folder_name)
    if not os.path.exists(folder_path):
        return []
    return sorted(
        glob.glob(os.path.join(folder_path, "*.mp4")) +
        glob.glob(os.path.join(folder_path, "*.mkv"))
    )


# --- Обробники навігації ---

def action_dir_next():
    global current_dir_index, current_video_index, switch_requested
    print("\n[EVENT] -> Наступна папка (BCM 16)")
    stop_all()
    current_dir_index = (current_dir_index + 1) % len(DIR_LIST)
    current_video_index = 0
    switch_requested = True


def action_dir_prev():
    global current_dir_index, current_video_index, switch_requested
    print("\n[EVENT] <- Попередня папка (BCM 20)")
    stop_all()
    current_dir_index = (current_dir_index - 1) % len(DIR_LIST)
    current_video_index = 0
    switch_requested = True


def action_vid_next():
    global current_video_index, switch_requested
    folder = DIR_LIST[current_dir_index]
    playlist = get_playlist(folder)
    
    if not playlist:
        return
        
    print("\n[EVENT] >> Наступне відео (BCM 21)")
    stop_all()
    current_video_index = (current_video_index + 1) % len(playlist)
    switch_requested = True


def action_vid_prev():
    global current_video_index, switch_requested
    folder = DIR_LIST[current_dir_index]
    playlist = get_playlist(folder)
    
    if not playlist:
        return

    print("\n[EVENT] << Попереднє відео (BCM 26)")
    stop_all()
    current_video_index = (current_video_index - 1) % len(playlist)
    switch_requested = True


# --- Ініціалізація кнопок ---
prepare_screen()

# Збільшено bounce_time до 0.3с для запобігання хибним наводкам між 20 і 21
btn_dir_next = Button(PIN_DIR_NEXT, pull_up=True, bounce_time=0.3)
btn_dir_next.when_pressed = action_dir_next

btn_dir_prev = Button(PIN_DIR_PREV, pull_up=True, bounce_time=0.3)
btn_dir_prev.when_pressed = action_dir_prev

btn_vid_next = Button(PIN_VID_NEXT, pull_up=True, bounce_time=0.3)
btn_vid_next.when_pressed = action_vid_next

btn_vid_prev = Button(PIN_VID_PREV, pull_up=True, bounce_time=0.3)
btn_vid_prev.when_pressed = action_vid_prev

print(f"Ініціалізовано 4 кнопки (BCM 16, 20, 21, 26)")


def run_video(path, total_videos):
    global switch_requested, current_proc
    
    if not os.path.exists(path):
        print(f"Помилка: Файл {path} не знайдено")
        return False

    folder_name = DIR_LIST[current_dir_index].upper()
    osd_message = f"Папка: {folder_name} ({current_video_index + 1}/{total_videos})"

    cmd = [
        "mpv",
        "--fullscreen",
        "--no-terminal",
        "--quiet",
        "--vo=gpu",
        "--gpu-context=drm",
        "--hwdec=auto",
        f"--osd-msg1={osd_message}",
        "--osd-duration=2500",
        "--osd-font-size=35",
        "--osd-align-x=left",
        "--osd-align-y=top",
        path
    ]
    
    print(f"Відтворення [{folder_name}]: {os.path.basename(path)}")
    
    current_proc = subprocess.Popen(
        cmd, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL
    )

    time.sleep(0.5)

    while True:
        if switch_requested:
            if current_proc and current_proc.poll() is None:
                current_proc.terminate()
                try:
                    current_proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    current_proc.kill()
            current_proc = None
            return True

        poll_result = current_proc.poll() if current_proc else 0
        if poll_result is not None:
            break

        time.sleep(0.1)

    current_proc = None
    return False


# --- Головний цикл ---
try:
    stop_all()
    print("\nСистема готова. Запуск відтворення...")
    
    while True:
        folder = DIR_LIST[current_dir_index]
        playlist = get_playlist(folder)
        
        if not playlist:
            print(f"Порожня папка: {folder}. Перехід далі...")
            current_dir_index = (current_dir_index + 1) % len(DIR_LIST)
            current_video_index = 0
            time.sleep(1)
            continue

        if current_video_index >= len(playlist):
            current_video_index = 0

        current_file = playlist[current_video_index]
        switch_requested = False
        
        interrupted = run_video(current_file, len(playlist))
        
        if not interrupted:
            current_video_index += 1
            if current_video_index >= len(playlist):
                current_video_index = 0
                current_dir_index = (current_dir_index + 1) % len(DIR_LIST)

except KeyboardInterrupt:
    stop_all()
    print("\nВимкнення...")
