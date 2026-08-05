import subprocess
import os
import time
import glob
from gpiozero import Button
from signal import pause

# --- Налаштування ---
VIDEO_BIN = "/home/pi/userland/host_applications/linux/apps/hello_pi/hello_video/hello_video.bin"
RPIPLAY_BIN = "/home/pi/RPiPlay/build/rpiplay"
HOME_DIR = "/home/pi/movies"
ENV = os.environ.copy()
ENV["LD_LIBRARY_PATH"] = "/opt/vc/lib"

# Твоя нумерація BCM пінів
# btn1=14, btn2=15, btn3=18, btn4=16, btn5=20, btn6=21
DIRS_MAP = {
    14: 'bandura',
    15: 'tour',
    18: 'tech',
    16: 'history',
    20: 'music',
    21: 'usb' # AirPlay режим
}

DIR_LIST = ['bandura', 'tour', 'tech', 'history', 'music', 'usb']
AIRPLAY_PIN = 21

# Глобальні прапорці
current_dir_index = 0
is_airplay_mode = False
interrupt_video = False

def prepare_screen():
    # Робимо колір тексту чорним (ідентичним до фону)
    # Тепер навіть якщо текст буде виводитись, його не буде видно
    os.system('setterm -foreground black -cursor off')
    os.system('clear')


def stop_all():
    """Очищення всіх медіа-процесів"""
    subprocess.run(["sudo", "killall", "-9", "hello_video.bin", "aplay", "rpiplay"], 
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    time.sleep(0.3)

def start_airplay():
    global is_airplay_mode, interrupt_video
    print("\n[EVENT] Натиснуто USB -> Вмикаю AirPlay")
    stop_all()
    is_airplay_mode = True
    interrupt_video = True
    # Запускаємо сервер
    subprocess.Popen([RPIPLAY_BIN, "-n", "Jukebox", "-b", "on", "-vr", "rpi", "-l"], env=ENV)

def switch_folder(folder_name):
    global is_airplay_mode, interrupt_video, current_dir_index
    print(f"\n[EVENT] Натиснуто кнопку папки -> {folder_name}")
    stop_all()
    is_airplay_mode = False
    interrupt_video = True
    current_dir_index = DIR_LIST.index(folder_name)

# --- Ініціалізація кнопок з Pull-Up ---
btn_objects = []

prepare_screen()

for pin, folder in DIRS_MAP.items():
    # pull_up=True вмикає внутрішній резистор до 3.3V
    btn = Button(pin, pull_up=True, bounce_time=0.2)
    
    if pin == AIRPLAY_PIN:
        btn.when_pressed = start_airplay
    else:
        # Використовуємо callback з параметром для збереження значення folder
        btn.when_pressed = lambda f=folder: switch_folder(f)
    
    btn_objects.append(btn)
    print(f"Ініціалізовано BCM {pin} (Pull-Up) -> {folder}")

def run_video(path):
    global interrupt_video
    audio = path.replace(".h264", ".wav")
    
    if not os.path.exists(path) or not os.path.exists(audio):
        print(f"Помилка: Не знайдено відео або звук для {path}")
        return False

    v_proc = subprocess.Popen([VIDEO_BIN, path], env=ENV)
    a_proc = subprocess.Popen(["aplay", "-D", "hw:0,0", audio])
    
    interrupt_video = False
    while a_proc.poll() is None:
        if interrupt_video or is_airplay_mode:
            v_proc.terminate()
            a_proc.terminate()
            return True
        time.sleep(0.1)
    
    v_proc.terminate()
    return False

# --- Головний цикл ---
try:
    stop_all()
    print("\nСистема готова. Очікування кнопок або запуск циклу...")
    
    while True:
        if is_airplay_mode:
            # У режимі AirPlay нічого не робимо, чекаємо переривання іншою кнопкою
            time.sleep(0.5)
            continue
            
        folder = DIR_LIST[current_dir_index]
        playlist = sorted(glob.glob(os.path.join(HOME_DIR, folder, "*.h264")))
        
        if not playlist:
            print(f"Порожня папка: {folder}. Перехід до наступної...")
            current_dir_index = (current_dir_index + 1) % len(DIR_LIST)
            time.sleep(1)
            continue

        for movie in playlist:
            if is_airplay_mode: break
            interrupted = run_video(movie)
            if interrupted: break
        
        if not interrupt_video and not is_airplay_mode:
            current_dir_index = (current_dir_index + 1) % len(DIR_LIST)

except KeyboardInterrupt:
    stop_all()
    print("\nВимкнення...")
