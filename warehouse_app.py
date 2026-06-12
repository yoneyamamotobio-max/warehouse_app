from __future__ import annotations

import json
import os
import re
import shutil
import sys
import ctypes
import traceback
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, QPointF, QRect, QItemSelectionModel, QSettings, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QAbstractItemView, QAbstractSpinBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QRadioButton, QScrollArea, QScroller, QSpinBox, QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QToolTip, QVBoxLayout, QWidget

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

DATA_PATH = APP_DIR / "inventory-data.json"
ICON_PATH = APP_DIR / "icon.ico"
STORE_LOG_PATH = APP_DIR / "store-error.log"
APP_ID = "Yone.WarehouseApp"
DAILY_BACKUP_RETENTION_DAYS = 90
GRID_COLUMNS = 12
GRID_ROWS = 23
AISLE_COLUMN_LABELS = {"B", "E", "F", "J"}
TOP_VIEW_MARGIN_LEFT = 72
TOP_VIEW_MARGIN_TOP = 54
TOP_VIEW_MARGIN_RIGHT = 94
TOP_VIEW_MARGIN_BOTTOM = 42
TOP_VIEW_SCROLL_PADDING = 140
TOP_VIEW_STACK_OFFSET_X = 10
TOP_VIEW_STACK_OFFSET_Y = 8
TOP_VIEW_SELECTED_STACK_OFFSET_X = 28
TOP_VIEW_SELECTED_STACK_OFFSET_Y = 22
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
FIXED_COLOR_LABEL_NOTES = {
    "RED": "#38",
    "BLUE": "#39",
    "YELLOW": "#40",
    "GREEN": "#45",
    "PINK": "#50",
    "PURPLE": "C/C",
    "GRAY": "混在 / その他",
}
DEFAULT_EDITABLE_COLOR_LABEL_NOTES = {
    "NAVY": "空パレット",
    "ORANGE": "スライス余り",
    "TEAL": "明細不明",
}
COLOR_ORDER = [
    "AUTO",
    "RED",
    "BLUE",
    "YELLOW",
    "GREEN",
    "PINK",
    "PURPLE",
    "GRAY",
    "NAVY",
    "ORANGE",
    "TEAL",
    "LIME",
    "BROWN",
    "WHITE",
    "BLACK",
    "CYAN",
    "MAGENTA",
]
EDITABLE_COLOR_LABEL_KEYS = [key for key in COLOR_ORDER if key not in FIXED_COLOR_LABEL_NOTES and key != "AUTO"]
AUTO_PART_COLOR_RULES = {
    "38": ("RED", "赤", "#FF6671"),
    "39": ("BLUE", "青", "#57C1FF"),
    "45": ("GREEN", "緑", "#31D07C"),
    "50": ("PINK", "桃", "#FF7AC3"),
    "40": ("YELLOW", "黄", "#FFC34D"),
}
AUTO_OTHER_COLOR = ("GRAY", "その他", "#7A8EA6")
VALID_SIZES = ["L", "LL", "EL", "OL"]
VALID_GRADES = ["A", "B", "C", "K", "片A", "S", ""]


def column_label(index: int) -> str:
    index += 1
    text = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        text = chr(65 + remainder) + text
    return text


def is_aisle_column(index: int) -> bool:
    return column_label(index) in AISLE_COLUMN_LABELS


def grid_column_display_label(index: int) -> str:
    label = column_label(index)
    if label in AISLE_COLUMN_LABELS:
        return f"{label}(通路)"
    return label


DEFAULT_LOCATIONS = [f"{column_label(col)}{row}" for row in range(1, GRID_ROWS + 1) for col in range(GRID_COLUMNS)]
ENTRY_LOCATION = f"{column_label((GRID_COLUMNS // 2) - 1)}{GRID_ROWS}"
ENTRY_MAP_X = 0.5
ENTRY_MAP_Y = 0.95
ENTRY_WAITING_SLOTS: List[Tuple[float, float]] = [
    (0.50, 1.08), (0.42, 1.08), (0.58, 1.08), (0.34, 1.08), (0.66, 1.08),
    (0.50, 1.13), (0.42, 1.13), (0.58, 1.13), (0.34, 1.13), (0.66, 1.13),
]
ENTRY_WAITING_TOLERANCE = 0.035


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def enable_swipe_scroll(scroll: QScrollArea) -> None:
    viewport = scroll.viewport()
    viewport.setAttribute(Qt.WA_AcceptTouchEvents, True)
    QScroller.grabGesture(viewport, QScroller.LeftMouseButtonGesture)


def normalize_lot(value) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().upper()


@dataclass
class InventoryItemLine:
    line_id: str = field(default_factory=lambda: uuid4().hex)
    part_code: str = ""
    size: str = "LL"
    thickness_mm: str = "10"
    finish_text: str = "S/S"
    grade: str = "A"
    sheet_count: int = 80
    lot: str = ""
    note: str = ""

    @property
    def identifier(self) -> str:
        grade_text = f" {self.grade}" if self.grade else ""
        return f"#{self.part_code}-{self.size}{self.thickness_mm} {self.finish_text}{grade_text} {self.sheet_count}"

    @property
    def height_mm(self) -> int:
        return int(round(parse_thickness_value(self.thickness_mm) * self.sheet_count))


def inventory_item_from_dict(item_data: dict) -> InventoryItemLine:
    data = item_data if isinstance(item_data, dict) else {}
    try:
        sheet_count = int(data.get("sheet_count", 80))
    except (TypeError, ValueError):
        sheet_count = 80
    return InventoryItemLine(
        line_id=str(data.get("line_id", uuid4().hex) or uuid4().hex),
        part_code=str(data.get("part_code", "") or ""),
        size=str(data.get("size", "LL") or "LL"),
        thickness_mm=str(data.get("thickness_mm", "10") or "10"),
        finish_text=str(data.get("finish_text", "S/S") or "S/S"),
        grade=str(data.get("grade", "A") or "A"),
        sheet_count=sheet_count,
        lot=normalize_lot(data.get("lot", "")),
        note=str(data.get("note", "") or ""),
    )


def inventory_item_to_dict(item: InventoryItemLine) -> dict:
    payload = asdict(item)
    payload["lot"] = normalize_lot(getattr(item, "lot", ""))
    return payload


@dataclass
class PalletRecord:
    pallet_number: str
    location_code: str
    received_date: str = ""
    color_key: str = "GRAY"
    color_mode: str = "AUTO"
    last_manual_color_key: str = "GRAY"
    stack_order: int = 0
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
    color_key: str = "GRAY"
    color_mode: str = "AUTO"
    last_manual_color_key: str = "GRAY"
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


@dataclass
class MapNoteRecord:
    note_id: str = field(default_factory=lambda: uuid4().hex)
    text: str = ""
    size: str = "LL"
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    color_key: str = "YELLOW"
    updated_at: str = field(default_factory=now_text)


@dataclass(frozen=True)
class PalletMoveState:
    pallet_number: str
    location_code: str
    map_x: Optional[float]
    map_y: Optional[float]
    stack_order: int


@dataclass(frozen=True)
class MoveAction:
    kind: str
    target_id: str
    pallet_before: Tuple[PalletMoveState, ...] = ()
    pallet_after: Tuple[PalletMoveState, ...] = ()
    note_before: Optional[Tuple[Optional[float], Optional[float]]] = None
    note_after: Optional[Tuple[Optional[float], Optional[float]]] = None


class InventoryStore:
    def __init__(self) -> None:
        self.locations = list(DEFAULT_LOCATIONS)
        self.blocked_locations: List[str] = []
        self.pallets: List[PalletRecord] = []
        self.shipments: List[ShipmentRecord] = []
        self.map_notes: List[MapNoteRecord] = []
        self.color_label_notes: Dict[str, str] = dict(DEFAULT_EDITABLE_COLOR_LABEL_NOTES)

    def ensure_defaults(self) -> None:
        for location in DEFAULT_LOCATIONS:
            if location not in self.locations:
                self.locations.append(location)
        self.sync_pallet_locations_to_visible_grid()

    def is_entry_waiting_pallet(self, pallet: PalletRecord) -> bool:
        return normalize_location_code(pallet.location_code) == ENTRY_LOCATION and pallet.map_y is not None and pallet.map_y > 1.0

    def pallets_at_location(self, location_code: str) -> List[PalletRecord]:
        location_code = visible_location_code(location_code)
        return [
            pallet
            for pallet in self.pallets
            if current_visible_location_for_pallet(pallet) == location_code and not self.is_entry_waiting_pallet(pallet)
        ]

    def has_pallet_at_location(self, location_code: str) -> bool:
        return bool(self.pallets_at_location(location_code))

    def set_blocked_location_with_validation(self, location_code: str, blocked: bool) -> bool:
        raw_location = str(location_code or "").strip()
        if not raw_location:
            return False
        location_code = normalize_location_code(raw_location)
        if blocked:
            pallets = self.pallets_at_location(location_code)
            if pallets:
                pallet_numbers = ", ".join(pallet.pallet_number for pallet in pallets[:6])
                more = "" if len(pallets) <= 6 else f" 他 {len(pallets) - 6} 件"
                raise ValueError(f"{location_code} には既にパレット {pallet_numbers}{more} があるため、置けないマスにはできません。")

        changed = False
        if blocked:
            if location_code not in self.blocked_locations:
                self.blocked_locations.append(location_code)
                changed = True
        else:
            before = len(self.blocked_locations)
            self.blocked_locations = [code for code in self.blocked_locations if normalize_location_code(code) != location_code]
            changed = len(self.blocked_locations) != before
        self.blocked_locations = sorted({normalize_location_code(code) for code in self.blocked_locations}, key=lambda code: location_to_grid(code))
        return changed

    def restore_blocked_locations_with_validation(self, locations: List[str]) -> None:
        self.blocked_locations = []
        for location in locations:
            try:
                self.set_blocked_location_with_validation(location, True)
            except ValueError:
                continue

    def sync_pallet_locations_to_visible_grid(self) -> None:
        for pallet in self.pallets:
            visible_code = current_visible_location_for_pallet(pallet)
            normalized_visible = normalize_location_code(visible_code) if visible_code else ""
            if normalized_visible and normalize_location_code(pallet.location_code) != normalized_visible:
                pallet.location_code = normalized_visible

    def normalize_stacks(self) -> None:
        self.sync_pallet_locations_to_visible_grid()
        groups: Dict[str, List[PalletRecord]] = {}
        for pallet in self.pallets:
            if self.is_entry_waiting_pallet(pallet):
                pallet.stack_order = 0
                continue
            groups.setdefault(normalize_location_code(pallet.location_code), []).append(pallet)
        for pallets in groups.values():
            pallets.sort(key=lambda p: (p.stack_order, p.updated_at, p.pallet_number))
            for index, pallet in enumerate(pallets):
                pallet.stack_order = index

    def next_stack_order(self, location_code: str, ignore: Optional[str] = None) -> int:
        location_code = normalize_location_code(location_code)
        values = [p.stack_order for p in self.pallets if normalize_location_code(p.location_code) == location_code and p.pallet_number != ignore and not self.is_entry_waiting_pallet(p)]
        return max(values) + 1 if values else 0

    def group_members(self, pallet: PalletRecord) -> List[PalletRecord]:
        if self.is_entry_waiting_pallet(pallet):
            return [pallet]
        location_code = normalize_location_code(pallet.location_code)
        members = [item for item in self.pallets if normalize_location_code(item.location_code) == location_code and not self.is_entry_waiting_pallet(item)]
        members.sort(key=lambda item: (item.stack_order, item.updated_at, item.pallet_number))
        return members

    def get_pallet(self, pallet_number: str) -> Optional[PalletRecord]:
        for pallet in self.pallets:
            if pallet.pallet_number == pallet_number:
                return pallet
        return None

    def get_map_note(self, note_id: str) -> Optional[MapNoteRecord]:
        for note in self.map_notes:
            if note.note_id == note_id:
                return note
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
        color_label_notes = {
            key: str(self.color_label_notes.get(key, DEFAULT_EDITABLE_COLOR_LABEL_NOTES.get(key, "")))
            for key in EDITABLE_COLOR_LABEL_KEYS
        }
        return {
            "locations": self.locations,
            "blocked_locations": self.blocked_locations,
            "color_label_notes": color_label_notes,
            "pallets": [
                {
                    "pallet_number": p.pallet_number,
                    "location_code": p.location_code,
                    "received_date": p.received_date,
                    "color_key": p.color_key,
                    "color_mode": p.color_mode,
                    "last_manual_color_key": p.last_manual_color_key,
                    "stack_order": p.stack_order,
                    "orientation": p.orientation,
                    "map_x": p.map_x,
                    "map_y": p.map_y,
                    "updated_at": p.updated_at,
                    "items": [inventory_item_to_dict(item) for item in p.items],
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
                    "color_mode": shipment.color_mode,
                    "last_manual_color_key": shipment.last_manual_color_key,
                    "orientation": shipment.orientation,
                    "map_x": shipment.map_x,
                    "map_y": shipment.map_y,
                    "items": [inventory_item_to_dict(item) for item in shipment.items],
                }
                for shipment in self.shipments
            ],
            "map_notes": [
                {
                    "note_id": note.note_id,
                    "text": note.text,
                    "size": note.size,
                    "map_x": note.map_x,
                    "map_y": note.map_y,
                    "color_key": note.color_key,
                    "updated_at": note.updated_at,
                }
                for note in self.map_notes
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InventoryStore":
        store = cls()
        raw_color_label_notes = payload.get("color_label_notes") or {}
        if isinstance(raw_color_label_notes, dict):
            store.color_label_notes = dict(DEFAULT_EDITABLE_COLOR_LABEL_NOTES)
            store.color_label_notes.update({
                str(key).upper(): str(value)
                for key, value in raw_color_label_notes.items()
                if str(key).upper() in EDITABLE_COLOR_LABEL_KEYS
            })
        store.locations = []
        for code in payload.get("locations", []):
            location = normalize_location_code(code)
            if location and location not in store.locations:
                store.locations.append(location)
        stored_blocked_locations = payload.get("blocked_locations") or []
        for pallet_data in payload.get("pallets", []):
            items = [inventory_item_from_dict(item_data) for item_data in pallet_data.get("items", [])]
            raw_color_key = str(pallet_data.get("color_key", "AUTO"))
            raw_color_mode = str(pallet_data.get("color_mode", "AUTO" if raw_color_key == "AUTO" else "MANUAL")).upper()
            raw_last_manual = str(pallet_data.get("last_manual_color_key", raw_color_key if raw_color_key != "AUTO" else auto_color_key_for_items(items))).upper()
            effective_color_key = resolve_effective_color_key(raw_color_mode, raw_last_manual, items)
            store.pallets.append(PalletRecord(pallet_number=pallet_data.get("pallet_number", ""), location_code=normalize_location_code(pallet_data.get("location_code", "")), received_date=pallet_data.get("received_date", ""), color_key=effective_color_key, color_mode=raw_color_mode, last_manual_color_key=raw_last_manual, stack_order=int(pallet_data.get("stack_order", 0)), orientation=int(pallet_data.get("orientation", 0)), map_x=pallet_data.get("map_x"), map_y=pallet_data.get("map_y"), updated_at=pallet_data.get("updated_at", now_text()), items=items))
        for shipment_data in payload.get("shipments", []):
            items = [inventory_item_from_dict(item_data) for item_data in shipment_data.get("items", [])]
            raw_color_key = str(shipment_data.get("color_key", "AUTO"))
            raw_color_mode = str(shipment_data.get("color_mode", "AUTO" if raw_color_key == "AUTO" else "MANUAL")).upper()
            raw_last_manual = str(shipment_data.get("last_manual_color_key", raw_color_key if raw_color_key != "AUTO" else auto_color_key_for_items(items))).upper()
            effective_color_key = resolve_effective_color_key(raw_color_mode, raw_last_manual, items)
            store.shipments.append(ShipmentRecord(shipment_id=shipment_data.get("shipment_id", uuid4().hex), shipped_at=shipment_data.get("shipped_at", now_text()), pallet_number=shipment_data.get("pallet_number", ""), location_code=normalize_location_code(shipment_data.get("location_code", "")), received_date=shipment_data.get("received_date", ""), color_key=effective_color_key, color_mode=raw_color_mode, last_manual_color_key=raw_last_manual, orientation=int(shipment_data.get("orientation", 0)), map_x=shipment_data.get("map_x"), map_y=shipment_data.get("map_y"), items=items))
        for note_data in payload.get("map_notes", []):
            size = str(note_data.get("size", "LL")).upper()
            if size not in VALID_SIZES:
                size = "LL"
            color_key = str(note_data.get("color_key", "YELLOW")).upper()
            if color_key not in COLOR_PRESETS or color_key == "AUTO":
                color_key = "YELLOW"
            store.map_notes.append(MapNoteRecord(note_id=note_data.get("note_id", uuid4().hex), text=str(note_data.get("text", "")), size=size, map_x=note_data.get("map_x"), map_y=note_data.get("map_y"), color_key=color_key, updated_at=note_data.get("updated_at", now_text())))
        store.ensure_defaults()
        store.restore_blocked_locations_with_validation(stored_blocked_locations)
        store.normalize_stacks()
        return store


def save_store(store: InventoryStore, path: Path = DATA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    bak_path = path.with_suffix(path.suffix + ".bak")
    bak_tmp_path = path.with_suffix(path.suffix + ".bak.tmp")
    try:
        try:
            create_daily_backup(path)
        except Exception:
            log_store_error(f"daily backup failed: {path}\n{traceback.format_exc()}")
        payload_text = json.dumps(store.to_dict(), ensure_ascii=False, indent=2)
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload_text)
            handle.flush()
            os.fsync(handle.fileno())
        # 破損した tmp を本体に昇格させないため、置換前にJSONとストア構造を検証する。
        verified_payload = json.loads(tmp_path.read_text(encoding="utf-8"))
        InventoryStore.from_dict(verified_payload)
        if path.exists():
            shutil.copy2(path, bak_tmp_path)
            bak_tmp_path.replace(bak_path)
        try:
            tmp_path.replace(path)
        except Exception:
            log_store_error(f"final replace failed: {path}\n{traceback.format_exc()}")
            raise
    finally:
        for cleanup_path in (tmp_path, bak_tmp_path):
            try:
                if cleanup_path.exists():
                    cleanup_path.unlink()
            except Exception:
                log_store_error(f"temporary file cleanup failed: {cleanup_path}\n{traceback.format_exc()}")


def create_daily_backup(path: Path = DATA_PATH) -> None:
    if not path.exists():
        return
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{path.stem}-{datetime.now():%Y-%m-%d}{path.suffix}"
    if backup_path.exists():
        prune_old_daily_backups(path)
        return
    shutil.copy2(path, backup_path)
    prune_old_daily_backups(path)


def prune_old_daily_backups(path: Path = DATA_PATH, retention_days: int = DAILY_BACKUP_RETENTION_DAYS) -> None:
    if retention_days <= 0:
        return
    backup_dir = path.parent / "backups"
    if not backup_dir.exists():
        return
    cutoff = datetime.now().date().toordinal() - retention_days
    pattern = re.compile(rf"^{re.escape(path.stem)}-(\d{{4}}-\d{{2}}-\d{{2}}){re.escape(path.suffix)}$")
    for candidate in backup_dir.glob(f"{path.stem}-*{path.suffix}"):
        match = pattern.match(candidate.name)
        if not match:
            continue
        try:
            backup_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if backup_date.toordinal() < cutoff:
            try:
                candidate.unlink()
            except Exception:
                log_store_error(f"daily backup prune failed: {candidate}\n{traceback.format_exc()}")


def log_store_error(message: str) -> None:
    try:
        with STORE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_text()}] {message}\n")
    except Exception:
        pass


def read_store_file(path: Path) -> InventoryStore:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return InventoryStore.from_dict(payload)


class StoreRecoveryError(RuntimeError):
    def __init__(self, message: str, paths: List[Path], log_path: Path) -> None:
        super().__init__(message)
        self.paths = paths
        self.log_path = log_path


def load_store(path: Path = DATA_PATH) -> InventoryStore:
    if not path.exists():
        store = InventoryStore()
        save_store(store, path)
        return store
    bak_path = path.with_suffix(path.suffix + ".bak")
    failed_paths: List[Path] = []

    try:
        return read_store_file(path)
    except Exception:
        log_store_error(f"load failed: {path}\n{traceback.format_exc()}")
        failed_paths.append(path)
        corrupt_path = path.with_name(f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}.corrupt{path.suffix}")
        try:
            path.replace(corrupt_path)
            failed_paths.append(corrupt_path)
            log_store_error(f"corrupt store moved to: {corrupt_path}")
        except Exception:
            log_store_error(f"failed to move corrupt store: {path}\n{traceback.format_exc()}")

    if bak_path.exists():
        try:
            return read_store_file(bak_path)
        except Exception:
            log_store_error(f"backup load failed: {bak_path}\n{traceback.format_exc()}")
            failed_paths.append(bak_path)
    else:
        log_store_error(f"backup store not found: {bak_path}")
        failed_paths.append(bak_path)

    log_store_error("store recovery failed; startup stopped")
    raise StoreRecoveryError("データ破損。復旧できません", failed_paths or [path, bak_path], STORE_LOG_PATH)


def show_store_recovery_dialog(error: StoreRecoveryError) -> None:
    dialog = QDialog()
    dialog.setWindowTitle("データ復旧")
    dialog.setMinimumWidth(620)
    layout = QVBoxLayout(dialog)
    title = QLabel("データ破損。復旧できません")
    title.setStyleSheet("font:700 18px 'Yu Gothic UI'; color:#ff9b9b;")
    layout.addWidget(title)
    message = QLabel("本体データとバックアップのどちらも読み込めなかったため、空データでは起動しません。破損ファイルを確認して、手動で復旧してください。")
    message.setWordWrap(True)
    layout.addWidget(message)
    path_text = "\n".join(str(p) for p in error.paths)
    paths = QLabel(f"破損または読込失敗したファイル:\n{path_text}\n\nログ:\n{error.log_path}")
    paths.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    paths.setWordWrap(True)
    paths.setStyleSheet("background:#0b1726; color:#d7ecff; border:1px solid #21466d; padding:10px;")
    layout.addWidget(paths)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


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


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def normalize_part_code(text: str) -> str:
    normalized = normalize_text(text).upper()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("#", "").replace("-", "")
    return normalized


def normalize_numeric_text(text: str) -> str:
    normalized = normalize_text(text)
    return re.sub(r"\s+", "", normalized)


def normalize_thickness_input(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).strip()
    for ch in ["、", "・", "･", "．", "，", ","]:
        normalized = normalized.replace(ch, ".")
    normalized = re.sub(r"\s+", "", normalized)
    for ch in ["〜", "～", "∼", "∾", "∿", "〰"]:
        normalized = normalized.replace(ch, "~")
    for ch in ["－", "ー", "―", "‐", "‑", "‒", "–", "—", "−"]:
        normalized = normalized.replace(ch, "-")
    return normalized


def is_valid_part_code(part_code: str) -> bool:
    return re.fullmatch(r"[A-Z0-9]+", normalize_part_code(part_code)) is not None


def normalize_finish_text(text: str) -> str:
    normalized = normalize_text(text)
    for ch in ["￥", "¥", "\\", "。", "？", "?"]:
        normalized = normalized.replace(ch, "/")
    return re.sub(r"\s+", " ", normalized).strip().upper()


def normalize_note(text: str) -> str:
    normalized = normalize_text(text).replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s{2,}", " ", normalized).strip()


def normalize_date_text(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return None
    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None
    if parsed > datetime.now().date():
        return None
    return parsed.strftime("%Y-%m-%d")


def is_entry_staged_pallet(pallet: PalletRecord) -> bool:
    if normalize_location_code(pallet.location_code) != ENTRY_LOCATION:
        return False
    if pallet.map_x is None or pallet.map_y is None:
        return True
    return any(
        abs(pallet.map_x - slot_x) <= ENTRY_WAITING_TOLERANCE and abs(pallet.map_y - slot_y) <= ENTRY_WAITING_TOLERANCE
        for slot_x, slot_y in ENTRY_WAITING_SLOTS
    )


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


def normalized_map_to_grid(map_x: float, map_y: float) -> Tuple[int, int]:
    clamped_x = max(0.0, min(0.999999, float(map_x)))
    clamped_y = max(0.0, min(0.999999, float(map_y)))
    col = min(GRID_COLUMNS - 1, max(0, int(clamped_x * GRID_COLUMNS)))
    row = min(GRID_ROWS - 1, max(0, int(clamped_y * GRID_ROWS)))
    return col, row


def format_location_code(col: int, row: int) -> str:
    safe_col = min(GRID_COLUMNS - 1, max(0, int(col)))
    safe_row = min(GRID_ROWS - 1, max(0, int(row)))
    return f"{column_label(safe_col)}{safe_row + 1:02d}"


def grid_center_to_map(col: int, row: int) -> Tuple[float, float]:
    safe_col = min(GRID_COLUMNS - 1, max(0, int(col)))
    safe_row = min(GRID_ROWS - 1, max(0, int(row)))
    return (safe_col + 0.5) / GRID_COLUMNS, (safe_row + 0.5) / GRID_ROWS


def visible_location_code(location: str) -> str:
    col, row = location_to_grid(location)
    return format_location_code(col, row)


def location_stack_label(pallet: PalletRecord) -> str:
    return f"{visible_location_code(pallet.location_code)}-{max(1, pallet.stack_order + 1)}"


def current_visible_location_for_pallet(pallet: PalletRecord) -> Optional[str]:
    if normalize_location_code(pallet.location_code) == ENTRY_LOCATION and pallet.map_y is not None and pallet.map_y > 1.0:
        return None
    location_code = normalize_location_code(pallet.location_code)
    if location_code and location_code != ENTRY_LOCATION:
        return visible_location_code(location_code)
    if pallet.map_x is not None and pallet.map_y is not None and pallet.map_y <= 1.0:
        col, row = normalized_map_to_grid(pallet.map_x, pallet.map_y)
        return format_location_code(col, row)
    return visible_location_code(location_code or "A1")


def column_code_from_location(location: str) -> str:
    code = normalize_location_code(location)
    prefix, _ = parse_location_code(code)
    return prefix


def color_label(color_key: str) -> str:
    return COLOR_PRESETS.get(color_key, COLOR_PRESETS["AUTO"])[0]


def editable_color_label_notes(store: Optional["InventoryStore"] = None) -> Dict[str, str]:
    notes = dict(DEFAULT_EDITABLE_COLOR_LABEL_NOTES)
    if store is not None:
        notes.update({
            key: str(value)
            for key, value in getattr(store, "color_label_notes", {}).items()
            if key in EDITABLE_COLOR_LABEL_KEYS
        })
    return notes


def color_choice_label(color_key: str, store: Optional["InventoryStore"] = None) -> str:
    key = str(color_key or "").upper()
    name = color_label(key)
    if key == "AUTO":
        return name
    if key in FIXED_COLOR_LABEL_NOTES:
        return f"{name} [{FIXED_COLOR_LABEL_NOTES[key]}]"
    note = editable_color_label_notes(store).get(key, "").strip()
    return f"{name} [{note}]" if note else name


def auto_color_key_for_items(items: List[InventoryItemLine]) -> str:
    finishes = {(item.finish_text or "").strip().upper() for item in items}
    if finishes == {"C/C"}:
        return "PURPLE"
    parts = {item.part_code.strip().upper() for item in items if item.part_code.strip()}
    if len(parts) == 1:
        part_code = next(iter(parts))
        if part_code in AUTO_PART_COLOR_RULES:
            return AUTO_PART_COLOR_RULES[part_code][0]
    return AUTO_OTHER_COLOR[0]


def auto_color_info(pallet: PalletRecord) -> Tuple[str, QColor]:
    auto_key = auto_color_key_for_items(pallet.items)
    finishes = {(item.finish_text or "").strip().upper() for item in pallet.items}
    if auto_key == "PURPLE" and finishes == {"C/C"}:
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


def auto_color_info_for_items(items: List[InventoryItemLine]) -> Tuple[str, QColor]:
    auto_key = auto_color_key_for_items(items)
    finishes = {(item.finish_text or "").strip().upper() for item in items}
    if auto_key == "PURPLE" and finishes == {"C/C"}:
        return "C/C = 紫", QColor(COLOR_PRESETS["PURPLE"][1])
    parts = {item.part_code.strip().upper() for item in items if item.part_code.strip()}
    if len(parts) == 1:
        part_code = next(iter(parts))
        if part_code in AUTO_PART_COLOR_RULES:
            _, label, color = AUTO_PART_COLOR_RULES[part_code]
            return f"#{part_code} = {label}", QColor(color)
    _, label, color = AUTO_OTHER_COLOR
    if len(parts) > 1:
        return f"混在 = {label}", QColor(color)
    return label, QColor(color)


def resolve_effective_color_key(color_mode: str, last_manual_color_key: str, items: List[InventoryItemLine]) -> str:
    if str(color_mode or "AUTO").upper() == "MANUAL":
        manual_key = str(last_manual_color_key or "GRAY").upper()
        if manual_key in COLOR_PRESETS and manual_key != "AUTO":
            return manual_key
        return "GRAY"
    return auto_color_key_for_items(items)


def pallet_color_text(pallet: PalletRecord) -> str:
    if str(pallet.color_mode or "AUTO").upper() != "AUTO":
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


def solid_circle_icon(color_value: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#d7ecff"), 1))
    painter.setBrush(QColor(color_value))
    painter.drawEllipse(1, 1, 12, 12)
    painter.end()
    return QIcon(pixmap)


def populate_color_combo(combo: QComboBox, selected_key: Optional[str] = None, include_auto: bool = True, store: Optional["InventoryStore"] = None) -> None:
    combo.clear()
    ordered_keys = [key for key in COLOR_ORDER if key in COLOR_PRESETS]
    ordered_keys.extend(key for key in COLOR_PRESETS if key not in ordered_keys)
    for key in ordered_keys:
        if key == "AUTO" and not include_auto:
            continue
        combo.addItem(color_swatch_icon(key), color_choice_label(key, store), key)
    if selected_key is not None:
        combo.setCurrentIndex(max(0, combo.findData(selected_key)))


def pallet_color(pallet: PalletRecord) -> QColor:
    preset = COLOR_PRESETS.get(pallet.color_key or "GRAY", COLOR_PRESETS["GRAY"])[1]
    if preset:
        return QColor(preset)
    return auto_color_info(pallet)[1]


def stack_display_number(store: "InventoryStore", pallet: PalletRecord) -> int:
    members = store.group_members(pallet)
    if len(members) <= 1:
        return 1
    return max(1, len(members) - pallet.stack_order)


def stack_position_label(store: "InventoryStore", pallet: PalletRecord) -> str:
    members = store.group_members(pallet)
    total = max(1, len(members))
    current = max(1, pallet.stack_order + 1)
    return f"{current}/{total}"


def pallet_popup_text(store: "InventoryStore", pallet: PalletRecord) -> str:
    lines = [f"パレット: {pallet.pallet_number}", "荷姿(上→下):"]
    ordered_items = pallet.items
    for item in ordered_items[:8]:
        line = f"- {item.identifier}"
        if item.lot:
            line += f" / Lot: {item.lot}"
        if item.note:
            line += f" / 備考: {item.note}"
        lines.append(line)
    if len(ordered_items) > 8:
        lines.append(f"... 他{len(ordered_items) - 8}件")
    lines.extend([
        "",
        "補足:",
        f"位置: {visible_location_code(pallet.location_code)} / 積み段: {stack_position_label(store, pallet)}",
        f"概算高: {pallet.estimated_height_mm}mm",
        f"入庫日: {pallet.received_date or '-'}",
        f"向き: {orientation_label(pallet.orientation)}",
        f"色: {pallet_color_text(pallet)}",
    ])
    return "\n".join(lines)


def footprint_mm_for_size(size: str, orientation: int = 0) -> Tuple[int, int]:
    size = str(size or "LL").upper()
    width, depth = (1400, 1300) if size == "L" else ((3500, 1400) if size == "OL" else (2300, 1300))
    return (depth, width) if orientation % 180 == 90 else (width, depth)


def footprint_mm(pallet: PalletRecord) -> Tuple[int, int]:
    sizes = [item.size.upper() for item in pallet.items] or ["LL"]
    size = max(sizes, key=lambda code: {"L": 1, "LL": 2, "EL": 2, "OL": 3}.get(code, 0))
    return footprint_mm_for_size(size, pallet.orientation)


def map_note_title(note: MapNoteRecord) -> str:
    for line in str(note.text or "").splitlines():
        title = line.strip()
        if title:
            return title
    return "メモ"


def map_note_popup_text(note: MapNoteRecord) -> str:
    return "\n".join([map_note_title(note), f"サイズ: {note.size}", "", note.text])


def parse_thickness_value(thickness_text: str) -> float:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", str(thickness_text or ""))]
    if not numbers:
        return 0.0
    return max(numbers)


def thickness_values(thickness_text: str) -> List[float]:
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", str(thickness_text or ""))]


def is_single_thickness(thickness_text: str) -> bool:
    text = normalize_thickness_input(thickness_text)
    return re.fullmatch(r"\d+(?:\.\d+)?", text) is not None


def is_thickness_range(thickness_text: str) -> bool:
    text = normalize_thickness_input(thickness_text)
    return re.fullmatch(r"\d+(?:\.\d+)?[-~〜]\d+(?:\.\d+)?", text) is not None


def is_valid_thickness(thickness_text: str) -> bool:
    text = normalize_thickness_input(thickness_text)
    if not text or text.startswith("-"):
        return False
    values = thickness_values(text)
    if not values:
        return False
    max_value = max(values)
    if max_value < 0.3 or max_value > 35.0:
        return False
    if is_single_thickness(text):
        return len(values) == 1
    if is_thickness_range(text):
        return len(values) >= 2
    return False


def format_thickness_value(value: float) -> str:
    rounded = round(min(35.0, max(0.3, value)), 3)
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
        lot=normalize_lot(getattr(item, "lot", "")),
        note=item.note,
    )


def shipment_notes_text(shipment: ShipmentRecord) -> str:
    notes = [item.note.strip() for item in shipment.items if item.note.strip()]
    return " / ".join(dict.fromkeys(notes)) if notes else "-"


HALF_WIDTH_INPUT_HINTS = Qt.ImhPreferLatin | Qt.ImhNoPredictiveText


def set_input_hints(widget: Optional[QWidget], hints) -> None:
    if widget is None:
        return
    if hasattr(widget, "setInputMethodHints"):
        widget.setInputMethodHints(hints)
    widget.setAttribute(Qt.WA_InputMethodEnabled, True)


def prefer_half_width(widget: Optional[QWidget]) -> None:
    set_input_hints(widget, HALF_WIDTH_INPUT_HINTS)


def request_software_keyboard(widget: Optional[QWidget]) -> None:
    if widget is None:
        return
    widget.setAttribute(Qt.WA_InputMethodEnabled, True)
    widget.setFocus(Qt.OtherFocusReason)
    try:
        QApplication.sendEvent(widget, QEvent(QEvent.RequestSoftwareInputPanel))
    except Exception:
        pass
    try:
        QGuiApplication.inputMethod().show()
    except Exception:
        pass


def normalize_lineedit_value(text: str, uppercase: bool = False, remove_spaces: bool = False, digits_only: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).strip()
    if digits_only:
        normalized = re.sub(r"[^0-9]", "", normalized)
    elif remove_spaces:
        normalized = re.sub(r"\s+", "", normalized)
    if uppercase:
        normalized = normalized.upper()
    return normalized


def normalize_thickness_text_value(text: str) -> str:
    return normalize_thickness_input(text)


def normalize_count_input(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).strip()
    return re.sub(r"\s+", "", normalized)


def is_valid_sheet_count_text(text: str) -> bool:
    normalized = normalize_count_input(text)
    if re.fullmatch(r"\d+", normalized) is None:
        return False
    value = int(normalized)
    return 1 <= value <= 600


def parse_sheet_count_text(text: str) -> Optional[int]:
    normalized = normalize_count_input(text)
    if re.fullmatch(r"\d+", normalized) is None:
        return None
    value = int(normalized)
    if value < 1 or value > 600:
        return None
    return value


def validate_item_fields(
    part_code_text: str,
    size_text: str,
    thickness_text: str,
    finish_text: str,
    grade_text: str,
    sheet_count_text: str,
    lot_text: str,
    note_text: str,
) -> Tuple[Optional[InventoryItemLine], Dict[str, str], Optional[str]]:
    original_note = str(note_text or "")
    normalized_part_code = normalize_part_code(part_code_text)
    normalized_size = normalize_text(size_text).upper()
    normalized_thickness = normalize_thickness_input(thickness_text)
    normalized_finish = normalize_finish_text(finish_text)
    normalized_grade = normalize_text(grade_text)
    normalized_lot = normalize_lot(lot_text)
    normalized_note = normalize_note(original_note)
    normalized_sheet_count = normalize_numeric_text(sheet_count_text)
    normalized_fields = {
        "part_code": normalized_part_code,
        "size": normalized_size,
        "thickness_mm": normalized_thickness,
        "finish_text": normalized_finish,
        "grade": normalized_grade,
        "sheet_count": normalized_sheet_count,
        "lot": normalized_lot,
        "note": normalized_note,
    }

    if not normalized_part_code:
        return None, normalized_fields, "品番を入力してください。"
    if not is_valid_part_code(normalized_part_code):
        return None, normalized_fields, "品番は半角英数字で入力してください。"
    if normalized_size not in VALID_SIZES:
        return None, normalized_fields, "サイズは選択肢の値のみ使えます。"
    if not normalized_thickness:
        return None, normalized_fields, "厚みを入力してください。"
    if not is_valid_thickness(normalized_thickness):
        return None, normalized_fields, "厚みは 0.3〜35mm の単一値、または 3-3.5 / 3~3.5 の形式で入力してください。"
    if not normalized_finish:
        return None, normalized_fields, "加工 / 裏表を入力してください。"
    if normalized_grade not in VALID_GRADES:
        return None, normalized_fields, "グレードは選択肢の値のみ使えます。"
    if re.fullmatch(r"\d+", normalized_sheet_count) is None:
        return None, normalized_fields, "枚数は 1〜600 の半角数字で入力してください。"
    sheet_count_value = int(normalized_sheet_count)
    if sheet_count_value < 1 or sheet_count_value > 600:
        return None, normalized_fields, "枚数は 1〜600 の半角数字で入力してください。"
    if "\n" in original_note or "\r" in original_note:
        return None, normalized_fields, "備考は改行できません。"
    if len(normalized_note) > 20:
        return None, normalized_fields, "備考は20文字以内で入力してください。"

    return InventoryItemLine(
        part_code=normalized_part_code,
        size=normalized_size,
        thickness_mm=normalized_thickness,
        finish_text=normalized_finish,
        grade=normalized_grade,
        sheet_count=sheet_count_value,
        lot=normalized_lot,
        note=normalized_note,
    ), normalized_fields, None


class AutoNormalizeLineEdit(QLineEdit):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None, *, uppercase: bool = False, remove_spaces: bool = False, digits_only: bool = False, prefer_latin: bool = True) -> None:
        super().__init__(text, parent)
        self.uppercase = uppercase
        self.remove_spaces = remove_spaces
        self.digits_only = digits_only
        if prefer_latin or digits_only:
            prefer_half_width(self)
        self.editingFinished.connect(self.normalize_value)

    def normalize_value(self) -> None:
        normalized = normalize_lineedit_value(self.text(), uppercase=self.uppercase, remove_spaces=self.remove_spaces, digits_only=self.digits_only)
        if normalized != self.text():
            self.setText(normalized)

    def focusOutEvent(self, event) -> None:
        self.normalize_value()
        super().focusOutEvent(event)


