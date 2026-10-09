import time
from gpiozero import Button

# Перелік BCM пінів для тестування
PINS = [16, 20, 21, 26]

buttons = {}

def on_press(pin_num):
    print(f"[ПОДІЯ] -> Кнопку BCM {pin_num} НАТИСНУТО (стан: LOW / 0)")

def on_release(pin_num):
    print(f"[ПОДІЯ] <- Кнопку BCM {pin_num} ВІДПУЩЕНО (стан: HIGH / 1)")

print("=" * 55)
print("  ТЕСТУВАННЯ КНОПОК GPIO (BCM 16, 20, 21, 26)")
print("=" * 55)

# Ініціалізація кнопок з внутрішньою підтяжкою Pull-Up
for pin in PINS:
    try:
        # f=pin фіксує значення аргументу у лямбда-функції
        btn = Button(pin, pull_up=True, bounce_time=0.1)
        btn.when_pressed = (lambda f=pin: on_press(f))
        btn.when_released = (lambda f=pin: on_release(f))
        buttons[pin] = btn
        
        # Перевірка початкового стану
        initial_state = "HIGH (1)" if btn.is_pressed else "HIGH (1)" # is_pressed == True коли LOW при pull_up
        raw_level = "LOW (0)" if btn.is_pressed else "HIGH (1)"
        print(f"Ініціалізовано BCM {pin:2d} | Початковий рівень: {raw_level}")
    except Exception as e:
        print(f"Помилка ініціалізації BCM {pin}: {e}")

print("-" * 55)
print("Натискайте кнопки. Натисніть Ctrl+C для виходу.\n")

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nТестування завершено.")
