import sys

from backend import run_console


def run_gui() -> None:
    try:
        from PySide6.QtWidgets import QApplication
        from app_gui import MainWindow
    except ModuleNotFoundError:
        print(
            "Ошибка: не найден модуль PySide6.\n"
            "Чтобы запустить графический интерфейс, установите PySide6:\n"
            "    pip install PySide6\n"
        )
        return

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def main() -> None:
    print("Выберите режим запуска:")
    print("1 — Консольный (Задание 1)")
    print("2 — Графический (Задание 2)")
    choice = input("Введите 1 или 2: ").strip().lower()

    if choice in {"1", "к", "консоль", "console"}:
        run_console()
    elif choice in {"2", "г", "gui", "интерфейс"}:
        run_gui()
    else:
        print("Неверный выбор. Введите 1 (консоль) или 2 (графика).")


if __name__ == "__main__":
    main()