class HintedTableDelegate(QStyledItemDelegate):
    def __init__(
        self,
        normalize_rules: Optional[Dict[int, Dict[str, bool]]] = None,
        digits_only_columns: Optional[set] = None,
        parent: Optional[QWidget] = None,
        combo_options: Optional[Dict[int, List[str]]] = None,
    ) -> None:
        super().__init__(parent)
        self.normalize_rules = normalize_rules or {}
        self.digits_only_columns = digits_only_columns or set()
        self.combo_options = combo_options or {}

    def createEditor(self, parent, option, index):
        if index.column() in self.combo_options:
            combo = QComboBox(parent)
            combo.addItems(self.combo_options[index.column()])
            combo.setEditable(False)
            combo.setStyleSheet("QComboBox { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:4px 8px; font:11pt 'Yu Gothic UI', 'Segoe UI'; }")
            return combo
        editor = super().createEditor(parent, option, index)
        target = editor.lineEdit() if hasattr(editor, "lineEdit") else editor
        if index.column() in self.digits_only_columns or index.column() in self.normalize_rules:
            prefer_half_width(target)
        else:
            return editor
        rule = self.normalize_rules.get(index.column(), {})
        if hasattr(target, "editingFinished"):
            target.editingFinished.connect(lambda col=index.column(), w=target, r=rule: self.normalize_editor_value(w, col, r))
        if hasattr(editor, "lineEdit"):
            try:
                target.setAttribute(Qt.WA_InputMethodEnabled, True)
            except Exception:
                pass
        return editor

    def normalize_editor_value(self, editor: QWidget, column: int, rule: Dict[str, bool]) -> None:
        if not hasattr(editor, "text") or not hasattr(editor, "setText"):
            return
        if rule.get("finish", False):
            normalized = normalize_finish_text(editor.text())
        elif rule.get("thickness", False):
            normalized = normalize_thickness_text_value(editor.text())
        elif column in self.digits_only_columns:
            normalized = normalize_count_input(editor.text())
        else:
            normalized = normalize_lineedit_value(editor.text(), uppercase=rule.get("uppercase", False), remove_spaces=rule.get("remove_spaces", False))
        if normalized != editor.text():
            editor.setText(normalized)

    def setEditorData(self, editor, index) -> None:
        if index.column() in self.combo_options and isinstance(editor, QComboBox):
            value = str(index.data(Qt.EditRole) or index.data(Qt.DisplayRole) or "")
            found = editor.findText(value)
            editor.setCurrentIndex(found if found >= 0 else 0)
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index) -> None:
        if index.column() in self.combo_options and isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.EditRole)
            return
        super().setModelData(editor, model, index)


class TouchFriendlyHeaderView(QHeaderView):
    def __init__(self, orientation, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation, parent)
        self.resize_margin = 10
        self.resizing_section = -1
        self.resize_start_pos = 0
        self.resize_start_width = 0
        self.setSectionResizeMode(QHeaderView.Interactive)
        self.setMinimumSectionSize(40)
        self.setSectionsClickable(True)
        self.setMouseTracking(True)

    def section_near_edge(self, pos: QPoint) -> int:
        x = pos.x()
        for logical in range(self.count()):
            section_x = self.sectionViewportPosition(logical)
            section_w = self.sectionSize(logical)
            right_edge = section_x + section_w
            if abs(x - right_edge) <= self.resize_margin:
                return logical
        return -1

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        logical = self.section_near_edge(pos)
        if logical >= 0:
            self.resizing_section = logical
            self.resize_start_pos = pos.x()
            self.resize_start_width = self.sectionSize(logical)
            self.setCursor(Qt.SplitHCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self.resizing_section >= 0:
            delta = pos.x() - self.resize_start_pos
            new_width = max(self.minimumSectionSize(), self.resize_start_width + delta)
            self.resizeSection(self.resizing_section, new_width)
            event.accept()
            return
        if self.section_near_edge(pos) >= 0:
            self.setCursor(Qt.SplitHCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.resizing_section >= 0:
            self.resizing_section = -1
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self.resizing_section < 0:
            self.unsetCursor()
        super().leaveEvent(event)


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
        self.itemSelectionChanged.connect(self.update_drag_feedback)

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
        self.update_drag_feedback()

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
        selected_rows = {index.row() for index in self.selectionModel().selectedRows()} if self.selectionModel() is not None else set()
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
                elif row in selected_rows:
                    item.setBackground(QColor("#245f99"))
                    item.setForeground(QColor("#ffffff"))
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


class AutoNormalizeClearOnFocusLineEdit(ClearOnFocusLineEdit):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None, *, uppercase: bool = False, remove_spaces: bool = False, digits_only: bool = False, prefer_latin: bool = True) -> None:
        super().__init__(text, parent)
        self.uppercase = uppercase
        self.remove_spaces = remove_spaces
        self.digits_only = digits_only
        if prefer_latin or digits_only:
            prefer_half_width(self)
        self.editingFinished.connect(self.normalize_value)

    def normalize_value(self) -> None:
        normalized = normalize_lineedit_value(self.text(), uppercase=self.uppercase, remove_spaces=self.remove_spaces, digits_only=self.digits_only)
        if normalized != self.text():
            self.setText(normalized)

    def focusOutEvent(self, event) -> None:
        self.normalize_value()
        super().focusOutEvent(event)


class ThicknessLineEdit(AutoNormalizeLineEdit):
    def __init__(self, text: str = "10", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent, remove_spaces=True)

    def normalize_value(self) -> None:
        normalized = normalize_thickness_input(self.text())
        if normalized != self.text():
            self.setText(normalized)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        request_software_keyboard(self)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        request_software_keyboard(self)

    def can_step(self) -> bool:
        return is_valid_thickness(self.text())

    def step_by(self, steps: int) -> None:
        if not self.can_step():
            return
        current = parse_thickness_value(self.text())
        self.setText(format_thickness_value(current + steps))


class FinishClearOnFocusLineEdit(AutoNormalizeClearOnFocusLineEdit):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent, uppercase=False, remove_spaces=False)

    def normalize_value(self) -> None:
        normalized = normalize_finish_text(self.text())
        if normalized != self.text():
            self.setText(normalized)


class CountLineEdit(AutoNormalizeLineEdit):
    textValueChanged = Signal(str)

    def __init__(self, text: str = "0", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent, remove_spaces=True)
        self.textChanged.connect(self.textValueChanged.emit)

    def normalize_value(self) -> None:
        normalized = normalize_count_input(self.text())
        if normalized != self.text():
            self.setText(normalized)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        request_software_keyboard(self)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        request_software_keyboard(self)

    def numeric_value(self) -> Optional[int]:
        normalized = normalize_count_input(self.text())
        if re.fullmatch(r"\d+", normalized) is None:
            return None
        return int(normalized)

    def set_numeric_value(self, value: int) -> None:
        self.setText(str(int(value)))

    def is_valid_value(self, minimum: int = 1, maximum: int = 600) -> bool:
        normalized = normalize_count_input(self.text())
        if re.fullmatch(r"\d+", normalized) is None:
            return False
        value = int(normalized)
        return minimum <= value <= maximum

    def step_by(self, steps: int, minimum: int = 0, maximum: int = 600, fallback: Optional[int] = None) -> None:
        current = self.numeric_value()
        if current is None:
            current = fallback if fallback is not None else max(minimum, 0)
        next_value = max(minimum, min(maximum, current + steps))
        self.set_numeric_value(next_value)


class RepeatStepController(QObject):
    def __init__(self, button: QPushButton, callback, enabled_check=lambda: True, delay: int = 350, interval: int = 80) -> None:
        super().__init__(button)
        self.button = button
        self.callback = callback
        self.enabled_check = enabled_check
        self.delay_timer = QTimer(button)
        self.delay_timer.setSingleShot(True)
        self.delay_timer.setInterval(delay)
        self.repeat_timer = QTimer(button)
        self.repeat_timer.setInterval(interval)
        self.delay_timer.timeout.connect(self.repeat_timer.start)
        self.repeat_timer.timeout.connect(self.fire)
        button.pressed.connect(self.start)
        button.released.connect(self.stop)
        button.installEventFilter(self)

    def fire(self) -> None:
        if not self.button.isEnabled() or not self.enabled_check():
            self.stop()
            return
        self.callback()

    def start(self) -> None:
        self.stop()
        if not self.button.isEnabled() or not self.enabled_check():
            return
        self.callback()
        self.delay_timer.start()

    def stop(self) -> None:
        self.delay_timer.stop()
        self.repeat_timer.stop()

    def eventFilter(self, source, event) -> bool:
        if source is self.button and event.type() in (QEvent.Hide, QEvent.Leave, QEvent.FocusOut, QEvent.WindowDeactivate, QEvent.MouseButtonRelease, QEvent.TouchEnd):
            self.stop()
        return super().eventFilter(source, event)


class RememberedWindowDialog(QDialog):
    def configure_window_persistence(self, settings_prefix: str) -> None:
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.window_settings = QSettings(APP_ID, "WarehouseApp")
        self.window_geometry_key = f"{settings_prefix}/geometry"
        self.window_maximized_key = f"{settings_prefix}/maximized"

    def restore_remembered_window(self) -> None:
        saved_geometry = self.window_settings.value(self.window_geometry_key)
        if isinstance(saved_geometry, QRect) and saved_geometry.isValid():
            visible_on_screen = any(
                screen.availableGeometry().intersects(saved_geometry)
                for screen in QGuiApplication.screens()
            )
            if visible_on_screen:
                self.setGeometry(saved_geometry)
        if self.window_settings.value(self.window_maximized_key, False, type=bool):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def save_additional_window_state(self) -> None:
        pass

    def save_remembered_window(self) -> None:
        maximized = self.isMaximized() or bool(self.windowState() & Qt.WindowMaximized)
        normal_geometry = self.normalGeometry() if maximized else self.geometry()
        if normal_geometry.isValid():
            self.window_settings.setValue(self.window_geometry_key, normal_geometry)
        self.window_settings.setValue(self.window_maximized_key, maximized)
        self.save_additional_window_state()
        self.window_settings.sync()

    def accept(self) -> None:
        self.save_remembered_window()
        super().accept()

    def reject(self) -> None:
        self.save_remembered_window()
        super().reject()

    def closeEvent(self, event) -> None:
        self.save_remembered_window()
        super().closeEvent(event)


class RegistrationDialog(RememberedWindowDialog):
    WINDOW_SETTINGS_PREFIX = "new_item_dialog"

    def __init__(
        self,
        locations: List[str],
        parent: Optional[QWidget] = None,
        initial_payload: Optional[Tuple[str, str, int, str, str, List[InventoryItemLine]]] = None,
        initial_item: Optional[InventoryItemLine] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("新規登録")
        self.setSizeGripEnabled(True)
        self.configure_window_persistence(self.WINDOW_SETTINGS_PREFIX)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1120, max(760, int(available.width() * 0.92))), min(760, max(560, int(available.height() * 0.86))))
        else:
            self.resize(1040, 700)
        self.items: List[InventoryItemLine] = list(initial_payload[5]) if initial_payload is not None else []
        seed_item = initial_item if initial_payload is None else None
        self.editing_row: Optional[int] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        input_scroll = QScrollArea()
        self.input_scroll = input_scroll
        self.keyboard_scroll_widgets: List[QWidget] = []
        input_scroll.setWidgetResizable(True)
        input_scroll.setFrameShape(QFrame.NoFrame)
        input_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        enable_swipe_scroll(input_scroll)
        input_body = QWidget()
        input_layout = QVBoxLayout(input_body)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)
        input_scroll.setWidget(input_body)
        content_layout.addWidget(input_scroll, 0)

        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        content_layout.addWidget(list_panel, 1)
        root.addWidget(content, 1)

        form = QFormLayout()
        self.pallet_number = AutoNormalizeLineEdit(uppercase=True, remove_spaces=True)
        self.pallet_number.setPlaceholderText("例: R080324")
        self.received_date = AutoNormalizeLineEdit(initial_payload[1] if initial_payload is not None else datetime.now().strftime("%Y-%m-%d"), remove_spaces=True)
        self.orientation = QComboBox(); self.orientation.addItem("横向き", 0); self.orientation.addItem("縦向き", 90)
        initial_color_mode = initial_payload[3] if initial_payload is not None else "AUTO"
        initial_manual_color_key = initial_payload[4] if initial_payload is not None else "GRAY"
        store = getattr(parent, "store", None)
        self.color_auto = QRadioButton("自動判別")
        self.color_manual = QRadioButton("手動指定")
        self.color = QComboBox()
        populate_color_combo(self.color, initial_manual_color_key, include_auto=False, store=store)
        self.color_result = QLabel()
        self.color_preview = QLabel("      ")
        self.color_preview.setMinimumWidth(72)
        self.color_preview.setAlignment(Qt.AlignCenter)
        self.manual_color_row = QWidget()
        manual_color_layout = QHBoxLayout(self.manual_color_row)
        manual_color_layout.setContentsMargins(0, 0, 0, 0)
        manual_color_layout.addWidget(self.color)
        color_mode_row = QWidget()
        color_mode_layout = QHBoxLayout(color_mode_row)
        color_mode_layout.setContentsMargins(0, 0, 0, 0)
        color_mode_layout.addWidget(self.color_auto)
        color_mode_layout.addWidget(self.color_manual)
        color_mode_layout.addStretch(1)
        color_result_row = QWidget()
        color_result_layout = QHBoxLayout(color_result_row)
        color_result_layout.setContentsMargins(0, 0, 0, 0)
        color_result_layout.addWidget(self.color_result, 1)
        color_result_layout.addWidget(self.color_preview)
        form.addRow("パレット番号", self.pallet_number)
        form.addRow("入庫日", self.received_date)
        form.addRow("向き", self.orientation)
        form.addRow("色設定", color_mode_row)
        form.addRow("自動判別結果", color_result_row)
        form.addRow("手動色", self.manual_color_row)
        input_layout.addLayout(form)

        box = QFrame(); grid = QGridLayout(box)
        self.step_button_groups: List[Tuple[QPushButton, QPushButton, object]] = []
        self.step_repeat_controllers: List[RepeatStepController] = []
        initial_part_code = seed_item.part_code if seed_item is not None else "39"
        initial_size = seed_item.size if seed_item is not None and seed_item.size in VALID_SIZES else "LL"
        initial_thickness = seed_item.thickness_mm if seed_item is not None else "10"
        initial_finish = seed_item.finish_text if seed_item is not None else "S/S"
        initial_grade = seed_item.grade if seed_item is not None else "A"
        initial_sheet_count = str(seed_item.sheet_count) if seed_item is not None else "80"
        initial_lot = normalize_lot(getattr(seed_item, "lot", "")) if seed_item is not None else ""
        self.part_code = AutoNormalizeClearOnFocusLineEdit(initial_part_code, uppercase=True, remove_spaces=True)
        self.size = QComboBox(); self.size.addItems(VALID_SIZES)
        self.size.setCurrentText(initial_size)
        self.thickness = ThicknessLineEdit(initial_thickness)
        self.finish = FinishClearOnFocusLineEdit(initial_finish)
        self.grade = QComboBox(); self.grade.setEditable(True); self.grade.addItems(VALID_GRADES)
        self.grade.setCurrentText(initial_grade)
        self.sheet_count = CountLineEdit(initial_sheet_count)
        self.lot = AutoNormalizeLineEdit(initial_lot, uppercase=True)
        thickness_control = self.create_step_control(self.thickness, lambda: self.thickness.step_by(1), lambda: self.thickness.step_by(-1), lambda: self.thickness.can_step())
        sheet_control = self.create_step_control(self.sheet_count, lambda: self.sheet_count.step_by(1, minimum=0, maximum=600, fallback=80), lambda: self.sheet_count.step_by(-1, minimum=0, maximum=600, fallback=80), lambda: True)
        self.note = QLineEdit(); self.note.setMaxLength(20)
        self.preview = QLabel()
        grid.addWidget(QLabel("品番"), 0, 0); grid.addWidget(QLabel("サイズ"), 0, 1); grid.addWidget(QLabel("厚み(mm)"), 0, 2)
        grid.addWidget(self.part_code, 1, 0); grid.addWidget(self.size, 1, 1); grid.addWidget(thickness_control, 1, 2)
        grid.addWidget(QLabel("加工 / 裏表"), 2, 0); grid.addWidget(QLabel("グレード"), 2, 1); grid.addWidget(QLabel("枚数"), 2, 2)
        grid.addWidget(self.finish, 3, 0); grid.addWidget(self.grade, 3, 1); grid.addWidget(sheet_control, 3, 2); grid.addWidget(self.preview, 4, 0, 1, 3)
        grid.addWidget(QLabel("Lot"), 5, 0)
        grid.addWidget(self.lot, 6, 0, 1, 3)
        grid.addWidget(QLabel("備考"), 7, 0)
        grid.addWidget(self.note, 8, 0, 1, 3)
        input_layout.addWidget(box)
        for widget in [self.part_code, self.finish, self.note]: widget.textChanged.connect(self.update_preview)
        self.size.currentTextChanged.connect(self.update_preview); self.grade.currentTextChanged.connect(self.update_preview)
        self.thickness.textChanged.connect(self.update_preview); self.sheet_count.textChanged.connect(self.update_preview)
        self.thickness.textChanged.connect(self.update_step_buttons)
        self.update_preview()
        self.update_step_buttons()

        action_row = QHBoxLayout()
        self.add_line_button = QPushButton("明細を追加")
        self.add_line_button.clicked.connect(self.add_line)
        self.cancel_line_edit_button = QPushButton("編集解除")
        self.cancel_line_edit_button.clicked.connect(self.clear_item_edit_selection)
        self.remove_line_button = QPushButton("選択明細削除")
        self.remove_line_button.clicked.connect(self.remove_selected_item_row)
        action_row.addWidget(self.add_line_button)
        action_row.addWidget(self.cancel_line_edit_button)
        action_row.addWidget(self.remove_line_button)
        input_layout.addLayout(action_row)
        input_layout.addStretch(1)

        list_title = QLabel("登録済み明細")
        list_title.setStyleSheet("font:700 12pt 'Yu Gothic UI', 'Segoe UI'; color:#dff6ff;")
        list_layout.addWidget(list_title)
        self.item_table = QTableWidget(0, 8)
        self.item_table.setHorizontalHeaderLabels(["品番", "サイズ", "厚み", "加工 / 裏表", "グレード", "枚数", "Lot", "備考"])
        self.item_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.item_table.horizontalHeader().setMinimumHeight(38)
        self.item_table.setColumnWidth(0, 80)
        self.item_table.setColumnWidth(1, 70)
        self.item_table.setColumnWidth(2, 90)
        self.item_table.setColumnWidth(3, 130)
        self.item_table.setColumnWidth(4, 90)
        self.item_table.setColumnWidth(5, 70)
        self.item_table.setColumnWidth(6, 120)
        self.item_table.setColumnWidth(7, 150)
        self.item_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.item_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.item_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.item_table.setMinimumHeight(280)
        self.item_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.item_table.setShowGrid(True)
        self.item_table.setGridStyle(Qt.SolidLine)
        self.item_table.verticalHeader().setVisible(False)
        self.item_table.setAlternatingRowColors(True)
        self.item_table.setStyleSheet("""
        QTableWidget {
            background:#07111e;
            alternate-background-color:#0a1726;
            color:#f6fbff;
            gridline-color:#284967;
            selection-background-color:#1f6fb3;
            selection-color:#ffffff;
            font:11pt 'Yu Gothic UI', 'Segoe UI';
        }
        QHeaderView::section {
            background:#102033;
            color:#f6fbff;
            border-right:1px solid #5f7890;
            border-bottom:1px solid #5f7890;
            padding:6px;
            font:700 11pt 'Yu Gothic UI', 'Segoe UI';
        }
        """)
        self.item_table.itemChanged.connect(lambda *_args: self.update_color_controls())
        self.item_table.itemSelectionChanged.connect(self.handle_item_selection_changed)
        list_layout.addWidget(self.item_table, 1)
        if initial_payload is not None:
            self.pallet_number.setText(initial_payload[0])
            self.orientation.setCurrentIndex(1 if initial_payload[2] % 180 == 90 else 0)
            for item in self.items:
                self.insert_item_row(item)
        self.color_auto.setChecked(initial_color_mode == "AUTO")
        self.color_manual.setChecked(initial_color_mode != "AUTO")
        self.color_auto.toggled.connect(self.update_color_controls)
        self.color_manual.toggled.connect(self.update_color_controls)
        self.color.currentIndexChanged.connect(self.update_color_controls)
        self.update_color_controls()
        self.refresh_item_editor_buttons()
        self.install_keyboard_scroll_handlers()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setText("完了")
            ok_button.setDefault(False)
            ok_button.setAutoDefault(False)
        if cancel_button is not None:
            cancel_button.setDefault(False)
            cancel_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.restore_remembered_window()

    def install_keyboard_scroll_handlers(self) -> None:
        widgets: List[QWidget] = [
            self.pallet_number,
            self.received_date,
            self.part_code,
            self.thickness,
            self.finish,
            self.sheet_count,
            self.lot,
            self.note,
        ]
        grade_editor = self.grade.lineEdit() if self.grade.isEditable() else None
        if grade_editor is not None:
            widgets.append(grade_editor)
        for widget in widgets:
            widget.installEventFilter(self)
        self.keyboard_scroll_widgets = widgets

    def eventFilter(self, source, event) -> bool:
        if source in getattr(self, "keyboard_scroll_widgets", []) and event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress, QEvent.TouchBegin):
            widget = source
            QTimer.singleShot(0, lambda w=widget: self.scroll_input_widget_into_keyboard_safe_area(w))
            QTimer.singleShot(250, lambda w=widget: self.scroll_input_widget_into_keyboard_safe_area(w))
        return super().eventFilter(source, event)

    def scroll_input_widget_into_keyboard_safe_area(self, widget: QWidget) -> None:
        scroll = getattr(self, "input_scroll", None)
        if scroll is None or widget is None or not widget.isVisible():
            return
        viewport = scroll.viewport()
        top_left = widget.mapTo(viewport, QPoint(0, 0))
        target_top = top_left.y()
        target_bottom = target_top + widget.height()
        top_margin = 8
        bottom_margin = 16
        keyboard_margin = min(max(int(viewport.height() * 0.34), 120), 260)
        safe_bottom = max(top_margin + 1, viewport.height() - keyboard_margin - bottom_margin)
        scroll_bar = scroll.verticalScrollBar()
        new_value = scroll_bar.value()
        if target_bottom > safe_bottom:
            new_value += target_bottom - safe_bottom
        elif target_top < top_margin:
            new_value += target_top - top_margin
        if new_value != scroll_bar.value():
            scroll_bar.setValue(max(scroll_bar.minimum(), min(scroll_bar.maximum(), new_value)))

    def create_step_control(self, editor: QWidget, step_up, step_down, enabled_check) -> QWidget:
        editor.setStyleSheet("QLineEdit { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:6px 8px; min-height:40px; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; }")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(editor, 1)
        button_column = QVBoxLayout()
        button_column.setContentsMargins(0, 0, 0, 0)
        button_column.setSpacing(4)
        up_button = QPushButton("▲")
        down_button = QPushButton("▼")
        button_style = """
        QPushButton {
            background:#2f80c8;
            color:#ffffff;
            border:1px solid #6ab8ff;
            border-radius:4px;
            padding:2px 0;
            font:700 12pt 'Yu Gothic UI', 'Segoe UI';
        }
        QPushButton:hover { background:#3b95e6; }
        QPushButton:disabled {
            background:#2b3748;
            color:#71859b;
            border-color:#405066;
        }
        """
        for button, tooltip in [(up_button, "1増やす"), (down_button, "1減らす")]:
            button.setMinimumSize(48, 28)
            button.setFixedSize(48, 28)
            button.setFocusPolicy(Qt.NoFocus)
            button.setToolTip(tooltip)
            button.setStyleSheet(button_style)
            button_column.addWidget(button)
        self.step_repeat_controllers.append(RepeatStepController(up_button, step_up, enabled_check))
        self.step_repeat_controllers.append(RepeatStepController(down_button, step_down, enabled_check))
        layout.addLayout(button_column)
        self.step_button_groups.append((up_button, down_button, enabled_check))
        return wrapper

    def update_step_buttons(self) -> None:
        for up_button, down_button, enabled_check in self.step_button_groups:
            enabled = bool(enabled_check())
            up_button.setEnabled(enabled)
            down_button.setEnabled(enabled)

    def update_preview(self) -> None:
        part = normalize_part_code(self.part_code.text()) or "38"
        finish = normalize_finish_text(self.finish.text()) or "S/S"
        grade = self.grade.currentText().strip()
        thickness = normalize_thickness_input(self.thickness.text()) or "10"
        quantity_text = normalize_count_input(self.sheet_count.text()) or "80"
        grade_text = f" {grade}" if grade else ""
        self.preview.setText(f"プレビュー: #{part}-{self.size.currentText()}{thickness} {finish}{grade_text} {quantity_text}")
        self.update_color_controls()

    def current_draft_item(self) -> Optional[InventoryItemLine]:
        item, _normalized_fields, _error = validate_item_fields(
            self.part_code.text(),
            self.size.currentText(),
            self.thickness.text(),
            self.finish.text(),
            self.grade.currentText(),
            self.sheet_count.text(),
            self.lot.text(),
            self.note.text(),
        )
        return item

    def item_table_cell(self, text: str, item: InventoryItemLine) -> QTableWidgetItem:
        cell = QTableWidgetItem(text)
        cell.setData(Qt.UserRole, item)
        cell.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        return cell

    def insert_item_row(self, item: InventoryItemLine) -> None:
        row = self.item_table.rowCount()
        self.item_table.insertRow(row)
        self.set_item_row(row, item)

    def set_item_row(self, row: int, item: InventoryItemLine) -> None:
        values = [
            item.part_code,
            item.size,
            str(item.thickness_mm),
            item.finish_text,
            item.grade,
            str(item.sheet_count),
            item.lot,
            item.note,
        ]
        for col, value in enumerate(values):
            self.item_table.setItem(row, col, self.item_table_cell(value, item))

    def item_from_row(self, row: int) -> Optional[InventoryItemLine]:
        if row < 0 or row >= self.item_table.rowCount():
            return None
        row_item = self.item_table.item(row, 0)
        stored_item = row_item.data(Qt.UserRole) if row_item is not None else None
        return stored_item if isinstance(stored_item, InventoryItemLine) else None

    def registered_items(self) -> List[InventoryItemLine]:
        if not hasattr(self, "item_table"):
            return list(self.items)
        items: List[InventoryItemLine] = []
        for row in range(self.item_table.rowCount()):
            row_item = self.item_table.item(row, 0)
            stored_item = row_item.data(Qt.UserRole) if row_item is not None else None
            if isinstance(stored_item, InventoryItemLine):
                items.append(stored_item)
        return items

    def draft_items_for_color_preview(self) -> List[InventoryItemLine]:
        items = self.registered_items()
        draft_item = self.current_draft_item()
        if draft_item is None:
            return items
        if self.editing_row is not None and 0 <= self.editing_row < len(items):
            existing = items[self.editing_row]
            draft_item.line_id = existing.line_id
            items[self.editing_row] = draft_item
        else:
            items.append(draft_item)
        return items

    def update_color_controls(self) -> None:
        preview_items = self.draft_items_for_color_preview()
        auto_text, auto_color = auto_color_info_for_items(preview_items)
        self.color_result.setText(auto_text)
        active_color = auto_color if self.color_auto.isChecked() else QColor(COLOR_PRESETS.get(str(self.color.currentData()), COLOR_PRESETS["GRAY"])[1] or "#7A8EA6")
        text_color = "#091522" if active_color.lightness() > 150 else "#f6fbff"
        self.color_preview.setStyleSheet(f"background:{active_color.name()}; color:{text_color}; border:1px solid #254d77; border-radius:6px; padding:4px 8px; font-weight:700;")
        self.color_preview.setText(color_label(str(self.color.currentData())) if self.color_manual.isChecked() else "AUTO")
        self.color.setEnabled(self.color_manual.isChecked())
        self.manual_color_row.setVisible(self.color_manual.isChecked())

    def add_line(self) -> None:
        draft_item, normalized_fields, error = validate_item_fields(
            self.part_code.text(),
            self.size.currentText(),
            self.thickness.text(),
            self.finish.text(),
            self.grade.currentText(),
            self.sheet_count.text(),
            self.lot.text(),
            self.note.text(),
        )
        if draft_item is None:
            if error:
                QMessageBox.warning(self, "入力エラー", error)
            return
        self.part_code.setText(normalized_fields["part_code"])
        self.thickness.setText(normalized_fields["thickness_mm"])
        self.finish.setText(normalized_fields["finish_text"])
        self.grade.setCurrentText(normalized_fields["grade"])
        self.sheet_count.setText(normalized_fields["sheet_count"])
        self.lot.setText(normalized_fields["lot"])
        self.note.setText(normalized_fields["note"])
        if self.editing_row is not None and 0 <= self.editing_row < self.item_table.rowCount():
            existing = self.item_from_row(self.editing_row)
            if existing is not None:
                draft_item.line_id = existing.line_id
            self.set_item_row(self.editing_row, draft_item)
            self.clear_item_edit_selection()
        else:
            self.insert_item_row(draft_item)
        self.update_color_controls()
        self.refresh_item_editor_buttons()

    def load_item_into_form(self, item: InventoryItemLine) -> None:
        self.part_code.setText(item.part_code)
        self.size.setCurrentText(item.size)
        self.thickness.setText(str(item.thickness_mm))
        self.finish.setText(item.finish_text)
        grade_index = self.grade.findText(item.grade)
        if grade_index >= 0:
            self.grade.setCurrentIndex(grade_index)
        else:
            self.grade.setCurrentText(item.grade)
        self.sheet_count.setText(str(item.sheet_count))
        self.lot.setText(normalize_lot(getattr(item, "lot", "")))
        self.note.setText(item.note)
        self.update_preview()
        self.update_step_buttons()

    def handle_item_selection_changed(self) -> None:
        selected_rows = self.item_table.selectionModel().selectedRows()
        if not selected_rows:
            self.editing_row = None
            self.refresh_item_editor_buttons()
            self.update_color_controls()
            return
        row = selected_rows[0].row()
        item = self.item_from_row(row)
        if item is None:
            self.editing_row = None
            self.refresh_item_editor_buttons()
            self.update_color_controls()
            return
        self.editing_row = row
        self.load_item_into_form(item)
        self.refresh_item_editor_buttons()
        self.update_color_controls()

    def clear_item_edit_selection(self) -> None:
        self.item_table.blockSignals(True)
        self.item_table.clearSelection()
        self.item_table.blockSignals(False)
        self.editing_row = None
        self.refresh_item_editor_buttons()
        self.update_color_controls()

    def remove_selected_item_row(self) -> None:
        row = self.editing_row if self.editing_row is not None else self.item_table.currentRow()
        if row < 0 or row >= self.item_table.rowCount():
            QMessageBox.information(self, "明細削除", "削除したい明細を選択してください。")
            return
        self.item_table.removeRow(row)
        self.clear_item_edit_selection()
        self.update_color_controls()

    def refresh_item_editor_buttons(self) -> None:
        editing = self.editing_row is not None
        self.add_line_button.setText("選択明細を更新" if editing else "明細を追加")
        self.cancel_line_edit_button.setEnabled(editing)
        self.remove_line_button.setEnabled(editing)

    def payload(self) -> Optional[Tuple[str, str, int, str, str, List[InventoryItemLine]]]:
        pallet_number = self.pallet_number.text().strip().upper()
        if not pallet_number:
            QMessageBox.warning(self, "入力エラー", "パレット番号を入力してください。")
            return None
        received_date = normalize_date_text(self.received_date.text())
        if not received_date:
            QMessageBox.warning(self, "入力エラー", "入庫日は YYYY-MM-DD 形式の実在する日付で、未来日は入力できません。")
            return None
        output_items = self.registered_items()
        if not output_items:
            QMessageBox.warning(self, "入力エラー", "明細を1件以上追加してください。")
            return None
        self.received_date.setText(received_date)
        color_mode = "AUTO" if self.color_auto.isChecked() else "MANUAL"
        last_manual_color_key = str(self.color.currentData())
        return pallet_number, received_date, int(self.orientation.currentData()), color_mode, last_manual_color_key, output_items

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)


