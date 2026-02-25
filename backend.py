from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import BinaryIO, Dict, Iterable, List, Optional, Tuple

PRD_SIG = b"PS"
PRD_HDR_SIZE = 2 + 2 + 4 + 4 + 16
PRS_HDR_SIZE = 4 + 4

I8 = "<b"
U16 = "<H"
I16 = "<h"
I32 = "<i"


def type_ru(t: str) -> str:
    return {"I": "Изделие", "U": "Узел", "D": "Деталь"}.get(t, "?")


def norm(s: str) -> str:
    return (s or "").strip()


def eq(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


@dataclass
class PrdRec:
    off: int
    del_: int
    first_spec: int
    next_: int
    typ: str
    name: str


@dataclass
class PrsRec:
    off: int
    del_: int
    comp_off: int
    qty: int
    next_: int


class PSApp:
    """Backend: работа с .prd/.prs строго по структурам задания, без CLI."""

    def __init__(self) -> None:
        self.prd_path: Optional[str] = None
        self.prs_path: Optional[str] = None
        self.prd: Optional[BinaryIO] = None
        self.prs: Optional[BinaryIO] = None

        self.data_len = 0
        self.prd_head = -1
        self.prd_free = PRD_HDR_SIZE
        self.prs_head = -1
        self.prs_free = PRS_HDR_SIZE
        self.prs_name = ""

    def prd_rec_size(self) -> int:
        return 1 + 4 + 4 + self.data_len

    @staticmethod
    def prs_rec_size() -> int:
        return 1 + 4 + 2 + 4

    def opened(self) -> bool:
        return self.prd is not None and self.prs is not None

    def require_open(self) -> None:
        if not self.opened():
            raise RuntimeError("Сначала Create или Open.")

    def close(self) -> None:
        for f in (self.prd, self.prs):
            try:
                if f:
                    f.flush()
                    f.close()
            except Exception:
                pass
        self.prd = None
        self.prs = None
        self.prd_path = None
        self.prs_path = None

    @staticmethod
    def valid_sig(path: str) -> bool:
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            return f.read(2) == PRD_SIG

    def create(self, base_name: str, maxlen: int) -> None:
        """Создать новые файлы base_name.prd/.prs (перезапись на совести GUI)."""
        if maxlen < 4:
            raise ValueError("maxLen должен быть >= 4.")

        prd_path = base_name + ".prd"
        prs_path = base_name + ".prs"

        self.close()

        self.data_len = maxlen
        self.prd_head = -1
        self.prd_free = PRD_HDR_SIZE
        self.prs_head = -1
        self.prs_free = PRS_HDR_SIZE
        self.prs_name = os.path.basename(prs_path)

        self.prd = open(prd_path, "wb+")
        self.prs = open(prs_path, "wb+")
        self.prd_path = prd_path
        self.prs_path = prs_path

        self._prd_hdr_write()
        self._prs_hdr_write()

    def open(self, base_name: str) -> None:
        """Открыть base_name.prd и связанный .prs из заголовка."""
        prd_path = base_name + ".prd"
        if not os.path.exists(prd_path):
            raise FileNotFoundError("PRD не найден.")
        if not self.valid_sig(prd_path):
            raise RuntimeError("Неверная сигнатура PRD.")

        self.close()

        self.prd = open(prd_path, "rb+")
        self.prd_path = prd_path
        self._prd_hdr_read()

        prs_path = os.path.join(os.path.dirname(prd_path) or ".", self.prs_name)
        if not os.path.exists(prs_path):
            raise FileNotFoundError("Связанный PRS не найден.")
        self.prs = open(prs_path, "rb+")
        self.prs_path = prs_path
        self._prs_hdr_read()

    def _prd_hdr_write(self) -> None:
        assert self.prd is not None
        self.prd.seek(0)
        self.prd.write(PRD_SIG)
        self.prd.write(struct.pack(U16, self.data_len))
        self.prd.write(struct.pack(I32, self.prd_head))
        self.prd.write(struct.pack(I32, self.prd_free))
        nb = self.prs_name.encode("ascii", "ignore")[:16]
        self.prd.write(nb + b"\x00" * (16 - len(nb)))

    def _prd_hdr_read(self) -> None:
        assert self.prd is not None
        self.prd.seek(0)
        if self.prd.read(2) != PRD_SIG:
            raise RuntimeError("Неверная сигнатура PRD.")
        self.data_len = struct.unpack(U16, self.prd.read(2))[0]
        self.prd_head = struct.unpack(I32, self.prd.read(4))[0]
        self.prd_free = struct.unpack(I32, self.prd.read(4))[0]
        self.prs_name = (
            self.prd.read(16)
            .split(b"\x00", 1)[0]
            .decode("ascii", "ignore")
            .strip()
        )

    def _prs_hdr_write(self) -> None:
        assert self.prs is not None
        self.prs.seek(0)
        self.prs.write(struct.pack(I32, self.prs_head))
        self.prs.write(struct.pack(I32, self.prs_free))

    def _prs_hdr_read(self) -> None:
        assert self.prs is not None
        self.prs.seek(0)
        self.prs_head = struct.unpack(I32, self.prs.read(4))[0]
        self.prs_free = struct.unpack(I32, self.prs.read(4))[0]

    def _prd_read(self, off: int) -> PrdRec:
        assert self.prd is not None
        self.prd.seek(off)
        del_ = struct.unpack(I8, self.prd.read(1))[0]
        first_spec = struct.unpack(I32, self.prd.read(4))[0]
        next_ = struct.unpack(I32, self.prd.read(4))[0]
        raw = self.prd.read(self.data_len).decode("ascii", "ignore").rstrip(" ")

        typ = "I"
        name = raw.strip()
        if len(raw) >= 2 and raw[1] == ":":
            typ = raw[0]
            name = raw[2:].strip()

        return PrdRec(off, del_, first_spec, next_, typ, name)

    def _prd_write(self, r: PrdRec) -> None:
        assert self.prd is not None
        self.prd.seek(r.off)
        self.prd.write(struct.pack(I8, r.del_))
        self.prd.write(struct.pack(I32, r.first_spec))
        self.prd.write(struct.pack(I32, r.next_))

        payload = f"{r.typ}:{r.name}".encode("ascii", "ignore")
        fixed = bytearray(b" " * self.data_len)
        fixed[: min(self.data_len, len(payload))] = payload[: self.data_len]
        self.prd.write(bytes(fixed))

    def _prs_read(self, off: int) -> PrsRec:
        assert self.prs is not None
        self.prs.seek(off)
        del_ = struct.unpack(I8, self.prs.read(1))[0]
        comp_off = struct.unpack(I32, self.prs.read(4))[0]
        qty = struct.unpack(I16, self.prs.read(2))[0]
        next_ = struct.unpack(I32, self.prs.read(4))[0]
        return PrsRec(off, del_, comp_off, qty, next_)

    def _prs_write(self, r: PrsRec) -> None:
        assert self.prs is not None
        self.prs.seek(r.off)
        self.prs.write(struct.pack(I8, r.del_))
        self.prs.write(struct.pack(I32, r.comp_off))
        self.prs.write(struct.pack(I16, r.qty))
        self.prs.write(struct.pack(I32, r.next_))

    def scan_prd_physical(self) -> Iterable[PrdRec]:
        self.require_open()
        size = self.prd_rec_size()
        off = PRD_HDR_SIZE
        while off + size <= self.prd_free:
            yield self._prd_read(off)
            off += size

    def scan_prs_physical(self) -> Iterable[PrsRec]:
        self.require_open()
        size = self.prs_rec_size()
        off = PRS_HDR_SIZE
        while off + size <= self.prs_free:
            yield self._prs_read(off)
            off += size

    def iter_prd_logical(self) -> Iterable[PrdRec]:
        self.require_open()
        ptr = self.prd_head
        seen = set()
        while ptr != -1:
            if ptr in seen:
                raise RuntimeError("Цикл в логическом списке PRD.")
            seen.add(ptr)
            r = self._prd_read(ptr)
            if r.del_ == 0:
                yield r
            ptr = r.next_

    def find_any(self, name: str) -> Optional[PrdRec]:
        name = norm(name)
        for r in self.scan_prd_physical():
            if eq(r.name, name):
                return r
        return None

    def find_active(self, name: str) -> Optional[PrdRec]:
        name = norm(name)
        for r in self.scan_prd_physical():
            if r.del_ == 0 and eq(r.name, name):
                return r
        return None

    def _insert_sorted(self, new_off: int) -> None:
        new = self._prd_read(new_off)
        key = new.name.lower()

        if self.prd_head == -1:
            new.next_ = -1
            self._prd_write(new)
            self.prd_head = new_off
            self._prd_hdr_write()
            return

        prev_off = -1
        cur_off = self.prd_head
        while cur_off != -1:
            cur = self._prd_read(cur_off)
            if key < cur.name.lower():
                break
            prev_off = cur_off
            cur_off = cur.next_

        new.next_ = cur_off
        self._prd_write(new)

        if prev_off == -1:
            self.prd_head = new_off
            self._prd_hdr_write()
        else:
            prev = self._prd_read(prev_off)
            prev.next_ = new_off
            self._prd_write(prev)

    def rebuild_alphabetical(self) -> None:
        active = [r for r in self.scan_prd_physical() if r.del_ == 0]
        active.sort(key=lambda x: x.name.lower())

        for i, r in enumerate(active):
            r.next_ = -1 if i == len(active) - 1 else active[i + 1].off
            self._prd_write(r)

        self.prd_head = -1 if not active else active[0].off
        self._prd_hdr_write()

    def get_components(self) -> List[Tuple[str, str]]:
        """Список (name, type_letter) в порядке логического списка."""
        return [(r.name, r.typ) for r in self.iter_prd_logical()]

    def add_component(self, name: str, typ: str) -> None:
        self.require_open()
        name = norm(name)
        if not name:
            raise ValueError("Пустое имя.")
        if self.find_any(name) is not None:
            raise ValueError("Дублирование имени компонента.")

        rec = PrdRec(self.prd_free, 0, -1, -1, typ, name)
        self._prd_write(rec)
        self._insert_sorted(rec.off)

        self.prd_free += self.prd_rec_size()
        self._prd_hdr_write()

    def delete_component(self, name: str) -> None:
        self.require_open()
        comp = self.find_active(name)
        if comp is None:
            raise ValueError("Компонент не найден.")

        for c in self.scan_prd_physical():
            if c.del_ != 0 or c.off == comp.off:
                continue
            ptr = c.first_spec
            while ptr != -1:
                sr = self._prs_read(ptr)
                if sr.del_ == 0 and sr.comp_off == comp.off:
                    raise ValueError(
                        "На компонент есть ссылки в спецификациях других компонентов."
                    )
                ptr = sr.next_

        comp.del_ = -1
        self._prd_write(comp)

        ptr = comp.first_spec
        while ptr != -1:
            sr = self._prs_read(ptr)
            sr.del_ = -1
            self._prs_write(sr)
            ptr = sr.next_

    def restore_one(self, name: str) -> None:
        self.require_open()
        comp = self.find_any(name)
        if comp is None:
            raise ValueError("Компонент не найден.")

        comp.del_ = 0
        self._prd_write(comp)

        ptr = comp.first_spec
        while ptr != -1:
            sr = self._prs_read(ptr)
            sr.del_ = 0
            self._prs_write(sr)
            ptr = sr.next_

        self.rebuild_alphabetical()

    def restore_all(self) -> None:
        self.require_open()
        for c in self.scan_prd_physical():
            if c.del_ != 0:
                c.del_ = 0
                self._prd_write(c)
        for s in self.scan_prs_physical():
            if s.del_ != 0:
                s.del_ = 0
                self._prs_write(s)
        self.rebuild_alphabetical()

    def _would_create_cycle(self, parent_off: int, child_off: int) -> bool:
        if parent_off == child_off:
            return True
        return self._has_path(start_off=child_off, target_off=parent_off)

    def _has_path(self, start_off: int, target_off: int) -> bool:
        stack = [start_off]
        visited = set()

        while stack:
            cur_off = stack.pop()
            if cur_off == target_off:
                return True
            if cur_off in visited:
                continue
            visited.add(cur_off)

            cur = self._prd_read(cur_off)
            ptr = cur.first_spec
            while ptr != -1:
                sr = self._prs_read(ptr)
                if sr.del_ == 0:
                    child_off = sr.comp_off
                    child = self._prd_read(child_off)
                    if child.del_ == 0:
                        stack.append(child_off)
                ptr = sr.next_

        return False

    def add_spec(self, a: str, b: str, qty: int = 1) -> None:
        """Add link A/B with quantity. If A/B exists -> increase qty. Forbid cycles."""
        self.require_open()
        a = norm(a)
        b = norm(b)

        parent = self.find_active(a)
        if parent is None:
            raise ValueError("A component not found.")
        if parent.typ == "D":
            raise ValueError("Specification is not allowed for Detail.")

        child = self.find_active(b)
        if child is None:
            raise ValueError("B component not found.")
        if qty < 1:
            raise ValueError("qty must be >= 1.")

        if self._would_create_cycle(parent.off, child.off):
            raise ValueError("Cycle detected: this link would create a loop.")

        ptr = parent.first_spec
        while ptr != -1:
            sr = self._prs_read(ptr)
            if sr.del_ == 0 and sr.comp_off == child.off:
                sr.qty += qty
                self._prs_write(sr)
                return
            ptr = sr.next_

        sr = PrsRec(off=self.prs_free, del_=0, comp_off=child.off, qty=qty, next_=-1)
        self._prs_write(sr)

        if parent.first_spec == -1:
            parent.first_spec = sr.off
            self._prd_write(parent)
        else:
            cur = parent.first_spec
            last = -1
            while cur != -1:
                r = self._prs_read(cur)
                last = cur
                cur = r.next_
            tail = self._prs_read(last)
            tail.next_ = sr.off
            self._prs_write(tail)

        self.prs_free += self.prs_rec_size()
        self._prs_hdr_write()

    def delete_spec(self, a: str, b: str) -> None:
        self.require_open()
        a = norm(a)
        b = norm(b)

        parent = self.find_active(a)
        if parent is None:
            raise ValueError("A component not found.")
        if parent.typ == "D":
            raise ValueError("Specification is not allowed for Detail.")

        child = self.find_active(b)
        if child is None:
            raise ValueError("B component not found.")

        ptr = parent.first_spec
        while ptr != -1:
            sr = self._prs_read(ptr)
            if sr.del_ == 0 and sr.comp_off == child.off:
                sr.del_ = -1
                self._prs_write(sr)
                return
            ptr = sr.next_

        raise ValueError("A/B link not found.")

    def get_spec(self, a: str) -> List[Tuple[str, str, int]]:
        self.require_open()
        a = norm(a)

        parent = self.find_active(a)
        if parent is None:
            raise ValueError("Component not found.")
        if parent.typ == "D":
            raise ValueError("Specification is not allowed for Detail.")

        result: List[Tuple[str, str, int]] = []
        ptr = parent.first_spec
        while ptr != -1:
            sr = self._prs_read(ptr)
            if sr.del_ == 0:
                child = self._prd_read(sr.comp_off)
                if child.del_ == 0:
                    result.append((child.name, child.typ, sr.qty))
            ptr = sr.next_

        result.sort(key=lambda x: x[0].lower())
        return result

    def build_tree_text(self, name: str) -> str:
        self.require_open()
        root = self.find_active(name)
        if root is None:
            raise ValueError("Component not found.")
        if root.typ == "D":
            raise ValueError("Tree is not allowed for Detail.")

        out: List[str] = [root.name]
        self._tree_dfs(root, prefix="", stack=set(), out=out)
        return "\n".join(out)

    def _tree_dfs(self, node: PrdRec, prefix: str, stack: set, out: List[str]) -> None:
        if node.off in stack:
            out.append(prefix + "└─ [cycle detected]")
            return
        stack.add(node.off)

        items = self.get_spec(node.name)
        for i, (child_name, child_typ, qty) in enumerate(items):
            last = i == len(items) - 1
            branch = "└─ " if last else "├─ "
            suffix = f" x{qty}" if qty != 1 else ""
            out.append(prefix + branch + child_name + suffix)

            if child_typ != "D":
                child_rec = self.find_active(child_name)
                if child_rec is not None:
                    self._tree_dfs(
                        child_rec,
                        prefix + ("   " if last else "│  "),
                        stack,
                        out,
                    )

        stack.remove(node.off)

    def truncate(self) -> None:
        self.require_open()
        assert self.prd_path and self.prs_path and self.prd and self.prs

        prd_path, prs_path = self.prd_path, self.prs_path

        active = [c for c in self.scan_prd_physical() if c.del_ == 0]
        active.sort(key=lambda x: x.name.lower())

        new_prd_off: Dict[int, int] = {}
        w_prd = PRD_HDR_SIZE
        for c in active:
            new_prd_off[c.off] = w_prd
            w_prd += self.prd_rec_size()

        buckets: Dict[int, List[Tuple[int, int]]] = {}
        for p in active:
            keep: List[Tuple[int, int]] = []
            ptr = p.first_spec
            while ptr != -1:
                sr = self._prs_read(ptr)
                if sr.del_ == 0 and sr.comp_off in new_prd_off:
                    keep.append((sr.comp_off, sr.qty))
                ptr = sr.next_
            buckets[p.off] = keep

        tmp_prd = prd_path + ".tmp"
        tmp_prs = prs_path + ".tmp"

        self.prd.close()
        self.prs.close()

        with open(tmp_prd, "wb+") as prd_new, open(tmp_prs, "wb+") as prs_new:
            prs_name = os.path.basename(prs_path)
            prd_head = -1 if not active else PRD_HDR_SIZE
            prd_free = PRD_HDR_SIZE
            prs_head = -1
            prs_free = PRS_HDR_SIZE

            prd_new.write(PRD_SIG)
            prd_new.write(struct.pack(U16, self.data_len))
            prd_new.write(struct.pack(I32, prd_head))
            prd_new.write(struct.pack(I32, prd_free))
            nb = prs_name.encode("ascii", "ignore")[:16]
            prd_new.write(nb + b"\x00" * (16 - len(nb)))

            prs_new.write(struct.pack(I32, prs_head))
            prs_new.write(struct.pack(I32, prs_free))

            w = PRD_HDR_SIZE
            for i, old in enumerate(active):
                next_ = -1 if i == len(active) - 1 else w + self.prd_rec_size()
                rec = PrdRec(w, 0, -1, next_, old.typ, old.name)

                prd_new.seek(rec.off)
                prd_new.write(struct.pack(I8, rec.del_))
                prd_new.write(struct.pack(I32, rec.first_spec))
                prd_new.write(struct.pack(I32, rec.next_))

                payload = f"{rec.typ}:{rec.name}".encode("ascii", "ignore")
                fixed = bytearray(b" " * self.data_len)
                fixed[: min(self.data_len, len(payload))] = payload[: self.data_len]
                prd_new.write(bytes(fixed))
                w += self.prd_rec_size()

            prd_free = w
            prd_new.seek(2 + 2 + 4)
            prd_new.write(struct.pack(I32, prd_free))

            w_prs = PRS_HDR_SIZE
            first_prs: Optional[int] = None

            for p in active:
                items = buckets[p.off]
                if not items:
                    continue

                first_for_parent = w_prs
                for i, (child_old, qty) in enumerate(items):
                    child_new = new_prd_off[child_old]
                    next_ = -1 if i == len(items) - 1 else w_prs + self.prs_rec_size()
                    sr = PrsRec(w_prs, 0, child_new, qty, next_)

                    prs_new.seek(sr.off)
                    prs_new.write(struct.pack(I8, sr.del_))
                    prs_new.write(struct.pack(I32, sr.comp_off))
                    prs_new.write(struct.pack(I16, sr.qty))
                    prs_new.write(struct.pack(I32, sr.next_))
                    w_prs += self.prs_rec_size()

                parent_new = new_prd_off[p.off]
                prd_new.seek(parent_new + 1)
                prd_new.write(struct.pack(I32, first_for_parent))
                if first_prs is None:
                    first_prs = first_for_parent

            prs_head = first_prs if first_prs is not None else -1
            prs_free = w_prs
            prs_new.seek(0)
            prs_new.write(struct.pack(I32, prs_head))
            prs_new.write(struct.pack(I32, prs_free))

        os.replace(tmp_prd, prd_path)
        os.replace(tmp_prs, prs_path)

        self.prd = open(prd_path, "rb+")
        self.prs = open(prs_path, "rb+")
        self.prd_path = prd_path
        self.prs_path = prs_path
        self._prd_hdr_read()
        self._prs_hdr_read()


def run_console() -> None:
    app = PSApp()

    help_text = """
Available commands:

Create <name> <maxLen>      — создать новые файлы
Open <name>                 — открыть существующие файлы
Add <name> <type>           — добавить компонент (I, U, D)
Delete <name>               — логически удалить компонент
Restore <name>              — восстановить компонент
RestoreAll                  — восстановить все компоненты
SpecAdd <A> <B> [qty]       — добавить связь A/B
SpecDel <A> <B>             — удалить связь A/B
Print <name>                — вывести дерево изделия
Truncate                    — физически удалить помеченные записи
Help                        — показать список команд
Exit                        — выход из программы
"""

    print("Задание 1 — консольный режим")
    print('Введите "Help" для просмотра команд.')

    while True:
        try:
            cmd = input(">>> ").strip()
            if not cmd:
                continue

            parts = cmd.split()
            command = parts[0].lower()

            if command == "help":
                print(help_text)

            elif command == "exit":
                app.close()
                break

            elif command == "create":
                app.create(parts[1], int(parts[2]))
                print("Database created.")

            elif command == "open":
                app.open(parts[1])
                print("Database opened.")

            elif command == "add":
                app.add_component(parts[1], parts[2].upper())
                print("Component added.")

            elif command == "delete":
                app.delete_component(parts[1])
                print("Component marked as deleted.")

            elif command == "restore":
                app.restore_one(parts[1])
                print("Component restored.")

            elif command == "restoreall":
                app.restore_all()
                print("All components restored.")

            elif command == "specadd":
                qty = int(parts[3]) if len(parts) > 3 else 1
                app.add_spec(parts[1], parts[2], qty)
                print("Specification added.")

            elif command == "specdel":
                app.delete_spec(parts[1], parts[2])
                print("Specification deleted.")

            elif command == "print":
                print(app.build_tree_text(parts[1]))

            elif command == "truncate":
                app.truncate()
                print("Files truncated.")

            else:
                print('Unknown command. Type "Help".')

        except Exception as e:
            print("Error:", e)
