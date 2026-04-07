from __future__ import annotations

import json
import re
import sys
import ctypes
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QAbstractItemView, QAbstractSpinBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip, QVBoxLayout, QWidget

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

DATA_PATH = APP_DIR / "inventory-data.json"
ICON_PATH = APP_DIR / "icon.ico"
APP_ID = "Yone.WarehouseApp"
GRID_COLUMNS = 20
GRID_ROWS = 20
COLOR_PRESETS = {
    "AUTO": ("自動", None),
    "BLUE": ("青", "#57C1FF"),
    "GREEN": ("緑", "#31D07C"),
    "GRAY": ("その他", "#7A8EA6"),
    "RED": ("赤", "#FF6671"),
    "YELLOW": ("黄", "#FFC34D"),
    "PURPLE": ("紫", "#A785FF"),
    "ORANGE": ("橙", "#FF9D57"),
    "TEAL": ("青緑", "#3DD9C5"),
    "PINK": ("桃", "#FF7AC3"),
    "NAVY": ("紺", "#3E5FCE"),
    "LIME": ("黄緑", "#9AD93A"),
    "BROWN": ("茶", "#B57A52"),
    "WHITE": ("白", "#E8EEF5"),
    "BLACK": ("黒", "#3B4652"),
    "CYAN": ("水", "#67E8F9"),
    "MAGENTA": ("紅", "#E85AD8"),
}
COLOR_CHOICE_LABELS = {
    "AUTO": "自動",
    "RED": "赤 [#38]",
    "BLUE": "青 [#39]",
    "GREEN": "緑 [#45]",
    "PINK": "桃 [#50]",
    "YELLOW": "黄 [#40]",
    "PURPLE": "紫 [C/C]",
    "GRAY": "その他 [混在 / その他]",
    "ORANGE": "橙",
    "TEAL": "青緑",
    "NAVY": "紺",
    "LIME": "黄緑",
    "BROWN": "茶",
    "WHITE": "白",
    "BLACK": "黒",
    "CYAN": "水",
    "MAGENTA": "紅",
}
AUTO_PART_COLOR_RULES = {
    "38": ("RED", "赤", "#FF6671"),
    "39": ("BLUE", "青", "#57C1FF"),
    "45": ("GREEN", "緑", "#31D07C"),
    "50": ("PINK", "桃", "#FF7AC3"),
    "40": ("YELLOW", "黄", "#FFC34D"),
}
AUTO_OTHER_COLOR = ("GRAY", "その他", "#7A8EA6")


def column_label(index: int) -> str:
    index += 1
    text = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        text = chr(65 + remainder) + text
    return text


DEFAULT_LOCATIONS = [f"{column_label(col)}{row}" for row in range(1, GRID_ROWS + 1) for col in range(GRID_COLUMNS)]
ENTRY_LOCATION = f"{column_label((GRID_COLUMNS // 2) - 1)}{GRID_ROWS}"
ENTRY_MAP_X = 0.5
ENTRY_MAP_Y = 0.95


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class InventoryItemLine:
    line_id: str = field(default_factory=lambda: uuid4().hex)
    part_code: str = ""
    size: str = "LL"
    thickness_mm: str = "10"
    finish_text: str = "S/S"
    grade: str = "A"
    sheet_count: int = 80
    note: str = ""

    @property
    def identifier(self) -> str:
        return f"#{self.part_code}-{self.size}{self.thickness_mm} {self.finish_text} {self.grade} {self.sheet_count}"

    @property
    def height_mm(self) -> int:
        return int(round(parse_thickness_value(self.thickness_mm) * self.sheet_count))


@dataclass
class PalletRecord:
    pallet_number: str
    location_code: str
    received_date: str = ""
    color_key: str = "AUTO"
    stack_order: int = 0
    stack_group: Optional[str] = None
    orientation: int = 0
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    items: List[InventoryItemLine] = field(default_factory=list)
    updated_at: str = field(default_factory=now_text)

    @property
    def total_sheets(self) -> int:
        return sum(item.sheet_count for item in self.items)

    @property
    def material_height_mm(self) -> int:
        return sum(item.height_mm for item in self.items)

    @property
    def estimated_height_mm(self) -> int:
        return 200 + self.material_height_mm

    @property
    def stack_label(self) -> str:
        return f"{self.stack_order + 1}段目"

    @property
    def summary_text(self) -> str:
        if not self.items:
            return "空パレット"
        if len(self.items) == 1:
            return self.items[0].identifier
        return f"{self.items[0].identifier} 他{len(self.items) - 1}件"


@dataclass
class ShipmentRecord:
    shipment_id: str = field(default_factory=lambda: uuid4().hex)
    shipped_at: str = field(default_factory=now_text)
    pallet_number: str = ""
    location_code: str = ""
    received_date: str = ""
    color_key: str = "AUTO"
    orientation: int = 0
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    items: List[InventoryItemLine] = field(default_factory=list)

    @property
    def total_sheets(self) -> int:
        return sum(item.sheet_count for item in self.items)

    @property
    def material_height_mm(self) -> int:
        return sum(item.height_mm for item in self.items)

    @property
    def estimated_height_mm(self) -> int:
        return 200 + self.material_height_mm

    @property
    def summary_text(self) -> str:
        if not self.items:
            return "空パレット"
        if len(self.items) == 1:
            return self.items[0].identifier
        return f"{self.items[0].identifier} 他{len(self.items) - 1}件"