class EditPalletDialog(RememberedWindowDialog):
    COLUMN_WIDTHS_SETTINGS_KEY = "edit_pallet/item_table_header_state_v2"
    WINDOW_SETTINGS_PREFIX = "pallet_edit_dialog"
    ORDER_COL = 0
    PART_COL = 1
    SIZE_COL = 2
    THICKNESS_COL = 3
    THICKNESS_DOWN_COL = 4
    THICKNESS_UP_COL = 5
    FINISH_COL = 6
    GRADE_COL = 7
    SHEET_COL = 8
    SHEET_DOWN_COL = 9
    SHEET_UP_COL = 10
    LOT_COL = 11
    NOTE_COL = 12

    def __init__(self, pallet: PalletRecord, locations: List[str], parent: Optional[QWidget] = None, initial_payload: Optional[Tuple[str, str, str, int, str, str, int, List[InventoryItemLine]]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("パレット編集")
        self.setSizeGripEnabled(True)
        self.configure_window_persistence(self.WINDOW_SETTINGS_PREFIX)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1180, max(820, int(available.width() * 0.92))), min(760, max(560, int(available.height() * 0.86))))
        else:
            self.resize(1080, 700)
        self.original_pallet_number = pallet.pallet_number
        self.step_repeat_controllers: List[RepeatStepController] = []
        self.column_width_settings = QSettings(APP_ID, "WarehouseApp")
        self.column_width_save_timer = QTimer(self)
        self.column_width_save_timer.setSingleShot(True)
        self.column_width_save_timer.timeout.connect(self.save_item_table_column_widths)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        info_scroll = QScrollArea()
        info_scroll.setWidgetResizable(True)
        info_scroll.setFrameShape(QFrame.NoFrame)
        info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        info_scroll.setMinimumWidth(340)
        enable_swipe_scroll(info_scroll)
        info_body = QWidget()
        info_layout = QVBoxLayout(info_body)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(10)
        info_scroll.setWidget(info_body)
        content_layout.addWidget(info_scroll, 0)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        content_layout.addWidget(detail_panel, 1)
        root.addWidget(content, 1)

        form = QFormLayout()
        source_pallet_number = initial_payload[0] if initial_payload is not None else pallet.pallet_number
        source_received_date = initial_payload[1] if initial_payload is not None else pallet.received_date
        source_location_code = initial_payload[2] if initial_payload is not None else pallet.location_code
        source_orientation = initial_payload[3] if initial_payload is not None else pallet.orientation
        source_color_mode = initial_payload[4] if initial_payload is not None else (pallet.color_mode or "AUTO")
        source_last_manual_color_key = initial_payload[5] if initial_payload is not None else (pallet.last_manual_color_key or pallet.color_key or "GRAY")
        store = getattr(parent, "store", None)
        source_stack_order = initial_payload[6] if initial_payload is not None else pallet.stack_order
        source_items = initial_payload[7] if initial_payload is not None else pallet.items
        self.pallet_number = AutoNormalizeLineEdit(source_pallet_number, uppercase=True, remove_spaces=True)
        self.received_date = AutoNormalizeLineEdit(source_received_date, remove_spaces=True)
        self.location_code = source_location_code
        self.location = QLabel(f"{visible_location_code(source_location_code)} 位置変更はマップ上でドラッグ")
        self.orientation = QComboBox(); self.orientation.addItem("横向き", 0); self.orientation.addItem("縦向き", 90); self.orientation.setCurrentIndex(1 if source_orientation % 180 == 90 else 0)
        self.color_auto = QRadioButton("自動判別")
        self.color_manual = QRadioButton("手動指定")
        self.color = QComboBox()
        populate_color_combo(self.color, source_last_manual_color_key, include_auto=False, store=store)
        self.color_result = QLabel()
        self.color_preview = QLabel("      ")
        self.color_preview.setMinimumWidth(72)
        self.color_preview.setAlignment(Qt.AlignCenter)
        self.manual_color_row = QWidget()
        manual_color_layout = QHBoxLayout(self.manual_color_row)
        manual_color_layout.setContentsMargins(0, 0, 0, 0)
        manual_color_layout.addWidget(self.color)
        color_mode_row = QWidget()
        color_mode_layout = QHBoxLayout(color_mode_row)
        color_mode_layout.setContentsMargins(0, 0, 0, 0)
        color_mode_layout.addWidget(self.color_auto)
        color_mode_layout.addWidget(self.color_manual)
        color_mode_layout.addStretch(1)
        color_result_row = QWidget()
        color_result_layout = QHBoxLayout(color_result_row)
        color_result_layout.setContentsMargins(0, 0, 0, 0)
        color_result_layout.addWidget(self.color_result, 1)
        color_result_layout.addWidget(self.color_preview)
        self.stack_order = QSpinBox(); self.stack_order.setRange(0, 999); self.stack_order.setValue(source_stack_order); self.stack_order.setButtonSymbols(QAbstractSpinBox.NoButtons)
        form.addRow("パレット番号", self.pallet_number)
        form.addRow("入庫日", self.received_date)
        form.addRow("ロケーション", self.location)
        form.addRow("向き", self.orientation)
        form.addRow("色設定", color_mode_row)
        form.addRow("自動判別結果", color_result_row)
        form.addRow("手動色", self.manual_color_row)
        info_layout.addLayout(form)
        info_layout.addStretch(1)

        detail_title = QLabel("アイテム詳細")
        detail_title.setStyleSheet("font:700 12pt 'Yu Gothic UI', 'Segoe UI'; color:#dff6ff;")
        detail_layout.addWidget(detail_title)
        self.item_table = ReorderTableWidget(0, 13)
        self.item_table.setItemDelegate(HintedTableDelegate({
            self.PART_COL: {"uppercase": True, "remove_spaces": True},
            self.THICKNESS_COL: {"thickness": True},
            self.FINISH_COL: {"finish": True},
            self.LOT_COL: {"uppercase": True},
        }, {self.SHEET_COL}, self.item_table, {
            self.SIZE_COL: VALID_SIZES,
            self.GRADE_COL: VALID_GRADES,
        }))
        self.item_table.setHorizontalHeaderLabels(["順", "品番", "サイズ", "厚み", "", "", "加工 / 裏表", "グレード", "枚数", "", "", "Lot", "備考"])
        self.item_table.rows_changed_callback = self.refresh_item_order_labels
        self.item_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
        header = self.item_table.horizontalHeader()
        header.setMinimumSectionSize(24)
        header.setSectionResizeMode(QHeaderView.Interactive)
        for col in [self.THICKNESS_DOWN_COL, self.THICKNESS_UP_COL, self.SHEET_DOWN_COL, self.SHEET_UP_COL]:
            header.setSectionResizeMode(col, QHeaderView.Fixed)
        self.restore_item_table_column_widths()
        header.sectionResized.connect(self.schedule_item_table_column_width_save)
        self.item_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.item_table.setMinimumHeight(360)
        self.item_table.verticalHeader().setVisible(False)
        self.item_table.cellClicked.connect(self.handle_table_cell_clicked)
        detail_layout.addWidget(self.item_table, 1)

        action_row = QHBoxLayout()
        add_button = QPushButton("明細行追加"); add_button.clicked.connect(self.add_empty_row)
        remove_button = QPushButton("選択行削除"); remove_button.clicked.connect(self.remove_current_row)
        action_row.addWidget(add_button); action_row.addWidget(remove_button); action_row.addStretch(1)
        detail_layout.addLayout(action_row)

        for item in source_items:
            self.add_row(item)
        self.refresh_item_order_labels()
        self.color_auto.setChecked(source_color_mode == "AUTO")
        self.color_manual.setChecked(source_color_mode != "AUTO")
        self.color_auto.toggled.connect(self.update_color_controls)
        self.color_manual.toggled.connect(self.update_color_controls)
        self.color.currentIndexChanged.connect(self.update_color_controls)
        self.item_table.itemChanged.connect(self.handle_item_table_item_changed)
        self.update_color_controls()
        if self.item_table.rowCount() > 0:
            self.item_table.setCurrentCell(0, self.PART_COL)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setDefault(False)
            ok_button.setAutoDefault(False)
        if cancel_button is not None:
            cancel_button.setDefault(False)
            cancel_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.restore_remembered_window()

    def default_item_table_column_widths(self) -> Dict[int, int]:
        return {
            self.ORDER_COL: 52,
            self.PART_COL: 100,
            self.SIZE_COL: 76,
            self.THICKNESS_COL: 90,
            self.THICKNESS_DOWN_COL: 34,
            self.THICKNESS_UP_COL: 34,
            self.FINISH_COL: 140,
            self.GRADE_COL: 90,
            self.SHEET_COL: 80,
            self.SHEET_DOWN_COL: 34,
            self.SHEET_UP_COL: 34,
            self.LOT_COL: 130,
            self.NOTE_COL: 180,
        }

    def apply_default_item_table_column_widths(self) -> None:
        for column, width in self.default_item_table_column_widths().items():
            self.item_table.setColumnWidth(column, width)

    def restore_item_table_column_widths(self) -> None:
        self.apply_default_item_table_column_widths()
        saved_state = self.column_width_settings.value(self.COLUMN_WIDTHS_SETTINGS_KEY)
        if saved_state is None:
            return
        if isinstance(saved_state, bytes):
            saved_state = QByteArray(saved_state)
        if not isinstance(saved_state, QByteArray):
            self.column_width_settings.remove(self.COLUMN_WIDTHS_SETTINGS_KEY)
            return
        try:
            restored = self.item_table.horizontalHeader().restoreState(saved_state)
        except Exception:
            restored = False
        if not restored:
            self.column_width_settings.remove(self.COLUMN_WIDTHS_SETTINGS_KEY)
            self.apply_default_item_table_column_widths()
            return
        for column in range(self.item_table.columnCount()):
            self.item_table.setColumnWidth(column, max(24, self.item_table.columnWidth(column)))
        for column in [self.THICKNESS_DOWN_COL, self.THICKNESS_UP_COL, self.SHEET_DOWN_COL, self.SHEET_UP_COL]:
            self.item_table.setColumnWidth(column, 34)

    def schedule_item_table_column_width_save(self, _column: int, _old_width: int, _new_width: int) -> None:
        self.column_width_save_timer.start(300)

    def save_item_table_column_widths(self) -> None:
        if not hasattr(self, "item_table"):
            return
        self.column_width_settings.setValue(
            self.COLUMN_WIDTHS_SETTINGS_KEY,
            self.item_table.horizontalHeader().saveState(),
        )
        self.column_width_settings.sync()

    def save_additional_window_state(self) -> None:
        self.save_item_table_column_widths()

    def add_row(self, item: Optional[InventoryItemLine] = None, insert_at_top: bool = False) -> None:
        item = item or InventoryItemLine(part_code="", size="LL", thickness_mm="10", finish_text="S/S", grade="A", sheet_count=1)
        row = 0 if insert_at_top else self.item_table.rowCount()
        self.item_table.insertRow(row)
        row_values = ["", item.part_code, item.size, str(item.thickness_mm), "-", "+", item.finish_text, item.grade, str(item.sheet_count), "-", "+", item.lot, item.note]
        for col, value in enumerate(row_values):
            self.item_table.setItem(row, col, QTableWidgetItem(value))
        self.refresh_item_order_labels()
        if hasattr(self, "color_result"):
            self.update_color_controls()

    def refresh_item_order_labels(self) -> None:
        for row in range(self.item_table.rowCount()):
            item = self.item_table.item(row, self.ORDER_COL)
            if item is None:
                item = QTableWidgetItem()
                self.item_table.setItem(row, self.ORDER_COL, item)
            item.setText(str(row + 1))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            for col, text in [(self.THICKNESS_DOWN_COL, "-"), (self.THICKNESS_UP_COL, "+"), (self.SHEET_DOWN_COL, "-"), (self.SHEET_UP_COL, "+")]:
                button_item = self.item_table.item(row, col)
                if button_item is None:
                    button_item = QTableWidgetItem()
                    self.item_table.setItem(row, col, button_item)
                button_item.setText(text)
                button_item.setTextAlignment(Qt.AlignCenter)
                button_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                button_item.setBackground(QColor("#12304d"))
                button_item.setForeground(QColor("#dff6ff"))
            self.ensure_step_button_widget(row, self.THICKNESS_DOWN_COL, "-", "厚みを1減らす", lambda r=row: self.adjust_row_thickness(r, -1), lambda r=row: is_valid_thickness(self.cell_text(r, self.THICKNESS_COL)))
            self.ensure_step_button_widget(row, self.THICKNESS_UP_COL, "+", "厚みを1増やす", lambda r=row: self.adjust_row_thickness(r, 1), lambda r=row: is_valid_thickness(self.cell_text(r, self.THICKNESS_COL)))
            self.ensure_step_button_widget(row, self.SHEET_DOWN_COL, "-", "枚数を1減らす", lambda r=row: self.adjust_row_quantity(r, -1), lambda: True)
            self.ensure_step_button_widget(row, self.SHEET_UP_COL, "+", "枚数を1増やす", lambda r=row: self.adjust_row_quantity(r, 1), lambda: True)
            self.refresh_thickness_step_buttons(row)
        self.item_table.update_drag_feedback()

    def ensure_step_button_widget(self, row: int, col: int, text: str, tooltip: str, callback, enabled_check) -> None:
        existing = self.item_table.cellWidget(row, col)
        if existing is not None:
            button = existing.findChild(QPushButton)
            if button is not None:
                button.setText(text)
                button.setToolTip(tooltip)
                button.setEnabled(enabled_check())
                return
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        button = QPushButton(text)
        button.setFocusPolicy(Qt.NoFocus)
        button.setMinimumSize(30, 24)
        button.setStyleSheet("""
        QPushButton {
            background:#12304d;
            color:#dff6ff;
            border:1px solid #2b5b85;
            border-radius:4px;
            padding:2px 0;
            font:700 11pt 'Yu Gothic UI', 'Segoe UI';
        }
        QPushButton:disabled {
            background:#263142;
            color:#75879b;
            border-color:#3f5368;
        }
        """)
        button.setToolTip(tooltip)
        button.setEnabled(enabled_check())
        layout.addWidget(button)
        self.item_table.setCellWidget(row, col, wrapper)
        self.step_repeat_controllers.append(RepeatStepController(button, callback, enabled_check))

    def refresh_thickness_step_buttons(self, row: int) -> None:
        enabled = is_valid_thickness(self.cell_text(row, self.THICKNESS_COL))
        for col in [self.THICKNESS_DOWN_COL, self.THICKNESS_UP_COL]:
            button_item = self.item_table.item(row, col)
            if button_item is None:
                continue
            flags = Qt.ItemIsSelectable
            if enabled:
                flags |= Qt.ItemIsEnabled
            button_item.setFlags(flags)
            button_item.setBackground(QColor("#12304d" if enabled else "#263142"))
            button_item.setForeground(QColor("#dff6ff" if enabled else "#75879b"))
            widget = self.item_table.cellWidget(row, col)
            if widget is not None:
                button = widget.findChild(QPushButton)
                if button is not None:
                    button.setEnabled(enabled)
        for col in [self.SHEET_DOWN_COL, self.SHEET_UP_COL]:
            widget = self.item_table.cellWidget(row, col)
            if widget is not None:
                button = widget.findChild(QPushButton)
                if button is not None:
                    button.setEnabled(True)
        self.item_table.update_drag_feedback()

    def handle_item_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self.THICKNESS_COL:
            self.refresh_thickness_step_buttons(item.row())
        self.update_color_controls()

    def cell_text(self, row: int, col: int) -> str:
        item = self.item_table.item(row, col)
        return item.text() if item is not None else ""

    def set_cell_text(self, row: int, col: int, text: str) -> None:
        item = self.item_table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.item_table.setItem(row, col, item)
        item.setText(text)

    def adjust_selected_row_thickness(self, delta: int) -> None:
        row = self.item_table.currentRow()
        self.adjust_row_thickness(row, delta)

    def adjust_row_thickness(self, row: int, delta: int) -> None:
        if row < 0 or row >= self.item_table.rowCount():
            return
        current = self.cell_text(row, self.THICKNESS_COL) or "10"
        if not is_valid_thickness(current):
            return
        next_value = format_thickness_value(parse_thickness_value(current) + delta)
        self.set_cell_text(row, self.THICKNESS_COL, next_value)
        self.item_table.setCurrentCell(row, self.THICKNESS_COL)
        self.update_color_controls()

    def adjust_selected_row_quantity(self, delta: int) -> None:
        row = self.item_table.currentRow()
        self.adjust_row_quantity(row, delta)

    def adjust_row_quantity(self, row: int, delta: int) -> None:
        if row < 0 or row >= self.item_table.rowCount():
            return
        current_text = normalize_numeric_text(self.cell_text(row, self.SHEET_COL))
        current = int(current_text) if current_text.isdigit() else 1
        next_value = max(1, min(600, current + delta))
        self.set_cell_text(row, self.SHEET_COL, str(next_value))
        self.item_table.setCurrentCell(row, self.SHEET_COL)
        self.update_color_controls()

    def handle_table_cell_clicked(self, row: int, col: int) -> None:
        if col == self.THICKNESS_DOWN_COL:
            self.adjust_row_thickness(row, -1)
        elif col == self.THICKNESS_UP_COL:
            self.adjust_row_thickness(row, 1)
        elif col == self.SHEET_DOWN_COL:
            self.adjust_row_quantity(row, -1)
        elif col == self.SHEET_UP_COL:
            self.adjust_row_quantity(row, 1)

    def draft_items_for_color_preview(self) -> List[InventoryItemLine]:
        items: List[InventoryItemLine] = []
        for row in range(self.item_table.rowCount()):
            item, _normalized_fields, _error = validate_item_fields(
                self.cell_text(row, self.PART_COL),
                self.cell_text(row, self.SIZE_COL),
                self.cell_text(row, self.THICKNESS_COL),
                self.cell_text(row, self.FINISH_COL),
                self.cell_text(row, self.GRADE_COL),
                self.cell_text(row, self.SHEET_COL),
                self.cell_text(row, self.LOT_COL),
                self.cell_text(row, self.NOTE_COL),
            )
            if item is not None:
                items.append(item)
        return items

    def update_color_controls(self) -> None:
        preview_items = self.draft_items_for_color_preview()
        auto_text, auto_color = auto_color_info_for_items(preview_items)
        self.color_result.setText(auto_text)
        active_color = auto_color if self.color_auto.isChecked() else QColor(COLOR_PRESETS.get(str(self.color.currentData()), COLOR_PRESETS["GRAY"])[1] or "#7A8EA6")
        text_color = "#091522" if active_color.lightness() > 150 else "#f6fbff"
        self.color_preview.setStyleSheet(f"background:{active_color.name()}; color:{text_color}; border:1px solid #254d77; border-radius:6px; padding:4px 8px; font-weight:700;")
        self.color_preview.setText(color_label(str(self.color.currentData())) if self.color_manual.isChecked() else "AUTO")
        self.color.setEnabled(self.color_manual.isChecked())
        self.manual_color_row.setVisible(self.color_manual.isChecked())

    def add_empty_row(self) -> None:
        current_row = self.item_table.currentRow()
        if current_row >= 0:
            values = []
            for col in [self.PART_COL, self.SIZE_COL, self.THICKNESS_COL, self.FINISH_COL, self.GRADE_COL, self.SHEET_COL, self.LOT_COL, self.NOTE_COL]:
                cell = self.item_table.item(current_row, col)
                values.append((cell.text() if cell else "").strip())
            part_code, size, thickness, finish_text, grade, sheet_count, lot, note = values
            normalized_sheet_count = normalize_numeric_text(sheet_count)
            cloned = InventoryItemLine(
                part_code=normalize_part_code(part_code),
                size=(normalize_text(size).upper() or "LL"),
                thickness_mm=(normalize_thickness_input(thickness) or "10"),
                finish_text=(normalize_finish_text(finish_text) or "S/S"),
                grade=normalize_text(grade),
                sheet_count=int(normalized_sheet_count) if normalized_sheet_count.isdigit() else 1,
                lot=normalize_lot(lot),
                note=normalize_note(note)[:20],
            )
            self.add_row(cloned, insert_at_top=True)
            self.item_table.setCurrentCell(0, self.PART_COL)
            return
        self.add_row(insert_at_top=True)
        self.item_table.setCurrentCell(0, self.PART_COL)

    def remove_current_row(self) -> None:
        row = self.item_table.currentRow()
        if row >= 0:
            self.item_table.removeRow(row)
            self.refresh_item_order_labels()
            self.update_color_controls()
            if self.item_table.rowCount() > 0:
                self.item_table.setCurrentCell(min(row, self.item_table.rowCount() - 1), self.PART_COL)

    def payload(self) -> Optional[Tuple[str, str, str, int, str, str, int, List[InventoryItemLine]]]:
        pallet_number = self.pallet_number.text().strip().upper()
        received_date = normalize_date_text(self.received_date.text())
        location_code = normalize_location_code(self.location_code)
        if not pallet_number or not location_code:
            QMessageBox.warning(self, "入力エラー", "パレット番号を入力してください。")
            return None
        if not received_date:
            QMessageBox.warning(self, "入力エラー", "入庫日は YYYY-MM-DD 形式の実在する日付で、未来日は入力できません。")
            return None

        items: List[InventoryItemLine] = []
        for row in range(self.item_table.rowCount()):
            item, normalized_fields, error = validate_item_fields(
                self.cell_text(row, self.PART_COL),
                self.cell_text(row, self.SIZE_COL),
                self.cell_text(row, self.THICKNESS_COL),
                self.cell_text(row, self.FINISH_COL),
                self.cell_text(row, self.GRADE_COL),
                self.cell_text(row, self.SHEET_COL),
                self.cell_text(row, self.LOT_COL),
                self.cell_text(row, self.NOTE_COL),
            )
            if item is None:
                QMessageBox.warning(self, "入力エラー", f"{row + 1}行目の{error}")
                return None
            self.set_cell_text(row, self.PART_COL, normalized_fields["part_code"])
            self.set_cell_text(row, self.SIZE_COL, normalized_fields["size"])
            self.set_cell_text(row, self.THICKNESS_COL, normalized_fields["thickness_mm"])
            self.set_cell_text(row, self.FINISH_COL, normalized_fields["finish_text"])
            self.set_cell_text(row, self.GRADE_COL, normalized_fields["grade"])
            self.set_cell_text(row, self.SHEET_COL, normalized_fields["sheet_count"])
            self.set_cell_text(row, self.LOT_COL, normalized_fields["lot"])
            self.set_cell_text(row, self.NOTE_COL, normalized_fields["note"])
            items.append(item)

        if not items:
            QMessageBox.warning(self, "入力エラー", "明細を1件以上入力してください。")
            return None

        self.received_date.setText(received_date)
        color_mode = "AUTO" if self.color_auto.isChecked() else "MANUAL"
        last_manual_color_key = str(self.color.currentData())
        return pallet_number, received_date, location_code, int(self.orientation.currentData()), color_mode, last_manual_color_key, self.stack_order.value(), items

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            return
        super().keyPressEvent(event)



