import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QWidget,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)

from backend import PSApp

TYPE_MAP = {"Изделие": "I", "Узел": "U", "Деталь": "D"}
TYPE_RU = {"I": "Изделие", "U": "Узел", "D": "Деталь"}


def show_error(parent, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


class TreeWindow(QMainWindow):
    def __init__(self, text: str):
        super().__init__()
        self.setWindowTitle("Дерево структуры")
        self.resize(600, 500)

        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setText(text)
        self.setCentralWidget(edit)


class SpecWindow(QMainWindow):
    def __init__(self, backend: PSApp):
        super().__init__()
        self.backend = backend

        self.setWindowTitle("Спецификация")
        self.resize(750, 450)

        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        layout.addLayout(top)

        top.addWidget(QLabel("Компонент A:"))
        self.cb_a = QComboBox()
        top.addWidget(self.cb_a, 1)

        btn_refresh = QPushButton("Обновить список")
        btn_refresh.clicked.connect(self.reload_a_list)
        top.addWidget(btn_refresh)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Компонент B", "Тип", "Кол-во"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        layout.addLayout(bottom)

        btn_load = QPushButton("Загрузить спецификацию")
        btn_load.clicked.connect(self.load_spec)
        bottom.addWidget(btn_load)

        btn_add = QPushButton("Добавить элемент")
        btn_add.clicked.connect(self.add_item)
        bottom.addWidget(btn_add)

        btn_del = QPushButton("Удалить элемент")
        btn_del.clicked.connect(self.remove_item)
        bottom.addWidget(btn_del)

        btn_tree = QPushButton("Показать дерево")
        btn_tree.clicked.connect(self.show_tree)
        bottom.addWidget(btn_tree)

        bottom.addStretch(1)

        self.reload_a_list()
        self.cb_a.currentIndexChanged.connect(self.load_spec)

    def reload_a_list(self) -> None:
        self.cb_a.clear()
        # A должен быть только изделие/узел
        for name, typ in self.backend.get_components():
            if typ in ("I", "U"):
                self.cb_a.addItem(name)

        if self.cb_a.count() == 0:
            self.table.setRowCount(0)

    def _current_a(self) -> str | None:
        a = self.cb_a.currentText().strip()
        return a if a else None

    def load_spec(self) -> None:
        a = self._current_a()
        if not a:
            self.table.setRowCount(0)
            return

        try:
            rows = self.backend.get_spec(a)  # [(b_name, b_typ, qty), ...]
        except Exception as e:
            show_error(self, "Ошибка", str(e))
            return

        self.table.setRowCount(len(rows))
        for i, (b_name, b_typ, qty) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(b_name))
            self.table.setItem(i, 1, QTableWidgetItem(TYPE_RU.get(b_typ, "?")))
            self.table.setItem(i, 2, QTableWidgetItem(str(qty)))

        self.table.resizeColumnsToContents()

    def add_item(self) -> None:
        a = self._current_a()
        if not a:
            show_error(self, "Ошибка", "Выберите компонент A (изделие/узел).")
            return

        before = {}
        try:
            for b_name, b_typ, qty in self.backend.get_spec(a):
                before[b_name.lower()] = qty
        except Exception:
            before = {}

        w = QWidget()
        form = QFormLayout(w)

        cb_b = QComboBox()
        # B может быть любой, кроме A
        for name, typ in self.backend.get_components():
            if name.strip().lower() == a.strip().lower():
                continue
            cb_b.addItem(f"{name} ({TYPE_RU.get(typ, '?')})", userData=name)

        sp_qty = QSpinBox()
        sp_qty.setRange(1, 9999)
        sp_qty.setValue(1)

        form.addRow("Компонент B:", cb_b)
        form.addRow("Количество:", sp_qty)

        box = QMessageBox(self)
        box.setWindowTitle("Добавление элемента спецификации")
        box.setText("Введите данные элемента:")
        box.layout().addWidget(w, 1, 0, 1, box.layout().columnCount())
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if box.exec() != QMessageBox.Ok:
            return

        b = cb_b.currentData()
        qty = int(sp_qty.value())

        try:
            self.backend.add_spec(a, b, qty)
            self.load_spec()

            after = {}
            for b_name, b_typ, q in self.backend.get_spec(a):
                after[b_name.lower()] = q

            if b.lower() in before:
                QMessageBox.information(
                    self,
                    "Обновлено",
                    f"Количество для '{b}' изменено: {before[b.lower()]} → {after[b.lower()]}"
                )
            else:
                QMessageBox.information(self, "Добавлено", f"Элемент '{b}' добавлен.")
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def remove_item(self) -> None:
        a = self._current_a()
        if not a:
            show_error(self, "Ошибка", "Выберите компонент A.")
            return

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Удаление", "Выберите строку в таблице.")
            return

        b_item = self.table.item(row, 0)
        if not b_item:
            return
        b = b_item.text().strip()

        ans = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить связь '{a} / {b}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        try:
            self.backend.delete_spec(a, b)
            self.load_spec()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def show_tree(self) -> None:
        a = self._current_a()
        if not a:
            show_error(self, "Ошибка", "Выберите компонент A.")
            return

        try:
            text = self.backend.build_tree_text(a)
        except Exception as e:
            show_error(self, "Ошибка", str(e))
            return

        w = TreeWindow(text)
        w.show()
        self._tree_win = w  # сохранить ссылку


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.backend = PSApp()

        self.setWindowTitle("PS — Задание 2 (Графический интерфейс)")
        self.resize(900, 500)

        self.status = QLabel("Файлы не открыты")
        self.statusBar().addWidget(self.status)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Имя", "Тип"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.setCentralWidget(self.table)

        self._build_toolbar()

        self._spec_win = None

    def _need_open(self) -> bool:
        try:
            self.backend.require_open()
            return True
        except Exception as e:
            show_error(self, "Ошибка", str(e))
            return False

    def _selected_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _build_toolbar(self) -> None:
        tb = QToolBar("Действия")
        self.addToolBar(tb)

        tb.addAction("Создать", self.on_create)
        tb.addAction("Открыть", self.on_open)
        tb.addSeparator()

        tb.addAction("Обновить", self.refresh)
        tb.addAction("Добавить", self.on_add)
        tb.addAction("Удалить", self.on_delete)
        tb.addSeparator()

        tb.addAction("Восстановить", self.on_restore_one)
        tb.addAction("Восстановить всё", self.on_restore_all)
        tb.addAction("Уплотнить", self.on_truncate)
        tb.addSeparator()

        tb.addAction("Спецификация", self.open_spec_window)

    def on_create(self) -> None:
        w = QWidget()
        layout = QFormLayout(w)

        e_name = QLineEdit("data")
        sp_len = QSpinBox()
        sp_len.setRange(4, 1000)
        sp_len.setValue(40)

        layout.addRow("Имя базы (без .prd/.prs):", e_name)
        layout.addRow("maxLen:", sp_len)

        box = QMessageBox(self)
        box.setWindowTitle("Создание")
        box.setText("Создать новую базу?")
        box.layout().addWidget(w, 1, 0, 1, box.layout().columnCount())
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if box.exec() != QMessageBox.Ok:
            return

        base = e_name.text().strip()
        maxlen = int(sp_len.value())
        if not base:
            show_error(self, "Ошибка", "Имя базы пустое.")
            return

        if os.path.exists(base + ".prd") or os.path.exists(base + ".prs"):
            ans = QMessageBox.question(
                self,
                "Перезапись",
                "Файлы уже существуют. Перезаписать?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return

        try:
            self.backend.create(base, maxlen)
            self.status.setText(f"Открыто: {base}.prd / {base}.prs")
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка создания", str(e))

    def on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть PRD файл",
            "",
            "PRD файлы (*.prd);;Все файлы (*)",
        )
        if not path:
            return

        base = os.path.splitext(path)[0]
        try:
            self.backend.open(base)
            self.status.setText(
                f"Открыто: {os.path.basename(base)}.prd / {self.backend.prs_name}"
            )
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка открытия", str(e))

    def refresh(self) -> None:
        if not self._need_open():
            return

        rows = self.backend.get_components()
        self.table.setRowCount(len(rows))

        for i, (name, typ) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(TYPE_RU.get(typ, "?")))

        self.table.resizeColumnsToContents()

    def on_add(self) -> None:
        if not self._need_open():
            return

        w = QWidget()
        layout = QFormLayout(w)

        e_name = QLineEdit()
        cb = QComboBox()
        cb.addItems(list(TYPE_MAP.keys()))

        layout.addRow("Имя:", e_name)
        layout.addRow("Тип:", cb)

        box = QMessageBox(self)
        box.setWindowTitle("Добавление компонента")
        box.setText("Введите данные компонента:")
        box.layout().addWidget(w, 1, 0, 1, box.layout().columnCount())
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if box.exec() != QMessageBox.Ok:
            return

        name = e_name.text().strip()
        if not name:
            show_error(self, "Ошибка", "Имя пустое.")
            return

        typ = TYPE_MAP[cb.currentText()]
        try:
            self.backend.add_component(name, typ)
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def on_delete(self) -> None:
        if not self._need_open():
            return

        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Удаление", "Выберите компонент в таблице.")
            return

        ans = QMessageBox.question(
            self,
            "Удаление",
            f"Пометить '{name}' как удалённый?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        try:
            self.backend.delete_component(name)
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def on_restore_one(self) -> None:
        if not self._need_open():
            return

        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Восстановление", "Выберите компонент в таблице.")
            return

        try:
            self.backend.restore_one(name)
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def on_restore_all(self) -> None:
        if not self._need_open():
            return

        ans = QMessageBox.question(
            self,
            "Восстановление",
            "Восстановить все удалённые записи?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        try:
            self.backend.restore_all()
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def on_truncate(self) -> None:
        if not self._need_open():
            return

        ans = QMessageBox.question(
            self,
            "Уплотнение",
            "Физически уплотнить файлы (удалить помеченные записи)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        try:
            self.backend.truncate()
            self.refresh()
        except Exception as e:
            show_error(self, "Ошибка", str(e))

    def open_spec_window(self) -> None:
        if not self._need_open():
            return
        if self._spec_win is None:
            self._spec_win = SpecWindow(self.backend)
        self._spec_win.show()
        self._spec_win.raise_()
        self._spec_win.activateWindow()

    def closeEvent(self, event) -> None:
        try:
            self.backend.close()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