class InventoryStore:
    def __init__(self) -> None:
        self.locations = list(DEFAULT_LOCATIONS)
        self.blocked_locations: List[str] = []
        self.pallets: List[PalletRecord] = []
        self.shipments: List[ShipmentRecord] = []

    def ensure_defaults(self) -> None:
        for location in DEFAULT_LOCATIONS:
            if location not in self.locations:
                self.locations.append(location)

    def ensure_stack_groups(self) -> None:
        for pallet in self.pallets:
            if not pallet.stack_group:
                pallet.stack_group = pallet.pallet_number

    def normalize_stacks(self) -> None:
        groups: Dict[Tuple[str, str], List[PalletRecord]] = {}
        for pallet in self.pallets:
            groups.setdefault((pallet.location_code, pallet.stack_group or pallet.pallet_number), []).append(pallet)
        for pallets in groups.values():
            pallets.sort(key=lambda p: (p.stack_order, p.updated_at, p.pallet_number))
            for index, pallet in enumerate(pallets):
                pallet.stack_order = index

    def next_stack_order(self, location_code: str, ignore: Optional[str] = None) -> int:
        values = [p.stack_order for p in self.pallets if p.location_code == location_code and p.pallet_number != ignore]
        return max(values) + 1 if values else 0

    def group_members(self, pallet: PalletRecord) -> List[PalletRecord]:
        key = pallet.stack_group or pallet.pallet_number
        members = [item for item in self.pallets if (item.stack_group or item.pallet_number) == key]
        members.sort(key=lambda item: (item.stack_order, item.updated_at, item.pallet_number))
        return members

    def get_pallet(self, pallet_number: str) -> Optional[PalletRecord]:
        for pallet in self.pallets:
            if pallet.pallet_number == pallet_number:
                return pallet
        return None

    def unique_pallet_number(self, base_number: str, ignore: Optional[str] = None) -> str:
        candidate = (base_number or "").strip() or "PALLET"
        existing = {pallet.pallet_number for pallet in self.pallets if pallet.pallet_number != ignore}
        if candidate not in existing:
            return candidate
        index = 1
        while f"{candidate}-{index}" in existing:
            index += 1
        return f"{candidate}-{index}"

    def to_dict(self) -> dict:
        return {
            "locations": self.locations,
            "blocked_locations": self.blocked_locations,
            "pallets": [
                {
                    "pallet_number": p.pallet_number,
                    "location_code": p.location_code,
                    "received_date": p.received_date,
                    "color_key": p.color_key,
                    "stack_order": p.stack_order,
                    "stack_group": p.stack_group,
                    "orientation": p.orientation,
                    "map_x": p.map_x,
                    "map_y": p.map_y,
                    "updated_at": p.updated_at,
                    "items": [asdict(item) for item in p.items],
                }
                for p in self.pallets
            ],
            "shipments": [
                {
                    "shipment_id": shipment.shipment_id,
                    "shipped_at": shipment.shipped_at,
                    "pallet_number": shipment.pallet_number,
                    "location_code": shipment.location_code,
                    "received_date": shipment.received_date,
                    "color_key": shipment.color_key,
                    "orientation": shipment.orientation,
                    "map_x": shipment.map_x,
                    "map_y": shipment.map_y,
                    "items": [asdict(item) for item in shipment.items],
                }
                for shipment in self.shipments
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InventoryStore":
        store = cls()
        store.locations = list(DEFAULT_LOCATIONS)
        store.blocked_locations = [normalize_location_code(code) for code in payload.get("blocked_locations", [])]
        for pallet_data in payload.get("pallets", []):
            items = [InventoryItemLine(**item_data) for item_data in pallet_data.get("items", [])]
            store.pallets.append(PalletRecord(pallet_number=pallet_data.get("pallet_number", ""), location_code=normalize_location_code(pallet_data.get("location_code", "")), received_date=pallet_data.get("received_date", ""), color_key=pallet_data.get("color_key", "AUTO"), stack_order=int(pallet_data.get("stack_order", 0)), stack_group=pallet_data.get("stack_group"), orientation=int(pallet_data.get("orientation", 0)), map_x=pallet_data.get("map_x"), map_y=pallet_data.get("map_y"), updated_at=pallet_data.get("updated_at", now_text()), items=items))
        for shipment_data in payload.get("shipments", []):
            items = [InventoryItemLine(**item_data) for item_data in shipment_data.get("items", [])]
            store.shipments.append(ShipmentRecord(shipment_id=shipment_data.get("shipment_id", uuid4().hex), shipped_at=shipment_data.get("shipped_at", now_text()), pallet_number=shipment_data.get("pallet_number", ""), location_code=normalize_location_code(shipment_data.get("location_code", "")), received_date=shipment_data.get("received_date", ""), color_key=shipment_data.get("color_key", "AUTO"), orientation=int(shipment_data.get("orientation", 0)), map_x=shipment_data.get("map_x"), map_y=shipment_data.get("map_y"), items=items))
        store.ensure_defaults()
        store.ensure_stack_groups()
        store.normalize_stacks()
        return store


def save_store(store: InventoryStore, path: Path = DATA_PATH) -> None:
    path.write_text(json.dumps(store.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_store(path: Path = DATA_PATH) -> InventoryStore:
    if not path.exists():
        store = InventoryStore()
        save_store(store, path)
        return store
    return InventoryStore.from_dict(json.loads(path.read_text(encoding="utf-8")))


def orientation_label(orientation: int) -> str:
    return "縦向き" if orientation % 180 == 90 else "横向き"


def parse_location_code(location: str) -> Tuple[str, int]:
    text = (location or "").strip().upper()
    if "-" in text:
        prefix, suffix = text.split("-", 1)
    else:
        prefix = "".join(ch for ch in text if ch.isalpha()) or text
        suffix = "".join(ch for ch in text if ch.isdigit())
    try:
        number = int(suffix)
    except ValueError:
        number = 1
    return prefix or "Z", max(1, number)


def normalize_location_code(location: str) -> str:
    text = (location or "").strip().upper()
    if text.startswith("STAGE"):
        return ENTRY_LOCATION
    prefix, number = parse_location_code(text)
    return f"{prefix}{number}"


def location_to_grid(location: str) -> Tuple[int, int]:
    code = normalize_location_code(location)
    prefix, number = parse_location_code(code)
    col = 0
    for ch in prefix:
        if "A" <= ch <= "Z":
            col = col * 26 + (ord(ch) - 64)
    col = max(1, col) - 1
    row = max(1, number) - 1
    return min(GRID_COLUMNS - 1, col), min(GRID_ROWS - 1, row)


def column_code_from_location(location: str) -> str:
    code = normalize_location_code(location)
    prefix, _ = parse_location_code(code)
    return prefix


def color_label(color_key: str) -> str:
    return COLOR_PRESETS.get(color_key, COLOR_PRESETS["AUTO"])[0]


def auto_color_key_for_items(items: List[InventoryItemLine]) -> str:
    finishes = {(item.finish_text or "").strip().upper() for item in items}
    if "C/C" in finishes:
        return "PURPLE"
    parts = {item.part_code.strip().upper() for item in items if item.part_code.strip()}
    if len(parts) == 1:
        part_code = next(iter(parts))
        if part_code in AUTO_PART_COLOR_RULES:
            return AUTO_PART_COLOR_RULES[part_code][0]
    return AUTO_OTHER_COLOR[0]


def auto_color_info(pallet: PalletRecord) -> Tuple[str, QColor]:
    auto_key = auto_color_key_for_items(pallet.items)
    if auto_key == "PURPLE":
        return "C/C=紫", QColor(COLOR_PRESETS["PURPLE"][1])
    parts = {item.part_code.strip().upper() for item in pallet.items if item.part_code.strip()}
    if len(parts) == 1:
        part_code = next(iter(parts))
        if part_code in AUTO_PART_COLOR_RULES:
            _, label, color = AUTO_PART_COLOR_RULES[part_code]
            return f"#{part_code}={label}", QColor(color)
    if len(parts) > 1:
        _, label, color = AUTO_OTHER_COLOR
        return f"混在={label}", QColor(color)
    _, label, color = AUTO_OTHER_COLOR
    return label, QColor(color)


def pallet_color_text(pallet: PalletRecord) -> str:
    if (pallet.color_key or "AUTO") != "AUTO":
        return color_label(pallet.color_key)
    auto_label, _ = auto_color_info(pallet)
    return f"自動 / {auto_label}"


def color_swatch_icon(color_key: str) -> QIcon:
    color_value = COLOR_PRESETS.get(color_key, COLOR_PRESETS["AUTO"])[1] or "#7a8ea6"
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#d7ecff"), 1))
    painter.setBrush(QColor(color_value))
    painter.drawRoundedRect(1, 1, 14, 14, 4, 4)
    painter.end()
    return QIcon(pixmap)


def populate_color_combo(combo: QComboBox, selected_key: Optional[str] = None, include_auto: bool = True) -> None:
    combo.clear()
    for key, (label, _) in COLOR_PRESETS.items():
        if key == "AUTO" and not include_auto:
            continue
        combo.addItem(color_swatch_icon(key), COLOR_CHOICE_LABELS.get(key, label), key)
    if selected_key is not None:
        combo.setCurrentIndex(max(0, combo.findData(selected_key)))


def pallet_color(pallet: PalletRecord) -> QColor:
    preset = COLOR_PRESETS.get(pallet.color_key or "AUTO", COLOR_PRESETS["AUTO"])[1]
    if preset:
        return QColor(preset)
    return auto_color_info(pallet)[1]


def pallet_popup_text(pallet: PalletRecord) -> str:
    lines = [f"パレット: {pallet.pallet_number}", "荷姿(上→下):"]
    ordered_items = list(reversed(pallet.items))
    lines.extend(f"- {item.identifier}" + (f" / {item.note}" if item.note else "") for item in ordered_items[:8])
    if len(ordered_items) > 8:
        lines.append(f"... 他{len(ordered_items) - 8}件")
    lines.extend([
        "",
        "補足:",
        f"位置: {pallet.location_code} / {pallet.stack_label}",
        f"概算高: {pallet.estimated_height_mm}mm",
        f"入庫日: {pallet.received_date or '-'}",
        f"向き: {orientation_label(pallet.orientation)}",
        f"色: {pallet_color_text(pallet)}",
    ])
    return "\n".join(lines)


def footprint_mm(pallet: PalletRecord) -> Tuple[int, int]:
    sizes = [item.size.upper() for item in pallet.items] or ["LL"]
    size = max(sizes, key=lambda code: {"L": 1, "LL": 2, "EL": 2, "OL": 3}.get(code, 0))
    width, depth = (1400, 1300) if size == "L" else ((3500, 1400) if size == "OL" else (2300, 1300))
    return (depth, width) if pallet.orientation % 180 == 90 else (width, depth)


def parse_thickness_value(thickness_text: str) -> float:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", str(thickness_text or ""))]
    if not numbers:
        return 0.0
    return max(numbers)


def format_thickness_value(value: float) -> str:
    rounded = round(max(0.0, value), 3)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    text = f"{rounded:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def clone_item(item: InventoryItemLine, sheet_count: Optional[int] = None) -> InventoryItemLine:
    return InventoryItemLine(
        part_code=item.part_code,
        size=item.size,
        thickness_mm=item.thickness_mm,
        finish_text=item.finish_text,
        grade=item.grade,
        sheet_count=sheet_count if sheet_count is not None else item.sheet_count,
        note=item.note,
    )


def shipment_notes_text(shipment: ShipmentRecord) -> str:
    notes = [item.note.strip() for item in shipment.items if item.note.strip()]
    return " / ".join(dict.fromkeys(notes)) if notes else "-"


class ReorderTableWidget(QTableWidget):
    def __init__(self, rows: int, columns: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(rows, columns, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._drag_row = -1
        self._hover_row = -1
        self._press_pos = QPoint()
        self.rows_changed_callback = None
        self.setMouseTracking(True)

    def row_snapshot(self) -> List[List[str]]:
        rows: List[List[str]] = []
        for row in range(self.rowCount()):
            values = []
            for col in range(self.columnCount()):
                item = self.item(row, col)
                values.append(item.text() if item else "")
            rows.append(values)
        return rows

    def restore_rows(self, rows: List[List[str]], current_row: int) -> None:
        self.setRowCount(0)
        for values in rows:
            row = self.rowCount()
            self.insertRow(row)
            for col, value in enumerate(values):
                self.setItem(row, col, QTableWidgetItem(value))
        if 0 <= current_row < self.rowCount():
            self.setCurrentCell(current_row, 0)
        if callable(self.rows_changed_callback):
            self.rows_changed_callback()

    def move_row(self, source_row: int, target_row: int) -> None:
        if source_row < 0 or source_row >= self.rowCount():
            return
        if target_row < 0 or target_row >= self.rowCount():
            return
        if source_row == target_row:
            return
        rows = self.row_snapshot()
        moved = rows.pop(source_row)
        rows.insert(target_row, moved)
        self.restore_rows(rows, target_row)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_row = self.rowAt(self._press_pos.y())
            self._hover_row = self._drag_row
            self.update_drag_feedback()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_row >= 0:
            self._hover_row = self.rowAt(event.position().toPoint().y())
            self.update_drag_feedback()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_row >= 0:
            target_point = event.position().toPoint()
            target_row = self.rowAt(target_point.y())
            if target_row >= 0 and (target_point - self._press_pos).manhattanLength() > 6:
                self.move_row(self._drag_row, target_row)
        self._drag_row = -1
        self._hover_row = -1
        self.update_drag_feedback()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self._drag_row < 0:
            self._hover_row = -1
            self.update_drag_feedback()
        super().leaveEvent(event)

    def update_drag_feedback(self) -> None:
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item is None:
                    continue
                if row == self._drag_row and self._drag_row >= 0:
                    item.setBackground(QColor("#1d5d99"))
                    item.setForeground(QColor("#ffffff"))
                elif row == self._hover_row and self._drag_row >= 0:
                    item.setBackground(QColor("#163450"))
                    item.setForeground(QColor("#dff6ff"))
                else:
                    item.setBackground(QColor("#06101c"))
                    item.setForeground(QColor("#f6fbff"))


class ClearOnFocusLineEdit(QLineEdit):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._clear_on_first_focus = True

    def focusInEvent(self, event) -> None:
        if self._clear_on_first_focus:
            self.clear()
            self._clear_on_first_focus = False
        super().focusInEvent(event)


class ThicknessSpinBox(QAbstractSpinBox):
    textChanged = Signal(str)

    def __init__(self, text: str = "10", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.setAccelerated(True)
        self.lineEdit().setText(text)
        self.lineEdit().textChanged.connect(self.textChanged.emit)

    def text(self) -> str:
        return self.lineEdit().text()

    def setText(self, text: str) -> None:
        self.lineEdit().setText(text)

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabled:
        return QAbstractSpinBox.StepUpEnabled | QAbstractSpinBox.StepDownEnabled

    def stepBy(self, steps: int) -> None:
        current = parse_thickness_value(self.text().strip())
        self.setText(format_thickness_value(current + steps))


class RegistrationDialog(QDialog):
    def __init__(self, locations: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新規登録")
        self.resize(720, 620)
        self.items: List[InventoryItemLine] = []
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.pallet_number = QLineEdit()
        self.pallet_number.setPlaceholderText("例: R080324")
        self.received_date = QLineEdit(datetime.now().strftime("%Y-%m-%d"))
        self.orientation = QComboBox(); self.orientation.addItem("横向き", 0); self.orientation.addItem("縦向き", 90)
        self.color = QComboBox()
        populate_color_combo(self.color, "AUTO", include_auto=True)
        form.addRow("パレット番号", self.pallet_number)
        form.addRow("入庫日", self.received_date)
        form.addRow("向き", self.orientation)
        form.addRow("色", self.color)
        root.addLayout(form)

        box = QFrame(); grid = QGridLayout(box)
        self.part_code = ClearOnFocusLineEdit("39")
        self.size = QComboBox(); self.size.addItems(["L", "LL", "EL", "OL"])
        self.size.setCurrentText("LL")
        self.thickness = ThicknessSpinBox("10")
        self.finish = ClearOnFocusLineEdit("S/S")
        self.grade = QComboBox(); self.grade.setEditable(True); self.grade.addItems(["A", "B", "C", "K", "片A", "S"])
        self.grade.setCurrentText("A")
        self.sheet_count = QSpinBox(); self.sheet_count.setRange(1, 9999); self.sheet_count.setValue(80)
        self.note = QLineEdit()
        self.preview = QLabel()
        grid.addWidget(QLabel("品番"), 0, 0); grid.addWidget(QLabel("サイズ"), 0, 1); grid.addWidget(QLabel("厚み(mm)"), 0, 2)
        grid.addWidget(self.part_code, 1, 0); grid.addWidget(self.size, 1, 1); grid.addWidget(self.thickness, 1, 2)
        grid.addWidget(QLabel("加工 / 裏表"), 2, 0); grid.addWidget(QLabel("グレード"), 2, 1); grid.addWidget(QLabel("枚数"), 2, 2)
        grid.addWidget(self.finish, 3, 0); grid.addWidget(self.grade, 3, 1); grid.addWidget(self.sheet_count, 3, 2); grid.addWidget(self.preview, 4, 0, 1, 3)
        grid.addWidget(QLabel("備考"), 5, 0)
        grid.addWidget(self.note, 6, 0, 1, 3)
        root.addWidget(box)
        for widget in [self.part_code, self.finish]: widget.textChanged.connect(self.update_preview)
        self.size.currentTextChanged.connect(self.update_preview); self.grade.currentTextChanged.connect(self.update_preview)
        self.thickness.textChanged.connect(self.update_preview); self.sheet_count.valueChanged.connect(self.update_preview)
        self.update_preview()

        add_line_button = QPushButton("明細を追加"); add_line_button.clicked.connect(self.add_line); root.addWidget(add_line_button)
        self.item_table = QTableWidget(0, 3); self.item_table.setHorizontalHeaderLabels(["識別", "高さ(mm)", "備考"])
        self.item_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.item_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.item_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.item_table.setMinimumHeight(180)
        root.addWidget(self.item_table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def update_preview(self) -> None:
        part = self.part_code.text().replace("#", "").replace("-", "").strip().upper() or "38"
        finish = self.finish.text().strip() or "S/S"
        grade = self.grade.currentText().strip() or "A"
        thickness = self.thickness.text().strip() or "10"
        self.preview.setText(f"プレビュー: #{part}-{self.size.currentText()}{thickness} {finish} {grade} {self.sheet_count.value()}")

    def add_line(self) -> None:
        part = self.part_code.text().replace("#", "").replace("-", "").strip().upper()
        thickness = self.thickness.text().strip()
        finish = self.finish.text().strip(); grade = self.grade.currentText().strip()
        if not part:
            QMessageBox.warning(self, "入力エラー", "品番を入力してください。")
            return
        if not thickness or not finish or not grade:
            QMessageBox.warning(self, "入力エラー", "厚み、加工 / 裏表、グレードを入力してください。")
            return
        item = InventoryItemLine(part_code=part, size=self.size.currentText(), thickness_mm=thickness, finish_text=finish, grade=grade, sheet_count=self.sheet_count.value(), note=self.note.text().strip())
        self.items.append(item)
        row = self.item_table.rowCount(); self.item_table.insertRow(row)
        self.item_table.setItem(row, 0, QTableWidgetItem(item.identifier)); self.item_table.setItem(row, 1, QTableWidgetItem(str(item.height_mm))); self.item_table.setItem(row, 2, QTableWidgetItem(item.note))

    def payload(self) -> Optional[Tuple[str, str, int, str, List[InventoryItemLine]]]:
        pallet_number = self.pallet_number.text().strip().upper()
        if not pallet_number:
            QMessageBox.warning(self, "入力エラー", "パレット番号を入力してください。")
            return None
        if not self.items:
            QMessageBox.warning(self, "入力エラー", "明細を1件以上追加してください。")
            return None
        return pallet_number, self.received_date.text().strip(), int(self.orientation.currentData()), str(self.color.currentData()), list(self.items)

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class EditPalletDialog(QDialog):
    def __init__(self, pallet: PalletRecord, locations: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("パレット編集")
        self.resize(760, 620)
        self.original_pallet_number = pallet.pallet_number

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.pallet_number = QLineEdit(pallet.pallet_number)
        self.received_date = QLineEdit(pallet.received_date)
        self.location = QComboBox(); self.location.setEditable(True); self.location.addItems(sorted(locations)); self.location.setCurrentText(pallet.location_code)
        self.orientation = QComboBox(); self.orientation.addItem("横向き", 0); self.orientation.addItem("縦向き", 90); self.orientation.setCurrentIndex(1 if pallet.orientation % 180 == 90 else 0)
        self.color = QComboBox()
        selected_color_key = pallet.color_key if (pallet.color_key or "AUTO") != "AUTO" else auto_color_key_for_items(pallet.items)
        populate_color_combo(self.color, selected_color_key, include_auto=False)
        self.stack_order = QSpinBox(); self.stack_order.setRange(0, 999); self.stack_order.setValue(pallet.stack_order)
        form.addRow("パレット番号", self.pallet_number)
        form.addRow("入庫日", self.received_date)
        form.addRow("ロケーション", self.location)
        form.addRow("向き", self.orientation)
        form.addRow("色", self.color)
        form.addRow("積み段", self.stack_order)
        root.addLayout(form)

        self.item_table = ReorderTableWidget(0, 8)
        self.item_table.setHorizontalHeaderLabels(["順", "品番", "サイズ", "厚み", "加工 / 裏表", "グレード", "枚数", "備考"])
        self.item_table.rows_changed_callback = self.refresh_item_order_labels
        self.item_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.item_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.item_table.verticalHeader().setVisible(False)
        root.addWidget(self.item_table, 1)

        action_row = QHBoxLayout()
        add_button = QPushButton("明細行追加"); add_button.clicked.connect(self.add_empty_row)
        remove_button = QPushButton("選択行削除"); remove_button.clicked.connect(self.remove_current_row)
        action_row.addWidget(add_button); action_row.addWidget(remove_button); action_row.addStretch(1)
        root.addLayout(action_row)

        for item in reversed(pallet.items):
            self.add_row(item)
        self.refresh_item_order_labels()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def add_row(self, item: Optional[InventoryItemLine] = None, insert_at_top: bool = False) -> None:
        item = item or InventoryItemLine(part_code="", size="LL", thickness_mm="10", finish_text="S/S", grade="A", sheet_count=1)
        row = 0 if insert_at_top else self.item_table.rowCount()
        self.item_table.insertRow(row)
        for col, value in enumerate(["", item.part_code, item.size, str(item.thickness_mm), item.finish_text, item.grade, str(item.sheet_count), item.note]):
            self.item_table.setItem(row, col, QTableWidgetItem(value))
        self.refresh_item_order_labels()

    def refresh_item_order_labels(self) -> None:
        for row in range(self.item_table.rowCount()):
            item = self.item_table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                self.item_table.setItem(row, 0, item)
            item.setText(str(row + 1))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def add_empty_row(self) -> None:
        current_row = self.item_table.currentRow()
        if current_row >= 0:
            values = []
            for col in range(1, 8):
                cell = self.item_table.item(current_row, col)
                values.append((cell.text() if cell else "").strip())
            part_code, size, thickness, finish_text, grade, sheet_count, note = values
            cloned = InventoryItemLine(
                part_code=part_code,
                size=size or "LL",
                thickness_mm=thickness or "10",
                finish_text=finish_text or "S/S",
                grade=grade or "A",
                sheet_count=int(sheet_count) if sheet_count.isdigit() else 1,
                note=note,
            )
            self.add_row(cloned, insert_at_top=True)
            self.item_table.setCurrentCell(0, 1)
            return
        self.add_row(insert_at_top=True)
        self.item_table.setCurrentCell(0, 1)

    def remove_current_row(self) -> None:
        row = self.item_table.currentRow()
        if row >= 0:
            self.item_table.removeRow(row)
            self.refresh_item_order_labels()

    def payload(self) -> Optional[Tuple[str, str, str, int, str, int, List[InventoryItemLine]]]:
        pallet_number = self.pallet_number.text().strip().upper()
        location_code = normalize_location_code(self.location.currentText())
        if not pallet_number or not location_code:
            QMessageBox.warning(self, "入力エラー", "パレット番号とロケーションを入力してください。")
            return None

        display_items: List[InventoryItemLine] = []
        for row in range(self.item_table.rowCount()):
            values = []
            for col in range(8):
                cell = self.item_table.item(row, col)
                values.append((cell.text() if cell else "").strip())
            _, part_code, size, thickness, finish_text, grade, sheet_count, note = values
            part_code = part_code.replace("#", "").replace("-", "").upper()
            if not part_code:
                QMessageBox.warning(self, "入力エラー", f"{row + 1}行目の品番を入力してください。")
                return None
            try:
                sheet_count_value = int(sheet_count)
            except ValueError:
                QMessageBox.warning(self, "入力エラー", f"{row + 1}行目の枚数が数値ではありません。")
                return None
            if not size:
                size = "LL"
            if not thickness or not finish_text or not grade:
                QMessageBox.warning(self, "入力エラー", f"{row + 1}行目の厚み、加工 / 裏表、グレードを入力してください。")
                return None
            display_items.append(InventoryItemLine(part_code=part_code, size=size.upper(), thickness_mm=thickness, finish_text=finish_text, grade=grade, sheet_count=sheet_count_value, note=note))

        items = list(reversed(display_items))

        if not items:
            QMessageBox.warning(self, "入力エラー", "明細を1件以上入力してください。")
            return None

        return pallet_number, self.received_date.text().strip(), location_code, int(self.orientation.currentData()), str(self.color.currentData()), self.stack_order.value(), items

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class TransferDialog(QDialog):
    def __init__(self, source_pallet: PalletRecord, target_pallets: List[PalletRecord], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("積み替えモード")
        self.resize(560, 260)
        self.source_pallet = source_pallet
        self.target_pallets = target_pallets

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.source_line = QComboBox()
        for item in source_pallet.items:
            self.source_line.addItem(item.identifier, item.line_id)
        self.target_pallet = QComboBox()
        for pallet in target_pallets:
            self.target_pallet.addItem(f"{pallet.pallet_number} ({pallet.location_code})", pallet.pallet_number)
        self.quantity = QSpinBox(); self.quantity.setRange(1, max([item.sheet_count for item in source_pallet.items] or [1]))
        self.source_line.currentIndexChanged.connect(self.sync_quantity_limit)
        form.addRow("移動元明細", self.source_line)
        form.addRow("移動先パレット", self.target_pallet)
        form.addRow("移動枚数", self.quantity)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.sync_quantity_limit()

    def sync_quantity_limit(self) -> None:
        item = self.selected_item()
        if item is None:
            self.quantity.setRange(1, 1)
            self.quantity.setValue(1)
            return
        self.quantity.setRange(1, max(1, item.sheet_count))
        self.quantity.setValue(min(self.quantity.value(), item.sheet_count))

    def selected_item(self) -> Optional[InventoryItemLine]:
        line_id = self.source_line.currentData()
        for item in self.source_pallet.items:
            if item.line_id == line_id:
                return item
        return None

    def payload(self) -> Optional[Tuple[str, str, int]]:
        item = self.selected_item()
        target = self.target_pallet.currentData()
        if item is None or not target:
            QMessageBox.warning(self, "入力エラー", "移動元明細と移動先パレットを選択してください。")
            return None
        return item.line_id, str(target), int(self.quantity.value())

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class TopMapWidget(QWidget):
    palletSelected = Signal(str)
    palletMoved = Signal(str, float, float, str)
    selectionCleared = Signal()
    palletDoubleClicked = Signal(str)
    blockedLocationToggled = Signal(str, bool)

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.selected_pallet = None; self.hover_pallet = None
        self.location_rects: Dict[str, QRect] = {}; self.pallet_rects: Dict[str, QRect] = {}
        self.dragging_pallet = None; self.drag_offset = QPoint(); self.drag_point = QPoint(); self.zoom = 1.0
        self.drag_start_point = QPoint()
        self.pan_offset = QPoint()
        self.panning = False
        self.pan_anchor = QPoint()
        self.blocked_edit_mode = False
        self.setMinimumHeight(560); self.setMouseTracking(True); self.setAttribute(Qt.WA_AcceptTouchEvents, True)

    def scaled_bounds(self) -> QRect:
        base = self.rect().adjusted(18, 18, -18, -18); center = base.center()
        width = max(200, int(base.width() * self.zoom)); height = max(170, int(base.height() * self.zoom * 1.07))
        rect = QRect(center.x() - width // 2, center.y() - height // 2, width, height)
        rect.translate(self.pan_offset)
        return rect

    def clamp_pan(self) -> None:
        base = self.rect().adjusted(18, 18, -18, -18)
        max_x = max(0, (int(base.width() * self.zoom) - base.width()) // 2)
        max_y = max(0, (int(base.height() * self.zoom * 1.07) - base.height()) // 2)
        self.pan_offset.setX(max(-max_x, min(max_x, self.pan_offset.x())))
        self.pan_offset.setY(max(-max_y, min(max_y, self.pan_offset.y())))

    def draw_grid(self, painter: QPainter, bounds: QRect) -> Tuple[int, int]:
        columns = GRID_COLUMNS; rows = GRID_ROWS
        painter.setPen(QPen(QColor("#102e4e"), 1, Qt.DotLine))
        for i in range(columns + 1):
            x = bounds.left() + i * bounds.width() / columns; painter.drawLine(int(x), bounds.top(), int(x), bounds.bottom())
        for i in range(rows + 1):
            y = bounds.top() + i * bounds.height() / rows; painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))
        painter.setPen(QPen(QColor("#1a4f80"), 1)); painter.drawRect(bounds)
        painter.setPen(QColor("#3b6f9e"))
        painter.setFont(QFont("Consolas", 7))
        for i in range(columns):
            x = bounds.left() + (i + 0.5) * bounds.width() / columns
            painter.drawText(QRect(int(x) - 14, bounds.top() - 16, 28, 12), Qt.AlignCenter, column_label(i))
        for i in range(rows):
            y = bounds.top() + (i + 0.5) * bounds.height() / rows
            painter.drawText(QRect(bounds.right() + 4, int(y) - 6, 28, 12), Qt.AlignVCenter | Qt.AlignLeft, str(i + 1))
        return columns, rows

    def compute_location_rects(self, bounds: QRect, columns: int, rows: int) -> Dict[str, QRect]:
        locations = sorted(self.store.locations)
        cell_map: Dict[str, QRect] = {}
        cell_w = bounds.width() / columns
        cell_h = bounds.height() / rows
        for location in locations:
            col, row = location_to_grid(location)
            cell_map[location] = QRect(
                int(bounds.left() + col * cell_w),
                int(bounds.top() + row * cell_h),
                max(24, int(cell_w)),
                max(24, int(cell_h)),
            )
        return cell_map

    def default_point_for_location(self, location: str) -> QPoint:
        rect = self.location_rects.get(location)
        if rect is None:
            bounds = self.scaled_bounds()
            return bounds.center()
        return rect.center()

    def draw_scale(self, bounds: QRect) -> float:
        scale = min(bounds.width() / 42000.0, bounds.height() / 28000.0)
        return max(0.012, min(scale, 0.06))

    def clamped_normalized_for_pallet(self, pallet: PalletRecord, map_x: float, map_y: float, stack_index: int = 0) -> Tuple[float, float]:
        bounds = self.scaled_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return map_x, map_y
        width_mm, depth_mm = footprint_mm(pallet)
        scale = self.draw_scale(bounds)
        half_w = (width_mm * scale) / 2.0
        half_h = (depth_mm * scale) / 2.0
        shift_x = stack_index * 6
        shift_y = stack_index * 5
        min_x = (half_w - shift_x) / bounds.width()
        max_x = (bounds.width() - half_w - shift_x) / bounds.width()
        min_y = (half_h + shift_y) / bounds.height()
        max_y = (bounds.height() - half_h + shift_y) / bounds.height()
        clamped_x = min(max(map_x, max(0.0, min_x)), min(0.999, max_x))
        clamped_y = min(max(map_y, max(0.0, min_y)), min(0.999, max_y))
        return clamped_x, clamped_y

    def normalized_position(self, point: QPoint, pallet: Optional[PalletRecord] = None) -> Tuple[float, float]:
        bounds = self.scaled_bounds()
        x = 0.5 if bounds.width() <= 0 else (point.x() - bounds.left()) / bounds.width()
        y = 0.5 if bounds.height() <= 0 else (point.y() - bounds.top()) / bounds.height()
        x = max(0.0, min(0.999, x))
        y = max(0.0, min(0.999, y))
        col = min(GRID_COLUMNS - 1, max(0, int(round(x * GRID_COLUMNS - 0.5))))
        row = min(GRID_ROWS - 1, max(0, int(round(y * GRID_ROWS - 0.5))))
        snapped_x = (col + 0.5) / GRID_COLUMNS
        snapped_y = (row + 0.5) / GRID_ROWS
        if pallet is not None:
            return self.clamped_normalized_for_pallet(pallet, snapped_x, snapped_y)
        return snapped_x, snapped_y

    def point_from_pallet(self, pallet: PalletRecord) -> QPoint:
        bounds = self.scaled_bounds()
        if pallet.map_x is not None and pallet.map_y is not None:
            map_x, map_y = self.clamped_normalized_for_pallet(pallet, pallet.map_x, pallet.map_y)
            x = bounds.left() + int(bounds.width() * map_x)
            y = bounds.top() + int(bounds.height() * map_y)
            return QPoint(x, y)
        return self.default_point_for_location(pallet.location_code)

    def nearest_location(self, point: QPoint) -> Optional[str]:
        if not self.location_rects:
            return None
        best_location = None
        best_distance = None
        for location, rect in self.location_rects.items():
            if location in self.store.blocked_locations:
                continue
            center = rect.center()
            distance = (center.x() - point.x()) ** 2 + (center.y() - point.y()) ** 2
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_location = location
            if rect.adjusted(-18, -18, 18, 18).contains(point):
                return location
        return best_location

    def location_at(self, point: QPoint) -> Optional[str]:
        for location, rect in self.location_rects.items():
            if rect.contains(point):
                return location
        return None

    def normalized_position_for_location(self, location: str, pallet: Optional[PalletRecord] = None) -> Tuple[float, float]:
        col, row = location_to_grid(location)
        map_x, map_y = (col + 0.5) / GRID_COLUMNS, (row + 0.5) / GRID_ROWS
        if pallet is not None:
            return self.clamped_normalized_for_pallet(pallet, map_x, map_y)
        return map_x, map_y

    def tooltip_text(self, pallet: PalletRecord) -> str:
        return pallet_popup_text(pallet)

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, rect: QRect) -> None:
        active = pallet.pallet_number in {self.selected_pallet, self.hover_pallet, self.dragging_pallet}
        color = pallet_color(pallet); fill = QColor(color); fill.setAlpha(42)
        outline = QColor(color.lighter(145) if active else color)
        painter.setBrush(fill); painter.setPen(QPen(outline, 2 if active else 1))
        painter.drawRoundedRect(rect, 5, 5); painter.setPen(QColor("#dff6ff")); painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.drawText(rect.adjusted(6, 4, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.pallet_number)
        painter.setFont(QFont("Yu Gothic UI", 7)); painter.drawText(rect.adjusted(6, 18, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.summary_text[:24])
        badge = QRect(rect.right() - 20, rect.bottom() - 16, 16, 12)
        painter.setBrush(color); painter.setPen(Qt.NoPen); painter.drawEllipse(badge)
        painter.setPen(QColor("#04111c")); painter.drawText(badge, Qt.AlignCenter, str(pallet.stack_order + 1))

    def paintEvent(self, event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.fillRect(self.rect(), QColor("#07111f"))
        self.location_rects.clear(); self.pallet_rects.clear(); bounds = self.scaled_bounds(); columns, rows = self.draw_grid(painter, bounds)
        entrance_rect = QRect(bounds.center().x() - 80, bounds.bottom() - 28, 160, 18)
        painter.setPen(QPen(QColor("#4fc3ff"), 2))
        painter.drawLine(entrance_rect.left(), entrance_rect.top(), entrance_rect.left() + 18, entrance_rect.top())
        painter.drawLine(entrance_rect.right() - 18, entrance_rect.top(), entrance_rect.right(), entrance_rect.top())
        painter.setPen(QColor("#7fd0ff")); painter.setFont(QFont("Yu Gothic UI", 8, QFont.Bold))
        painter.drawText(entrance_rect, Qt.AlignCenter, "入口")
        for location, rect in self.compute_location_rects(bounds, columns, rows).items():
            self.location_rects[location] = rect
            if location in self.store.blocked_locations:
                painter.setPen(QPen(QColor("#c85a68"), 1))
                painter.setBrush(QColor(200, 90, 104, 70))
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
                painter.setPen(QColor("#ffb4bc"))
                painter.setFont(QFont("Consolas", 8, QFont.Bold))
                painter.drawText(rect, Qt.AlignCenter, "X")
        group_index: Dict[str, int] = {}
        group_counts: Dict[str, int] = {}
        selected_group_key = None
        if self.selected_pallet:
            selected = self.store.get_pallet(self.selected_pallet)
            if selected is not None:
                selected_group_key = selected.stack_group or selected.pallet_number
        for pallet in sorted(self.store.pallets, key=lambda p: (p.location_code, p.stack_group or p.pallet_number, p.stack_order, p.pallet_number)):
            key = pallet.stack_group or pallet.pallet_number
            group_index[pallet.pallet_number] = group_counts.get(key, 0)
            group_counts[key] = group_counts.get(key, 0) + 1
        for pallet in sorted(self.store.pallets, key=lambda p: (p.location_code, p.stack_order, p.pallet_number)):
            width_mm, depth_mm = footprint_mm(pallet)
            base_point = self.point_from_pallet(pallet)
            scale = self.draw_scale(bounds)
            stack_index = group_index.get(pallet.pallet_number, pallet.stack_order)
            group_key = pallet.stack_group or pallet.pallet_number
            selected_stack = selected_group_key is not None and group_key == selected_group_key and group_counts.get(group_key, 1) > 1
            shift_x = 22 if selected_stack else 6
            shift_y = 17 if selected_stack else 5
            if selected_stack and stack_index > 0:
                painter.setPen(QPen(QColor("#5da7d9"), 1, Qt.DotLine))
                painter.drawLine(base_point, QPoint(base_point.x() + stack_index * shift_x, base_point.y() - stack_index * shift_y))
            rect = QRect(base_point.x() - int(width_mm * scale / 2) + stack_index * shift_x, base_point.y() - int(depth_mm * scale / 2) - stack_index * shift_y, max(18, int(width_mm * scale)), max(14, int(depth_mm * scale)))
            if self.dragging_pallet == pallet.pallet_number:
                rect.moveTo(self.drag_point - self.drag_offset)
            self.pallet_rects[pallet.pallet_number] = rect; self.draw_pallet(painter, pallet, rect)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        if self.blocked_edit_mode:
            location = self.location_at(point)
            if location:
                blocked = location not in self.store.blocked_locations
                self.blockedLocationToggled.emit(location, blocked)
            return
        if self.begin_drag_at(point):
            return
        self.selected_pallet = None
        self.selectionCleared.emit()
        if self.zoom > 1.0:
            self.panning = True
            self.pan_anchor = point

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        if self.panning:
            self.pan_offset += point - self.pan_anchor
            self.pan_anchor = point
            self.clamp_pan()
            self.update()
            return
        self.update_drag_at(point)

    def mouseReleaseEvent(self, event) -> None:
        if self.panning:
            self.panning = False
            return
        self.end_drag_at(event.position().toPoint())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number
                self.palletSelected.emit(pallet_number)
                self.palletDoubleClicked.emit(pallet_number)
                self.update()
                return

    def begin_drag_at(self, point: QPoint) -> bool:
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number
                self.dragging_pallet = pallet_number
                self.drag_start_point = point
                self.drag_offset = point - rect.topLeft()
                self.drag_point = point
                self.palletSelected.emit(pallet_number)
                self.update()
                return True
        return False

    def update_drag_at(self, point: QPoint) -> None:
        self.drag_point = point
        hit = None
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                hit = pallet_number
                break
        self.hover_pallet = hit
        pallet = self.store.get_pallet(hit) if hit else None
        if pallet:
            text = self.tooltip_text(pallet)
            self.setToolTip(text)
            QToolTip.showText(self.mapToGlobal(point), text, self)
        else:
            self.setToolTip("")
            QToolTip.hideText()
        self.setCursor(Qt.PointingHandCursor if hit and not self.dragging_pallet else Qt.ArrowCursor)
        self.update()

    def end_drag_at(self, point: QPoint) -> None:
        if not self.dragging_pallet:
            return
        moved = (point - self.drag_start_point).manhattanLength()
        if moved <= 6:
            self.dragging_pallet = None
            self.update()
            return
        destination = self.nearest_location(point)
        if destination:
            pallet = self.store.get_pallet(self.dragging_pallet)
            map_x, map_y = self.normalized_position_for_location(destination, pallet)
            self.palletMoved.emit(self.dragging_pallet, map_x, map_y, destination)
        self.dragging_pallet = None
        self.update()

    def event(self, event) -> bool:
        if event.type() in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            points = event.points()
            if not points:
                return True
            point = points[0].position().toPoint()
            if event.type() == QEvent.TouchBegin:
                self.begin_drag_at(point)
            elif event.type() == QEvent.TouchUpdate:
                self.update_drag_at(point)
            else:
                self.end_drag_at(point)
            return True
        return super().event(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9))); self.clamp_pan(); self.update()

    def zoom_in(self) -> None:
        self.zoom = min(2.8, self.zoom * 1.15); self.clamp_pan(); self.update()

    def zoom_out(self) -> None:
        self.zoom = max(0.5, self.zoom / 1.15); self.clamp_pan(); self.update()

    def reset_zoom(self) -> None:
        self.zoom = 1.0; self.pan_offset = QPoint(); self.update()

class IsometricMapWidget(QWidget):
    palletSelected = Signal(str)
    selectionCleared = Signal()
    palletDoubleClicked = Signal(str)

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.hover_pallet = None; self.selected_pallet = None; self.pallet_rects: Dict[str, QRect] = {}; self.zoom = 1.0
        self.pan_offset = QPoint()
        self.panning = False
        self.pan_anchor = QPoint()
        self.view_rotation = 1
        self.setMinimumHeight(560); self.setMouseTracking(True)

    def scaled_bounds(self) -> QRect:
        base = self.rect().adjusted(22, 22, -22, -22); center = base.center()
        width = max(220, int(base.width() * self.zoom)); height = max(180, int(base.height() * self.zoom))
        rect = QRect(center.x() - width // 2, center.y() - height // 2, width, height)
        rect.translate(self.pan_offset)
        return rect

    def clamp_pan(self) -> None:
        base = self.rect().adjusted(22, 22, -22, -22)
        base_pan_x = max(80, int(base.width() * 0.28))
        base_pan_y = max(60, int(base.height() * 0.22))
        zoom_pan_x = max(0, (int(base.width() * self.zoom) - base.width()) // 2)
        zoom_pan_y = max(0, (int(base.height() * self.zoom) - base.height()) // 2)
        max_x = base_pan_x + zoom_pan_x
        max_y = base_pan_y + zoom_pan_y
        self.pan_offset.setX(max(-max_x, min(max_x, self.pan_offset.x())))
        self.pan_offset.setY(max(-max_y, min(max_y, self.pan_offset.y())))

    def floor_metrics(self, bounds: QRect) -> Tuple[QPointF, float, float]:
        origin = QPointF(bounds.center().x(), bounds.top() + max(54.0, bounds.height() * 0.08))
        half_w = bounds.width() * 0.40
        half_h = bounds.height() * 0.24
        return origin, half_w, half_h

    def vertical_height_scale(self, bounds: QRect) -> float:
        _, half_w, half_h = self.floor_metrics(bounds)
        width_scale = (half_w * 2.0) / 42000.0
        depth_scale = (half_h * 2.0) / 28000.0
        return min(width_scale, depth_scale)

    def rotated_normalized_point(self, nx: float, ny: float) -> Tuple[float, float]:
        rotation = self.view_rotation % 4
        if rotation == 1:
            return ny, 1.0 - nx
        if rotation == 2:
            return 1.0 - nx, 1.0 - ny
        if rotation == 3:
            return 1.0 - ny, nx
        return nx, ny

    def project_normalized_point(self, bounds: QRect, nx: float, ny: float) -> QPointF:
        origin, half_w, half_h = self.floor_metrics(bounds)
        rx, ry = self.rotated_normalized_point(nx, ny)
        return QPointF(origin.x() + (rx - ry) * half_w, origin.y() + (rx + ry) * half_h)

    def location_normalized_point(self, location: str) -> Tuple[float, float]:
        col, row = location_to_grid(location)
        return (col + 0.5) / GRID_COLUMNS, (row + 0.5) / GRID_ROWS

    def draw_floor(self, painter: QPainter, bounds: QRect) -> None:
        corners = [
            self.project_normalized_point(bounds, 0.0, 0.0),
            self.project_normalized_point(bounds, 1.0, 0.0),
            self.project_normalized_point(bounds, 1.0, 1.0),
            self.project_normalized_point(bounds, 0.0, 1.0),
        ]
        floor = QPolygonF(corners)
        painter.setPen(QPen(QColor("#235f9e"), 2))
        painter.setBrush(QColor(10, 22, 34, 24))
        painter.drawPolygon(floor)
        painter.setPen(QPen(QColor("#16385c"), 1))
        for i in range(1, GRID_COLUMNS):
            x = i / float(GRID_COLUMNS)
            painter.drawLine(self.project_normalized_point(bounds, x, 0.0), self.project_normalized_point(bounds, x, 1.0))
        for i in range(1, GRID_ROWS):
            y = i / float(GRID_ROWS)
            painter.drawLine(self.project_normalized_point(bounds, 0.0, y), self.project_normalized_point(bounds, 1.0, y))
        painter.setPen(QPen(QColor("#235f9e"), 1))
        painter.drawLine(corners[0], corners[2])
        painter.drawLine(corners[1], corners[3])

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, base: QPointF) -> QRect:
        width_mm, depth_mm = footprint_mm(pallet)
        total_width_mm = 42000.0
        total_depth_mm = 28000.0
        width_norm = max(0.012, width_mm / total_width_mm)
        depth_norm = max(0.012, depth_mm / total_depth_mm)
        cx_norm = pallet.map_x if pallet.map_x is not None else self.location_normalized_point(pallet.location_code)[0]
        cy_norm = pallet.map_y if pallet.map_y is not None else self.location_normalized_point(pallet.location_code)[1]
        bounds = self.scaled_bounds()
        corners_bottom = [
            self.project_normalized_point(bounds, cx_norm - width_norm / 2.0, cy_norm - depth_norm / 2.0),
            self.project_normalized_point(bounds, cx_norm + width_norm / 2.0, cy_norm - depth_norm / 2.0),
            self.project_normalized_point(bounds, cx_norm + width_norm / 2.0, cy_norm + depth_norm / 2.0),
            self.project_normalized_point(bounds, cx_norm - width_norm / 2.0, cy_norm + depth_norm / 2.0),
        ]
        current_center = QPointF(
            sum(point.x() for point in corners_bottom) / 4.0,
            sum(point.y() for point in corners_bottom) / 4.0,
        )
        offset_x = base.x() - current_center.x()
        offset_y = base.y() - current_center.y()
        corners_bottom = [QPointF(point.x() + offset_x, point.y() + offset_y) for point in corners_bottom]
        height = max(20.0, min(240.0, pallet.estimated_height_mm * self.vertical_height_scale(bounds) * 2.3))
        top = QPolygonF([QPointF(point.x(), point.y() - height) for point in corners_bottom])
        bottom_index = max(range(4), key=lambda index: (corners_bottom[index].y(), corners_bottom[index].x()))
        prev_index = (bottom_index - 1) % 4
        next_index = (bottom_index + 1) % 4
        face_a = QPolygonF([
            corners_bottom[bottom_index],
            corners_bottom[prev_index],
            QPointF(corners_bottom[prev_index].x(), corners_bottom[prev_index].y() - height),
            QPointF(corners_bottom[bottom_index].x(), corners_bottom[bottom_index].y() - height),
        ])
        face_b = QPolygonF([
            corners_bottom[bottom_index],
            corners_bottom[next_index],
            QPointF(corners_bottom[next_index].x(), corners_bottom[next_index].y() - height),
            QPointF(corners_bottom[bottom_index].x(), corners_bottom[bottom_index].y() - height),
        ])
        color = pallet_color(pallet); active = pallet.pallet_number in {self.selected_pallet, self.hover_pallet}
        fill = QColor(color)
        fill.setAlpha(170)
        outline = QColor(color.lighter(145) if active else color.darker(115))
        painter.setPen(QPen(outline, 2 if active else 1))
        painter.setBrush(fill); painter.drawPolygon(face_a)
        painter.setBrush(fill); painter.drawPolygon(face_b)
        painter.setBrush(fill); painter.drawPolygon(top)
        label_anchor = min([QPointF(point.x(), point.y() - height) for point in corners_bottom], key=lambda point: point.y() + (point.x() * 0.02))
        painter.setPen(QColor("#daf5ff")); painter.setFont(QFont("Consolas", 7, QFont.Bold)); painter.drawText(QPointF(label_anchor.x() + 4, label_anchor.y() + 13), pallet.pallet_number)
        painter.setFont(QFont("Yu Gothic UI", 6)); painter.drawText(QPointF(label_anchor.x() + 4, label_anchor.y() + 24), pallet.summary_text[:14])
        min_x = min(point.x() for point in corners_bottom)
        max_x = max(point.x() for point in corners_bottom)
        min_y = min(point.y() for point in corners_bottom) - height
        max_y = max(point.y() for point in corners_bottom)
        return QRect(int(min_x - 4), int(min_y - 4), int((max_x - min_x) + 10), int((max_y - min_y) + 10))

    def tooltip_text(self, pallet: PalletRecord) -> str:
        return pallet_popup_text(pallet)

    def paintEvent(self, event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.fillRect(self.rect(), QColor("#07111f")); self.pallet_rects.clear(); bounds = self.scaled_bounds(); self.draw_floor(painter, bounds)
        entrance_point = self.project_normalized_point(bounds, ENTRY_MAP_X, ENTRY_MAP_Y)
        painter.setPen(QPen(QColor("#4fc3ff"), 2))
        painter.setBrush(QColor(79, 195, 255, 60))
        painter.drawEllipse(QPointF(entrance_point.x(), entrance_point.y()), 8, 8)
        painter.drawLine(QPointF(entrance_point.x(), entrance_point.y()), QPointF(entrance_point.x(), entrance_point.y() + 26))
        painter.setPen(QColor("#7fd0ff"))
        painter.setFont(QFont("Yu Gothic UI", 8, QFont.Bold))
        painter.drawText(QRect(int(entrance_point.x() - 46), int(entrance_point.y() + 28), 92, 18), Qt.AlignCenter, "入口")
        groups: Dict[str, List[PalletRecord]] = {}
        for pallet in self.store.pallets:
            groups.setdefault(pallet.stack_group or pallet.pallet_number, []).append(pallet)
        base_points: Dict[str, QPointF] = {}
        for group_key, members in groups.items():
            members.sort(key=lambda p: (p.stack_order, p.updated_at, p.pallet_number))
            anchor = members[0]
            if anchor.map_x is not None and anchor.map_y is not None:
                base = self.project_normalized_point(bounds, anchor.map_x, anchor.map_y)
            else:
                nx, ny = self.location_normalized_point(anchor.location_code)
                base = self.project_normalized_point(bounds, nx, ny)
            lift = 0.0
            for member in members:
                base_points[member.pallet_number] = QPointF(base)
                rect = self.draw_pallet(painter, member, QPointF(base.x(), base.y() - lift))
                self.pallet_rects[member.pallet_number] = rect
                lift += max(20.0, min(240.0, member.estimated_height_mm * self.vertical_height_scale(bounds) * 2.3))
        if self.selected_pallet and self.selected_pallet in base_points:
            selected_base = base_points[self.selected_pallet]
            painter.setPen(QPen(QColor("#8fd8ff"), 1, Qt.DotLine))
            painter.drawLine(entrance_point, selected_base)
        view_names = {0: "入口手前", 1: "右側", 2: "奥側", 3: "左側"}
        painter.setPen(QColor("#6d90b5")); painter.setFont(QFont("Yu Gothic UI", 9)); painter.drawText(bounds.adjusted(6, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, f"45度ビュー / {view_names.get(self.view_rotation % 4, '')}")

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        if self.panning:
            self.pan_offset += point - self.pan_anchor
            self.pan_anchor = point
            self.clamp_pan()
            self.update()
            return
        hit = None
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                hit = pallet_number; break
        self.hover_pallet = hit; pallet = self.store.get_pallet(hit) if hit else None
        if pallet:
            text = self.tooltip_text(pallet)
            self.setToolTip(text)
            QToolTip.showText(self.mapToGlobal(point), text, self)
        else:
            self.setToolTip("")
            QToolTip.hideText()
        self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor); self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number; self.palletSelected.emit(pallet_number); self.update(); return
        self.selected_pallet = None
        self.selectionCleared.emit()
        self.panning = True
        self.pan_anchor = point

    def mouseReleaseEvent(self, event) -> None:
        self.panning = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number
                self.palletSelected.emit(pallet_number)
                self.palletDoubleClicked.emit(pallet_number)
                self.update()
                return

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9))); self.clamp_pan(); self.update()

    def zoom_in(self) -> None:
        self.zoom = min(2.8, self.zoom * 1.15); self.clamp_pan(); self.update()

    def zoom_out(self) -> None:
        self.zoom = max(0.5, self.zoom / 1.15); self.clamp_pan(); self.update()

    def reset_zoom(self) -> None:
        self.zoom = 1.0; self.pan_offset = QPoint(); self.update()

    def rotate_view_90(self) -> None:
        self.view_rotation = (self.view_rotation + 1) % 4
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        parent = self.parent()
        while parent is not None and not isinstance(parent, MainWindow):
            parent = parent.parent()
        if isinstance(parent, MainWindow):
            parent.apply_responsive_layout()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.store = load_store(); self.current_pallet_number = None
        self.inventory_sort_key = "part_code"
        self.inventory_sort_desc = False
        self.detail_drag_active = False
        self.detail_drag_offset = QPoint()
        self.detail_frame_manual_position: Optional[QPoint] = None
        self.setWindowTitle("Warehouse Management App - PySide6"); self.resize(1480, 920); self.setMinimumSize(900, 620)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.build_ui(); self.apply_theme(); self.refresh_all()

    def build_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central); root.setContentsMargins(14, 14, 14, 14); root.setSpacing(10)
        self.title_label = QLabel("WAREHOUSE"); self.title_label.setStyleSheet("font:700 18px 'Consolas'; color:#7fd0ff;")
        self.summary_label = QLabel(); self.summary_label.setStyleSheet("color:#89a4c2;"); self.summary_label.setWordWrap(True)
        self.new_button = QPushButton("新規登録"); self.new_button.clicked.connect(self.open_registration)
        self.blocked_mode_button = QPushButton("置けないマス設定"); self.blocked_mode_button.setCheckable(True); self.blocked_mode_button.toggled.connect(self.set_blocked_edit_mode)
        self.edit_button = QPushButton("明細編集"); self.edit_button.clicked.connect(self.edit_selected_pallet)
        self.ship_button = QPushButton("出庫"); self.ship_button.clicked.connect(self.ship_selected_pallet)
        self.transfer_button = QPushButton("積み替え"); self.transfer_button.clicked.connect(self.transfer_selected_pallet)
        self.unstack_button = QPushButton("列を解除"); self.unstack_button.clicked.connect(self.unstack_selected_pallet)
        self.stack_up_button = QPushButton("段を上げる"); self.stack_up_button.clicked.connect(lambda: self.adjust_selected_stack(1))
        self.stack_down_button = QPushButton("段を下げる"); self.stack_down_button.clicked.connect(lambda: self.adjust_selected_stack(-1))
        self.rotate_button = QPushButton("向き変更"); self.rotate_button.clicked.connect(self.rotate_selected_pallet)
        self.zoom_in_button = QPushButton("拡大"); self.zoom_out_button = QPushButton("縮小"); self.zoom_reset_button = QPushButton("等倍")
        self.zoom_in_button.clicked.connect(self.zoom_in_current_view); self.zoom_out_button.clicked.connect(self.zoom_out_current_view); self.zoom_reset_button.clicked.connect(self.reset_zoom_current_view)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("パレット番号 / 品番 / 加工 / ロケーション検索"); self.search_input.textChanged.connect(self.refresh_all)
        self.copy_inventory_button = QPushButton("一覧コピー"); self.copy_inventory_button.clicked.connect(self.copy_inventory_table)
        self.restore_shipment_button = QPushButton("復元"); self.restore_shipment_button.clicked.connect(self.restore_selected_shipments)
        self.delete_shipment_button = QPushButton("履歴削除"); self.delete_shipment_button.clicked.connect(self.delete_selected_shipments)
        self.export_button = QPushButton("Export"); self.export_button.clicked.connect(self.export_data)
        self.import_button = QPushButton("Import"); self.import_button.clicked.connect(self.import_data)
        self.clear_selection_button = QPushButton("選択解除"); self.clear_selection_button.clicked.connect(self.clear_selection)
        self.action_buttons = [self.new_button, self.blocked_mode_button, self.edit_button, self.ship_button, self.transfer_button, self.unstack_button, self.stack_up_button, self.stack_down_button, self.rotate_button, self.zoom_in_button, self.zoom_out_button, self.zoom_reset_button, self.export_button, self.import_button]
        for button in self.action_buttons: button.setMinimumHeight(40)
        self.search_input.setMinimumHeight(40)
        self.copy_inventory_button.setMinimumHeight(40)
        title_row = QHBoxLayout(); title_row.addWidget(self.title_label); title_row.addWidget(self.summary_label, 1)
        action_row = QHBoxLayout()
        for widget in [self.new_button, self.blocked_mode_button, self.edit_button, self.ship_button, self.transfer_button, self.unstack_button, self.stack_down_button, self.stack_up_button, self.rotate_button, self.zoom_in_button, self.zoom_out_button, self.zoom_reset_button]:
            action_row.addWidget(widget)
        action_row.addStretch(1)
        action_row.addWidget(self.export_button)
        action_row.addWidget(self.import_button)
        utility_row = QHBoxLayout(); utility_row.addWidget(self.search_input, 1); utility_row.addWidget(self.copy_inventory_button); utility_row.addWidget(self.restore_shipment_button); utility_row.addWidget(self.delete_shipment_button)
        header_shell = QVBoxLayout(); header_shell.setSpacing(8); header_shell.addLayout(title_row); header_shell.addLayout(action_row); header_shell.addLayout(utility_row); root.addLayout(header_shell)
        self.map_container = QWidget(); root.addWidget(self.map_container, 1)
        map_layout = QVBoxLayout(self.map_container); map_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(); map_layout.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self.handle_tab_changed)
        self.detail_frame = QFrame(self.map_container); self.detail_frame.hide()
        self.detail_frame.installEventFilter(self)
        detail_layout = QHBoxLayout()
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(8)
        self.detail_frame.setLayout(detail_layout)
        self.stack_detail_selector = QListWidget()
        self.stack_detail_selector.setObjectName("stackDetailSelector")
        self.stack_detail_selector.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stack_detail_selector.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.stack_detail_selector.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stack_detail_selector.setFixedWidth(44)
        self.stack_detail_selector.setSpacing(2)
        self.stack_detail_selector.installEventFilter(self)
        self.stack_detail_selector.viewport().installEventFilter(self)
        self.stack_detail_selector.currentRowChanged.connect(self.handle_stack_detail_tab_changed)
        detail_layout.addWidget(self.stack_detail_selector)
        self.stack_detail_pages = QStackedWidget()
        self.stack_detail_pages.installEventFilter(self)
        detail_layout.addWidget(self.stack_detail_pages, 1)
        self.top_map = TopMapWidget(self.store); self.top_map.palletSelected.connect(self.select_pallet); self.top_map.palletMoved.connect(self.move_pallet); self.top_map.selectionCleared.connect(self.clear_selection); self.top_map.palletDoubleClicked.connect(self.open_selected_pallet_editor); self.top_map.blockedLocationToggled.connect(self.toggle_blocked_location); self.tabs.addTab(self.wrap_widget(self.top_map), "真上")
        self.iso_map = IsometricMapWidget(self.store); self.iso_map.palletSelected.connect(self.select_pallet); self.iso_map.selectionCleared.connect(self.clear_selection); self.iso_map.palletDoubleClicked.connect(self.open_selected_pallet_editor)
        self.iso_rotate_button = QPushButton("視点90°")
        self.iso_rotate_button.setParent(self.iso_map)
        self.iso_rotate_button.clicked.connect(self.rotate_iso_view)
        self.iso_rotate_button.raise_()
        self.tabs.addTab(self.wrap_widget(self.iso_map), "45度ビュー")
        self.inventory_table = QTableWidget(0, 12); self.inventory_table.setHorizontalHeaderLabels(["品名", "品番", "サイズ", "厚み", "加工 / 裏表", "グレード", "総枚数", "総高さ", "パレット数", "保管場所", "入庫日", "備考"])
        self.inventory_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.inventory_table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeToContents); self.inventory_table.horizontalHeader().setSectionResizeMode(11, QHeaderView.Stretch); self.tabs.addTab(self.wrap_widget(self.inventory_table), "在庫一覧")
        self.inventory_table.horizontalHeader().sectionClicked.connect(self.handle_inventory_header_click)
        self.shipment_table = QTableWidget(0, 10); self.shipment_table.setHorizontalHeaderLabels(["出庫日", "パレット番号", "品名", "品数", "総枚数", "総高さ", "最終位置", "入庫日", "色", "備考"])
        self.shipment_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.shipment_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.shipment_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch); self.shipment_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch); self.tabs.addTab(self.wrap_widget(self.shipment_table), "出庫一覧")
        self.apply_responsive_layout()
        self.handle_tab_changed(self.tabs.currentIndex())
        self.update_detail_overlay_geometry()

    def wrap_widget(self, widget: QWidget) -> QWidget:
        shell = QWidget(); layout = QVBoxLayout(shell); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(widget); return shell

    def active_map_widget(self) -> Optional[QWidget]:
        if not hasattr(self, "tabs"):
            return None
        if self.tabs.currentIndex() == 0:
            return self.top_map
        if self.tabs.currentIndex() == 1:
            return self.iso_map
        return None

    def current_stack_detail_pallet(self) -> Optional[PalletRecord]:
        if not hasattr(self, "stack_detail_pages"):
            return None
        current_page = self.stack_detail_pages.currentWidget()
        if current_page is None:
            return None
        pallet_number = current_page.property("pallet_number")
        if not pallet_number:
            return None
        return self.store.get_pallet(str(pallet_number))

    def update_stack_detail_style(self) -> None:
        compact = self.width() < 1180
        narrow = self.width() < 980
        current_pallet = self.current_stack_detail_pallet()
        color = pallet_color(current_pallet) if isinstance(current_pallet, PalletRecord) else QColor("#f0c860")
        border_color = color.name()
        soft = QColor(color)
        soft.setAlpha(78)
        self.detail_frame.setStyleSheet(f"background:{soft.name(QColor.HexArgb)}; border:2px solid {border_color}; border-radius:8px;")
        self.stack_detail_selector.setStyleSheet(
            f"QListWidget#stackDetailSelector {{ background:transparent; border:none; outline:none; padding:0; }}"
            f"QListWidget#stackDetailSelector::item {{ background:#243141; color:#c8d7ea; padding:3px 0; margin:0 0 2px 0; border-radius:5px; text-align:center; font-weight:700; min-height:18px; }}"
            f"QListWidget#stackDetailSelector::item:selected {{ background:{border_color}; color:#10161e; }}"
        )
        self.stack_detail_pages.setStyleSheet(
            f"QLabel {{ color:#fff7d6; font:{'8pt' if narrow else ('8.5pt' if compact else '9pt')} 'Yu Gothic UI'; }}"
        )

    def handle_tab_changed(self, _index: int) -> None:
        is_inventory = self.tabs.currentIndex() == 2
        is_shipment = self.tabs.currentIndex() == 3
        self.search_input.setVisible(is_inventory)
        self.copy_inventory_button.setVisible(is_inventory)
        self.restore_shipment_button.setVisible(is_shipment)
        self.delete_shipment_button.setVisible(is_shipment)
        if hasattr(self, "iso_rotate_button"):
            self.iso_rotate_button.setVisible(self.tabs.currentIndex() == 1)
        self.update_detail_overlay_geometry()

    def handle_stack_detail_tab_changed(self, _index: int) -> None:
        if hasattr(self, "stack_detail_pages") and self.stack_detail_pages.currentIndex() != _index:
            self.stack_detail_pages.setCurrentIndex(_index)
        self.update_stack_detail_style()
        self.update_detail_overlay_geometry()

    def eventFilter(self, source, event) -> bool:
        detail_frame = getattr(self, "detail_frame", None)
        stack_detail_pages = getattr(self, "stack_detail_pages", None)
        stack_detail_selector = getattr(self, "stack_detail_selector", None)
        map_container = getattr(self, "map_container", None)
        tabs = getattr(self, "tabs", None)
        current_page = stack_detail_pages.currentWidget() if stack_detail_pages is not None else None
        current_label = current_page.findChild(QLabel) if current_page is not None else None
        current_scroll = current_page.findChild(QScrollArea) if current_page is not None else None
        draggable_sources = {detail_frame, stack_detail_pages, current_page, current_label}
        if current_scroll is not None:
            draggable_sources.add(current_scroll)
            draggable_sources.add(current_scroll.viewport())
        if event.type() == QEvent.MouseButtonPress and source in draggable_sources and event.button() == Qt.LeftButton:
            self.detail_drag_active = True
            if detail_frame is not None:
                self.detail_drag_offset = event.globalPosition().toPoint() - detail_frame.pos()
            return False
        if event.type() == QEvent.MouseMove and self.detail_drag_active and detail_frame is not None and map_container is not None and tabs is not None and source in draggable_sources and (event.buttons() & Qt.LeftButton):
            frame_size = detail_frame.size()
            new_pos = event.globalPosition().toPoint() - self.detail_drag_offset
            max_x = max(14, map_container.width() - frame_size.width() - 14)
            max_y = max(tabs.tabBar().height() + 12, map_container.height() - frame_size.height() - 14)
            clamped = QPoint(max(14, min(new_pos.x(), max_x)), max(tabs.tabBar().height() + 12, min(new_pos.y(), max_y)))
            detail_frame.move(clamped)
            self.detail_frame_manual_position = QPoint(clamped)
            return True
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self.detail_drag_active = False
        if event.type() == QEvent.MouseButtonDblClick and stack_detail_pages is not None and stack_detail_selector is not None:
            watched = {detail_frame, stack_detail_selector, stack_detail_selector.viewport(), stack_detail_pages}
            if current_page is not None:
                watched.add(current_page)
                if current_label is not None:
                    watched.add(current_label)
                if current_scroll is not None:
                    watched.add(current_scroll)
                    watched.add(current_scroll.viewport())
            if source in watched:
                pallet = self.current_stack_detail_pallet()
                if pallet is not None:
                    self.open_selected_pallet_editor(pallet.pallet_number)
                    return True
        return super().eventFilter(source, event)

    def apply_responsive_layout(self) -> None:
        width = self.width()
        compact = width < 1180
        narrow = width < 980
        button_height = 34 if compact else 40
        combo_height = 34 if compact else 40
        self.title_label.setStyleSheet(f"font:700 {'15' if compact else '18'}px 'Consolas'; color:#7fd0ff;")
        self.summary_label.setStyleSheet(f"color:#89a4c2; font:{'8.5pt' if compact else '10pt'} 'Yu Gothic UI';")
        text_map = {
            self.new_button: "新規" if compact else "新規登録",
            self.blocked_mode_button: "禁止マス" if compact else "置けないマス設定",
            self.edit_button: "編集" if compact else "明細編集",
            self.ship_button: "出庫",
            self.transfer_button: "積替" if compact else "積み替え",
            self.unstack_button: "解除" if compact else "列を解除",
            self.stack_up_button: "上げる" if compact else "段を上げる",
            self.stack_down_button: "下げる" if compact else "段を下げる",
            self.rotate_button: "向き" if compact else "向き変更",
            self.zoom_in_button: "拡大",
            self.zoom_out_button: "縮小",
            self.zoom_reset_button: "等倍",
            self.export_button: "出力" if compact else "Export",
            self.import_button: "読込" if compact else "Import",
        }
        for button in self.action_buttons:
            button.setMinimumHeight(button_height)
            button.setText(text_map.get(button, button.text()))
        self.search_input.setMinimumHeight(combo_height)
        self.copy_inventory_button.setMinimumHeight(combo_height)
        self.restore_shipment_button.setMinimumHeight(combo_height)
        self.delete_shipment_button.setMinimumHeight(combo_height)
        self.copy_inventory_button.setText("コピー" if compact else "一覧コピー")
        self.search_input.setPlaceholderText("検索" if narrow else "パレット番号 / 品番 / 加工 / ロケーション検索")
        if hasattr(self, "iso_rotate_button") and hasattr(self, "iso_map"):
            self.iso_rotate_button.setText("視点90°")
            self.iso_rotate_button.setFixedHeight(30 if compact else 34)
            self.iso_rotate_button.adjustSize()
            self.iso_rotate_button.move(max(10, self.iso_map.width() - self.iso_rotate_button.width() - 14), 12)
        self.update_stack_detail_style()

    def update_detail_overlay_geometry(self) -> None:
        if not hasattr(self, "detail_frame") or not hasattr(self, "map_container") or not hasattr(self, "stack_detail_pages"):
            return
        current_pallet = self.store.get_pallet(self.current_pallet_number or "") if hasattr(self, "store") else None
        if current_pallet is None:
            self.detail_frame.hide()
            return
        active_widget = self.active_map_widget()
        if active_widget is None:
            self.detail_frame.hide()
            return
        rect_map = getattr(active_widget, "pallet_rects", {})
        anchor_rect = rect_map.get(current_pallet.pallet_number)
        if anchor_rect is None:
            self.detail_frame.hide()
            return
        widget_top_left = active_widget.mapTo(self.map_container, QPoint(0, 0))
        anchor_left = widget_top_left.x() + anchor_rect.right() + 12
        anchor_top = widget_top_left.y() + anchor_rect.top()
        width = 360 if self.width() >= 1200 else 310
        current_page = self.stack_detail_pages.currentWidget()
        detail_label = current_page.findChild(QLabel) if current_page is not None else None
        line_count = max(1, (detail_label.text().count("\n") + 1) if detail_label is not None else 4)
        line_height = detail_label.fontMetrics().lineSpacing() if detail_label is not None else 16
        selector_width = self.stack_detail_selector.width() if self.stack_detail_selector.isVisible() else 0
        top_limit = self.tabs.tabBar().height() + 12
        available_height = max(140, self.map_container.height() - top_limit - 14)
        preferred_height = max(120, 28 + (line_count * line_height))
        detail_height = min(preferred_height, available_height)
        if self.detail_frame_manual_position is not None:
            x = self.detail_frame_manual_position.x()
            y = self.detail_frame_manual_position.y()
        else:
            x = min(anchor_left, self.map_container.width() - width - selector_width - 24)
            x = max(14, x)
            y = min(anchor_top, self.map_container.height() - detail_height - 14)
            y = max(top_limit, y)
        x = max(14, min(x, max(14, self.map_container.width() - width - selector_width - 24)))
        y = max(top_limit, min(y, max(top_limit, self.map_container.height() - detail_height - 14)))
        self.detail_frame.setGeometry(x, y, width + selector_width + 8, detail_height)
        self.detail_frame.raise_()
        self.detail_frame.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_responsive_layout()
        self.update_detail_overlay_geometry()

    def apply_theme(self) -> None:
        self.setStyleSheet("""QWidget { background:#091522; color:#e7f3ff; font:10pt 'Yu Gothic UI'; } QFrame { background:#0f1d2c; border:1px solid #163450; border-radius:8px; } QLineEdit, QComboBox, QSpinBox, QAbstractSpinBox, QTableWidget { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:6px; } QPushButton { background:#1d5d99; color:white; border:none; border-radius:8px; padding:8px 14px; font-weight:600; } QPushButton:hover { background:#2675c2; } QPushButton:checked { background:#8f3d47; } QHeaderView::section { background:#11253d; color:#9dd9ff; border:none; padding:6px; } QTabWidget::pane { border:1px solid #1a3c60; background:#07111f; } QTabBar::tab { background:#11253d; color:#88c3f0; padding:10px 16px; margin-right:4px; border-top-left-radius:6px; border-top-right-radius:6px; } QTabBar::tab:selected { background:#1d5d99; color:white; }""")

    def set_blocked_edit_mode(self, enabled: bool) -> None:
        self.top_map.blocked_edit_mode = enabled
        self.top_map.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.top_map.update()

    def toggle_blocked_location(self, location: str, blocked: bool) -> None:
        location = normalize_location_code(location)
        if blocked:
            if location not in self.store.blocked_locations:
                self.store.blocked_locations.append(location)
        else:
            self.store.blocked_locations = [code for code in self.store.blocked_locations if code != location]
        self.store.blocked_locations.sort(key=lambda code: location_to_grid(code))
        self.refresh_all()

    def keyword_tokens(self) -> List[str]:
        return [token for token in self.search_input.text().strip().lower().split() if token]

    def item_matches_keyword(self, item: InventoryItemLine) -> bool:
        tokens = self.keyword_tokens()
        if not tokens:
            return True
        haystacks = [
            item.identifier.lower(),
            item.part_code.lower(),
            item.size.lower(),
            item.finish_text.lower(),
            item.grade.lower(),
            item.note.lower(),
            str(item.thickness_mm),
            str(item.sheet_count),
        ]
        return all(any(token in hay for hay in haystacks) for token in tokens)

    def filtered_pallets(self) -> List[PalletRecord]:
        tokens = self.keyword_tokens()
        if not tokens:
            return list(self.store.pallets)
        result = []
        for pallet in self.store.pallets:
            pallet_haystacks = [
                pallet.pallet_number.lower(),
                pallet.location_code.lower(),
                pallet.received_date.lower(),
                color_label(pallet.color_key).lower(),
            ]
            pallet_match = all(any(token in hay for hay in pallet_haystacks) for token in tokens)
            item_match = any(self.item_matches_keyword(item) for item in pallet.items)
            if pallet_match or item_match:
                result.append(pallet)
        return result

    def refresh_all(self) -> None:
        self.store.ensure_defaults(); self.store.ensure_stack_groups(); self.store.normalize_stacks(); save_store(self.store)
        capacity = self.capacity_percent()
        self.summary_label.setText(f"パレット {len(self.store.pallets)} / 明細 {sum(len(p.items) for p in self.store.pallets)} / 総枚数 {sum(p.total_sheets for p in self.store.pallets)} / 面積使用率 {capacity:.1f}% / 禁止マス {len(self.store.blocked_locations)}")
        self.top_map.update(); self.iso_map.update(); self.refresh_inventory_table(); self.refresh_shipment_table(); self.refresh_detail()

    def capacity_percent(self) -> float:
        base_area = 1300 * 2300 * 100
        used_area = sum(footprint_mm(pallet)[0] * footprint_mm(pallet)[1] for pallet in self.store.pallets)
        return 0.0 if base_area <= 0 else (used_area / base_area) * 100.0

    def refresh_inventory_table(self) -> None:
        rows: Dict[Tuple[str, str, str, str, str, str, str], dict] = {}
        for pallet in self.filtered_pallets():
            for item in pallet.items:
                if not self.item_matches_keyword(item):
                    pallet_tokens = self.keyword_tokens()
                    pallet_haystacks = [pallet.pallet_number.lower(), pallet.location_code.lower(), pallet.received_date.lower(), color_label(pallet.color_key).lower()]
                    if pallet_tokens and not all(any(token in hay for hay in pallet_haystacks) for token in pallet_tokens):
                        continue
                thickness_text = str(item.thickness_mm)
                key = (item.identifier, item.part_code, item.size, thickness_text, item.finish_text, item.grade, item.note)
                row = rows.setdefault(key, {"identifier": item.identifier, "part_code": item.part_code, "size": item.size, "thickness": thickness_text, "finish": item.finish_text, "grade": item.grade, "note": item.note, "sheets": 0, "height": 0, "pallets": set(), "locations": set(), "received_dates": set()})
                row["sheets"] += item.sheet_count; row["height"] += item.height_mm; row["pallets"].add(pallet.pallet_number); row["locations"].add(pallet.location_code); row["received_dates"].add(pallet.received_date or "-")
        sort_key = self.inventory_sort_key
        reverse = self.inventory_sort_desc

        def sort_value(row: dict):
            if sort_key == "identifier":
                return (row["identifier"], row["part_code"], row["size"])
            if sort_key == "thickness":
                return (parse_thickness_value(row["thickness"]), row["thickness"], row["part_code"], row["size"])
            if sort_key == "finish":
                return (row["finish"], row["part_code"], row["size"])
            if sort_key == "grade":
                return (row["grade"], row["part_code"], row["size"])
            if sort_key == "height":
                return (row["height"], row["part_code"], row["size"])
            if sort_key == "sheets":
                return (row["sheets"], row["part_code"], row["size"])
            if sort_key == "size":
                return (row["size"], row["part_code"], parse_thickness_value(row["thickness"]), row["thickness"])
            if sort_key == "pallets":
                return (len(row["pallets"]), row["part_code"], row["size"])
            if sort_key == "locations":
                return (", ".join(sorted(row["locations"])), row["part_code"], row["size"])
            if sort_key == "received_dates":
                return (", ".join(sorted(row["received_dates"])), row["part_code"], row["size"])
            if sort_key == "note":
                return (row["note"], row["part_code"], row["size"])
            return (row["part_code"], row["size"], parse_thickness_value(row["thickness"]), row["thickness"])

        ordered = sorted(rows.values(), key=sort_value, reverse=reverse)
        self.inventory_table.setRowCount(len(ordered))
        for row_index, row in enumerate(ordered):
            values = [row["identifier"], row["part_code"], row["size"], str(row["thickness"]), row["finish"], row["grade"], str(row["sheets"]), str(row["height"]), str(len(row["pallets"])), ", ".join(sorted(row["locations"])), ", ".join(sorted(row["received_dates"])), row["note"] or "-"]
            for col, value in enumerate(values): self.inventory_table.setItem(row_index, col, QTableWidgetItem(value))

    def refresh_shipment_table(self) -> None:
        ordered = sorted(self.store.shipments, key=lambda shipment: shipment.shipped_at, reverse=True)
        self.shipment_table.setRowCount(len(ordered))
        for row_index, shipment in enumerate(ordered):
            values = [
                shipment.shipped_at,
                shipment.pallet_number,
                shipment.summary_text,
                str(len(shipment.items)),
                str(shipment.total_sheets),
                str(shipment.estimated_height_mm),
                shipment.location_code or "-",
                shipment.received_date or "-",
                color_label(shipment.color_key),
                shipment_notes_text(shipment),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, shipment.shipment_id)
                self.shipment_table.setItem(row_index, col, item)

    def copy_inventory_table(self) -> None:
        if self.inventory_table.rowCount() == 0:
            QApplication.clipboard().setText("")
            return
        headers = []
        for col in range(self.inventory_table.columnCount()):
            item = self.inventory_table.horizontalHeaderItem(col)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]
        for row in range(self.inventory_table.rowCount()):
            values = []
            for col in range(self.inventory_table.columnCount()):
                item = self.inventory_table.item(row, col)
                values.append(item.text() if item else "")
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    def delete_selected_shipments(self) -> None:
        rows = sorted({index.row() for index in self.shipment_table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "履歴削除", "削除したい出庫履歴を選択してください。")
            return
        if QMessageBox.question(self, "履歴削除", f"{len(rows)}件の出庫履歴を削除しますか？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        target_ids = []
        for row in rows:
            item = self.shipment_table.item(row, 0)
            shipment_id = item.data(Qt.UserRole) if item is not None else None
            if shipment_id:
                target_ids.append(str(shipment_id))
        self.store.shipments = [shipment for shipment in self.store.shipments if shipment.shipment_id not in target_ids]
        self.refresh_all()

    def restore_selected_shipments(self) -> None:
        rows = sorted({index.row() for index in self.shipment_table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "復元", "復元したい出庫履歴を選択してください。")
            return
        target_shipments: List[ShipmentRecord] = []
        for row in rows:
            item = self.shipment_table.item(row, 0)
            shipment_id = item.data(Qt.UserRole) if item is not None else None
            if not shipment_id:
                continue
            shipment = next((record for record in self.store.shipments if record.shipment_id == str(shipment_id)), None)
            if shipment is not None:
                target_shipments.append(shipment)
        if not target_shipments:
            return
        restored_numbers: List[str] = []
        renamed_pairs: List[Tuple[str, str]] = []
        for shipment in target_shipments:
            pallet_number = self.store.unique_pallet_number(shipment.pallet_number)
            if pallet_number != shipment.pallet_number:
                renamed_pairs.append((shipment.pallet_number, pallet_number))
            location_code = ENTRY_LOCATION
            if location_code not in self.store.locations:
                self.store.locations.append(location_code)
            restored = PalletRecord(
                pallet_number=pallet_number,
                location_code=location_code,
                received_date=shipment.received_date,
                color_key=shipment.color_key,
                stack_order=self.store.next_stack_order(location_code),
                stack_group=pallet_number,
                orientation=shipment.orientation,
                map_x=ENTRY_MAP_X,
                map_y=ENTRY_MAP_Y,
                items=[clone_item(item) for item in shipment.items],
                updated_at=now_text(),
            )
            self.store.pallets.append(restored)
            restored_numbers.append(pallet_number)
        target_ids = {shipment.shipment_id for shipment in target_shipments}
        self.store.shipments = [shipment for shipment in self.store.shipments if shipment.shipment_id not in target_ids]
        if restored_numbers:
            self.select_pallet(restored_numbers[0])
        self.refresh_all()
        if renamed_pairs:
            note = "\n".join([f"{before} -> {after}" for before, after in renamed_pairs[:6]])
            more = "" if len(renamed_pairs) <= 6 else f"\n他 {len(renamed_pairs) - 6} 件"
            QMessageBox.information(self, "復元", f"重複したパレット番号には連番を付けて復元しました。\n{note}{more}")

    def handle_inventory_header_click(self, column: int) -> None:
        mapping = {
            0: "identifier",
            1: "part_code",
            2: "size",
            3: "thickness",
            4: "finish",
            5: "grade",
            6: "sheets",
            7: "height",
            8: "pallets",
            9: "locations",
            10: "received_dates",
            11: "note",
        }
        target = mapping.get(column)
        if not target:
            return
        if self.inventory_sort_key == target:
            self.inventory_sort_desc = not self.inventory_sort_desc
        else:
            self.inventory_sort_key = target
            self.inventory_sort_desc = False
        self.refresh_inventory_table()

    def ship_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "出庫", "先にパレットを選択してください。")
            return
        if QMessageBox.question(self, "出庫", f"パレット {pallet.pallet_number} を出庫して倉庫表示から外しますか？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        shipment = ShipmentRecord(
            pallet_number=pallet.pallet_number,
            location_code=pallet.location_code,
            received_date=pallet.received_date,
            color_key=pallet.color_key,
            orientation=pallet.orientation,
            map_x=pallet.map_x,
            map_y=pallet.map_y,
            items=[clone_item(item) for item in pallet.items],
        )
        self.store.shipments.append(shipment)
        self.store.pallets = [item for item in self.store.pallets if item.pallet_number != pallet.pallet_number]
        self.clear_selection()
        self.refresh_all()

    def select_pallet(self, pallet_number: str) -> None:
        if self.current_pallet_number != pallet_number:
            self.detail_frame_manual_position = None
        self.current_pallet_number = pallet_number
        self.top_map.selected_pallet = pallet_number; self.iso_map.selected_pallet = pallet_number; self.top_map.update(); self.iso_map.update(); self.refresh_detail()

    def refresh_detail(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            self.detail_frame.hide()
            return
        active_widget = self.active_map_widget()
        if active_widget is None or not hasattr(active_widget, "tooltip_text"):
            self.detail_frame.hide()
            return
        self.stack_detail_selector.blockSignals(True)
        self.stack_detail_selector.clear()
        while self.stack_detail_pages.count():
            page = self.stack_detail_pages.widget(0)
            self.stack_detail_pages.removeWidget(page)
            page.deleteLater()
        members = list(reversed(self.store.group_members(pallet)))
        current_index = 0
        for index, member in enumerate(members):
            page = QWidget()
            page.setProperty("pallet_number", member.pallet_number)
            page.installEventFilter(self)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.installEventFilter(self)
            scroll.viewport().installEventFilter(self)
            inner = QWidget()
            inner_layout = QVBoxLayout(inner)
            inner_layout.setContentsMargins(4, 4, 6, 4)
            detail_label = QLabel(active_widget.tooltip_text(member))
            detail_label.setWordWrap(True)
            detail_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            detail_label.installEventFilter(self)
            inner_layout.addWidget(detail_label)
            inner_layout.addStretch(1)
            scroll.setWidget(inner)
            page_layout.addWidget(scroll)
            self.stack_detail_pages.addWidget(page)
            item = QListWidgetItem(f"{index + 1}")
            item.setTextAlignment(Qt.AlignCenter)
            self.stack_detail_selector.addItem(item)
            if member.pallet_number == pallet.pallet_number:
                current_index = index
        self.stack_detail_pages.setCurrentIndex(current_index)
        self.stack_detail_selector.setCurrentRow(current_index)
        self.stack_detail_selector.setVisible(self.stack_detail_selector.count() > 1)
        self.stack_detail_selector.blockSignals(False)
        self.update_stack_detail_style()
        self.update_detail_overlay_geometry()
        self.detail_frame.show()

    def nearby_stack_target(self, source: PalletRecord, map_x: float, map_y: float, location_code: str) -> Optional[PalletRecord]:
        best = None
        best_distance = None
        for pallet in self.store.pallets:
            if pallet.pallet_number == source.pallet_number:
                continue
            if pallet.location_code != location_code or pallet.map_x is None or pallet.map_y is None:
                continue
            distance = (pallet.map_x - map_x) ** 2 + (pallet.map_y - map_y) ** 2
            if distance <= 0.0049 and (best_distance is None or distance < best_distance):
                best = pallet
                best_distance = distance
        return best

    def move_pallet(self, pallet_number: str, map_x: float, map_y: float, destination: str) -> None:
        pallet = self.store.get_pallet(pallet_number)
        if not pallet: return
        destination = normalize_location_code(destination)
        if destination not in self.store.locations: self.store.locations.append(destination)
        members = self.store.group_members(pallet)
        old_x = pallet.map_x if pallet.map_x is not None else map_x
        old_y = pallet.map_y if pallet.map_y is not None else map_y
        dx = map_x - old_x
        dy = map_y - old_y
        target_stack = self.nearby_stack_target(pallet, map_x, map_y, destination)

        if target_stack and (target_stack.stack_group or target_stack.pallet_number) != (pallet.stack_group or pallet.pallet_number):
            target_group = target_stack.stack_group or target_stack.pallet_number
            target_members = self.store.group_members(target_stack)
            next_order = len(target_members)
            for index, member in enumerate(members):
                member.location_code = destination
                member.map_x = target_stack.map_x if target_stack.map_x is not None else map_x
                member.map_y = target_stack.map_y if target_stack.map_y is not None else map_y
                member.stack_group = target_group
                member.stack_order = next_order + index
                member.updated_at = now_text()
        else:
            group_key = pallet.stack_group or pallet.pallet_number
            for member in members:
                member.location_code = destination
                member.stack_group = group_key
                member.map_x = (member.map_x if member.map_x is not None else old_x) + dx
                member.map_y = (member.map_y if member.map_y is not None else old_y) + dy
                member.updated_at = now_text()
        pallet.updated_at = now_text(); self.select_pallet(pallet_number); self.refresh_all()

    def rotate_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "向き変更", "先にパレットを選択してください。")
            return
        pallet.orientation = 90 if pallet.orientation % 180 == 0 else 0
        if pallet.location_code:
            pallet.map_x, pallet.map_y = self.top_map.normalized_position_for_location(pallet.location_code, pallet)
        elif pallet.map_x is not None and pallet.map_y is not None:
            pallet.map_x, pallet.map_y = self.top_map.clamped_normalized_for_pallet(pallet, pallet.map_x, pallet.map_y)
        pallet.updated_at = now_text(); self.refresh_all()

    def adjust_selected_stack(self, delta: int) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "積み段変更", "先にパレットを選択してください。")
            return
        members = self.store.group_members(pallet)
        current_index = next((index for index, item in enumerate(members) if item.pallet_number == pallet.pallet_number), None)
        if current_index is None:
            return
        new_index = max(0, min(len(members) - 1, current_index + delta))
        if new_index == current_index:
            return
        other = members[new_index]
        pallet.stack_order, other.stack_order = other.stack_order, pallet.stack_order
        pallet.updated_at = now_text()
        self.refresh_all()

    def unstack_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "列を解除", "先にパレットを選択してください。")
            return
        members = self.store.group_members(pallet)
        if len(members) <= 1:
            QMessageBox.information(self, "列を解除", "このパレットは単独なので解除する列がありません。")
            return
        pallet.stack_group = pallet.pallet_number
        pallet.stack_order = 0
        pallet.map_x = min(0.98, (pallet.map_x if pallet.map_x is not None else 0.5) + 0.035)
        pallet.map_y = min(0.98, (pallet.map_y if pallet.map_y is not None else 0.5) + 0.02)
        pallet.updated_at = now_text()
        self.refresh_all()

    def edit_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "編集", "先にパレットを選択してください。")
            return
        self.open_selected_pallet_editor(pallet.pallet_number)

    def open_selected_pallet_editor(self, pallet_number: str) -> None:
        if pallet_number:
            self.current_pallet_number = pallet_number
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            return
        dialog = EditPalletDialog(pallet, self.store.locations, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        pallet_number, received_date, location_code, orientation, color_key, stack_order, items = payload
        requested_number = pallet_number
        pallet_number = self.store.unique_pallet_number(pallet_number, ignore=pallet.pallet_number)
        location_code = normalize_location_code(location_code)
        if location_code not in self.store.locations:
            self.store.locations.append(location_code)
        old_group = pallet.stack_group or pallet.pallet_number
        old_number = pallet.pallet_number
        pallet.pallet_number = pallet_number
        pallet.location_code = location_code
        pallet.received_date = received_date
        pallet.orientation = orientation
        pallet.color_key = color_key
        pallet.stack_order = stack_order
        pallet.items = items
        if old_group == old_number:
            pallet.stack_group = pallet_number
        pallet.updated_at = now_text()
        self.current_pallet_number = pallet_number
        self.refresh_all()
        if pallet_number != requested_number:
            QMessageBox.information(self, "編集", f"パレット番号が重複していたため、`{pallet_number}` に変更しました。")

    def transfer_selected_pallet(self) -> None:
        source = self.store.get_pallet(self.current_pallet_number or "")
        if not source:
            QMessageBox.information(self, "積み替え", "先に移動元パレットを選択してください。")
            return
        targets = [pallet for pallet in self.store.pallets if pallet.pallet_number != source.pallet_number]
        if not targets or not source.items:
            QMessageBox.information(self, "積み替え", "移動先パレットまたは移動元明細がありません。")
            return
        dialog = TransferDialog(source, targets, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        line_id, target_number, quantity = payload
        source_item = next((item for item in source.items if item.line_id == line_id), None)
        target = self.store.get_pallet(target_number)
        if source_item is None or target is None:
            return
        source_item.sheet_count -= quantity
        if source_item.sheet_count <= 0:
            source.items = [item for item in source.items if item.line_id != line_id]
        target.items.append(clone_item(source_item, quantity))
        source.updated_at = now_text()
        target.updated_at = now_text()
        self.refresh_all()

    def open_registration(self) -> None:
        dialog = RegistrationDialog(self.store.locations, self)
        if dialog.exec() != QDialog.Accepted: return
        payload = dialog.payload()
        if payload is None: return
        pallet_number, received_date, orientation, color_key, items = payload
        requested_number = pallet_number
        pallet_number = self.store.unique_pallet_number(pallet_number)
        if color_key == "AUTO":
            color_key = auto_color_key_for_items(items)
        location_code = ENTRY_LOCATION
        if location_code not in self.store.locations: self.store.locations.append(location_code)
        self.store.pallets.append(PalletRecord(pallet_number=pallet_number, location_code=location_code, received_date=received_date, color_key=color_key, stack_order=self.store.next_stack_order(location_code), stack_group=pallet_number, orientation=orientation, map_x=ENTRY_MAP_X, map_y=ENTRY_MAP_Y, items=items, updated_at=now_text()))
        self.select_pallet(pallet_number); self.refresh_all()
        if pallet_number != requested_number:
            QMessageBox.information(self, "新規登録", f"パレット番号が重複していたため、`{pallet_number}` として登録しました。")

    def export_data(self) -> None:
        default_name = APP_DIR / f"inventory-export-{datetime.now():%Y%m%d-%H%M%S}.json"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export", str(default_name), "JSON Files (*.json)")
        if file_path: save_store(self.store, Path(file_path)); QMessageBox.information(self, "Export", f"書き出しました。\n{file_path}")

    def import_data(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import", str(APP_DIR), "JSON Files (*.json)")
        if not file_path: return
        self.store = load_store(Path(file_path)); save_store(self.store); self.top_map.store = self.store; self.iso_map.store = self.store; self.current_pallet_number = None; self.refresh_all(); QMessageBox.information(self, "Import", f"読み込みました。\n{file_path}")

    def clear_selection(self) -> None:
        self.current_pallet_number = None; self.top_map.selected_pallet = None; self.iso_map.selected_pallet = None; self.top_map.update(); self.iso_map.update(); self.refresh_detail()

    def current_zoom_widget(self) -> Optional[QWidget]:
        current = self.tabs.currentWidget()
        if current is None or current.layout() is None or current.layout().count() == 0: return None
        return current.layout().itemAt(0).widget()

    def zoom_in_current_view(self) -> None:
        widget = self.current_zoom_widget();
        if hasattr(widget, "zoom_in"): widget.zoom_in()

    def zoom_out_current_view(self) -> None:
        widget = self.current_zoom_widget();
        if hasattr(widget, "zoom_out"): widget.zoom_out()

    def reset_zoom_current_view(self) -> None:
        widget = self.current_zoom_widget();
        if hasattr(widget, "reset_zoom"): widget.reset_zoom()

    def rotate_iso_view(self) -> None:
        if hasattr(self, "iso_map"):
            self.iso_map.rotate_view_90()


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    app = QApplication(sys.argv)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = MainWindow()
    if ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(ICON_PATH)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