class TransferDialog(QDialog):
    NEW_PALLET_VALUE = "__NEW_PALLET__"

    def __init__(self, source_pallet: PalletRecord, target_pallets: List[PalletRecord], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("積み替えモード")
        self.resize(560, 320)
        self.source_pallet = source_pallet
        self.target_pallets = target_pallets

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.form = form
        self.source_line = QComboBox()
        for item in source_pallet.items:
            label = item.identifier
            if item.lot:
                label += f" / Lot: {item.lot}"
            if item.note:
                label += f" / 備考: {item.note}"
            self.source_line.addItem(label, item.line_id)
        self.target_pallet = QComboBox()
        self.target_pallet.addItem("空パレットを作成", self.NEW_PALLET_VALUE)
        for pallet in target_pallets:
            self.target_pallet.addItem(f"{pallet.pallet_number} ({visible_location_code(pallet.location_code)})", pallet.pallet_number)
        self.new_pallet_number = AutoNormalizeLineEdit(uppercase=True, remove_spaces=True)
        self.new_pallet_number.setPlaceholderText("空パレット番号を入力")
        self.quantity = CountLineEdit("1")
        self.source_line.currentIndexChanged.connect(self.sync_quantity_limit)
        self.target_pallet.currentIndexChanged.connect(self.update_target_mode)
        form.addRow("移動元明細", self.source_line)
        form.addRow("移動先パレット", self.target_pallet)
        form.addRow("空パレット番号", self.new_pallet_number)
        form.addRow("移動枚数", self.quantity)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.sync_quantity_limit()
        self.update_target_mode()

    def update_target_mode(self) -> None:
        is_new_pallet = self.target_pallet.currentData() == self.NEW_PALLET_VALUE
        self.new_pallet_number.setVisible(is_new_pallet)
        label = self.form.labelForField(self.new_pallet_number)
        if label is not None:
            label.setVisible(is_new_pallet)

    def sync_quantity_limit(self) -> None:
        item = self.selected_item()
        if item is None:
            self.quantity.setText("1")
            return
        current_value = self.quantity.numeric_value()
        if current_value is None or current_value < 1:
            self.quantity.setText("1")
            return
        if current_value > item.sheet_count:
            self.quantity.setText(str(item.sheet_count))

    def selected_item(self) -> Optional[InventoryItemLine]:
        line_id = self.source_line.currentData()
        for item in self.source_pallet.items:
            if item.line_id == line_id:
                return item
        return None

    def payload(self) -> Optional[Tuple[str, str, str, int]]:
        item = self.selected_item()
        target = self.target_pallet.currentData()
        if item is None or not target:
            QMessageBox.warning(self, "入力エラー", "移動元明細と移動先パレットを選択してください。")
            return None
        quantity = parse_sheet_count_text(self.quantity.text())
        if quantity is None:
            QMessageBox.warning(self, "入力エラー", "移動枚数は 1〜600 の半角数字で入力してください。")
            return None
        if quantity > item.sheet_count:
            QMessageBox.warning(self, "入力エラー", f"移動枚数は移動元枚数以下で入力してください。現在の枚数: {item.sheet_count}")
            return None
        if target == self.NEW_PALLET_VALUE:
            requested_number = self.new_pallet_number.text().strip().upper()
            if not requested_number:
                QMessageBox.warning(self, "入力エラー", "空パレット番号を入力してください。")
                return None
            return item.line_id, "NEW", requested_number, quantity
        return item.line_id, "EXISTING", str(target), quantity

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class MapNoteDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, note: Optional[MapNoteRecord] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("メモ編集" if note is not None else "メモ追加")
        self.resize(520, 420)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("例:\n空パレット10枚\n品番確認待ち")
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setMinimumHeight(220)
        self.size_combo = QComboBox()
        self.size_combo.addItems(VALID_SIZES)
        self.size_combo.setCurrentText("LL")
        self.color_combo = QComboBox()
        store = getattr(parent, "store", None)
        populate_color_combo(self.color_combo, "YELLOW", include_auto=False, store=store)
        if note is not None:
            self.text_edit.setPlainText(note.text)
            self.size_combo.setCurrentText(note.size if note.size in VALID_SIZES else "LL")
            color_index = self.color_combo.findData(note.color_key)
            if color_index >= 0:
                self.color_combo.setCurrentIndex(color_index)
        form.addRow("本文", self.text_edit)
        form.addRow("サイズ", self.size_combo)
        form.addRow("色", self.color_combo)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setText("更新" if note is not None else "登録")
            ok_button.setDefault(False)
            ok_button.setAutoDefault(False)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if cancel_button is not None:
            cancel_button.setDefault(False)
            cancel_button.setAutoDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def payload(self) -> Optional[Tuple[str, str, str]]:
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "メモ追加", "本文を入力してください。")
            return None
        if len(text) > 1000:
            QMessageBox.warning(self, "メモ追加", "本文は1000文字以内で入力してください。")
            return None
        size = self.size_combo.currentText()
        color_key = self.color_combo.currentData() or "YELLOW"
        return text, size, str(color_key)

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class ColorLabelNotesDialog(QDialog):
    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("色説明設定")
        self.inputs: Dict[str, QLineEdit] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        info = QLabel("固定説明色は自動判定ルールに紐付くため変更できません。")
        info.setWordWrap(True)
        root.addWidget(info)
        form = QFormLayout()
        notes = editable_color_label_notes(store)
        for key in COLOR_ORDER:
            if key == "AUTO" or key not in COLOR_PRESETS:
                continue
            if key in FIXED_COLOR_LABEL_NOTES:
                form.addRow(color_swatch_label(key), QLabel(color_choice_label(key, store)))
                continue
            edit = QLineEdit(notes.get(key, ""))
            edit.setPlaceholderText(color_label(key))
            edit.setMaxLength(40)
            self.inputs[key] = edit
            form.addRow(color_swatch_label(key), edit)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def payload(self) -> Dict[str, str]:
        return {key: edit.text().strip() for key, edit in self.inputs.items()}


def color_swatch_label(color_key: str) -> QLabel:
    label = QLabel(color_label(color_key))
    label.setToolTip(color_label(color_key))
    return label


class TopMapWidget(QWidget):
    palletSelected = Signal(str)
    palletMoved = Signal(str, float, float, str)
    selectionCleared = Signal()
    palletDoubleClicked = Signal(str)
    blockedLocationToggled = Signal(str, bool)
    palletContextRequested = Signal(str, QPoint)
    mapNoteSelected = Signal(str)
    mapNoteDoubleClicked = Signal(str)
    mapNoteMoved = Signal(str, float, float)
    mapNoteContextRequested = Signal(str, QPoint)
    dragStarted = Signal()

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.selected_pallet = None; self.hover_pallet = None; self.selected_note = None
        self.hover_note = None
        self.hover_target = None
        self.selected_pallets: set[str] = set()
        self.location_rects: Dict[str, QRect] = {}; self.pallet_rects: Dict[str, QRect] = {}; self.note_rects: Dict[str, QRect] = {}
        self.dragging_pallet = None; self.drag_offset = QPoint(); self.drag_point = QPoint(); self.zoom = 1.0
        self.dragging_note = None
        self.is_dragging = False
        self.drag_start_point = QPoint()
        self.drag_candidate_label: Optional[str] = None
        self.base_cache_pixmap: Optional[QPixmap] = None
        self.base_cache_key = None
        self.base_cache_dirty = True
        self.drag_cache_pixmap: Optional[QPixmap] = None
        self.drag_cache_pallet: Optional[str] = None
        self.drag_cache_note: Optional[str] = None
        self.pan_offset = QPoint()
        self.panning = False
        self.pan_anchor = QPoint()
        self.touch_zoom_distance: Optional[float] = None
        self.touch_zoom_midpoint: Optional[QPoint] = None
        self.blocked_edit_mode = False
        self.attention_visible = True
        self.attention_timer = QTimer(self)
        self.attention_timer.timeout.connect(self.toggle_attention_state)
        self.attention_timer.start(520)
        self.setMinimumHeight(560); self.setMouseTracking(True); self.setAttribute(Qt.WA_AcceptTouchEvents, True)

    def toggle_attention_state(self) -> None:
        self.attention_visible = not self.attention_visible
        if self.selected_pallet or self.selected_pallets or self.selected_note:
            self.update()

    def scaled_bounds(self) -> QRect:
        bottom_margin = 92 if self.has_entry_waiting_pallets() and self.height() >= 520 else TOP_VIEW_MARGIN_BOTTOM
        base = self.rect().adjusted(TOP_VIEW_MARGIN_LEFT, TOP_VIEW_MARGIN_TOP, -TOP_VIEW_MARGIN_RIGHT, -bottom_margin); center = base.center()
        width = max(200, int(base.width() * self.zoom)); height = max(170, int(base.height() * self.zoom * 1.07))
        rect = QRect(center.x() - width // 2, center.y() - height // 2, width, height)
        rect.translate(self.pan_offset)
        return rect

    def has_entry_waiting_pallets(self) -> bool:
        return any(is_entry_staged_pallet(pallet) for pallet in self.store.pallets) or any((note.map_y or 0.0) > 1.0 for note in self.store.map_notes)

    def entry_waiting_area_rect(self, bounds: QRect) -> QRect:
        available = self.rect().adjusted(18, 18, -18, -18)
        return QRect(available.left(), available.bottom() - 46, available.width(), 46)

    def clamp_pan(self) -> None:
        base = self.rect().adjusted(TOP_VIEW_MARGIN_LEFT, TOP_VIEW_MARGIN_TOP, -TOP_VIEW_MARGIN_RIGHT, -TOP_VIEW_MARGIN_BOTTOM)
        max_x = TOP_VIEW_SCROLL_PADDING + max(0, (int(base.width() * self.zoom) - base.width()) // 2)
        max_y = TOP_VIEW_SCROLL_PADDING + max(0, (int(base.height() * self.zoom * 1.07) - base.height()) // 2)
        self.pan_offset.setX(max(-max_x, min(max_x, self.pan_offset.x())))
        self.pan_offset.setY(max(-max_y, min(max_y, self.pan_offset.y())))

    def draw_grid(self, painter: QPainter, bounds: QRect) -> Tuple[int, int]:
        columns = GRID_COLUMNS; rows = GRID_ROWS
        painter.setPen(QPen(QColor("#102e4e"), 1, Qt.DotLine))
        x_edges = self.grid_edges(bounds.left(), bounds.width(), columns)
        y_edges = self.grid_edges(bounds.top(), bounds.height(), rows)
        for x in x_edges:
            painter.drawLine(int(x), bounds.top(), int(x), bounds.bottom())
        for y in y_edges:
            painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))
        painter.setPen(QPen(QColor("#1a4f80"), 1)); painter.drawRect(bounds)
        self.draw_grid_labels(painter, bounds, columns, rows)
        return columns, rows

    def grid_edges(self, start: int, length: int, count: int) -> List[int]:
        return [start + (i * length) // count for i in range(count + 1)]

    def grid_cell_rect(self, bounds: QRect, col: int, row: int) -> QRect:
        x_edges = self.grid_edges(bounds.left(), bounds.width(), GRID_COLUMNS)
        y_edges = self.grid_edges(bounds.top(), bounds.height(), GRID_ROWS)
        x0 = x_edges[col]
        x1 = x_edges[col + 1]
        y0 = y_edges[row]
        y1 = y_edges[row + 1]
        return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))

    def draw_grid_labels(self, painter: QPainter, bounds: QRect, columns: int, rows: int) -> None:
        painter.save()
        x_edges = self.grid_edges(bounds.left(), bounds.width(), columns)
        y_edges = self.grid_edges(bounds.top(), bounds.height(), rows)
        for i in range(columns):
            x = (x_edges[i] + x_edges[i + 1]) / 2
            label = grid_column_display_label(i)
            aisle = is_aisle_column(i)
            painter.setPen(QColor("#ffe066") if aisle else QColor("#3b6f9e"))
            painter.setFont(QFont("Yu Gothic UI", 10 if aisle else 15, QFont.Bold))
            for label_rect in (
                QRect(int(x) - 42, bounds.top() - 30, 84, 24),
                QRect(int(x) - 42, bounds.bottom() + 6, 84, 24),
            ):
                painter.fillRect(label_rect.adjusted(1, 1, -1, -1), QColor(7, 17, 31, 190))
                painter.drawText(label_rect, Qt.AlignCenter, label)
        for i in range(rows):
            y = (y_edges[i] + y_edges[i + 1]) / 2
            painter.setPen(QColor("#3b6f9e"))
            painter.setFont(QFont("Yu Gothic UI", 13, QFont.Bold))
            for label_rect, alignment in (
                (QRect(bounds.left() - 48, int(y) - 10, 44, 20), Qt.AlignVCenter | Qt.AlignRight),
                (QRect(bounds.right() + 4, int(y) - 10, 44, 20), Qt.AlignVCenter | Qt.AlignLeft),
            ):
                painter.fillRect(label_rect.adjusted(-1, 0, 0, 0), QColor(7, 17, 31, 215))
                painter.drawText(label_rect, alignment, f"{i + 1:02d}")
        painter.restore()

    def draw_entry_waiting_area(self, painter: QPainter, bounds: QRect) -> None:
        if not self.has_entry_waiting_pallets():
            return
        area = self.entry_waiting_area_rect(bounds)
        painter.setPen(QPen(QColor("#2c79b8"), 1, Qt.DashLine))
        painter.setBrush(QColor(9, 24, 38, 185))
        painter.drawRoundedRect(area, 10, 10)
        painter.setPen(QColor("#7fd0ff"))
        painter.setFont(QFont("Yu Gothic UI", 8, QFont.Bold))
        painter.drawText(area.adjusted(10, 4, -10, -4), Qt.AlignTop | Qt.AlignLeft, "仮置きエリア（未配置）")
        painter.setPen(QPen(QColor("#214d76"), 1, Qt.DotLine))
        for slot_x, slot_y in ENTRY_WAITING_SLOTS:
            point = self.point_from_waiting_slot(bounds, slot_x, slot_y)
            painter.drawRoundedRect(QRect(point.x() - 24, point.y() - 11, 48, 22), 5, 5)

    def point_from_waiting_slot(self, bounds: QRect, map_x: float, map_y: float) -> QPoint:
        area = self.entry_waiting_area_rect(bounds)
        min_y = min(slot_y for _slot_x, slot_y in ENTRY_WAITING_SLOTS)
        max_y = max(slot_y for _slot_x, slot_y in ENTRY_WAITING_SLOTS)
        y_ratio = 0.5 if max_y == min_y else (map_y - min_y) / (max_y - min_y)
        x = area.left() + int(area.width() * map_x)
        y = area.center().y() + int((max(0.0, min(1.0, y_ratio)) - 0.5) * max(1, area.height() - 24))
        return QPoint(x, y)

    def compute_location_rects(self, bounds: QRect, columns: int, rows: int) -> Dict[str, QRect]:
        locations = sorted(self.store.locations)
        cell_map: Dict[str, QRect] = {}
        for location in locations:
            col, row = location_to_grid(location)
            cell_map[normalize_location_code(location)] = self.grid_cell_rect(bounds, col, row)
        return cell_map

    def default_point_for_location(self, location: str) -> QPoint:
        rect = self.location_rects.get(normalize_location_code(location))
        if rect is None:
            bounds = self.scaled_bounds()
            return bounds.center()
        return rect.center()

    def center_on_pallet(self, pallet_number: str) -> None:
        pallet = self.store.get_pallet(pallet_number)
        if pallet is None:
            return
        target = self.point_from_pallet(pallet)
        viewport_center = self.rect().center()
        self.pan_offset += viewport_center - target
        self.clamp_pan()
        self.invalidate_base_cache()
        self.update()

    def draw_scale(self, bounds: QRect) -> float:
        scale = min(bounds.width() / 42000.0, bounds.height() / 28000.0)
        return max(0.012, min(scale, 0.06))

    def clamped_normalized_for_pallet(self, pallet: PalletRecord, map_x: float, map_y: float, stack_index: int = 0) -> Tuple[float, float]:
        if map_y > 1.0:
            return max(0.0, min(0.999, map_x)), map_y
        bounds = self.scaled_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return map_x, map_y
        width_mm, depth_mm = footprint_mm(pallet)
        scale = self.draw_scale(bounds)
        half_w = (width_mm * scale) / 2.0
        half_h = (depth_mm * scale) / 2.0
        shift_x = stack_index * TOP_VIEW_STACK_OFFSET_X
        shift_y = stack_index * TOP_VIEW_STACK_OFFSET_Y
        min_x = (half_w - shift_x) / bounds.width()
        max_x = (bounds.width() - half_w - shift_x) / bounds.width()
        min_y = (half_h + shift_y) / bounds.height()
        max_y = (bounds.height() - half_h + shift_y) / bounds.height()
        clamped_x = min(max(map_x, max(0.0, min_x)), min(0.999, max_x))
        clamped_y = min(max(map_y, max(0.0, min_y)), min(0.999, max_y))
        return clamped_x, clamped_y

    def clamped_normalized_for_note(self, note: MapNoteRecord, map_x: float, map_y: float) -> Tuple[float, float]:
        if map_y > 1.0:
            return max(0.0, min(0.999, map_x)), map_y
        bounds = self.scaled_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return map_x, map_y
        width_mm, depth_mm = footprint_mm_for_size(note.size)
        scale = self.draw_scale(bounds)
        half_w = (width_mm * scale) / 2.0
        half_h = (depth_mm * scale) / 2.0
        min_x = half_w / bounds.width()
        max_x = (bounds.width() - half_w) / bounds.width()
        min_y = half_h / bounds.height()
        max_y = (bounds.height() - half_h) / bounds.height()
        clamped_x = min(max(map_x, max(0.0, min_x)), min(0.999, max_x))
        clamped_y = min(max(map_y, max(0.0, min_y)), min(0.999, max_y))
        return clamped_x, clamped_y

    def normalized_position(self, point: QPoint, pallet: Optional[PalletRecord] = None) -> Tuple[float, float]:
        bounds = self.scaled_bounds()
        x = 0.5 if bounds.width() <= 0 else (point.x() - bounds.left()) / bounds.width()
        y = 0.5 if bounds.height() <= 0 else (point.y() - bounds.top()) / bounds.height()
        x = max(0.0, min(0.999, x))
        y = max(0.0, min(0.999, y))
        col, row = normalized_map_to_grid(x, y)
        snapped_x = (col + 0.5) / GRID_COLUMNS
        snapped_y = (row + 0.5) / GRID_ROWS
        if pallet is not None:
            return self.clamped_normalized_for_pallet(pallet, snapped_x, snapped_y)
        return snapped_x, snapped_y

    def point_from_pallet(self, pallet: PalletRecord) -> QPoint:
        bounds = self.scaled_bounds()
        if self.store.is_entry_waiting_pallet(pallet) and pallet.map_x is not None and pallet.map_y is not None:
            return self.point_from_waiting_slot(bounds, pallet.map_x, pallet.map_y)
        return self.default_point_for_location(pallet.location_code)

    def point_from_note(self, note: MapNoteRecord) -> QPoint:
        bounds = self.scaled_bounds()
        map_x = note.map_x if note.map_x is not None else ENTRY_MAP_X
        map_y = note.map_y if note.map_y is not None else ENTRY_MAP_Y
        if map_y > 1.0:
            return self.point_from_waiting_slot(bounds, map_x, map_y)
        return QPoint(bounds.left() + int(bounds.width() * map_x), bounds.top() + int(bounds.height() * map_y))

    def nearest_location(self, point: QPoint) -> Optional[str]:
        if not self.location_rects:
            return None
        for location, rect in self.location_rects.items():
            if location in self.store.blocked_locations:
                continue
            if rect.contains(point):
                return location
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
        return best_location

    def location_at(self, point: QPoint) -> Optional[str]:
        for location, rect in self.location_rects.items():
            if rect.contains(point):
                return location
        return None

    def candidate_label_at(self, point: QPoint) -> Optional[str]:
        bounds = self.scaled_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0 or not bounds.contains(point):
            return None
        col = min(GRID_COLUMNS - 1, max(0, int((point.x() - bounds.left()) * GRID_COLUMNS / bounds.width())))
        row = min(GRID_ROWS - 1, max(0, int((point.y() - bounds.top()) * GRID_ROWS / bounds.height())))
        return visible_location_code(format_location_code(col, row))

    def normalized_position_for_location(self, location: str, pallet: Optional[PalletRecord] = None) -> Tuple[float, float]:
        col, row = location_to_grid(location)
        map_x, map_y = (col + 0.5) / GRID_COLUMNS, (row + 0.5) / GRID_ROWS
        if pallet is not None:
            return self.clamped_normalized_for_pallet(pallet, map_x, map_y)
        return map_x, map_y

    def tooltip_text(self, pallet: PalletRecord) -> str:
        return pallet_popup_text(self.store, pallet)

    def draw_note(self, painter: QPainter, note: MapNoteRecord, rect: QRect) -> None:
        painter.save()
        selected = note.note_id == self.selected_note
        active = note.note_id == self.dragging_note or selected
        base_color = QColor(COLOR_PRESETS.get(note.color_key, COLOR_PRESETS["YELLOW"])[1] or "#FFC34D")
        fill = QColor(base_color.lighter(155))
        fill.setAlpha(28)
        hatch = QColor(base_color.lighter(125))
        hatch.setAlpha(170)
        outline = QColor("#fff8c9" if active else base_color.lighter(115))
        if selected and self.attention_visible:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#7fd0ff"), 4, Qt.DashLine))
            painter.drawRoundedRect(rect.adjusted(-10, -10, 10, 10), 8, 8)
        painter.setBrush(fill)
        painter.setPen(QPen(outline, 5 if selected else 4))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setClipRect(rect.adjusted(2, 2, -2, -2))
        painter.setPen(QPen(hatch, 2))
        step = 10
        for offset in range(-rect.height(), rect.width() + rect.height(), step):
            painter.drawLine(rect.left() + offset, rect.bottom(), rect.left() + offset + rect.height(), rect.top())
        painter.setClipping(False)
        fold_size = max(10, min(18, rect.width() // 5))
        fold = QPolygonF([
            QPointF(rect.right() - fold_size, rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.top() + fold_size),
        ])
        fold_fill = QColor("#ffe07a")
        fold_fill.setAlpha(150)
        painter.setBrush(fold_fill)
        painter.setPen(QPen(outline, 1))
        painter.drawPolygon(fold)
        label_rect = QRect(rect.left() + 5, rect.top() + 4, min(46, max(32, rect.width() - 14)), 16)
        label_fill = QColor("#1f2430")
        label_fill.setAlpha(220)
        painter.setBrush(label_fill)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(label_rect, 4, 4)
        painter.setPen(QColor("#fff2a8"))
        painter.setFont(QFont("Yu Gothic UI", 7, QFont.Bold))
        painter.drawText(label_rect, Qt.AlignCenter, painter.fontMetrics().elidedText(map_note_title(note), Qt.ElideRight, label_rect.width() - 6))
        text_back = QRect(rect.left() + 5, rect.top() + 23, max(20, rect.width() - 10), max(12, rect.height() - 28))
        preview_back = QColor("#fff7c2")
        preview_back.setAlpha(90)
        painter.setBrush(preview_back)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(text_back, 3, 3)
        painter.setPen(QColor("#3a2a08"))
        painter.setFont(QFont("Yu Gothic UI", 8, QFont.Bold))
        preview = map_note_title(note)
        painter.drawText(rect.adjusted(7, 24, -7, -6), Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, preview[:32])
        painter.restore()

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, rect: QRect, stack_index: int = 0, stack_count: int = 1) -> None:
        multi_selected = pallet.pallet_number in self.selected_pallets
        active = pallet.pallet_number in {self.selected_pallet, self.hover_pallet, self.dragging_pallet} or multi_selected
        selected = pallet.pallet_number == self.selected_pallet or multi_selected
        waiting_move = is_entry_staged_pallet(pallet)
        color = pallet_color(pallet); fill = QColor(color); fill.setAlpha(42)
        outline = QColor(color.lighter(145) if active else color)
        if selected and self.attention_visible:
            selected_pulse = rect.adjusted(-12, -12, 12, 12)
            selected_color = QColor("#7fd0ff")
            selected_color.setAlpha(96)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(selected_color, 3, Qt.DashLine))
            painter.drawRoundedRect(selected_pulse, 10, 10)
        if waiting_move and self.attention_visible:
            pulse = rect.adjusted(-8, -8, 8, 8)
            pulse_color = QColor("#ffd866")
            pulse_color.setAlpha(84)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(pulse_color, 3, Qt.DashLine))
            painter.drawRoundedRect(pulse, 8, 8)
        painter.setBrush(fill); painter.setPen(QPen(outline, 2 if active else 1))
        painter.drawRoundedRect(rect, 5, 5); painter.setPen(QColor("#dff6ff")); painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.drawText(rect.adjusted(6, 4, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.pallet_number)
        painter.setFont(QFont("Yu Gothic UI", 7)); painter.drawText(rect.adjusted(6, 18, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.summary_text[:24])
        badge = QRect(rect.right() - 20, rect.bottom() - 16, 16, 12)
        painter.setBrush(color); painter.setPen(Qt.NoPen); painter.drawEllipse(badge)
        display_stack_number = 1 if stack_count <= 1 else max(1, stack_count - stack_index)
        painter.setPen(QColor("#04111c")); painter.drawText(badge, Qt.AlignCenter, str(display_stack_number))
        if waiting_move:
            move_badge = QRect(rect.left() + 4, rect.bottom() - 16, 28, 12)
            painter.setBrush(QColor("#ffd866" if self.attention_visible else "#a7842a"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(move_badge, 4, 4)
            painter.setPen(QColor("#04111c"))
            painter.setFont(QFont("Yu Gothic UI", 6, QFont.Bold))
            painter.drawText(move_badge, Qt.AlignCenter, "移動")

    def cache_key(self):
        return (
            self.size().width(),
            self.size().height(),
            round(self.zoom, 4),
            self.pan_offset.x(),
            self.pan_offset.y(),
            tuple(sorted(self.store.blocked_locations)),
            tuple((p.pallet_number, p.location_code, p.stack_order, p.orientation, p.map_x, p.map_y, p.updated_at, p.color_key, len(p.items)) for p in self.store.pallets),
            tuple((n.note_id, n.size, n.map_x, n.map_y, n.color_key, n.updated_at) for n in self.store.map_notes),
        )

    def invalidate_base_cache(self) -> None:
        self.base_cache_pixmap = None
        self.base_cache_key = None
        self.base_cache_dirty = True
        self.drag_cache_pixmap = None
        self.drag_cache_pallet = None
        self.drag_cache_note = None

    def render_top_map(self, painter: QPainter, exclude_pallet: Optional[str] = None, exclude_note: Optional[str] = None, static_cache: bool = False) -> None:
        saved_state = None
        if static_cache:
            saved_state = (self.selected_pallet, set(self.selected_pallets), self.selected_note, self.hover_pallet, self.hover_note, self.dragging_pallet, self.dragging_note, self.attention_visible)
            self.hover_pallet = None
            self.hover_note = None
            self.dragging_pallet = None
            self.dragging_note = None
            self.attention_visible = False
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#07111f"))
        self.location_rects.clear(); self.pallet_rects.clear(); self.note_rects.clear(); bounds = self.scaled_bounds(); columns, rows = self.draw_grid(painter, bounds)
        self.draw_entry_waiting_area(painter, bounds)
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
                selected_group_key = selected.pallet_number if self.store.is_entry_waiting_pallet(selected) else normalize_location_code(selected.location_code)
        for pallet in sorted(self.store.pallets, key=lambda p: (normalize_location_code(p.location_code), p.stack_order, p.pallet_number)):
            key = pallet.pallet_number if self.store.is_entry_waiting_pallet(pallet) else normalize_location_code(pallet.location_code)
            group_index[pallet.pallet_number] = group_counts.get(key, 0)
            group_counts[key] = group_counts.get(key, 0) + 1
        for pallet in sorted(self.store.pallets, key=lambda p: (p.location_code, p.stack_order, p.pallet_number)):
            width_mm, depth_mm = footprint_mm(pallet)
            base_point = self.point_from_pallet(pallet)
            scale = self.draw_scale(bounds)
            stack_index = group_index.get(pallet.pallet_number, pallet.stack_order)
            group_key = pallet.pallet_number if self.store.is_entry_waiting_pallet(pallet) else normalize_location_code(pallet.location_code)
            selected_stack = selected_group_key is not None and group_key == selected_group_key and group_counts.get(group_key, 1) > 1
            shift_x = TOP_VIEW_SELECTED_STACK_OFFSET_X if selected_stack else TOP_VIEW_STACK_OFFSET_X
            shift_y = TOP_VIEW_SELECTED_STACK_OFFSET_Y if selected_stack else TOP_VIEW_STACK_OFFSET_Y
            if pallet.pallet_number != exclude_pallet and selected_stack and stack_index > 0:
                painter.setPen(QPen(QColor("#5da7d9"), 1, Qt.DotLine))
                line_target = QPoint(base_point.x() + stack_index * shift_x, base_point.y() - stack_index * shift_y)
                painter.drawLine(base_point, line_target)
            rect = QRect(base_point.x() - int(width_mm * scale / 2) + stack_index * shift_x, base_point.y() - int(depth_mm * scale / 2) - stack_index * shift_y, max(18, int(width_mm * scale)), max(14, int(depth_mm * scale)))
            if self.dragging_pallet == pallet.pallet_number:
                rect.moveTo(self.drag_point - self.drag_offset)
            self.pallet_rects[pallet.pallet_number] = rect
            if pallet.pallet_number != exclude_pallet:
                self.draw_pallet(painter, pallet, rect, stack_index=stack_index, stack_count=group_counts.get(group_key, 1))
        for note in sorted(self.store.map_notes, key=lambda item: item.updated_at):
            width_mm, depth_mm = footprint_mm_for_size(note.size)
            base_point = self.point_from_note(note)
            scale = self.draw_scale(bounds)
            rect = QRect(base_point.x() - int(width_mm * scale / 2), base_point.y() - int(depth_mm * scale / 2), max(18, int(width_mm * scale)), max(14, int(depth_mm * scale)))
            if self.dragging_note == note.note_id:
                rect.moveTo(self.drag_point - self.drag_offset)
            self.note_rects[note.note_id] = rect
            if note.note_id != exclude_note:
                self.draw_note(painter, note, rect)
        if saved_state is not None:
            self.selected_pallet, self.selected_pallets, self.selected_note, self.hover_pallet, self.hover_note, self.dragging_pallet, self.dragging_note, self.attention_visible = saved_state

    def rebuild_base_cache(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        pixmap = QPixmap(self.size())
        cache_painter = QPainter(pixmap)
        self.render_top_map(cache_painter, static_cache=True)
        cache_painter.end()
        self.base_cache_pixmap = pixmap
        self.base_cache_key = self.cache_key()
        self.base_cache_dirty = False

    def rebuild_drag_cache(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        exclude_pallet = self.dragging_pallet
        exclude_note = self.dragging_note
        pixmap = QPixmap(self.size())
        cache_painter = QPainter(pixmap)
        self.render_top_map(cache_painter, exclude_pallet=exclude_pallet, exclude_note=exclude_note, static_cache=True)
        cache_painter.end()
        self.drag_cache_pixmap = pixmap
        self.drag_cache_pallet = exclude_pallet
        self.drag_cache_note = exclude_note

    def draw_cached_overlay_pallet(self, painter: QPainter, pallet_number: str) -> None:
        pallet = self.store.get_pallet(pallet_number)
        rect = self.pallet_rects.get(pallet_number)
        if pallet is None or rect is None:
            return
        members = self.store.group_members(pallet)
        stack_index = next((index for index, member in enumerate(members) if member.pallet_number == pallet_number), pallet.stack_order)
        self.draw_pallet(painter, pallet, QRect(rect), stack_index=stack_index, stack_count=max(1, len(members)))

    def draw_cached_overlay_note(self, painter: QPainter, note_id: str) -> None:
        note = self.store.get_map_note(note_id)
        rect = self.note_rects.get(note_id)
        if note is not None and rect is not None:
            self.draw_note(painter, note, QRect(rect))

    def draw_interaction_overlays(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        seen: set[str] = set()
        for pallet_number in self.selected_pallets:
            self.draw_cached_overlay_pallet(painter, pallet_number)
            seen.add(pallet_number)
        for pallet_number in (self.selected_pallet, self.hover_pallet):
            if pallet_number and pallet_number not in seen:
                self.draw_cached_overlay_pallet(painter, pallet_number)
                seen.add(pallet_number)
        for note_id in {note_id for note_id in (self.selected_note, self.hover_note) if note_id}:
            self.draw_cached_overlay_note(painter, note_id)

    def draw_drag_foreground(self, painter: QPainter) -> None:
        if self.dragging_pallet:
            pallet = self.store.get_pallet(self.dragging_pallet)
            source_rect = self.pallet_rects.get(self.dragging_pallet)
            if pallet is not None and source_rect is not None:
                rect = QRect(source_rect)
                rect.moveTo(self.drag_point - self.drag_offset)
                color = pallet_color(pallet)
                fill = QColor(color)
                fill.setAlpha(92)
                painter.setBrush(fill)
                painter.setPen(QPen(QColor("#f6fbff"), 2))
                painter.drawRect(rect)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Consolas", 8, QFont.Bold))
                painter.drawText(rect.adjusted(5, 3, -5, -3), Qt.AlignTop | Qt.AlignLeft, pallet.pallet_number)
        if self.dragging_note:
            note = self.store.get_map_note(self.dragging_note)
            source_rect = self.note_rects.get(self.dragging_note)
            if note is not None and source_rect is not None:
                rect = QRect(source_rect)
                rect.moveTo(self.drag_point - self.drag_offset)
                color = QColor(COLOR_PRESETS.get(note.color_key, COLOR_PRESETS["YELLOW"])[1] or "#FFC34D")
                fill = QColor(color)
                fill.setAlpha(60)
                painter.setBrush(fill)
                painter.setPen(QPen(QColor("#fff8c9"), 3))
                painter.drawRect(rect)
                painter.setPen(QColor("#fff8c9"))
                painter.setFont(QFont("Yu Gothic UI", 8, QFont.Bold))
                painter.drawText(rect.adjusted(5, 3, -5, -3), Qt.AlignTop | Qt.AlignLeft, "メモ")
        if self.drag_candidate_label:
            label_rect = self.drag_candidate_label_rect()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(7, 17, 31, 190))
            painter.drawRect(label_rect)
            painter.setPen(QColor("#dff6ff"))
            painter.setFont(QFont("Consolas", 11, QFont.Bold))
            painter.drawText(label_rect, Qt.AlignCenter, self.drag_candidate_label)

    def drag_candidate_label_rect(self) -> QRect:
        text = self.drag_candidate_label or ""
        width = max(48, 10 + len(text) * 9)
        rect = QRect(self.drag_point.x() + 12, self.drag_point.y() - 30, width, 22)
        rect.moveLeft(max(6, min(rect.left(), max(6, self.width() - rect.width() - 6))))
        rect.moveTop(max(6, min(rect.top(), max(6, self.height() - rect.height() - 6))))
        return rect

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self.is_dragging and (self.dragging_pallet or self.dragging_note):
            if self.drag_cache_pixmap is None or self.drag_cache_pixmap.size() != self.size() or self.drag_cache_pallet != self.dragging_pallet or self.drag_cache_note != self.dragging_note:
                self.rebuild_drag_cache()
            if self.drag_cache_pixmap is not None:
                painter.drawPixmap(0, 0, self.drag_cache_pixmap)
            else:
                self.render_top_map(painter, exclude_pallet=self.dragging_pallet, exclude_note=self.dragging_note)
            self.draw_drag_foreground(painter)
            painter.end()
            return
        if self.base_cache_dirty or self.base_cache_pixmap is None or self.base_cache_pixmap.size() != self.size():
            self.rebuild_base_cache()
        if self.base_cache_pixmap is not None:
            painter.drawPixmap(0, 0, self.base_cache_pixmap)
        else:
            self.render_top_map(painter)
        self.draw_interaction_overlays(painter)
        painter.end()

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        if event.button() == Qt.RightButton:
            for note_id, rect in self.note_rects.items():
                if rect.contains(point):
                    self.selected_note = note_id
                    self.selected_pallet = None
                    self.selected_pallets = set()
                    self.mapNoteSelected.emit(note_id)
                    self.mapNoteContextRequested.emit(note_id, event.globalPosition().toPoint())
                    self.update()
                    return
            for pallet_number, rect in self.pallet_rects.items():
                if rect.contains(point):
                    self.selected_pallet = pallet_number
                    self.selected_pallets = {pallet_number}
                    self.selected_note = None
                    self.palletSelected.emit(pallet_number)
                    self.palletContextRequested.emit(pallet_number, event.globalPosition().toPoint())
                    self.update()
                    return
            return
        if event.button() != Qt.LeftButton:
            return
        if self.blocked_edit_mode:
            location = self.location_at(point)
            if location:
                blocked = location not in self.store.blocked_locations
                self.blockedLocationToggled.emit(location, blocked)
            return
        if self.begin_drag_at(point):
            return
        self.selected_pallet = None
        self.selected_pallets = set()
        self.selected_note = None
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
            self.invalidate_base_cache()
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
        for note_id, rect in self.note_rects.items():
            if rect.contains(point):
                self.selected_note = note_id
                self.selected_pallet = None
                self.selected_pallets = set()
                self.mapNoteSelected.emit(note_id)
                self.mapNoteDoubleClicked.emit(note_id)
                self.update()
                return
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number
                self.selected_pallets = {pallet_number}
                self.selected_note = None
                self.palletSelected.emit(pallet_number)
                self.palletDoubleClicked.emit(pallet_number)
                self.update()
                return

    def begin_drag_at(self, point: QPoint) -> bool:
        for note_id, rect in self.note_rects.items():
            if rect.contains(point):
                self.selected_note = note_id
                self.selected_pallet = None
                self.selected_pallets = set()
                self.dragging_note = note_id
                self.is_dragging = True
                self.drag_start_point = point
                self.drag_offset = point - rect.topLeft()
                self.drag_point = point
                if self.is_dragging:
                    self.drag_candidate_label = self.candidate_label_at(point)
                self.hover_target = None
                self.hover_note = None
                self.drag_cache_pixmap = None
                self.drag_cache_pallet = None
                self.drag_cache_note = None
                self.setToolTip("")
                QToolTip.hideText()
                self.setCursor(Qt.ArrowCursor)
                self.dragStarted.emit()
                self.rebuild_drag_cache()
                self.update()
                return True
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number
                self.selected_pallets = {pallet_number}
                self.selected_note = None
                self.dragging_pallet = pallet_number
                self.is_dragging = True
                self.drag_start_point = point
                self.drag_offset = point - rect.topLeft()
                self.drag_point = point
                if self.is_dragging:
                    self.drag_candidate_label = self.candidate_label_at(point)
                self.hover_target = None
                self.hover_note = None
                self.drag_cache_pixmap = None
                self.drag_cache_pallet = None
                self.drag_cache_note = None
                self.setToolTip("")
                QToolTip.hideText()
                self.setCursor(Qt.ArrowCursor)
                self.dragStarted.emit()
                self.rebuild_drag_cache()
                self.update()
                return True
        return False

    def current_drag_rect(self) -> Optional[QRect]:
        source_rect = None
        if self.dragging_note:
            source_rect = self.note_rects.get(self.dragging_note)
        elif self.dragging_pallet:
            source_rect = self.pallet_rects.get(self.dragging_pallet)
        if source_rect is None:
            return None
        rect = QRect(source_rect)
        rect.moveTo(self.drag_point - self.drag_offset)
        return rect

    def current_drag_update_rect(self) -> Optional[QRect]:
        drag_rect = self.current_drag_rect()
        label_rect = self.drag_candidate_label_rect() if self.drag_candidate_label else None
        if drag_rect is None:
            return label_rect
        return drag_rect.united(label_rect) if label_rect is not None else drag_rect

    def request_drag_update(self, old_rect: Optional[QRect] = None, new_rect: Optional[QRect] = None) -> None:
        dirty_rect = QRect()
        for rect in (old_rect, new_rect):
            if rect is not None and rect.isValid():
                expanded = rect.adjusted(-8, -8, 8, 8)
                dirty_rect = expanded if dirty_rect.isNull() else dirty_rect.united(expanded)
        if dirty_rect.isNull():
            dirty_rect = self.rect()
        clipped = dirty_rect.intersected(self.rect())
        self.update(clipped if clipped.isValid() and not clipped.isNull() else self.rect())

    def update_drag_at(self, point: QPoint) -> None:
        old_drag_rect = self.current_drag_update_rect() if self.is_dragging else None
        self.drag_point = point
        if self.is_dragging:
            self.drag_candidate_label = self.candidate_label_at(point)
        if self.is_dragging and self.dragging_note:
            self.hover_pallet = None
            self.request_drag_update(old_drag_rect, self.current_drag_update_rect())
            return
        if self.is_dragging and self.dragging_pallet:
            self.hover_pallet = None
            self.request_drag_update(old_drag_rect, self.current_drag_update_rect())
            return
        hit = None
        note_hit = None
        for note_id, rect in reversed(list(self.note_rects.items())):
            if rect.contains(point):
                note_hit = note_id
                break
        if note_hit is None:
            for pallet_number, rect in reversed(list(self.pallet_rects.items())):
                if rect.contains(point):
                    hit = pallet_number
                    break
        new_hover_target = ("note", note_hit) if note_hit else (("pallet", hit) if hit else None)
        if new_hover_target == self.hover_target:
            return
        self.hover_target = new_hover_target
        self.hover_note = note_hit
        self.hover_pallet = hit
        note = self.store.get_map_note(note_hit) if note_hit else None
        pallet = self.store.get_pallet(hit) if hit else None
        if note:
            text = map_note_popup_text(note)
            self.setToolTip(text)
            QToolTip.showText(self.mapToGlobal(point), text, self)
        elif pallet:
            text = self.tooltip_text(pallet)
            self.setToolTip(text)
            QToolTip.showText(self.mapToGlobal(point), text, self)
        else:
            self.setToolTip("")
            QToolTip.hideText()
        self.setCursor(Qt.PointingHandCursor if (hit or note_hit) and not self.dragging_pallet and not self.dragging_note else Qt.ArrowCursor)
        self.update()

    def finish_drag_state(self, pallet_number: Optional[str], show_detail: bool = False) -> None:
        self.dragging_pallet = None
        self.dragging_note = None
        self.hover_target = None
        self.drag_cache_pixmap = None
        self.drag_cache_pallet = None
        self.drag_cache_note = None
        self.drag_candidate_label = None
        self.is_dragging = False
        self.setToolTip("")
        QToolTip.hideText()
        if pallet_number:
            self.selected_pallet = pallet_number
            self.selected_pallets = {pallet_number}
            self.selected_note = None
            self.hover_pallet = pallet_number
            if show_detail:
                QTimer.singleShot(0, lambda pn=pallet_number: self.palletSelected.emit(pn))
        self.update()

    def end_drag_at(self, point: QPoint) -> None:
        if self.dragging_note:
            dragged_note = self.dragging_note
            moved = (point - self.drag_start_point).manhattanLength()
            if moved <= 6:
                QTimer.singleShot(0, lambda nid=dragged_note: self.mapNoteSelected.emit(nid))
            else:
                note = self.store.get_map_note(dragged_note)
                if note is not None:
                    center = point - self.drag_offset + QPoint(self.note_rects.get(dragged_note, QRect()).width() // 2, self.note_rects.get(dragged_note, QRect()).height() // 2)
                    destination = self.nearest_location(center)
                    if destination:
                        col, row = location_to_grid(destination)
                        map_x, map_y = self.clamped_normalized_for_note(note, (col + 0.5) / GRID_COLUMNS, (row + 0.5) / GRID_ROWS)
                    else:
                        bounds = self.scaled_bounds()
                        map_x = 0.5 if bounds.width() <= 0 else (center.x() - bounds.left()) / bounds.width()
                        map_y = 0.5 if bounds.height() <= 0 else (center.y() - bounds.top()) / bounds.height()
                        map_x, map_y = self.clamped_normalized_for_note(note, map_x, map_y)
                    self.mapNoteMoved.emit(dragged_note, map_x, map_y)
            self.finish_drag_state(None, show_detail=False)
            return
        if not self.dragging_pallet:
            return
        dragged_pallet = self.dragging_pallet
        moved = (point - self.drag_start_point).manhattanLength()
        if moved <= 6:
            self.finish_drag_state(dragged_pallet, show_detail=True)
            return
        destination = self.nearest_location(point)
        if destination:
            pallet = self.store.get_pallet(self.dragging_pallet)
            map_x, map_y = self.normalized_position_for_location(destination, pallet)
            self.palletMoved.emit(self.dragging_pallet, map_x, map_y, destination)
        self.finish_drag_state(dragged_pallet, show_detail=False)

    def event(self, event) -> bool:
        if event.type() in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            points = event.points()
            if not points:
                self.touch_zoom_distance = None
                self.touch_zoom_midpoint = None
                self.is_dragging = False
                self.dragging_note = None
                return True
            if event.type() == QEvent.TouchEnd:
                if self.touch_zoom_distance is not None:
                    self.touch_zoom_distance = None
                    self.touch_zoom_midpoint = None
                    self.finish_drag_state(self.dragging_pallet, show_detail=False)
                    return True
                self.end_drag_at(points[0].position().toPoint())
                return True
            if len(points) >= 2:
                first = points[0].position().toPoint()
                second = points[1].position().toPoint()
                midpoint = QPoint((first.x() + second.x()) // 2, (first.y() + second.y()) // 2)
                distance = ((first.x() - second.x()) ** 2 + (first.y() - second.y()) ** 2) ** 0.5
                if self.touch_zoom_distance is not None and self.touch_zoom_distance > 0:
                    self.zoom = max(0.5, min(2.8, self.zoom * (distance / self.touch_zoom_distance)))
                    if self.touch_zoom_midpoint is not None:
                        self.pan_offset += midpoint - self.touch_zoom_midpoint
                    self.clamp_pan()
                    self.invalidate_base_cache()
                    self.update()
                else:
                    self.finish_drag_state(self.dragging_pallet, show_detail=False)
                self.touch_zoom_distance = distance
                self.touch_zoom_midpoint = midpoint
                return True
            self.touch_zoom_distance = None
            self.touch_zoom_midpoint = None
            point = points[0].position().toPoint()
            if event.type() == QEvent.TouchBegin:
                self.begin_drag_at(point)
            elif event.type() == QEvent.TouchUpdate:
                self.update_drag_at(point)
            return True
        return super().event(event)

    def resizeEvent(self, event) -> None:
        self.invalidate_base_cache()
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9))); self.clamp_pan(); self.invalidate_base_cache(); self.update()

    def zoom_in(self) -> None:
        self.zoom = min(2.8, self.zoom * 1.15); self.clamp_pan(); self.invalidate_base_cache(); self.update()

    def zoom_out(self) -> None:
        self.zoom = max(0.5, self.zoom / 1.15); self.clamp_pan(); self.invalidate_base_cache(); self.update()

    def reset_zoom(self) -> None:
        self.zoom = 1.0; self.pan_offset = QPoint(); self.invalidate_base_cache(); self.update()

class IsometricMapWidget(QWidget):
    palletSelected = Signal(str)
    selectionCleared = Signal()
    palletDoubleClicked = Signal(str)
    palletContextRequested = Signal(str, QPoint)

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.hover_pallet = None; self.selected_pallet = None; self.pallet_rects: Dict[str, QRect] = {}; self.zoom = 1.0
        self.pan_offset = QPoint()
        self.panning = False
        self.pan_anchor = QPoint()
        self.touch_zoom_distance: Optional[float] = None
        self.touch_zoom_midpoint: Optional[QPoint] = None
        self.view_rotation = 1
        self.attention_visible = True
        self.attention_timer = QTimer(self)
        self.attention_timer.timeout.connect(self.toggle_attention_state)
        self.attention_timer.start(520)
        self.setMinimumHeight(560); self.setMouseTracking(True); self.setAttribute(Qt.WA_AcceptTouchEvents, True)

    def toggle_attention_state(self) -> None:
        self.attention_visible = not self.attention_visible
        self.update()

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

    def draw_blocked_cells(self, painter: QPainter, bounds: QRect) -> None:
        for location in self.store.blocked_locations:
            col, row = location_to_grid(location)
            left = col / float(GRID_COLUMNS)
            right = (col + 1) / float(GRID_COLUMNS)
            top = row / float(GRID_ROWS)
            bottom = (row + 1) / float(GRID_ROWS)
            cell = QPolygonF([
                self.project_normalized_point(bounds, left, top),
                self.project_normalized_point(bounds, right, top),
                self.project_normalized_point(bounds, right, bottom),
                self.project_normalized_point(bounds, left, bottom),
            ])
            center = self.project_normalized_point(bounds, (left + right) / 2.0, (top + bottom) / 2.0)
            painter.setPen(QPen(QColor("#c85a68"), 1.5))
            painter.setBrush(QColor(200, 90, 104, 92))
            painter.drawPolygon(cell)
            painter.setPen(QColor("#ffd1d7"))
            painter.setFont(QFont("Consolas", 8, QFont.Bold))
            painter.drawText(QRect(int(center.x() - 10), int(center.y() - 8), 20, 16), Qt.AlignCenter, "X")

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, base: QPointF) -> QRect:
        width_mm, depth_mm = footprint_mm(pallet)
        if pallet.orientation % 180 == 90:
            width_mm *= 0.8
            depth_mm *= 0.8
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
        selected = pallet.pallet_number == self.selected_pallet
        waiting_move = is_entry_staged_pallet(pallet)
        fill = QColor(color)
        fill.setAlpha(170)
        outline = QColor(color.lighter(145) if active else color.darker(115))
        if selected and self.attention_visible:
            selected_color = QColor("#7fd0ff")
            selected_color.setAlpha(92)
            painter.setPen(QPen(selected_color, 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(base, 24, 14)
        if waiting_move and self.attention_visible:
            pulse_color = QColor("#ffd866")
            pulse_color.setAlpha(70)
            painter.setPen(QPen(pulse_color, 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(base, 18, 10)
        painter.setPen(QPen(outline, 2 if active else 1))
        painter.setBrush(fill); painter.drawPolygon(face_a)
        painter.setBrush(fill); painter.drawPolygon(face_b)
        painter.setBrush(fill); painter.drawPolygon(top)
        label_anchor = min([QPointF(point.x(), point.y() - height) for point in corners_bottom], key=lambda point: point.y() + (point.x() * 0.02))
        painter.setPen(QColor("#daf5ff")); painter.setFont(QFont("Yu Gothic UI", 10, QFont.Bold)); painter.drawText(QPointF(label_anchor.x() + 4, label_anchor.y() + 15), pallet.pallet_number)
        if waiting_move:
            painter.setPen(QColor("#ffd866" if self.attention_visible else "#b59234"))
            painter.setFont(QFont("Yu Gothic UI", 10, QFont.Bold))
            painter.drawText(QPointF(label_anchor.x() + 4, label_anchor.y() + 29), "入口待機")
        min_x = min(point.x() for point in corners_bottom)
        max_x = max(point.x() for point in corners_bottom)
        min_y = min(point.y() for point in corners_bottom) - height
        max_y = max(point.y() for point in corners_bottom)
        return QRect(int(min_x - 4), int(min_y - 4), int((max_x - min_x) + 10), int((max_y - min_y) + 10))

    def tooltip_text(self, pallet: PalletRecord) -> str:
        return pallet_popup_text(self.store, pallet)

    def paintEvent(self, event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.fillRect(self.rect(), QColor("#07111f")); self.pallet_rects.clear(); bounds = self.scaled_bounds(); self.draw_floor(painter, bounds); self.draw_blocked_cells(painter, bounds)
        entrance_point = self.project_normalized_point(bounds, ENTRY_MAP_X, ENTRY_MAP_Y)
        painter.setPen(QPen(QColor("#4fc3ff"), 2))
        painter.setBrush(QColor(79, 195, 255, 60))
        painter.drawEllipse(QPointF(entrance_point.x(), entrance_point.y()), 8, 8)
        painter.drawLine(QPointF(entrance_point.x(), entrance_point.y()), QPointF(entrance_point.x(), entrance_point.y() + 26))
        painter.setPen(QColor("#7fd0ff"))
        painter.setFont(QFont("Yu Gothic UI", 12, QFont.Bold))
        painter.drawText(QRect(int(entrance_point.x() - 46), int(entrance_point.y() + 28), 92, 18), Qt.AlignCenter, "入口")
        groups: Dict[str, List[PalletRecord]] = {}
        for pallet in self.store.pallets:
            key = pallet.pallet_number if self.store.is_entry_waiting_pallet(pallet) else normalize_location_code(pallet.location_code)
            groups.setdefault(key, []).append(pallet)
        base_points: Dict[str, QPointF] = {}
        group_entries: List[Tuple[float, float, str, List[PalletRecord], QPointF]] = []
        for group_key, members in groups.items():
            members.sort(key=lambda p: (p.stack_order, p.updated_at, p.pallet_number))
            anchor = members[0]
            if anchor.map_x is not None and anchor.map_y is not None:
                projected_y = ENTRY_MAP_Y if anchor.map_y > 1.0 else anchor.map_y
                base = self.project_normalized_point(bounds, anchor.map_x, projected_y)
            else:
                nx, ny = self.location_normalized_point(anchor.location_code)
                base = self.project_normalized_point(bounds, nx, ny)
            group_entries.append((base.y(), base.x(), group_key, members, base))

        group_entries.sort(key=lambda entry: (entry[0], entry[1]))
        for _depth_y, _depth_x, _group_key, members, base in group_entries:
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
        painter.setPen(QColor("#6d90b5")); painter.setFont(QFont("Yu Gothic UI", 12, QFont.Bold)); painter.drawText(bounds.adjusted(6, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, f"45度ビュー / {view_names.get(self.view_rotation % 4, '')}")

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
        point = event.position().toPoint()
        if event.button() == Qt.RightButton:
            for pallet_number, rect in self.pallet_rects.items():
                if rect.contains(point):
                    self.selected_pallet = pallet_number
                    self.palletSelected.emit(pallet_number)
                    self.palletContextRequested.emit(pallet_number, event.globalPosition().toPoint())
                    self.update()
                    return
            return
        if event.button() != Qt.LeftButton:
            return
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

    def event(self, event) -> bool:
        if event.type() in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            points = event.points()
            if not points:
                self.touch_zoom_distance = None
                self.touch_zoom_midpoint = None
                self.panning = False
                return True
            if event.type() == QEvent.TouchEnd:
                self.touch_zoom_distance = None
                self.touch_zoom_midpoint = None
                self.panning = False
                return True
            if len(points) >= 2:
                first = points[0].position().toPoint()
                second = points[1].position().toPoint()
                midpoint = QPoint((first.x() + second.x()) // 2, (first.y() + second.y()) // 2)
                distance = ((first.x() - second.x()) ** 2 + (first.y() - second.y()) ** 2) ** 0.5
                if self.touch_zoom_distance is not None and self.touch_zoom_distance > 0:
                    self.zoom = max(0.5, min(2.8, self.zoom * (distance / self.touch_zoom_distance)))
                    if self.touch_zoom_midpoint is not None:
                        self.pan_offset += midpoint - self.touch_zoom_midpoint
                    self.clamp_pan()
                    self.update()
                self.touch_zoom_distance = distance
                self.touch_zoom_midpoint = midpoint
                self.panning = False
                return True
            self.touch_zoom_distance = None
            self.touch_zoom_midpoint = None
            point = points[0].position().toPoint()
            if event.type() == QEvent.TouchBegin:
                self.panning = True
                self.pan_anchor = point
            elif event.type() == QEvent.TouchUpdate and self.panning:
                self.pan_offset += point - self.pan_anchor
                self.pan_anchor = point
                self.clamp_pan()
                self.update()
            return True
        return super().event(event)

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
    INVENTORY_COLUMNS = [
        ("part_code", "品番", 88),
        ("size", "サイズ", 70),
        ("thickness", "厚み", 76),
        ("finish", "加工 / 裏表", 120),
        ("grade", "グレード", 76),
        ("sheets", "総枚数", 76),
        ("lot", "Lot", 120),
        ("note", "備考", 160),
        ("locations", "保管場所", 180),
        ("pallets", "パレット番号", 180),
        ("received_dates", "入庫日", 150),
    ]
    INVENTORY_PALLET_COLUMN = 9
    SHIPMENT_COLUMNS = [
        ("shipped_at", "出庫日", 118),
        ("pallet_number", "パレット番号", 130),
        ("part_code", "品番", 88),
        ("size", "サイズ", 70),
        ("thickness", "厚み", 76),
        ("finish", "加工 / 裏表", 120),
        ("grade", "グレード", 76),
        ("total_sheets", "総枚数", 76),
        ("lot", "Lot", 120),
        ("notes", "備考", 160),
        ("location_code", "最終位置", 180),
        ("received_date", "入庫日", 150),
    ]

    def __init__(self) -> None:
        super().__init__(); self.store = load_store(); self.current_pallet_number = None; self.current_note_id = None
        self.last_registration_item_cache: Optional[InventoryItemLine] = None
        self.move_undo_stack: List[MoveAction] = []
        self.move_redo_stack: List[MoveAction] = []
        self.move_history_limit = 30
        self.inventory_sort_key = "part_code"
        self.inventory_sort_desc = False
        self.shipment_sort_key = "shipped_at"
        self.shipment_sort_desc = True
        self.settings = QSettings(APP_ID, "WarehouseApp")
        hidden_columns = str(self.settings.value("inventory_hidden_columns", "") or "")
        self.inventory_hidden_columns: set[int] = {
            int(value) for value in hidden_columns.split(",") if value.isdigit()
        }
        self.detail_drag_active = False
        self.detail_drag_offset = QPoint()
        self.detail_frame_manual_position: Optional[QPoint] = None
        self.detail_frame_manual_size: Optional[Tuple[int, int]] = None
        self.detail_resize_active = False
        self.detail_resize_origin = QPoint()
        self.detail_resize_start_size: Optional[Tuple[int, int]] = None
        self.cell_popup_timer = QTimer(self)
        self.cell_popup_timer.setSingleShot(True)
        self.cell_popup = QLabel(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cell_popup.setWordWrap(True)
        self.cell_popup.setMaximumWidth(420)
        self.cell_popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.cell_popup.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.cell_popup.setStyleSheet(
            "QLabel { background:#fff7cc; color:#111111; border:1px solid #806000; "
            "border-radius:6px; padding:10px; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; }"
        )
        self.cell_popup.hide()
        self.cell_popup_timer.timeout.connect(self.cell_popup.hide)
        self.table_long_press_timer = QTimer(self)
        self.table_long_press_timer.setSingleShot(True)
        self.table_long_press_timer.timeout.connect(self.enable_table_multi_select_from_long_press)
        self.table_long_press_table: Optional[QTableWidget] = None
        self.table_long_press_point = QPoint()
        self.table_press_point = QPoint()
        self.table_press_moved = False
        self.table_multi_select_mode: set[QTableWidget] = set()
        self.store_dirty = False
        self.setWindowTitle("Warehouse Management App - PySide6"); self.resize(1480, 920); self.setMinimumSize(900, 620)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.build_ui(); self.apply_theme(); self.refresh_all()
        QApplication.instance().installEventFilter(self)

    def build_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central); root.setContentsMargins(14, 14, 14, 14); root.setSpacing(10)
        self.title_label = QLabel("大阪工場倉庫"); self.title_label.setStyleSheet("font:700 18px 'Yu Gothic UI', 'Segoe UI'; color:#7fd0ff;")
        self.summary_label = QLabel(); self.summary_label.setStyleSheet("color:#89a4c2;"); self.summary_label.setWordWrap(True)
        self.new_button = QPushButton("新規登録"); self.new_button.clicked.connect(self.open_registration)
        self.add_note_button = QPushButton("メモ追加"); self.add_note_button.clicked.connect(self.open_map_note_dialog)
        self.blocked_mode_button = QPushButton("置けないマス"); self.blocked_mode_button.setCheckable(True); self.blocked_mode_button.toggled.connect(self.set_blocked_edit_mode)
        self.blocked_mode_button.setObjectName("blockedModeButton")
        self.blocked_mode_button.setMinimumWidth(104)
        self.edit_button = QPushButton("明細編集"); self.edit_button.clicked.connect(self.edit_selected_pallet)
        self.edit_button.setMinimumWidth(86)
        self.ship_button = QPushButton("出庫"); self.ship_button.clicked.connect(self.ship_selected_pallet)
        self.ship_button.setMinimumWidth(64)
        self.transfer_button = QPushButton("積み替え"); self.transfer_button.clicked.connect(self.transfer_selected_pallet)
        self.transfer_button.setMinimumWidth(76)
        self.unstack_button = QPushButton("列を解除"); self.unstack_button.clicked.connect(self.unstack_selected_pallet)
        self.stack_up_button = QPushButton("段を上げる"); self.stack_up_button.clicked.connect(lambda: self.adjust_selected_stack(1))
        self.stack_down_button = QPushButton("段を下げる"); self.stack_down_button.clicked.connect(lambda: self.adjust_selected_stack(-1))
        self.rotate_button = QPushButton("向き変更"); self.rotate_button.clicked.connect(self.rotate_selected_pallet)
        self.color_notes_button = QPushButton("色説明設定"); self.color_notes_button.clicked.connect(self.open_color_label_notes_dialog)
        self.undo_move_button = QPushButton("戻る"); self.undo_move_button.clicked.connect(self.undo_last_move)
        self.redo_move_button = QPushButton("進む"); self.redo_move_button.clicked.connect(self.redo_last_move)
        self.undo_move_button.setObjectName("viewHistoryButton")
        self.redo_move_button.setObjectName("viewHistoryButton")
        self.undo_move_button.setToolTip("直前のパレットまたはメモ移動を戻す")
        self.redo_move_button.setToolTip("戻したパレットまたはメモ移動をやり直す")
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("例: 39 LL 10 A"); self.search_input.setClearButtonEnabled(True); self.search_input.textChanged.connect(self.refresh_all)
        self.copy_inventory_button = QPushButton("一覧コピー"); self.copy_inventory_button.clicked.connect(self.copy_inventory_table)
        self.copy_shipment_button = QPushButton("一覧コピー"); self.copy_shipment_button.clicked.connect(self.copy_shipment_table)
        self.export_inventory_button = QPushButton("棚卸データ出力"); self.export_inventory_button.clicked.connect(self.copy_inventory_summary)
        self.inventory_columns_button = QPushButton("表示項目設定"); self.inventory_columns_button.clicked.connect(self.open_inventory_column_menu)
        self.restore_shipment_button = QPushButton("復元"); self.restore_shipment_button.clicked.connect(self.restore_selected_shipments)
        self.delete_shipment_button = QPushButton("履歴削除"); self.delete_shipment_button.clicked.connect(self.delete_selected_shipments)
        self.export_button = QPushButton("Export"); self.export_button.clicked.connect(self.export_data)
        self.import_button = QPushButton("Import"); self.import_button.clicked.connect(self.import_data)
        self.clear_selection_button = QPushButton("選択解除"); self.clear_selection_button.clicked.connect(self.clear_selection)
        self.action_buttons = [self.new_button, self.add_note_button, self.blocked_mode_button, self.edit_button, self.ship_button, self.transfer_button, self.unstack_button, self.stack_up_button, self.stack_down_button, self.rotate_button, self.color_notes_button, self.export_button, self.import_button]
        for button in self.action_buttons: button.setMinimumHeight(40)
        self.search_input.setMinimumHeight(40)
        self.copy_inventory_button.setMinimumHeight(40)
        self.copy_shipment_button.setMinimumHeight(40)
        self.inventory_columns_button.setMinimumHeight(40)
        title_row = QHBoxLayout(); title_row.addWidget(self.title_label); title_row.addWidget(self.summary_label, 1)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for widget in [self.new_button, self.add_note_button, self.blocked_mode_button]:
            action_row.addWidget(widget)
        action_row.addSpacing(18)
        for widget in [self.edit_button, self.ship_button, self.transfer_button, self.unstack_button, self.stack_down_button, self.stack_up_button, self.rotate_button]:
            action_row.addWidget(widget)
        action_row.addSpacing(14)
        action_row.addWidget(self.color_notes_button)
        action_row.addStretch(1)
        action_row.addWidget(self.export_button)
        action_row.addWidget(self.import_button)
        utility_row = QHBoxLayout(); utility_row.addWidget(self.search_input, 1); utility_row.addWidget(self.inventory_columns_button); utility_row.addWidget(self.copy_inventory_button); utility_row.addWidget(self.copy_shipment_button); utility_row.addWidget(self.export_inventory_button); utility_row.addWidget(self.restore_shipment_button); utility_row.addWidget(self.delete_shipment_button)
        header_shell = QVBoxLayout(); header_shell.setSpacing(8); header_shell.addLayout(title_row); header_shell.addLayout(action_row); header_shell.addLayout(utility_row); root.addLayout(header_shell)
        self.map_container = QWidget(); root.addWidget(self.map_container, 1)
        map_layout = QVBoxLayout(self.map_container); map_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(); map_layout.addWidget(self.tabs, 1)
        self.view_history_controls = QWidget()
        view_history_layout = QHBoxLayout(self.view_history_controls)
        view_history_layout.setContentsMargins(6, 2, 6, 2)
        view_history_layout.setSpacing(6)
        self.undo_move_button.setMinimumSize(72, 38)
        self.redo_move_button.setMinimumSize(72, 38)
        view_history_layout.addWidget(self.undo_move_button)
        view_history_layout.addWidget(self.redo_move_button)
        self.tabs.setCornerWidget(self.view_history_controls, Qt.TopRightCorner)
        self.tabs.currentChanged.connect(self.handle_tab_changed)
        self.detail_frame = QFrame(self.map_container); self.detail_frame.hide()
        self.detail_frame.installEventFilter(self)
        detail_root = QVBoxLayout()
        detail_root.setContentsMargins(10, 8, 10, 8)
        detail_root.setSpacing(6)
        detail_layout = QHBoxLayout()
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        self.detail_frame.setLayout(detail_root)
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
        detail_root.addLayout(detail_layout, 1)
        self.detail_resize_handle = QFrame()
        self.detail_resize_handle.setObjectName("detailResizeHandle")
        self.detail_resize_handle.setFixedSize(18, 18)
        self.detail_resize_handle.setCursor(Qt.SizeFDiagCursor)
        self.detail_resize_handle.installEventFilter(self)
        resize_row = QHBoxLayout()
        resize_row.setContentsMargins(0, 0, 0, 0)
        resize_row.addStretch(1)
        resize_row.addWidget(self.detail_resize_handle)
        detail_root.addLayout(resize_row)
        self.top_map = TopMapWidget(self.store); self.top_map.palletSelected.connect(self.select_pallet); self.top_map.palletMoved.connect(self.move_pallet); self.top_map.selectionCleared.connect(self.clear_selection); self.top_map.palletDoubleClicked.connect(self.open_selected_pallet_editor); self.top_map.blockedLocationToggled.connect(self.set_blocked_location_with_validation); self.top_map.palletContextRequested.connect(self.open_pallet_context_menu); self.top_map.mapNoteSelected.connect(self.select_map_note); self.top_map.mapNoteDoubleClicked.connect(self.open_map_note_editor); self.top_map.mapNoteMoved.connect(self.move_map_note); self.top_map.mapNoteContextRequested.connect(self.open_map_note_context_menu); self.top_map.dragStarted.connect(self.hide_detail_for_drag); self.tabs.addTab(self.wrap_widget(self.top_map), "真上")
        self.iso_map = IsometricMapWidget(self.store); self.iso_map.palletSelected.connect(self.select_pallet); self.iso_map.selectionCleared.connect(self.clear_selection); self.iso_map.palletDoubleClicked.connect(self.open_selected_pallet_editor); self.iso_map.palletContextRequested.connect(self.open_pallet_context_menu)
        self.iso_rotate_button = QPushButton("視点90°")
        self.iso_rotate_button.setParent(self.iso_map)
        self.iso_rotate_button.clicked.connect(self.rotate_iso_view)
        self.iso_rotate_button.raise_()
        self.tabs.addTab(self.wrap_widget(self.iso_map), "45度ビュー")
        self.inventory_table = QTableWidget(0, len(self.INVENTORY_COLUMNS))
        self.inventory_table.setObjectName("inventoryTable")
        self.inventory_table.setHorizontalHeaderLabels([label for _key, label, _width in self.INVENTORY_COLUMNS])
        inventory_header = TouchFriendlyHeaderView(Qt.Horizontal, self.inventory_table)
        self.inventory_table.setHorizontalHeader(inventory_header)
        self.inventory_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.inventory_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.inventory_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inventory_table.setShowGrid(True)
        self.inventory_table.setGridStyle(Qt.SolidLine)
        self.inventory_table.setAlternatingRowColors(True)
        self.inventory_table.setMouseTracking(True)
        self.inventory_table.viewport().installEventFilter(self)
        self.inventory_table.horizontalHeader().setSectionsMovable(False)
        self.inventory_table.horizontalHeader().setSectionsClickable(True)
        self.inventory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.inventory_table.horizontalHeader().setMinimumSectionSize(72)
        self.inventory_table.horizontalHeader().setMinimumHeight(42)
        self.inventory_table.verticalHeader().setDefaultSectionSize(36)
        self.configure_table_for_touch(self.inventory_table)
        for col, (_key, _label, width) in enumerate(self.INVENTORY_COLUMNS):
            self.inventory_table.setColumnWidth(col, width)
        self.inventory_hint = QLabel("列幅は項目名の境目をドラッグで調整できます。ダブルクリックで真上ビューの位置を確認できます。")
        self.inventory_hint.setObjectName("inventoryHint")
        self.inventory_hint.setWordWrap(True)
        inventory_shell = QWidget()
        inventory_layout = QVBoxLayout(inventory_shell)
        inventory_layout.setContentsMargins(8, 8, 8, 8)
        inventory_layout.setSpacing(6)
        inventory_layout.addWidget(self.inventory_hint)
        inventory_layout.addWidget(self.inventory_table, 1)
        self.tabs.addTab(inventory_shell, "在庫一覧")
        self.inventory_table.horizontalHeader().sectionClicked.connect(self.handle_inventory_header_click)
        self.inventory_table.cellDoubleClicked.connect(self.select_pallet_from_inventory_table)
        self.inventory_table.cellClicked.connect(lambda row, col: self.show_table_cell_tooltip(self.inventory_table, row, col))
        self.inventory_table.cellPressed.connect(lambda row, col: QTimer.singleShot(0, lambda: self.show_table_cell_popup_if_elided(self.inventory_table, row, col)))
        self.inventory_table.itemPressed.connect(lambda item: QTimer.singleShot(0, lambda: self.show_table_item_popup(self.inventory_table, item)))
        self.inventory_table.currentCellChanged.connect(lambda _row, _col, _prev_row, _prev_col: self.hide_table_popup())
        self.inventory_table.itemSelectionChanged.connect(self.hide_table_popup)
        self.inventory_table.currentItemChanged.connect(lambda current, _previous: QTimer.singleShot(0, lambda: self.show_table_item_popup(self.inventory_table, current)))
        self.inventory_table.itemEntered.connect(lambda item: self.show_table_item_tooltip(self.inventory_table, item))
        self.inventory_table.currentItemChanged.connect(lambda current, _previous: self.show_table_item_tooltip(self.inventory_table, current))
        self.shipment_table = QTableWidget(0, len(self.SHIPMENT_COLUMNS)); self.shipment_table.setObjectName("shipmentTable"); self.shipment_table.setHorizontalHeaderLabels([label for _key, label, _width in self.SHIPMENT_COLUMNS])
        shipment_header = TouchFriendlyHeaderView(Qt.Horizontal, self.shipment_table)
        self.shipment_table.setHorizontalHeader(shipment_header)
        self.shipment_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.shipment_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.shipment_table.setShowGrid(True)
        self.shipment_table.setGridStyle(Qt.SolidLine)
        self.shipment_table.setAlternatingRowColors(True)
        self.shipment_table.setMouseTracking(True)
        self.shipment_table.viewport().installEventFilter(self)
        self.shipment_table.horizontalHeader().setSectionsMovable(False)
        self.shipment_table.horizontalHeader().setSectionsClickable(True)
        self.shipment_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.shipment_table.horizontalHeader().setMinimumSectionSize(72)
        self.shipment_table.horizontalHeader().setMinimumHeight(42)
        self.shipment_table.verticalHeader().setDefaultSectionSize(36)
        self.configure_table_for_touch(self.shipment_table)
        self.shipment_table.setContextMenuPolicy(Qt.CustomContextMenu); self.shipment_table.customContextMenuRequested.connect(self.open_shipment_context_menu)
        for col, (_key, _label, width) in enumerate(self.SHIPMENT_COLUMNS):
            self.shipment_table.setColumnWidth(col, width)
        self.shipment_table.horizontalHeader().sectionClicked.connect(self.handle_shipment_header_click)
        self.shipment_table.cellClicked.connect(lambda row, col: self.show_table_cell_tooltip(self.shipment_table, row, col))
        self.shipment_table.cellPressed.connect(lambda row, col: QTimer.singleShot(0, lambda: self.show_table_cell_popup_if_elided(self.shipment_table, row, col)))
        self.shipment_table.itemPressed.connect(lambda item: QTimer.singleShot(0, lambda: self.show_table_item_popup(self.shipment_table, item)))
        self.shipment_table.currentCellChanged.connect(lambda _row, _col, _prev_row, _prev_col: self.hide_table_popup())
        self.shipment_table.itemSelectionChanged.connect(self.hide_table_popup)
        self.shipment_table.currentItemChanged.connect(lambda current, _previous: QTimer.singleShot(0, lambda: self.show_table_item_popup(self.shipment_table, current)))
        self.shipment_table.itemEntered.connect(lambda item: self.show_table_item_tooltip(self.shipment_table, item))
        self.shipment_table.currentItemChanged.connect(lambda current, _previous: self.show_table_item_tooltip(self.shipment_table, current))
        self.tabs.addTab(self.wrap_widget(self.shipment_table), "出庫一覧")
        self.help_page = self.build_help_page(); self.help_tab_widget = self.wrap_widget(self.help_page); self.tabs.addTab(self.help_tab_widget, "ヘルプ")
        self.update_tab_visuals()
        self.apply_responsive_layout()
        self.handle_tab_changed(self.tabs.currentIndex())
        self.update_detail_overlay_geometry()

    def build_help_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        enable_swipe_scroll(scroll)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        sections = [
            ("画面の見方", "・真上ビューと45度ビューを切り替えられます。\n・真上ビューは配置確認、選択、ドラッグ移動に使います。\n・45度ビューは積み重なりや高さ方向の確認に使います。\n・使用率は通路列 B / E / F / J を除いた通常置場を基準に計算します。\n・通路以外の通常置場が埋まると100%です。\n・通路列にパレットを置くと100%を超えます。\n・置けないマスは使用済み扱いで使用率に含まれます。\n・メモは在庫ではないため、使用率や高さ計算には含まれません。"),
            ("通路列", "・B / E / F / J は通路列です。\n・列ラベルは B(通路) のように表示されます。\n・通路にも配置はできますが、本来置きたくない場所として扱います。\n・通路列は置けないマス設定とは別管理です。"),
            ("新規登録", "・新規登録から通常パレットを登録します。\n・パレット番号、入庫日、向き、色、明細を入力します。\n・明細は品番、サイズ、厚み、加工 / 裏表、グレード、枚数、Lot、備考を入力します。\n・Lotは任意入力です。未入力でも登録できます。\n・明細を追加してからOKを押すと登録されます。\n・登録後は未配置エリアに置かれます。\n・真上ビューでドラッグして実際の場所へ配置します。\n・アプリ起動中は、直前に新規登録した最後の明細が次回登録時の初期値になります。\n・アプリ再起動後は標準値 #39 / LL / 10 / S/S / A / 80 に戻ります。\n・備考、パレット番号、入庫日、場所、登録済み明細リストは引き継ぎません。"),
            ("入力ルール", "・品番とパレット番号は、全角英数字を半角へ変換し、英字を大文字へ変換します。\n・加工 / 裏表は日本語も入力できます。英数字は半角大文字へ変換します。\n・加工 / 裏表の ￥、\\、。、？、? は / に変換します。\n・厚みは 3-3.5 や 3~3.5 のような範囲表記も入力できます。\n・高さ計算では厚み範囲の最大値を使います。\n・枚数は数字のみ入力できます。\n・Lotは全角英数字を半角へ変換し、英字を大文字へ変換します。前後の空白は削除します。\n・備考は日本語も入力できます。"),
            ("メモ追加", "・メモ追加から地図メモを作成できます。\n・空パレット、明細不明、スライス余り、一時置き、確認待ちなど、通常明細にしづらいものに使います。\n・メモは在庫集計、高さ計算、使用率、出庫履歴には含まれません。\n・メモ本文は複数行入力できます。\n・本文の1行目がタイトルとして地図や詳細表示に出ます。\n・メモは通常パレットと重ねて置けます。\n・メモを削除する場合は出庫ではなく撤去します。"),
            ("移動", "・真上ビューでパレットやメモをドラッグして移動します。\n・ドラッグ中は A01、B12 のような現在の候補座標が表示されます。\n・同じマスに置くと段積みになります。\n・段積みは右上方向に少しずらして表示されます。\n・間違えて移動した場合は戻るで直前の移動を戻せます。\n・進むで戻した移動をやり直せます。\n・戻る / 進むは、アプリ起動中の真上ビューでの移動操作だけが対象です。\n・新規登録、編集、出庫、削除、撤去は戻る / 進むの対象外です。"),
            ("選択・編集", "・パレットをクリックすると内容が表示されます。\n・メモをクリックするとメモ内容が表示されます。\n・何もない場所をクリックすると選択を解除できます。\n・パレットは明細編集で編集できます。\n・メモを選択している場合は、同じボタンでメモを編集できます。\n・パレットやメモはダブルクリックでも編集できます。\n・右クリックメニューから編集、出庫、撤去などの操作を選べる項目があります。"),
            ("出庫", "・パレットを選択して出庫できます。\n・出庫したパレットは在庫から外れ、出庫一覧へ移ります。\n・積み重ねパレットを出庫した後、同じマスに残りがあれば自動で同じマスのパレットを選択します。\n・同じ場所のパレットを連続して出庫しやすくしています。\n・メモは出庫対象ではありません。削除する場合は撤去します。"),
            ("在庫一覧", "・現在登録されている在庫パレットを一覧で確認できます。\n・Lotは備考の前の独立した列に表示されます。\n・検索できます。Lotを含む表示項目に対して部分一致で探せます。\n・各項目の見出しを押すと並び替えできます。\n・品番等が同じでもLotが異なる明細は別在庫として表示されます。\n・タブレットではスクロールバーやスワイプで操作できます。\n・行上のスワイプで複数行を選択できます。\n・選択した在庫は編集、出庫、地図上の選択対象になります。\n・行をダブルクリックすると、該当パレットを地図上で確認できます。"),
            ("在庫一覧の出力", "■ 一覧コピー\n・在庫一覧に表示されている内容をそのままクリップボードへコピーします。\n・Excelへの貼り付けや内容確認に使います。\n・同じアイテムの数量集計は行いません。\n・一覧表示に近い形式でコピーします。\n\n■ 棚卸データ出力\n・棚卸表用の集計データをクリップボードへコピーします。\n・同じアイテムは数量を合計してまとめます。\n・棚卸表へ貼り付ける用途です。\n・一覧コピーとは用途が異なります。"),
            ("出庫一覧", "・出庫済みの履歴を確認できます。\n・出庫日は先頭列に表示されます。\n・検索できます。表示項目に対して部分一致で探せます。\n・各項目の見出しを押すと並び替えできます。\n・一覧コピーで、現在表示中の出庫一覧をヘッダー付きのタブ区切り形式でコピーできます。\n・Lotは備考とは別の独立した列でコピーされます。\n・操作感は在庫一覧とほぼ同じです。\n・在庫一覧と出庫一覧は選択色が異なるため見分けやすくなっています。\n・出庫履歴は復元や削除ができます。復元したパレットは未配置エリアに置かれます。"),
            ("置けないマス", "・置けないマスから配置できない場所を設定できます。\n・設備、柱、作業スペースなどを登録する用途です。\n・使用率計算では使用済み扱いになります。\n・通路列とは別管理です。\n・通路列を置けないマスにしても、通路列分は使用率の分母にも分子にも入りません。"),
            ("色説明設定", "■ 固定説明色\n・赤 [#38]\n・青 [#39]\n・黄 [#40]\n・緑 [#45]\n・桃 [#50]\n・紫 [C/C]\n・その他 [混在 / その他]\n・上記は自動判定や運用ルールと関係するため変更できません。\n\n■ 編集可能色\n・紺 [空パレット]\n・橙 [スライス余り]\n・青緑 [明細不明]\n・その他の色\n・色説明設定から説明を変更できます。\n・説明を空欄にすると色名のみ表示されます。\n・説明はパレット登録 / 編集とメモ登録 / 編集の色選択に反映されます。"),
            ("Export / Import", "・Export はデータファイルを書き出す機能です。\n・Import は書き出したデータを読み込む機能です。\n・普段の運用では基本的に使用しません。\n・PC移行、バックアップ、データ復元時などに利用します。\n・Import は現在のデータを変更するため注意して使用してください。"),
            ("保存とバックアップ", "・登録、編集、メモ追加、メモ編集、移動完了、出庫確定、撤去など、データ変更が確定した時に保存します。\n・ドラッグ中は保存せず、移動確定後に保存します。\n・保存に失敗した場合は再試行または別名保存を選べます。\n・日次バックアップは backups フォルダへ自動保存されます。"),
            ("困った時", "・位置や段順が変に見える場合は、まず真上ビューでロケーションと積み段を確認してください。\n・直前の移動ミスは戻るで戻せます。\n・データ読込エラーや保存エラーは store-error.log に記録されます。\n・本体データとバックアップの両方が読めない場合は、復旧ダイアログを表示して起動を停止します。"),
        ]

        title = QLabel("操作ヘルプ")
        title.setStyleSheet("font:700 18px 'Yu Gothic UI'; color:#dff6ff;")
        layout.addWidget(title)
        for heading, text in sections:
            card = QFrame()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(8)
            heading_label = QLabel(heading)
            heading_label.setStyleSheet("font:700 13pt 'Yu Gothic UI', 'Segoe UI'; color:#7fd0ff;")
            body_label = QLabel(text)
            body_label.setTextFormat(Qt.RichText if "<" in text and ">" in text else Qt.PlainText)
            body_label.setWordWrap(True)
            body_label.setStyleSheet("color:#e7f3ff; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; line-height:1.8;")
            card.setStyleSheet("QFrame { background:#0d1726; border:1px solid #2b455f; border-radius:10px; }")
            card_layout.addWidget(heading_label)
            card_layout.addWidget(body_label)
            layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def open_help_tab(self) -> None:
        if hasattr(self, "tabs"):
            self.tabs.setCurrentWidget(self.help_tab_widget)
        if isinstance(self.help_page, QScrollArea):
            self.help_page.verticalScrollBar().setValue(0)

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
        current_note = self.store.get_map_note(self.current_note_id or "") if hasattr(self, "store") else None
        if current_note is not None:
            color = QColor(COLOR_PRESETS.get(current_note.color_key, COLOR_PRESETS["YELLOW"])[1] or "#FFC34D")
            border_color = color.name()
            soft = QColor(color)
            soft.setAlpha(68)
            self.detail_frame.setStyleSheet(f"background:{soft.name(QColor.HexArgb)}; border:2px solid {border_color}; border-radius:8px;")
            self.stack_detail_selector.setVisible(False)
            self.stack_detail_pages.setStyleSheet(
                f"QLabel {{ background:transparent; color:#fff7d6; font:{'10pt' if narrow else ('11pt' if compact else '11.5pt')} 'Yu Gothic UI', 'Segoe UI'; }}"
            )
            return
        current_pallet = self.current_stack_detail_pallet()
        color = pallet_color(current_pallet) if isinstance(current_pallet, PalletRecord) else QColor("#f0c860")
        border_color = color.name()
        soft = QColor(color)
        soft.setAlpha(68)
        self.detail_frame.setStyleSheet(f"background:{soft.name(QColor.HexArgb)}; border:2px solid {border_color}; border-radius:8px;")
        self.stack_detail_selector.setStyleSheet(
            f"QListWidget#stackDetailSelector {{ background:transparent; border:none; outline:none; padding:0; }}"
            f"QListWidget#stackDetailSelector::item {{ background:#243141; color:#c8d7ea; padding:3px 0; margin:0 0 2px 0; border-radius:5px; text-align:center; font-weight:700; min-height:18px; }}"
            f"QListWidget#stackDetailSelector::item:selected {{ background:{border_color}; color:#10161e; }}"
        )
        self.stack_detail_pages.setStyleSheet(
            f"QLabel {{ background:transparent; color:#fff7d6; font:{'10pt' if narrow else ('11pt' if compact else '11.5pt')} 'Yu Gothic UI', 'Segoe UI'; }}"
        )

    def update_tab_visuals(self) -> None:
        tab_bar = self.tabs.tabBar()
        inventory_color = QColor("#39d98a")
        shipment_color = QColor("#ff8a80")
        help_color = QColor("#ffd37a")
        tab_bar.setTabTextColor(0, QColor("#88c3f0"))
        tab_bar.setTabTextColor(1, QColor("#88c3f0"))
        tab_bar.setTabTextColor(2, inventory_color)
        tab_bar.setTabTextColor(3, shipment_color)
        tab_bar.setTabTextColor(4, help_color)
        self.tabs.setTabIcon(2, solid_circle_icon(inventory_color.name()))
        self.tabs.setTabIcon(3, solid_circle_icon(shipment_color.name()))
        self.tabs.setTabIcon(4, solid_circle_icon(help_color.name()))

    def handle_tab_changed(self, _index: int) -> None:
        is_inventory = self.tabs.currentIndex() == 2
        is_shipment = self.tabs.currentIndex() == 3
        is_help = hasattr(self, "help_tab_widget") and self.tabs.currentWidget() == self.help_tab_widget
        self.search_input.setVisible(is_inventory or is_shipment)
        self.inventory_columns_button.setVisible(is_inventory)
        self.copy_inventory_button.setVisible(is_inventory)
        self.copy_shipment_button.setVisible(is_shipment)
        self.export_inventory_button.setVisible(is_inventory)
        self.restore_shipment_button.setVisible(is_shipment)
        self.delete_shipment_button.setVisible(is_shipment)
        if hasattr(self, "iso_rotate_button"):
            self.iso_rotate_button.setVisible(self.tabs.currentIndex() == 1)
        if is_help and isinstance(self.help_page, QScrollArea):
            self.help_page.verticalScrollBar().setValue(0)
        self.update_detail_overlay_geometry()

    def handle_stack_detail_tab_changed(self, _index: int) -> None:
        if hasattr(self, "stack_detail_pages") and self.stack_detail_pages.currentIndex() != _index:
            self.stack_detail_pages.setCurrentIndex(_index)
        current_pallet = self.current_stack_detail_pallet()
        if current_pallet is not None:
            self.current_pallet_number = current_pallet.pallet_number
            self.current_note_id = None
            self.top_map.selected_pallet = current_pallet.pallet_number
            self.top_map.selected_note = None
            self.iso_map.selected_pallet = current_pallet.pallet_number
            self.top_map.update()
            self.iso_map.update()
        self.update_stack_detail_style()
        self.update_detail_overlay_geometry()

    def configure_table_for_touch(self, table: QTableWidget) -> None:
        table.viewport().setAttribute(Qt.WA_AcceptTouchEvents, False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setAutoScroll(False)
        table.setDragDropMode(QAbstractItemView.NoDragDrop)

    def table_for_viewport(self, source) -> Optional[QTableWidget]:
        for table in (getattr(self, "inventory_table", None), getattr(self, "shipment_table", None)):
            if table is not None and source == table.viewport():
                return table
        return None

    def enable_table_multi_select_from_long_press(self) -> None:
        table = self.table_long_press_table
        if table is None:
            return
        row = table.rowAt(self.table_long_press_point.y())
        if row < 0:
            return
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_multi_select_mode.add(table)
        self.add_table_row_to_selection(table, row)
        QToolTip.showText(table.viewport().mapToGlobal(self.table_long_press_point), "複数選択モード", table)
        self.table_long_press_table = None

    def add_table_row_to_selection(self, table: QTableWidget, row: int) -> None:
        if row < 0 or row >= table.rowCount() or table.columnCount() <= 0:
            return
        table.setCurrentCell(row, max(0, table.currentColumn()))
        index = table.model().index(row, 0)
        table.selectionModel().select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def add_table_row_at_point_to_selection(self, table: QTableWidget, point: QPoint) -> None:
        self.add_table_row_to_selection(table, table.rowAt(point.y()))

    def disable_table_multi_select(self, table: Optional[QTableWidget] = None) -> None:
        tables = [table] if table is not None else list(self.table_multi_select_mode)
        for target in tables:
            if target is not None:
                target.setSelectionMode(QAbstractItemView.ExtendedSelection)
                self.table_multi_select_mode.discard(target)
        self.table_long_press_timer.stop()
        self.table_long_press_table = None

    def eventFilter(self, source, event) -> bool:
        detail_frame = getattr(self, "detail_frame", None)
        detail_resize_handle = getattr(self, "detail_resize_handle", None)
        stack_detail_pages = getattr(self, "stack_detail_pages", None)
        stack_detail_selector = getattr(self, "stack_detail_selector", None)
        inventory_table = getattr(self, "inventory_table", None)
        shipment_table = getattr(self, "shipment_table", None)
        map_container = getattr(self, "map_container", None)
        tabs = getattr(self, "tabs", None)
        current_page = stack_detail_pages.currentWidget() if stack_detail_pages is not None else None
        current_label = current_page.findChild(QLabel) if current_page is not None else None
        current_scroll = current_page.findChild(QScrollArea) if current_page is not None else None
        draggable_sources = {detail_frame, stack_detail_pages, current_page, current_label}
        if current_scroll is not None:
            draggable_sources.add(current_scroll)
            draggable_sources.add(current_scroll.viewport())
        popup_tables = {}
        if inventory_table is not None:
            popup_tables[inventory_table.viewport()] = inventory_table
        if shipment_table is not None:
            popup_tables[shipment_table.viewport()] = shipment_table
        popup_table = popup_tables.get(source)
        touch_table = self.table_for_viewport(source)
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.disable_table_multi_select()
        if touch_table is not None:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                point = event.position().toPoint()
                self.table_press_point = point
                self.table_press_moved = False
                touch_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
                self.table_long_press_timer.stop()
                self.table_long_press_table = None
                if touch_table.rowAt(point.y()) < 0:
                    touch_table.clearSelection()
            elif event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
                point = event.position().toPoint()
                if (point - self.table_press_point).manhattanLength() > 12:
                    self.table_press_moved = True
                    self.hide_table_popup()
            elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self.table_long_press_timer.stop()
                self.table_long_press_table = None
            elif event.type() == QEvent.TouchBegin:
                points = event.points()
                if points:
                    point = points[0].position().toPoint()
                    self.table_press_point = point
                    self.table_press_moved = False
                    touch_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
                    self.add_table_row_at_point_to_selection(touch_table, point)
            elif event.type() == QEvent.TouchUpdate:
                points = event.points()
                if points:
                    point = points[0].position().toPoint()
                    if (point - self.table_press_point).manhattanLength() > 12:
                        self.table_press_moved = True
                        self.hide_table_popup()
                    self.add_table_row_at_point_to_selection(touch_table, point)
                return True
            elif event.type() == QEvent.TouchEnd:
                self.table_long_press_timer.stop()
                self.table_long_press_table = None
        if event.type() in (QEvent.MouseButtonPress, QEvent.TouchBegin):
            allowed_sources = set(popup_tables.keys())
            allowed_sources.update({inventory_table, shipment_table, self.cell_popup})
            if source not in allowed_sources:
                self.hide_table_popup()
        if popup_table is not None:
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and not self.table_press_moved:
                point = event.position().toPoint()
                self.schedule_table_popup_from_point(popup_table, point)
            elif event.type() == QEvent.TouchEnd and not self.table_press_moved:
                points = event.points()
                if points:
                    point = points[0].position().toPoint()
                    self.schedule_table_popup_from_point(popup_table, point)
        if event.type() == QEvent.MouseButtonPress and source == detail_resize_handle and event.button() == Qt.LeftButton:
            self.detail_resize_active = True
            self.detail_resize_origin = event.globalPosition().toPoint()
            if detail_frame is not None:
                self.detail_resize_start_size = (detail_frame.width(), detail_frame.height())
            return True
        if event.type() == QEvent.MouseMove and self.detail_resize_active and source == detail_resize_handle and detail_frame is not None and map_container is not None and tabs is not None and (event.buttons() & Qt.LeftButton):
            start_width, start_height = self.detail_resize_start_size or (detail_frame.width(), detail_frame.height())
            delta = event.globalPosition().toPoint() - self.detail_resize_origin
            min_width = 260
            min_height = 120
            max_width = max(min_width, map_container.width() - detail_frame.x() - 14)
            max_height = max(min_height, map_container.height() - detail_frame.y() - 14)
            new_width = max(min_width, min(max_width, start_width + delta.x()))
            new_height = max(min_height, min(max_height, start_height + delta.y()))
            detail_frame.resize(new_width, new_height)
            self.detail_frame_manual_size = (new_width, new_height)
            return True
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
            self.detail_resize_active = False
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
                if self.current_note_id and self.store.get_map_note(self.current_note_id) is not None:
                    self.open_map_note_editor(self.current_note_id)
                    return True
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
        self.title_label.setStyleSheet(f"font:700 {'16' if compact else '18'}px 'Yu Gothic UI', 'Segoe UI'; color:#7fd0ff;")
        self.summary_label.setStyleSheet(f"color:#89a4c2; font:{'10pt' if compact else '11pt'} 'Yu Gothic UI', 'Segoe UI';")
        text_map = {
            self.new_button: "新規" if compact else "新規登録",
            self.add_note_button: "メモ" if compact else "メモ追加",
            self.blocked_mode_button: "置けないマス",
            self.edit_button: ("メモ" if compact else "メモ編集") if self.current_note_id else ("編集" if compact else "明細編集"),
            self.ship_button: "出庫",
            self.transfer_button: "積替" if compact else "積み替え",
            self.unstack_button: "解除" if compact else "列を解除",
            self.stack_up_button: "上げる" if compact else "段を上げる",
            self.stack_down_button: "下げる" if compact else "段を下げる",
            self.rotate_button: "向き" if compact else "向き変更",
            self.color_notes_button: "色説明" if compact else "色説明設定",
            self.export_button: "出力" if compact else "Export",
            self.import_button: "読込" if compact else "Import",
        }
        for button in self.action_buttons:
            button.setMinimumHeight(button_height)
            button.setText(text_map.get(button, button.text()))
        self.blocked_mode_button.setMinimumWidth(96 if compact else 104)
        self.edit_button.setMinimumWidth(72 if compact else 86)
        self.ship_button.setMinimumWidth(60 if compact else 64)
        self.transfer_button.setMinimumWidth(66 if compact else 76)
        history_button_width = 64 if compact else 72
        history_button_height = 34 if compact else 38
        self.undo_move_button.setMinimumSize(history_button_width, history_button_height)
        self.redo_move_button.setMinimumSize(history_button_width, history_button_height)
        self.search_input.setMinimumHeight(max(combo_height, 40))
        self.inventory_columns_button.setMinimumHeight(combo_height)
        self.copy_inventory_button.setMinimumHeight(combo_height)
        self.copy_shipment_button.setMinimumHeight(combo_height)
        self.export_inventory_button.setMinimumHeight(combo_height)
        self.restore_shipment_button.setMinimumHeight(combo_height)
        self.delete_shipment_button.setMinimumHeight(combo_height)
        self.inventory_columns_button.setText("項目" if compact else "表示項目設定")
        self.copy_inventory_button.setText("コピー" if compact else "一覧コピー")
        self.copy_shipment_button.setText("コピー" if compact else "一覧コピー")
        self.export_inventory_button.setText("棚卸出力" if compact else "棚卸データ出力")
        self.search_input.setPlaceholderText("検索" if narrow else "例: 39 LL 10 A")
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
        current_note = self.store.get_map_note(self.current_note_id or "") if hasattr(self, "store") else None
        if current_pallet is None and current_note is None:
            self.detail_frame.hide()
            return
        active_widget = self.active_map_widget()
        if active_widget is None:
            self.detail_frame.hide()
            return
        if current_note is not None:
            rect_map = getattr(active_widget, "note_rects", {})
            anchor_rect = rect_map.get(current_note.note_id)
        else:
            rect_map = getattr(active_widget, "pallet_rects", {})
            anchor_rect = rect_map.get(current_pallet.pallet_number)
        if anchor_rect is None:
            self.detail_frame.hide()
            return
        widget_top_left = active_widget.mapTo(self.map_container, QPoint(0, 0))
        anchor_left = widget_top_left.x() + anchor_rect.right() + 12
        anchor_top = widget_top_left.y() + anchor_rect.top()
        current_page = self.stack_detail_pages.currentWidget()
        detail_label = current_page.findChild(QLabel) if current_page is not None else None
        line_count = max(1, (detail_label.text().count("\n") + 1) if detail_label is not None else 4)
        line_height = detail_label.fontMetrics().lineSpacing() if detail_label is not None else 16
        selector_width = self.stack_detail_selector.width() if self.stack_detail_selector.isVisible() else 0
        top_limit = self.tabs.tabBar().height() + 12
        available_height = max(140, self.map_container.height() - top_limit - 14)
        preferred_height = max(120, 28 + (line_count * line_height))
        default_width = 360 if self.width() >= 1200 else 310
        if self.detail_frame_manual_size is not None:
            manual_width, manual_height = self.detail_frame_manual_size
            width = max(260, min(manual_width, max(260, self.map_container.width() - selector_width - 24)))
            detail_height = max(120, min(manual_height, available_height))
        else:
            width = default_width
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

    def hide_detail_for_drag(self) -> None:
        if hasattr(self, "detail_frame"):
            self.detail_frame.hide()
        QToolTip.hideText()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_responsive_layout()
        self.update_detail_overlay_geometry()

    def apply_theme(self) -> None:
        self.setStyleSheet("""
        QWidget { background:#091522; color:#e7f3ff; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; }
        QFrame { background:#0f1d2c; border:1px solid #163450; border-radius:8px; }
        QLineEdit, QComboBox, QTableWidget { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:7px; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; }
        QSpinBox, QAbstractSpinBox { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:5px 30px 5px 6px; min-height:38px; font:11.5pt 'Yu Gothic UI', 'Segoe UI'; }
        QSpinBox::up-button, QAbstractSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width:24px;
            height:17px;
            background:#163450;
            border-left:1px solid #254d77;
            border-bottom:1px solid #254d77;
            border-top-right-radius:6px;
        }
        QSpinBox::down-button, QAbstractSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width:24px;
            height:17px;
            background:#163450;
            border-left:1px solid #254d77;
            border-bottom-right-radius:6px;
        }
        QSpinBox::up-button:hover, QAbstractSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QAbstractSpinBox::down-button:hover { background:#1d5d99; }
        QPushButton { background:#1d5d99; color:white; border:none; border-radius:8px; padding:8px 8px; font:600 12pt 'Yu Gothic UI', 'Segoe UI'; }
        QPushButton:hover { background:#2675c2; }
        QPushButton:checked { background:#8f3d47; }
        QPushButton#blockedModeButton {
            font:600 10.5pt 'Yu Gothic UI', 'Segoe UI';
            padding:8px 7px;
        }
        QPushButton#viewHistoryButton {
            background:#174a76;
            border:1px solid #5fa9df;
            border-radius:6px;
            padding:6px 12px;
            font:700 11.5pt 'Yu Gothic UI', 'Segoe UI';
        }
        QPushButton#viewHistoryButton:hover { background:#236ba6; }
        QPushButton#viewHistoryButton:disabled {
            background:#152434;
            color:#607488;
            border-color:#2a4054;
        }
        QHeaderView::section { background:#11253d; color:#9dd9ff; border:none; padding:8px 6px; font:600 12.5pt 'Yu Gothic UI', 'Segoe UI'; }
        QTableWidget#inventoryTable {
            gridline-color:#34506a;
            border:1px solid #34506a;
            background:#07121f;
            alternate-background-color:#0b1828;
        }
        QTableWidget#inventoryTable::item {
            padding:7px 6px;
            border-right:1px solid #24384d;
            border-bottom:1px solid #24384d;
            font:11pt 'Yu Gothic UI', 'Segoe UI';
        }
        QTableWidget#inventoryTable::item:selected {
            background:#39d98a;
            color:#07111f;
        }
        QTableWidget#inventoryTable QHeaderView::section {
            background:#102033;
            color:#f6fbff;
            border-right:2px solid #5f7890;
            border-bottom:1px solid #5f7890;
            padding:9px 6px;
            font:700 12.5pt 'Yu Gothic UI', 'Segoe UI';
        }
        QTableWidget#shipmentTable {
            gridline-color:#34506a;
            border:1px solid #34506a;
            background:#07121f;
            alternate-background-color:#0b1828;
        }
        QTableWidget#shipmentTable::item {
            padding:7px 6px;
            border-right:1px solid #24384d;
            border-bottom:1px solid #24384d;
            font:11pt 'Yu Gothic UI', 'Segoe UI';
        }
        QTableWidget#shipmentTable::item:selected {
            background:#ff8a80;
            color:#07111f;
        }
        QTableWidget#shipmentTable QHeaderView::section {
            background:#102033;
            color:#f6fbff;
            border-right:2px solid #5f7890;
            border-bottom:1px solid #5f7890;
            padding:9px 6px;
            font:700 12.5pt 'Yu Gothic UI', 'Segoe UI';
        }
        QTableWidget QScrollBar:vertical {
            background:#07121f;
            width:30px;
            margin:0;
            border-left:1px solid #254d77;
        }
        QTableWidget QScrollBar::handle:vertical {
            background:#3f89c8;
            min-height:54px;
            border-radius:10px;
            margin:4px;
        }
        QTableWidget QScrollBar::handle:vertical:hover {
            background:#65b8f4;
        }
        QTableWidget QScrollBar:horizontal {
            background:#07121f;
            height:28px;
            margin:0;
            border-top:1px solid #254d77;
        }
        QTableWidget QScrollBar::handle:horizontal {
            background:#3f89c8;
            min-width:54px;
            border-radius:10px;
            margin:4px;
        }
        QTableWidget QScrollBar::add-line,
        QTableWidget QScrollBar::sub-line {
            width:0;
            height:0;
        }
        QLabel#inventoryHint {
            color:#8fb6d8;
            background:#0c1827;
            border:1px solid #24425e;
            border-radius:6px;
            padding:8px 10px;
            font:11pt 'Yu Gothic UI', 'Segoe UI';
        }
        QFrame#detailResizeHandle {
            background:#18304b;
            border:1px solid #5f7890;
            border-radius:4px;
        }
        QFrame#detailResizeHandle:hover {
            background:#244b72;
            border-color:#8fc7ff;
        }
        QTabWidget::pane { border:1px solid #1a3c60; background:#07111f; }
        QTabBar::tab { background:#11253d; color:#88c3f0; padding:11px 16px; margin-right:4px; border-top-left-radius:6px; border-top-right-radius:6px; font:600 12pt 'Yu Gothic UI', 'Segoe UI'; }
        QTabBar::tab:selected { background:#1d5d99; color:white; }
        """)
        self.update_tab_visuals()

    def set_blocked_edit_mode(self, enabled: bool) -> None:
        self.top_map.blocked_edit_mode = enabled
        self.top_map.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self.top_map.update()

    def set_blocked_location_with_validation(self, location: str, blocked: bool) -> None:
        try:
            changed = self.store.set_blocked_location_with_validation(location, blocked)
        except ValueError as exc:
            QMessageBox.information(self, "置けないマス設定", str(exc))
            return
        if not changed:
            return
        self.mark_store_dirty()
        self.refresh_all()

    def open_inventory_column_menu(self) -> None:
        menu = QMenu(self)
        for col, (_key, label, _width) in enumerate(self.INVENTORY_COLUMNS):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(col not in self.inventory_hidden_columns)
            action.toggled.connect(lambda checked, c=col: self.set_inventory_column_visible(c, checked))
        menu.exec(self.inventory_columns_button.mapToGlobal(QPoint(0, self.inventory_columns_button.height())))

    def set_inventory_column_visible(self, column: int, visible: bool) -> None:
        if visible:
            self.inventory_hidden_columns.discard(column)
        else:
            self.inventory_hidden_columns.add(column)
        self.settings.setValue("inventory_hidden_columns", ",".join(str(col) for col in sorted(self.inventory_hidden_columns)))
        self.apply_inventory_column_visibility()

    def apply_inventory_column_visibility(self) -> None:
        if not hasattr(self, "inventory_table"):
            return
        for col in range(self.inventory_table.columnCount()):
            self.inventory_table.setColumnHidden(col, col in self.inventory_hidden_columns)

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
            item.lot.lower(),
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
            color_text = pallet_color_text(pallet).lower()
            pallet_haystacks = [
                pallet.pallet_number.lower(),
                pallet.location_code.lower(),
                pallet.received_date.lower(),
                color_label(pallet.color_key).lower(),
                color_text,
            ]
            pallet_match = all(any(token in hay for hay in pallet_haystacks) for token in tokens)
            item_match = any(self.item_matches_keyword(item) for item in pallet.items)
            if pallet_match or item_match:
                result.append(pallet)
        return result

    def shipment_matches_keyword(self, shipment: ShipmentRecord) -> bool:
        tokens = self.keyword_tokens()
        if not tokens:
            return True
        haystacks = [
            shipment.shipped_at.lower(),
            shipment.pallet_number.lower(),
            shipment.summary_text.lower(),
            str(len(shipment.items)),
            str(shipment.total_sheets),
            str(shipment.estimated_height_mm),
            shipment.location_code.lower(),
            shipment.received_date.lower(),
            color_label(shipment.color_key).lower(),
            shipment_notes_text(shipment).lower(),
        ]
        for item in shipment.items:
            haystacks.extend([
                item.identifier.lower(),
                item.part_code.lower(),
                item.size.lower(),
                str(item.thickness_mm).lower(),
                item.finish_text.lower(),
                item.grade.lower(),
                str(item.sheet_count),
                item.lot.lower(),
                item.note.lower(),
            ])
        return all(any(token in hay for hay in haystacks) for token in tokens)

    def filtered_shipments(self) -> List[ShipmentRecord]:
        return [shipment for shipment in self.store.shipments if self.shipment_matches_keyword(shipment)]

    def shipment_item_values(self, shipment: ShipmentRecord, attr: str) -> List[str]:
        values: List[str] = []
        for item in shipment.items:
            value = str(getattr(item, attr, "") or "").strip()
            if value and value not in values:
                values.append(value)
        return values

    def shipment_item_text(self, shipment: ShipmentRecord, attr: str) -> str:
        values = self.shipment_item_values(shipment, attr)
        return ", ".join(values) if values else "-"

    def shipment_first_item_text(self, shipment: ShipmentRecord, attr: str) -> str:
        values = self.shipment_item_values(shipment, attr)
        return values[0] if values else ""

    def refresh_all(self) -> None:
        self.store.ensure_defaults(); self.store.normalize_stacks()
        for pallet in self.store.pallets:
            pallet.color_key = resolve_effective_color_key(pallet.color_mode, pallet.last_manual_color_key, pallet.items)
        placed_pallets = self.placed_pallets()
        capacity = self.capacity_percent()
        self.summary_label.setText(f"パレット {len(placed_pallets)} / 明細 {sum(len(p.items) for p in placed_pallets)} / 総枚数 {sum(p.total_sheets for p in placed_pallets)} / 使用率 {capacity:.1f}% / 禁止マス {len(self.store.blocked_locations)}")
        self.update_move_history_buttons()
        self.top_map.invalidate_base_cache()
        self.top_map.update(); self.iso_map.update(); self.refresh_inventory_table(); self.refresh_shipment_table(); self.refresh_detail()

    def normalize_store_stacks(self) -> None:
        self.store.normalize_stacks()

    def mark_store_dirty(self, immediate: bool = False) -> None:
        self.store_dirty = True
        self.persist_store_if_dirty()

    def prepare_store_for_save(self) -> None:
        self.store.ensure_defaults()
        self.store.normalize_stacks()
        for pallet in self.store.pallets:
            for item in pallet.items:
                item.lot = normalize_lot(getattr(item, "lot", ""))
            pallet.color_key = resolve_effective_color_key(pallet.color_mode, pallet.last_manual_color_key, pallet.items)
        for shipment in self.store.shipments:
            for item in shipment.items:
                item.lot = normalize_lot(getattr(item, "lot", ""))

    def save_store_with_alerts(self, path: Path = DATA_PATH) -> bool:
        self.prepare_store_for_save()
        target_path = path
        last_error: Optional[Exception] = None
        while True:
            try:
                save_store(self.store, target_path)
                self.store_dirty = False
                if target_path != DATA_PATH:
                    QMessageBox.information(self, "保存", f"保存しました。\n{target_path}")
                return True
            except Exception as error:
                last_error = error
                log_store_error(f"save failed: {target_path}\n{traceback.format_exc()}")

            action = self.show_save_failure_dialog(target_path, last_error)
            if action == "retry":
                continue
            if action == "save_as":
                default_name = APP_DIR / f"inventory-data-recovery-{datetime.now():%Y%m%d-%H%M%S}.json"
                file_path, _ = QFileDialog.getSaveFileName(self, "別名保存", str(default_name), "JSON Files (*.json)")
                if not file_path:
                    return False
                target_path = Path(file_path)
                continue
            return False

    def show_save_failure_dialog(self, path: Path, error: Optional[Exception]) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("保存失敗")
        box.setText("データの保存に失敗しました。")
        detail = f"保存先:\n{path}"
        if error is not None:
            detail += f"\n\n原因:\n{error}"
        detail += "\n\n未保存の変更があります。再試行するか、別名保存してください。"
        box.setInformativeText(detail)
        retry_button = box.addButton("再試行", QMessageBox.AcceptRole)
        save_as_button = box.addButton("別名保存", QMessageBox.ActionRole)
        close_button = box.addButton("閉じる", QMessageBox.RejectRole)
        box.setDefaultButton(retry_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == retry_button:
            return "retry"
        if clicked == save_as_button:
            return "save_as"
        if clicked == close_button:
            return "close"
        return "close"

    def persist_store_if_dirty(self) -> bool:
        if not self.store_dirty:
            return True
        return self.save_store_with_alerts(DATA_PATH)

    def closeEvent(self, event) -> None:
        if not self.persist_store_if_dirty():
            event.ignore()
            return
        super().closeEvent(event)

    def placed_pallets(self) -> List[PalletRecord]:
        return [pallet for pallet in self.store.pallets if not self.store.is_entry_waiting_pallet(pallet)]

    def aisle_cells_for_capacity(self) -> set[str]:
        return {
            format_location_code(col, row)
            for col in range(GRID_COLUMNS)
            if is_aisle_column(col)
            for row in range(GRID_ROWS)
        }

    def capacity_usable_cells(self) -> set[str]:
        all_cells = {
            format_location_code(col, row)
            for col in range(GRID_COLUMNS)
            for row in range(GRID_ROWS)
        }
        return all_cells - self.aisle_cells_for_capacity()

    def is_aisle_location(self, location_code: str) -> bool:
        col, _row = location_to_grid(location_code)
        return is_aisle_column(col)

    def capacity_percent(self) -> float:
        usable_cells = self.capacity_usable_cells()
        used_cells = {visible_location_code(pallet.location_code) for pallet in self.placed_pallets()}
        blocked_non_aisle_cells = {
            visible_location_code(location)
            for location in self.store.blocked_locations
            if not self.is_aisle_location(location)
        }
        occupied_cells = used_cells | blocked_non_aisle_cells
        if not usable_cells:
            return 0.0
        return (len(occupied_cells) / len(usable_cells)) * 100.0

    def refresh_inventory_table(self) -> None:
        rows: Dict[Tuple[str, str, str, str, str, str], dict] = {}
        for pallet in self.filtered_pallets():
            for item in pallet.items:
                if not self.item_matches_keyword(item):
                    pallet_tokens = self.keyword_tokens()
                    pallet_haystacks = [pallet.pallet_number.lower(), pallet.location_code.lower(), pallet.received_date.lower(), color_label(pallet.color_key).lower(), pallet_color_text(pallet).lower()]
                    if pallet_tokens and not all(any(token in hay for hay in pallet_haystacks) for token in pallet_tokens):
                        continue
                thickness_text = str(item.thickness_mm)
                key = (item.part_code, item.size, thickness_text, item.finish_text, item.grade, item.lot)
                row = rows.setdefault(
                    key,
                    {
                        "part_code": item.part_code,
                        "size": item.size,
                        "thickness": thickness_text,
                        "finish": item.finish_text,
                        "grade": item.grade,
                        "lot": item.lot,
                        "notes": [],
                        "sheets": 0,
                        "height": 0,
                        "placements": {},
                    },
                )
                row["sheets"] += item.sheet_count
                row["height"] += item.height_mm
                note = item.note.strip()
                if note and note not in row["notes"]:
                    row["notes"].append(note)
                row["placements"][pallet.pallet_number] = {
                    "sort_key": (*location_to_grid(pallet.location_code), pallet.stack_order, pallet.pallet_number),
                    "pallet_number": pallet.pallet_number,
                    "location": location_stack_label(pallet),
                    "received_date": pallet.received_date or "-",
                }
        sort_key = self.inventory_sort_key
        reverse = self.inventory_sort_desc

        def sorted_placements(row: dict) -> List[dict]:
            return sorted(row["placements"].values(), key=lambda placement: placement["sort_key"])

        def sort_value(row: dict):
            if sort_key == "thickness":
                return (parse_thickness_value(row["thickness"]), row["thickness"], row["part_code"], row["size"])
            if sort_key == "finish":
                return (row["finish"], row["part_code"], row["size"])
            if sort_key == "grade":
                return (row["grade"], row["part_code"], row["size"])
            if sort_key == "sheets":
                return (row["sheets"], row["part_code"], row["size"])
            if sort_key == "lot":
                return (row["lot"], row["part_code"], row["size"])
            if sort_key == "note":
                return (" / ".join(row["notes"]), row["part_code"], row["size"])
            if sort_key == "size":
                return (row["size"], row["part_code"], parse_thickness_value(row["thickness"]), row["thickness"])
            if sort_key == "pallets":
                return (", ".join(placement["pallet_number"] for placement in sorted_placements(row)), row["part_code"], row["size"])
            if sort_key == "locations":
                return (", ".join(placement["location"] for placement in sorted_placements(row)), row["part_code"], row["size"])
            if sort_key == "received_dates":
                return (", ".join(placement["received_date"] for placement in sorted_placements(row)), row["part_code"], row["size"])
            return (row["part_code"], row["size"], parse_thickness_value(row["thickness"]), row["thickness"])

        ordered = sorted(rows.values(), key=sort_value, reverse=reverse)
        self.inventory_table.setRowCount(len(ordered))
        for row_index, row in enumerate(ordered):
            placements = sorted_placements(row)
            pallet_numbers = [placement["pallet_number"] for placement in placements]
            values = [
                row["part_code"],
                row["size"],
                str(row["thickness"]),
                row["finish"],
                row["grade"],
                str(row["sheets"]),
                row["lot"],
                " / ".join(row["notes"]),
                ", ".join(placement["location"] for placement in placements),
                ", ".join(pallet_numbers),
                ", ".join(placement["received_date"] for placement in placements),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == self.INVENTORY_PALLET_COLUMN:
                    item.setData(Qt.UserRole, pallet_numbers)
                self.inventory_table.setItem(row_index, col, item)
        self.apply_inventory_column_visibility()

    def refresh_shipment_table(self) -> None:
        sort_key = self.shipment_sort_key
        reverse = self.shipment_sort_desc

        def sort_value(shipment: ShipmentRecord):
            if sort_key == "total_sheets":
                return (shipment.total_sheets, shipment.shipped_at, shipment.pallet_number)
            if sort_key == "pallet_number":
                return (shipment.pallet_number, shipment.shipped_at)
            if sort_key == "part_code":
                return (self.shipment_first_item_text(shipment, "part_code"), shipment.pallet_number)
            if sort_key == "size":
                return (self.shipment_first_item_text(shipment, "size"), shipment.pallet_number)
            if sort_key == "thickness":
                thickness = self.shipment_first_item_text(shipment, "thickness_mm")
                return (parse_thickness_value(thickness), thickness, shipment.pallet_number)
            if sort_key == "finish":
                return (self.shipment_first_item_text(shipment, "finish_text"), shipment.pallet_number)
            if sort_key == "grade":
                return (self.shipment_first_item_text(shipment, "grade"), shipment.pallet_number)
            if sort_key == "lot":
                return (self.shipment_first_item_text(shipment, "lot"), shipment.pallet_number)
            if sort_key == "location_code":
                return (location_to_grid(shipment.location_code or ENTRY_LOCATION), shipment.pallet_number)
            if sort_key == "received_date":
                return (shipment.received_date or "", shipment.pallet_number)
            if sort_key == "notes":
                return (shipment_notes_text(shipment), shipment.pallet_number)
            return (shipment.shipped_at, shipment.pallet_number)

        ordered = sorted(self.filtered_shipments(), key=sort_value, reverse=reverse)
        self.shipment_table.setRowCount(len(ordered))
        for row_index, shipment in enumerate(ordered):
            values = [
                shipment.shipped_at,
                shipment.pallet_number,
                self.shipment_item_text(shipment, "part_code"),
                self.shipment_item_text(shipment, "size"),
                self.shipment_item_text(shipment, "thickness_mm"),
                self.shipment_item_text(shipment, "finish_text"),
                self.shipment_item_text(shipment, "grade"),
                str(shipment.total_sheets),
                self.shipment_item_text(shipment, "lot"),
                shipment_notes_text(shipment),
                shipment.location_code or "-",
                shipment.received_date or "-",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setData(Qt.UserRole, shipment.shipment_id)
                self.shipment_table.setItem(row_index, col, item)

    def show_table_item_tooltip(self, table: QTableWidget, item: Optional[QTableWidgetItem]) -> None:
        if table is None or item is None:
            return
        text = (item.text() or "").strip()
        if not text:
            return
        if not self.is_cell_text_elided(table, item):
            return
        rect = table.visualItemRect(item)
        if not rect.isValid():
            return
        global_pos = table.viewport().mapToGlobal(rect.bottomRight() + QPoint(6, 6))
        QToolTip.showText(global_pos, text, table)

    def show_table_cell_tooltip(self, table: QTableWidget, row: int, column: int) -> None:
        if table is None:
            return
        item = table.item(row, column)
        if item is None:
            return
        self.show_table_item_tooltip(table, item)

    def hide_table_popup(self) -> None:
        self.cell_popup_timer.stop()
        self.cell_popup.hide()
        QToolTip.hideText()

    def is_cell_text_elided(self, table: QTableWidget, item: Optional[QTableWidgetItem]) -> bool:
        if table is None or item is None:
            return False
        text = item.text() or ""
        if not text:
            return False
        rect = table.visualItemRect(item)
        if not rect.isValid() or rect.width() <= 0:
            return False
        metrics = table.fontMetrics()
        available_width = max(0, rect.width() - 24)
        elided = metrics.elidedText(text, Qt.ElideRight, available_width)
        if elided != text:
            return True
        text_width = metrics.horizontalAdvance(text)
        return text_width >= max(0, available_width - 2)

    def format_table_popup_text(self, text: str) -> str:
        display_text = (text or "").strip()
        if len(display_text) > 80:
            display_text = display_text.replace(", ", ",\n")
        return display_text

    def show_table_item_popup(self, table: QTableWidget, item: Optional[QTableWidgetItem]) -> None:
        self.hide_table_popup()
        if table is None or item is None:
            return
        text = (item.text() or "").strip()
        if not text:
            return
        if not self.is_cell_text_elided(table, item):
            return
        rect = table.visualItemRect(item)
        if not rect.isValid():
            return
        display_text = self.format_table_popup_text(text)
        global_pos = table.viewport().mapToGlobal(rect.bottomLeft() + QPoint(0, 6))
        self.cell_popup.setText(display_text)
        self.cell_popup.adjustSize()
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            popup_width = self.cell_popup.width()
            popup_height = self.cell_popup.height()
            x = min(max(global_pos.x(), available.left() + 6), max(available.left() + 6, available.right() - popup_width - 6))
            y = global_pos.y()
            if y + popup_height > available.bottom() - 6:
                y = max(available.top() + 6, table.viewport().mapToGlobal(rect.topLeft()).y() - popup_height - 6)
            global_pos = QPoint(x, y)
        self.cell_popup.move(global_pos)
        self.cell_popup.show()
        self.cell_popup.raise_()
        self.cell_popup_timer.start(8000)

    def show_table_cell_popup(self, table: QTableWidget, row: int, column: int) -> None:
        if table is None or row < 0 or column < 0:
            self.hide_table_popup()
            return
        item = table.item(row, column)
        if item is None:
            self.hide_table_popup()
            return
        self.show_table_item_popup(table, item)

    def show_table_cell_popup_if_elided(self, table: QTableWidget, row: int, column: int) -> None:
        if table is None or row < 0 or column < 0:
            self.hide_table_popup()
            return
        item = table.item(row, column)
        if item is None or not self.is_cell_text_elided(table, item):
            self.hide_table_popup()
            return
        self.show_table_item_popup(table, item)

    def schedule_table_popup_from_point(self, table: QTableWidget, point: QPoint) -> None:
        if table is None:
            return
        index = table.indexAt(point)
        if not index.isValid():
            return
        row = index.row()
        column = index.column()
        QTimer.singleShot(0, lambda table=table, row=row, column=column: self.show_table_cell_popup(table, row, column))

    def copy_table_to_clipboard(self, table: QTableWidget, skip_hidden_columns: bool = False) -> None:
        if table.rowCount() == 0:
            QApplication.clipboard().setText("")
            return
        headers = []
        visible_columns = []
        for col in range(table.columnCount()):
            if skip_hidden_columns and table.isColumnHidden(col):
                continue
            visible_columns.append(col)
            item = table.horizontalHeaderItem(col)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]
        for row in range(table.rowCount()):
            values = []
            for col in visible_columns:
                item = table.item(row, col)
                values.append(item.text() if item else "")
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    def copy_inventory_table(self) -> None:
        self.copy_table_to_clipboard(self.inventory_table, skip_hidden_columns=True)

    def copy_shipment_table(self) -> None:
        self.copy_table_to_clipboard(self.shipment_table)

    def copy_inventory_summary(self) -> None:
        rows: Dict[Tuple[str, str, str, str, str, str], dict] = {}
        for pallet in self.filtered_pallets():
            for item in pallet.items:
                if not self.item_matches_keyword(item):
                    pallet_tokens = self.keyword_tokens()
                    pallet_haystacks = [pallet.pallet_number.lower(), pallet.location_code.lower(), pallet.received_date.lower(), color_label(pallet.color_key).lower(), pallet_color_text(pallet).lower()]
                    if pallet_tokens and not all(any(token in hay for hay in pallet_haystacks) for token in pallet_tokens):
                        continue
                key = (item.part_code, item.size, str(item.thickness_mm), item.finish_text, item.grade, item.lot)
                identifier = f"#{item.part_code}-{item.size}{item.thickness_mm} {item.finish_text}"
                if item.lot:
                    identifier += f" Lot:{item.lot}"
                row = rows.setdefault(
                    key,
                    {
                        "identifier": identifier,
                        "part_code": item.part_code,
                        "size": item.size,
                        "thickness": str(item.thickness_mm),
                        "finish": item.finish_text,
                        "grade": item.grade,
                        "lot": item.lot,
                        "sheets": 0,
                    },
                )
                row["sheets"] += item.sheet_count
        if not rows:
            QApplication.clipboard().setText("")
            QMessageBox.information(self, "棚卸データ出力", "出力できる在庫データがありません。")
            return
        ordered = sorted(
            rows.values(),
            key=lambda row: (row["part_code"], row["size"], parse_thickness_value(row["thickness"]), row["finish"], row["grade"], row["lot"]),
        )
        lines = ["\t".join(["品名", "合計枚数"])]
        for row in ordered:
            lines.append(
                "\t".join(
                    [
                        row["identifier"],
                        f"{row['grade']} {row['sheets']}".strip(),
                    ]
                )
            )
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "棚卸データ出力", "棚卸用の集計データをクリップボードへコピーしました。")

    def open_shipment_context_menu(self, pos: QPoint) -> None:
        row = self.shipment_table.rowAt(pos.y())
        if row < 0:
            return
        selected_rows = {index.row() for index in self.shipment_table.selectionModel().selectedRows()}
        if row not in selected_rows:
            self.shipment_table.clearSelection()
            self.shipment_table.selectRow(row)

        selected_count = len(self.shipment_table.selectionModel().selectedRows())
        menu = QMenu(self)
        restore_action = menu.addAction("復元")
        delete_action = menu.addAction("履歴削除")
        restore_action.setEnabled(selected_count > 0)
        delete_action.setEnabled(selected_count > 0)
        selected_action = menu.exec(self.shipment_table.viewport().mapToGlobal(pos))
        if selected_action == restore_action:
            self.restore_selected_shipments()
        elif selected_action == delete_action:
            self.delete_selected_shipments()

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
        self.mark_store_dirty()
        self.refresh_all()

    def restore_selected_shipments(self) -> None:
        rows = sorted({index.row() for index in self.shipment_table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "復元", "復元したい出庫履歴を選択してください。")
            return
        if QMessageBox.question(
            self,
            "復元確認",
            f"{len(rows)}件の出庫履歴を復元します。\n元位置ではなく仮置きエリア（未配置）へ置きます。続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
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
        if not self.has_entry_waiting_capacity(len(target_shipments)):
            QMessageBox.warning(self, "復元", self.entry_waiting_full_message())
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
                color_mode=shipment.color_mode,
                last_manual_color_key=shipment.last_manual_color_key,
                stack_order=self.store.next_stack_order(location_code),
                orientation=shipment.orientation,
                map_x=ENTRY_MAP_X,
                map_y=ENTRY_MAP_Y,
                items=[clone_item(item) for item in shipment.items],
                updated_at=now_text(),
            )
            try:
                restored.location_code, restored.map_x, restored.map_y = self.find_entry_waiting_placement(restored)
            except ValueError as exc:
                QMessageBox.warning(self, "復元", str(exc))
                return
            self.store.pallets.append(restored)
            restored_numbers.append(pallet_number)
        target_ids = {shipment.shipment_id for shipment in target_shipments}
        self.store.shipments = [shipment for shipment in self.store.shipments if shipment.shipment_id not in target_ids]
        self.store.normalize_stacks()
        if restored_numbers:
            self.select_pallet(restored_numbers[0])
        self.mark_store_dirty()
        self.refresh_all()
        if renamed_pairs:
            note = "\n".join([f"{before} -> {after}" for before, after in renamed_pairs[:6]])
            more = "" if len(renamed_pairs) <= 6 else f"\n他 {len(renamed_pairs) - 6} 件"
            QMessageBox.information(self, "復元", f"重複したパレット番号には連番を付けて復元しました。\n{note}{more}")

    def handle_inventory_header_click(self, column: int) -> None:
        if column < 0 or column >= len(self.INVENTORY_COLUMNS):
            return
        target = self.INVENTORY_COLUMNS[column][0]
        if not target:
            return
        if self.inventory_sort_key == target:
            self.inventory_sort_desc = not self.inventory_sort_desc
        else:
            self.inventory_sort_key = target
            self.inventory_sort_desc = False
        self.refresh_inventory_table()

    def handle_shipment_header_click(self, column: int) -> None:
        if column < 0 or column >= len(self.SHIPMENT_COLUMNS):
            return
        target = self.SHIPMENT_COLUMNS[column][0]
        if not target:
            return
        if self.shipment_sort_key == target:
            self.shipment_sort_desc = not self.shipment_sort_desc
        else:
            self.shipment_sort_key = target
            self.shipment_sort_desc = False
        self.refresh_shipment_table()

    def select_pallet_from_inventory_table(self, row: int, _column: int) -> None:
        item = self.inventory_table.item(row, self.INVENTORY_PALLET_COLUMN)
        pallet_numbers = item.data(Qt.UserRole) if item is not None else None
        if not isinstance(pallet_numbers, list) or not pallet_numbers:
            return
        valid_numbers = [pallet_number for pallet_number in pallet_numbers if self.store.get_pallet(pallet_number) is not None]
        if not valid_numbers:
            return
        self.tabs.setCurrentIndex(0)
        primary = self.current_pallet_number if self.current_pallet_number in valid_numbers else valid_numbers[0]
        self.current_pallet_number = None
        self.current_note_id = None
        self.top_map.selected_pallet = primary
        self.top_map.selected_pallets = set(valid_numbers)
        self.top_map.selected_note = None
        self.top_map.hover_pallet = primary
        self.top_map.invalidate_base_cache()
        self.iso_map.selected_pallet = None
        if len(valid_numbers) > 1:
            self.top_map.zoom = 1.0
            self.top_map.pan_offset = QPoint()
        else:
            self.top_map.center_on_pallet(primary)
        self.detail_frame.hide()
        self.top_map.update()
        self.iso_map.update()

    def next_pallet_after_shipping(self, location_code: str, previous_stack_order: int) -> Optional[str]:
        remaining = [
            pallet
            for pallet in self.store.pallets
            if normalize_location_code(pallet.location_code) == normalize_location_code(location_code)
            and not self.store.is_entry_waiting_pallet(pallet)
        ]
        if not remaining:
            return None
        remaining.sort(key=lambda item: (item.stack_order, item.updated_at, item.pallet_number))
        same_or_next = [item for item in remaining if item.stack_order >= previous_stack_order]
        target = same_or_next[0] if same_or_next else remaining[-1]
        return target.pallet_number

    def ship_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "出庫", "先にパレットを選択してください。")
            return
        if QMessageBox.question(self, "出庫", f"パレット {pallet.pallet_number} を出庫して倉庫表示から外しますか？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        shipped_location = normalize_location_code(pallet.location_code)
        shipped_stack_order = pallet.stack_order
        shipment = ShipmentRecord(
            pallet_number=pallet.pallet_number,
            location_code=pallet.location_code,
            received_date=pallet.received_date,
            color_key=pallet.color_key,
            color_mode=pallet.color_mode,
            last_manual_color_key=pallet.last_manual_color_key,
            orientation=pallet.orientation,
            map_x=pallet.map_x,
            map_y=pallet.map_y,
            items=[clone_item(item) for item in pallet.items],
        )
        self.store.shipments.append(shipment)
        self.store.pallets = [item for item in self.store.pallets if item.pallet_number != pallet.pallet_number]
        self.normalize_store_stacks()
        next_pallet_number = self.next_pallet_after_shipping(shipped_location, shipped_stack_order)
        if next_pallet_number:
            self.select_pallet(next_pallet_number)
        else:
            self.clear_selection()
        self.mark_store_dirty()
        self.refresh_all()

    def select_pallet(self, pallet_number: str) -> None:
        if self.current_pallet_number != pallet_number:
            self.detail_frame_manual_position = None
        self.current_pallet_number = pallet_number
        self.current_note_id = None
        self.top_map.selected_pallet = pallet_number
        self.top_map.selected_pallets = {pallet_number}
        self.top_map.selected_note = None
        self.iso_map.selected_pallet = pallet_number
        self.apply_responsive_layout()
        self.top_map.invalidate_base_cache()
        self.top_map.update()
        self.iso_map.update()
        self.refresh_detail()

    def select_map_note(self, note_id: str) -> None:
        if self.current_note_id != note_id:
            self.detail_frame_manual_position = None
        if self.store.get_map_note(note_id) is None:
            return
        self.current_note_id = note_id
        self.current_pallet_number = None
        self.top_map.selected_note = note_id
        self.top_map.selected_pallet = None
        self.top_map.selected_pallets = set()
        self.iso_map.selected_pallet = None
        self.apply_responsive_layout()
        self.top_map.invalidate_base_cache()
        self.top_map.update()
        self.iso_map.update()
        self.refresh_detail()

    def open_pallet_context_menu(self, pallet_number: str, global_pos: QPoint) -> None:
        pallet = self.store.get_pallet(pallet_number)
        if not pallet:
            return
        self.select_pallet(pallet_number)
        members = self.store.group_members(pallet)
        current_index = next((index for index, item in enumerate(members) if item.pallet_number == pallet_number), 0)

        menu = QMenu(self)
        edit_action = menu.addAction("明細編集")
        rotate_action = menu.addAction("向き変更")
        menu.addSeparator()
        stack_up_action = menu.addAction("段を上げる")
        stack_down_action = menu.addAction("段を下げる")
        unstack_action = menu.addAction("列を解除")
        stack_up_action.setEnabled(len(members) > 1 and current_index < len(members) - 1)
        stack_down_action.setEnabled(len(members) > 1 and current_index > 0)
        unstack_action.setEnabled(len(members) > 1)
        menu.addSeparator()
        transfer_action = menu.addAction("積み替え")
        ship_action = menu.addAction("出庫")

        selected_action = menu.exec(global_pos)
        if selected_action == edit_action:
            self.open_selected_pallet_editor(pallet_number)
        elif selected_action == rotate_action:
            self.rotate_selected_pallet()
        elif selected_action == stack_up_action:
            self.adjust_selected_stack(1)
        elif selected_action == stack_down_action:
            self.adjust_selected_stack(-1)
        elif selected_action == unstack_action:
            self.unstack_selected_pallet()
        elif selected_action == transfer_action:
            self.transfer_selected_pallet()
        elif selected_action == ship_action:
            self.ship_selected_pallet()

    def refresh_detail(self) -> None:
        note = self.store.get_map_note(self.current_note_id or "")
        if note is not None:
            self.stack_detail_selector.blockSignals(True)
            self.stack_detail_selector.clear()
            while self.stack_detail_pages.count():
                page = self.stack_detail_pages.widget(0)
                self.stack_detail_pages.removeWidget(page)
                page.deleteLater()
            page = QWidget()
            page.setProperty("note_id", note.note_id)
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
            detail_label = QLabel(map_note_popup_text(note))
            detail_label.setWordWrap(True)
            detail_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            detail_label.installEventFilter(self)
            inner_layout.addWidget(detail_label)
            inner_layout.addStretch(1)
            scroll.setWidget(inner)
            page_layout.addWidget(scroll)
            self.stack_detail_pages.addWidget(page)
            self.stack_detail_selector.setVisible(False)
            self.stack_detail_selector.blockSignals(False)
            self.update_stack_detail_style()
            self.update_detail_overlay_geometry()
            self.detail_frame.show()
            return
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
        # パレット積み列は内部の下→上順を、表示だけ上→下に変換する。
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
        if normalize_location_code(location_code) == ENTRY_LOCATION:
            return None
        location_code = normalize_location_code(location_code)
        source_members = {member.pallet_number for member in self.store.group_members(source)}
        for pallet in self.store.pallets_at_location(location_code):
            if pallet.pallet_number in source_members:
                continue
            return pallet
        return None

    def normalized_footprint(self, pallet: PalletRecord) -> Tuple[float, float]:
        width_mm, depth_mm = footprint_mm(pallet)
        return width_mm / 42000.0, depth_mm / 28000.0

    def pallet_would_collide(self, pallet: PalletRecord, map_x: float, map_y: float, location_code: str) -> bool:
        width_norm, depth_norm = self.normalized_footprint(pallet)
        padding_x = 0.002
        padding_y = 0.002
        for other in self.store.pallets:
            if other.pallet_number == pallet.pallet_number:
                continue
            if normalize_location_code(other.location_code) != normalize_location_code(location_code):
                continue
            other_x = other.map_x if other.map_x is not None else self.top_map.normalized_position_for_location(other.location_code, other)[0]
            other_y = other.map_y if other.map_y is not None else self.top_map.normalized_position_for_location(other.location_code, other)[1]
            other_width_norm, other_depth_norm = self.normalized_footprint(other)
            overlap_x = abs(map_x - other_x) < ((width_norm + other_width_norm) / 2.0 + padding_x)
            overlap_y = abs(map_y - other_y) < ((depth_norm + other_depth_norm) / 2.0 + padding_y)
            if overlap_x and overlap_y:
                return True
        return False

    def find_available_position(self, pallet: PalletRecord, location_code: str, preferred_x: Optional[float] = None, preferred_y: Optional[float] = None) -> Optional[Tuple[float, float]]:
        location_code = normalize_location_code(location_code)
        col, row = location_to_grid(location_code)
        cell_center_x = (col + 0.5) / GRID_COLUMNS
        cell_center_y = (row + 0.5) / GRID_ROWS
        cell_w = 1.0 / GRID_COLUMNS
        cell_h = 1.0 / GRID_ROWS
        current_x = preferred_x if preferred_x is not None else (pallet.map_x if pallet.map_x is not None else cell_center_x)
        current_y = preferred_y if preferred_y is not None else (pallet.map_y if pallet.map_y is not None else cell_center_y)
        offsets = [
            (0.0, 0.0),
            (0.16, 0.0), (-0.16, 0.0), (0.0, 0.16), (0.0, -0.16),
            (0.16, 0.16), (0.16, -0.16), (-0.16, 0.16), (-0.16, -0.16),
            (0.28, 0.0), (-0.28, 0.0), (0.0, 0.28), (0.0, -0.28),
            (0.28, 0.16), (-0.28, 0.16), (0.28, -0.16), (-0.28, -0.16),
            (0.16, 0.28), (-0.16, 0.28), (0.16, -0.28), (-0.16, -0.28),
        ]
        candidate_centers = [(current_x, current_y), (cell_center_x, cell_center_y)]
        for base_x, base_y in candidate_centers:
            for offset_x, offset_y in offsets:
                candidate_x = base_x + (cell_w * offset_x)
                candidate_y = base_y + (cell_h * offset_y)
                candidate_x, candidate_y = self.top_map.clamped_normalized_for_pallet(pallet, candidate_x, candidate_y)
                if self.pallet_would_collide(pallet, candidate_x, candidate_y, location_code):
                    continue
                return candidate_x, candidate_y
        return None

    def entry_waiting_count(self) -> int:
        return sum(1 for pallet in self.store.pallets if self.store.is_entry_waiting_pallet(pallet))

    def has_entry_waiting_capacity(self, needed: int = 1) -> bool:
        return self.entry_waiting_count() + needed <= len(ENTRY_WAITING_SLOTS)

    def entry_waiting_full_message(self) -> str:
        return f"仮置きエリア（未配置）は上限{len(ENTRY_WAITING_SLOTS)}個です。\n先に仮置きエリア内のパレットを配置してから操作してください。"

    def entry_waiting_slot_occupied(self, slot_x: float, slot_y: float, ignore: Optional[str] = None) -> bool:
        for pallet in self.store.pallets:
            if pallet.pallet_number == ignore or not self.store.is_entry_waiting_pallet(pallet):
                continue
            map_x = pallet.map_x if pallet.map_x is not None else ENTRY_MAP_X
            map_y = pallet.map_y if pallet.map_y is not None else ENTRY_MAP_Y
            if abs(map_x - slot_x) <= ENTRY_WAITING_TOLERANCE and abs(map_y - slot_y) <= ENTRY_WAITING_TOLERANCE:
                return True
        for note in self.store.map_notes:
            if note.note_id == ignore or (note.map_y or 0.0) <= 1.0:
                continue
            map_x = note.map_x if note.map_x is not None else ENTRY_MAP_X
            map_y = note.map_y if note.map_y is not None else ENTRY_MAP_Y
            if abs(map_x - slot_x) <= ENTRY_WAITING_TOLERANCE and abs(map_y - slot_y) <= ENTRY_WAITING_TOLERANCE:
                return True
        return False

    def find_entry_waiting_placement(self, pallet: PalletRecord) -> Tuple[str, float, float]:
        if not self.has_entry_waiting_capacity(0 if self.store.is_entry_waiting_pallet(pallet) else 1):
            raise ValueError(self.entry_waiting_full_message())
        for slot_x, slot_y in ENTRY_WAITING_SLOTS:
            if self.entry_waiting_slot_occupied(slot_x, slot_y, ignore=pallet.pallet_number):
                continue
            candidate_x, candidate_y = self.top_map.clamped_normalized_for_pallet(pallet, slot_x, slot_y)
            return ENTRY_LOCATION, candidate_x, candidate_y
        raise ValueError(self.entry_waiting_full_message())

    def find_map_note_waiting_placement(self, note: MapNoteRecord) -> Tuple[float, float]:
        for slot_x, slot_y in ENTRY_WAITING_SLOTS:
            if self.entry_waiting_slot_occupied(slot_x, slot_y, ignore=note.note_id):
                continue
            return self.top_map.clamped_normalized_for_note(note, slot_x, slot_y)
        raise ValueError("仮置きエリア（未配置）に空きがありません。\n先に仮置きエリア内のメモまたはパレットを配置してください。")

    def open_color_label_notes_dialog(self) -> None:
        dialog = ColorLabelNotesDialog(self.store, self)
        if dialog.exec() != QDialog.Accepted:
            return
        notes = dict(DEFAULT_EDITABLE_COLOR_LABEL_NOTES)
        notes.update({key: value for key, value in dialog.payload().items() if key in EDITABLE_COLOR_LABEL_KEYS})
        self.store.color_label_notes = notes
        self.mark_store_dirty()
        self.refresh_all()

    def pallet_move_states(self, pallet_numbers) -> Tuple[PalletMoveState, ...]:
        states = []
        for pallet_number in sorted(set(pallet_numbers)):
            pallet = self.store.get_pallet(pallet_number)
            if pallet is None:
                continue
            states.append(PalletMoveState(
                pallet_number=pallet.pallet_number,
                location_code=pallet.location_code,
                map_x=pallet.map_x,
                map_y=pallet.map_y,
                stack_order=pallet.stack_order,
            ))
        return tuple(states)

    def record_move_action(self, action: MoveAction) -> None:
        if action.kind == "pallet" and action.pallet_before == action.pallet_after:
            return
        if action.kind == "note" and action.note_before == action.note_after:
            return
        self.move_undo_stack.append(action)
        if len(self.move_undo_stack) > self.move_history_limit:
            del self.move_undo_stack[:-self.move_history_limit]
        self.move_redo_stack.clear()
        self.update_move_history_buttons()

    def update_move_history_buttons(self) -> None:
        if hasattr(self, "undo_move_button"):
            self.undo_move_button.setEnabled(bool(self.move_undo_stack))
        if hasattr(self, "redo_move_button"):
            self.redo_move_button.setEnabled(bool(self.move_redo_stack))

    def apply_move_action(self, action: MoveAction, use_after: bool) -> bool:
        if action.kind == "pallet":
            states = action.pallet_after if use_after else action.pallet_before
            applied = False
            timestamp = now_text()
            for state in states:
                pallet = self.store.get_pallet(state.pallet_number)
                if pallet is None:
                    continue
                pallet.location_code = state.location_code
                pallet.map_x = state.map_x
                pallet.map_y = state.map_y
                pallet.stack_order = state.stack_order
                pallet.updated_at = timestamp
                if state.location_code not in self.store.locations:
                    self.store.locations.append(state.location_code)
                applied = True
            if not applied:
                return False
            self.store.normalize_stacks()
            if self.store.get_pallet(action.target_id) is not None:
                self.select_pallet(action.target_id)
        elif action.kind == "note":
            note = self.store.get_map_note(action.target_id)
            state = action.note_after if use_after else action.note_before
            if note is None or state is None:
                return False
            note.map_x, note.map_y = state
            note.updated_at = now_text()
            self.select_map_note(note.note_id)
        else:
            return False
        self.mark_store_dirty()
        self.refresh_all()
        return True

    def undo_last_move(self) -> None:
        if not self.move_undo_stack:
            return
        action = self.move_undo_stack.pop()
        if self.apply_move_action(action, use_after=False):
            self.move_redo_stack.append(action)
        self.update_move_history_buttons()

    def redo_last_move(self) -> None:
        if not self.move_redo_stack:
            return
        action = self.move_redo_stack.pop()
        if self.apply_move_action(action, use_after=True):
            self.move_undo_stack.append(action)
        self.update_move_history_buttons()

    def open_map_note_dialog(self) -> None:
        dialog = MapNoteDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        text, size, color_key = payload
        note = MapNoteRecord(text=text, size=size, color_key=color_key, map_x=ENTRY_MAP_X, map_y=ENTRY_MAP_Y, updated_at=now_text())
        try:
            note.map_x, note.map_y = self.find_map_note_waiting_placement(note)
        except ValueError as exc:
            QMessageBox.warning(self, "メモ追加", str(exc))
            return
        self.store.map_notes.append(note)
        self.select_map_note(note.note_id)
        self.mark_store_dirty()
        self.refresh_all()

    def move_map_note(self, note_id: str, map_x: float, map_y: float) -> None:
        note = self.store.get_map_note(note_id)
        if note is None:
            return
        before = (note.map_x, note.map_y)
        note.map_x, note.map_y = self.top_map.clamped_normalized_for_note(note, map_x, map_y)
        after = (note.map_x, note.map_y)
        note.updated_at = now_text()
        self.current_note_id = note_id
        self.current_pallet_number = None
        self.record_move_action(MoveAction(
            kind="note",
            target_id=note_id,
            note_before=before,
            note_after=after,
        ))
        self.mark_store_dirty()
        self.refresh_all()

    def open_map_note_editor(self, note_id: str) -> None:
        note = self.store.get_map_note(note_id)
        if note is None:
            return
        dialog = MapNoteDialog(self, note)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        text, size, color_key = payload
        note.text = text
        note.size = size
        note.color_key = color_key
        note.updated_at = now_text()
        self.select_map_note(note.note_id)
        self.mark_store_dirty()
        self.refresh_all()

    def open_map_note_context_menu(self, note_id: str, global_pos: QPoint) -> None:
        note = self.store.get_map_note(note_id)
        if note is None:
            return
        menu = QMenu(self)
        remove_action = menu.addAction("撤去")
        selected_action = menu.exec(global_pos)
        if selected_action == remove_action:
            self.remove_map_note(note_id)

    def remove_map_note(self, note_id: str) -> None:
        note = self.store.get_map_note(note_id)
        if note is None:
            return
        preview = note.text.strip().splitlines()[0] if note.text.strip() else "メモ"
        if len(preview) > 40:
            preview = preview[:40] + "..."
        if QMessageBox.question(self, "メモ撤去", f"メモ「{preview}」を撤去しますか？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.map_notes = [item for item in self.store.map_notes if item.note_id != note_id]
        if self.current_note_id == note_id:
            self.current_note_id = None
            self.top_map.selected_note = None
            self.apply_responsive_layout()
        self.mark_store_dirty()
        self.refresh_all()

    def move_pallet(self, pallet_number: str, map_x: float, map_y: float, destination: str) -> None:
        pallet = self.store.get_pallet(pallet_number)
        if not pallet: return
        destination = normalize_location_code(destination)
        if destination not in self.store.locations: self.store.locations.append(destination)
        members = self.store.group_members(pallet)
        target_stack = self.nearby_stack_target(pallet, map_x, map_y, destination)
        if target_stack is not None:
            destination = normalize_location_code(target_stack.location_code)
        affected_numbers = {member.pallet_number for member in members}
        affected_numbers.update(member.pallet_number for member in self.store.pallets_at_location(destination))
        before = self.pallet_move_states(affected_numbers)
        destination_x, destination_y = self.top_map.normalized_position_for_location(destination, pallet)

        if target_stack:
            target_members = self.store.group_members(target_stack)
            next_order = len(target_members)
            for index, member in enumerate(members):
                member.location_code = destination
                member.map_x = target_stack.map_x if target_stack.map_x is not None else destination_x
                member.map_y = target_stack.map_y if target_stack.map_y is not None else destination_y
                member.stack_order = next_order + index
                member.updated_at = now_text()
        else:
            for index, member in enumerate(members):
                member.location_code = destination
                member.map_x, member.map_y = self.top_map.normalized_position_for_location(destination, member)
                member.stack_order = index
                member.updated_at = now_text()
        pallet.updated_at = now_text()
        self.store.normalize_stacks()
        after = self.pallet_move_states(affected_numbers)
        self.record_move_action(MoveAction(
            kind="pallet",
            target_id=pallet_number,
            pallet_before=before,
            pallet_after=after,
        ))
        self.select_pallet(pallet_number)
        self.mark_store_dirty()
        self.refresh_all()

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
        pallet.updated_at = now_text(); self.mark_store_dirty(); self.refresh_all()

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
        self.normalize_store_stacks()
        self.mark_store_dirty()
        self.refresh_all()

    def unstack_selected_pallet(self) -> None:
        selected_pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not selected_pallet:
            QMessageBox.information(self, "列を解除", "先にパレットを選択してください。")
            return
        members = self.store.group_members(selected_pallet)
        if len(members) <= 1:
            QMessageBox.information(self, "列を解除", "このパレットは単独なので解除する列がありません。")
            return
        if not self.has_entry_waiting_capacity():
            QMessageBox.warning(self, "列を解除", self.entry_waiting_full_message())
            return
        pallet = selected_pallet
        remaining_members = [member for member in members if member.pallet_number != pallet.pallet_number]
        for index, member in enumerate(remaining_members):
            member.stack_order = index
            member.updated_at = now_text()
        try:
            target_location, target_x, target_y = self.find_entry_waiting_placement(pallet)
        except ValueError as exc:
            QMessageBox.warning(self, "列を解除", str(exc))
            return
        pallet.stack_order = 0
        pallet.location_code = target_location
        pallet.map_x, pallet.map_y = target_x, target_y
        pallet.updated_at = now_text()
        self.current_pallet_number = pallet.pallet_number
        self.normalize_store_stacks()
        self.mark_store_dirty()
        self.refresh_all()
        QMessageBox.information(self, "列を解除", "解除したパレットは仮置きエリア（未配置）へ移動しました。")

    def edit_selected_pallet(self) -> None:
        if self.current_note_id and self.store.get_map_note(self.current_note_id) is not None:
            self.open_map_note_editor(self.current_note_id)
            return
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
        requested_number, received_date, location_code, orientation, color_mode, last_manual_color_key, stack_order, items = payload
        pallet_number = self.store.unique_pallet_number(requested_number, ignore=pallet.pallet_number)
        location_code = normalize_location_code(location_code)
        if location_code not in self.store.locations:
            self.store.locations.append(location_code)
        pallet.pallet_number = pallet_number
        pallet.location_code = location_code
        pallet.received_date = received_date
        pallet.orientation = orientation
        pallet.color_mode = color_mode
        pallet.last_manual_color_key = last_manual_color_key
        pallet.color_key = resolve_effective_color_key(color_mode, last_manual_color_key, items)
        pallet.stack_order = stack_order
        pallet.items = items
        pallet.updated_at = now_text()
        self.current_pallet_number = pallet_number
        self.normalize_store_stacks()
        self.mark_store_dirty()
        self.refresh_all()
        if pallet_number != requested_number:
            QMessageBox.information(self, "編集", f"同名ありのため、`{pallet_number}` で登録しました。")

    def transfer_selected_pallet(self) -> None:
        source = self.store.get_pallet(self.current_pallet_number or "")
        if not source:
            QMessageBox.information(self, "積み替え", "先に移動元パレットを選択してください。")
            return
        targets = [pallet for pallet in self.store.pallets if pallet.pallet_number != source.pallet_number]
        if not source.items:
            QMessageBox.information(self, "積み替え", "移動元明細がありません。")
            return
        dialog = TransferDialog(source, targets, self)
        if dialog.exec() != QDialog.Accepted:
            return
        payload = dialog.payload()
        if payload is None:
            return
        line_id, target_mode, target_ref, quantity = payload
        source_item = next((item for item in source.items if item.line_id == line_id), None)
        if source_item is None:
            return
        target: Optional[PalletRecord] = None
        requested_target_number = ""
        if target_mode == "NEW":
            if not self.has_entry_waiting_capacity():
                QMessageBox.warning(self, "積み替え", self.entry_waiting_full_message())
                return
            requested_target_number = target_ref
            target_number = self.store.unique_pallet_number(requested_target_number)
            location_code = ENTRY_LOCATION
            if location_code not in self.store.locations:
                self.store.locations.append(location_code)
            transferred_item = clone_item(source_item, quantity)
            target = PalletRecord(
                pallet_number=target_number,
                location_code=location_code,
                received_date=source.received_date,
                color_key=resolve_effective_color_key("AUTO", "GRAY", [transferred_item]),
                color_mode="AUTO",
                last_manual_color_key="GRAY",
                stack_order=self.store.next_stack_order(location_code),
                orientation=source.orientation,
                map_x=ENTRY_MAP_X,
                map_y=ENTRY_MAP_Y,
                items=[transferred_item],
                updated_at=now_text(),
            )
            try:
                target.location_code, target.map_x, target.map_y = self.find_entry_waiting_placement(target)
            except ValueError as exc:
                QMessageBox.warning(self, "積み替え", str(exc))
                return
            self.store.pallets.append(target)
        else:
            target = self.store.get_pallet(target_ref)
            if target is None:
                QMessageBox.warning(self, "積み替え", "移動先パレットが見つかりません。")
                return
        source_item.sheet_count -= quantity
        if source_item.sheet_count <= 0:
            source.items = [item for item in source.items if item.line_id != line_id]
        if target_mode != "NEW":
            target.items.append(clone_item(source_item, quantity))
        source.updated_at = now_text()
        target.updated_at = now_text()
        self.store.normalize_stacks()
        self.mark_store_dirty()
        if target_mode == "NEW":
            self.select_pallet(target.pallet_number)
        self.refresh_all()
        if target_mode == "NEW" and target.pallet_number != requested_target_number:
            QMessageBox.information(self, "積み替え", f"同名ありのため、空パレット番号は `{target.pallet_number}` で登録しました。")

    def open_registration(self) -> None:
        dialog = RegistrationDialog(self.store.locations, self, initial_item=self.last_registration_item_cache)
        if dialog.exec() != QDialog.Accepted: return
        payload = dialog.payload()
        if payload is None: return
        requested_number, received_date, orientation, color_mode, last_manual_color_key, items = payload
        pallet_number = self.store.unique_pallet_number(requested_number)
        if not self.has_entry_waiting_capacity():
            QMessageBox.warning(self, "新規登録", self.entry_waiting_full_message())
            return
        color_key = resolve_effective_color_key(color_mode, last_manual_color_key, items)
        location_code = ENTRY_LOCATION
        if location_code not in self.store.locations: self.store.locations.append(location_code)
        pallet = PalletRecord(pallet_number=pallet_number, location_code=location_code, received_date=received_date, color_key=color_key, color_mode=color_mode, last_manual_color_key=last_manual_color_key, stack_order=self.store.next_stack_order(location_code), orientation=orientation, map_x=ENTRY_MAP_X, map_y=ENTRY_MAP_Y, items=items, updated_at=now_text())
        try:
            pallet.location_code, pallet.map_x, pallet.map_y = self.find_entry_waiting_placement(pallet)
        except ValueError as exc:
            QMessageBox.warning(self, "新規登録", str(exc))
            return
        self.store.pallets.append(pallet)
        if items:
            cached_item = clone_item(items[-1])
            cached_item.note = ""
            self.last_registration_item_cache = cached_item
        self.normalize_store_stacks()
        self.select_pallet(pallet_number); self.mark_store_dirty(); self.refresh_all()
        if pallet_number != requested_number:
            QMessageBox.information(self, "新規登録", f"同名ありのため、`{pallet_number}` で登録しました。")

    def export_data(self) -> None:
        default_name = APP_DIR / f"inventory-export-{datetime.now():%Y%m%d-%H%M%S}.json"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export", str(default_name), "JSON Files (*.json)")
        if file_path:
            self.save_store_with_alerts(Path(file_path))

    def import_data(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import", str(APP_DIR), "JSON Files (*.json)")
        if not file_path: return
        answer = QMessageBox.question(
            self,
            "Import確認",
            "Importすると現在の在庫データは読み込んだ内容で上書きされます。続行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        import_path = Path(file_path)
        try:
            imported_store = read_store_file(import_path)
        except Exception:
            log_store_error(f"import failed: {import_path}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "Import", f"読み込みに失敗しました。現在のデータは変更していません。\n{file_path}")
            return
        self.store = imported_store; self.top_map.store = self.store; self.iso_map.store = self.store; self.current_pallet_number = None; self.current_note_id = None; self.top_map.selected_pallet = None; self.top_map.selected_pallets = set(); self.top_map.selected_note = None; self.top_map.hover_pallet = None; self.iso_map.selected_pallet = None; self.move_undo_stack.clear(); self.move_redo_stack.clear(); self.mark_store_dirty(immediate=True); self.refresh_all(); QMessageBox.information(self, "Import", f"読み込みました。\n{file_path}")

    def clear_selection(self) -> None:
        self.disable_table_multi_select()
        for table in (getattr(self, "inventory_table", None), getattr(self, "shipment_table", None)):
            if table is not None:
                table.clearSelection()
        self.current_pallet_number = None; self.current_note_id = None; self.top_map.selected_pallet = None; self.top_map.selected_pallets = set(); self.top_map.selected_note = None; self.top_map.hover_pallet = None; self.top_map.hover_note = None; self.top_map.hover_target = None; self.iso_map.selected_pallet = None; self.apply_responsive_layout(); self.top_map.invalidate_base_cache(); self.top_map.update(); self.iso_map.update(); self.refresh_detail()

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
    try:
        window = MainWindow()
    except StoreRecoveryError as error:
        show_store_recovery_dialog(error)
        return 1
    if ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(ICON_PATH)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
