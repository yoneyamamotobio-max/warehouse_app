from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget

APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "inventory-data.json"
DEFAULT_LOCATIONS = ["A-01", "A-02", "A-03", "B-01", "B-02", "C-01", "STAGE-1", "STAGE-2"]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class InventoryItemLine:
    line_id: str = field(default_factory=lambda: uuid4().hex)
    part_code: str = ""
    size: str = "LL"
    thickness_mm: int = 10
    finish_text: str = "S/S"
    grade: str = "A"
    sheet_count: int = 80

    @property
    def identifier(self) -> str:
        return f"#{self.part_code}-{self.size}{self.thickness_mm} {self.finish_text} {self.grade} {self.sheet_count}"

    @property
    def height_mm(self) -> int:
        return self.thickness_mm * self.sheet_count


@dataclass
class PalletRecord:
    pallet_number: str
    location_code: str
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


class InventoryStore:
    def __init__(self) -> None:
        self.locations = list(DEFAULT_LOCATIONS)
        self.pallets: List[PalletRecord] = []

    def ensure_defaults(self) -> None:
        for location in DEFAULT_LOCATIONS:
            if location not in self.locations:
                self.locations.append(location)

    def normalize_stacks(self) -> None:
        for location in self.locations:
            pallets = [p for p in self.pallets if p.location_code == location]
            pallets.sort(key=lambda p: (p.stack_order, p.updated_at, p.pallet_number))
            for index, pallet in enumerate(pallets):
                pallet.stack_order = index

    def next_stack_order(self, location_code: str, ignore: Optional[str] = None) -> int:
        values = [p.stack_order for p in self.pallets if p.location_code == location_code and p.pallet_number != ignore]
        return max(values) + 1 if values else 0

    def get_pallet(self, pallet_number: str) -> Optional[PalletRecord]:
        for pallet in self.pallets:
            if pallet.pallet_number == pallet_number:
                return pallet
        return None

    def to_dict(self) -> dict:
        return {
            "locations": self.locations,
            "pallets": [
                {
                    "pallet_number": p.pallet_number,
                    "location_code": p.location_code,
                    "stack_order": p.stack_order,
                    "orientation": p.orientation,
                    "map_x": p.map_x,
                    "map_y": p.map_y,
                    "updated_at": p.updated_at,
                    "items": [asdict(item) for item in p.items],
                }
                for p in self.pallets
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "InventoryStore":
        store = cls()
        store.locations = list(payload.get("locations") or DEFAULT_LOCATIONS)
        for pallet_data in payload.get("pallets", []):
            items = [InventoryItemLine(**item_data) for item_data in pallet_data.get("items", [])]
            store.pallets.append(PalletRecord(pallet_number=pallet_data.get("pallet_number", ""), location_code=pallet_data.get("location_code", ""), stack_order=int(pallet_data.get("stack_order", 0)), orientation=int(pallet_data.get("orientation", 0)), map_x=pallet_data.get("map_x"), map_y=pallet_data.get("map_y"), updated_at=pallet_data.get("updated_at", now_text()), items=items))
        store.ensure_defaults()
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


def pallet_color(pallet: PalletRecord) -> QColor:
    sizes = {item.size.upper() for item in pallet.items}
    if len(sizes) > 1:
        return QColor("#FFC34D")
    size = next(iter(sizes), "LL")
    if size == "L":
        return QColor("#57C1FF")
    if size == "OL":
        return QColor("#FF6671")
    return QColor("#31D07C")


def footprint_mm(pallet: PalletRecord) -> Tuple[int, int]:
    sizes = [item.size.upper() for item in pallet.items] or ["LL"]
    size = max(sizes, key=lambda code: {"L": 1, "LL": 2, "EL": 2, "OL": 3}.get(code, 0))
    width, depth = (1200, 1300) if size == "L" else ((1400, 3500) if size == "OL" else (1300, 2300))
    return (depth, width) if pallet.orientation % 180 == 90 else (width, depth)


class RegistrationDialog(QDialog):
    def __init__(self, locations: List[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新規登録")
        self.resize(700, 540)
        self.items: List[InventoryItemLine] = []
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.pallet_number = QLineEdit()
        self.pallet_number.setPlaceholderText("例: R080324")
        self.location = QComboBox(); self.location.setEditable(True); self.location.addItems(sorted(locations))
        self.orientation = QComboBox(); self.orientation.addItem("横向き", 0); self.orientation.addItem("縦向き", 90)
        form.addRow("パレット番号", self.pallet_number)
        form.addRow("ロケーション", self.location)
        form.addRow("向き", self.orientation)
        root.addLayout(form)

        box = QFrame(); grid = QGridLayout(box)
        self.part_code = QLineEdit(); self.part_code.setPlaceholderText("38")
        self.size = QComboBox(); self.size.addItems(["L", "LL", "EL", "OL"])
        self.thickness = QSpinBox(); self.thickness.setRange(1, 999); self.thickness.setValue(10)
        self.finish = QLineEdit("S/S")
        self.grade = QComboBox(); self.grade.setEditable(True); self.grade.addItems(["A", "B", "C", "K", "片A", "S"])
        self.sheet_count = QSpinBox(); self.sheet_count.setRange(1, 9999); self.sheet_count.setValue(80)
        self.preview = QLabel()
        grid.addWidget(QLabel("品番"), 0, 0); grid.addWidget(QLabel("サイズ"), 0, 1); grid.addWidget(QLabel("厚み(mm)"), 0, 2)
        grid.addWidget(self.part_code, 1, 0); grid.addWidget(self.size, 1, 1); grid.addWidget(self.thickness, 1, 2)
        grid.addWidget(QLabel("加工 / 裏表"), 2, 0); grid.addWidget(QLabel("グレード"), 2, 1); grid.addWidget(QLabel("枚数"), 2, 2)
        grid.addWidget(self.finish, 3, 0); grid.addWidget(self.grade, 3, 1); grid.addWidget(self.sheet_count, 3, 2); grid.addWidget(self.preview, 4, 0, 1, 3)
        root.addWidget(box)
        for widget in [self.part_code, self.finish]: widget.textChanged.connect(self.update_preview)
        self.size.currentTextChanged.connect(self.update_preview); self.grade.currentTextChanged.connect(self.update_preview)
        self.thickness.valueChanged.connect(self.update_preview); self.sheet_count.valueChanged.connect(self.update_preview)
        self.update_preview()

        add_line_button = QPushButton("明細を追加"); add_line_button.clicked.connect(self.add_line); root.addWidget(add_line_button)
        self.item_table = QTableWidget(0, 2); self.item_table.setHorizontalHeaderLabels(["識別", "高さ(mm)"])
        self.item_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.item_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        root.addWidget(self.item_table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def update_preview(self) -> None:
        part = self.part_code.text().replace("#", "").replace("-", "").strip().upper() or "38"
        finish = self.finish.text().strip() or "S/S"
        grade = self.grade.currentText().strip() or "A"
        self.preview.setText(f"プレビュー: #{part}-{self.size.currentText()}{self.thickness.value()} {finish} {grade} {self.sheet_count.value()}")

    def add_line(self) -> None:
        part = self.part_code.text().replace("#", "").replace("-", "").strip().upper()
        finish = self.finish.text().strip(); grade = self.grade.currentText().strip()
        if len(part) < 2 or len(part) > 3:
            QMessageBox.warning(self, "入力エラー", "品番は2〜3桁の英数字で入力してください。")
            return
        if not finish or not grade:
            QMessageBox.warning(self, "入力エラー", "加工 / 裏表 と グレードを入力してください。")
            return
        item = InventoryItemLine(part_code=part, size=self.size.currentText(), thickness_mm=self.thickness.value(), finish_text=finish, grade=grade, sheet_count=self.sheet_count.value())
        self.items.append(item)
        row = self.item_table.rowCount(); self.item_table.insertRow(row)
        self.item_table.setItem(row, 0, QTableWidgetItem(item.identifier)); self.item_table.setItem(row, 1, QTableWidgetItem(str(item.height_mm)))

    def payload(self) -> Optional[Tuple[str, str, int, List[InventoryItemLine]]]:
        pallet_number = self.pallet_number.text().strip().upper(); location_code = self.location.currentText().strip().upper()
        if not pallet_number or not location_code:
            QMessageBox.warning(self, "入力エラー", "パレット番号とロケーションを入力してください。")
            return None
        if not self.items:
            QMessageBox.warning(self, "入力エラー", "明細を1件以上追加してください。")
            return None
        return pallet_number, location_code, int(self.orientation.currentData()), list(self.items)

    def accept(self) -> None:
        if self.payload() is None:
            return
        super().accept()


class TopMapWidget(QWidget):
    palletSelected = Signal(str)
    palletMoved = Signal(str, float, float, str)

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.selected_pallet = None; self.hover_pallet = None
        self.location_rects: Dict[str, QRect] = {}; self.pallet_rects: Dict[str, QRect] = {}
        self.dragging_pallet = None; self.drag_offset = QPoint(); self.drag_point = QPoint(); self.zoom = 1.0
        self.setMinimumHeight(560); self.setMouseTracking(True)

    def scaled_bounds(self) -> QRect:
        base = self.rect().adjusted(18, 18, -18, -18); center = base.center()
        width = max(200, int(base.width() * self.zoom)); height = max(160, int(base.height() * self.zoom))
        return QRect(center.x() - width // 2, center.y() - height // 2, width, height)

    def draw_grid(self, painter: QPainter, bounds: QRect) -> Tuple[int, int]:
        columns = 30; rows = 22
        painter.setPen(QPen(QColor("#102e4e"), 1, Qt.DotLine))
        for i in range(columns + 1):
            x = bounds.left() + i * bounds.width() / columns; painter.drawLine(int(x), bounds.top(), int(x), bounds.bottom())
        for i in range(rows + 1):
            y = bounds.top() + i * bounds.height() / rows; painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))
        painter.setPen(QPen(QColor("#1a4f80"), 1)); painter.drawRect(bounds)
        return columns, rows

    def compute_location_rects(self, bounds: QRect, columns: int, rows: int) -> Dict[str, QRect]:
        locations = sorted(self.store.locations); prefixes = sorted({parse_location_code(location)[0] for location in locations}) or ["A"]
        prefix_index = {prefix: index for index, prefix in enumerate(prefixes)}; cell_map: Dict[str, QRect] = {}
        cell_w = bounds.width() / columns; cell_h = bounds.height() / rows
        for location in locations:
            prefix, number = parse_location_code(location)
            col = min(columns - 3, prefix_index.get(prefix, 0) * 4 + ((number - 1) % 4))
            row = min(rows - 3, max(0, (number - 1) // 4) * 2)
            cell_map[location] = QRect(int(bounds.left() + col * cell_w), int(bounds.top() + row * cell_h), max(44, int(cell_w * 2.4)), max(36, int(cell_h * 2.0)))
        return cell_map

    def default_point_for_location(self, location: str) -> QPoint:
        rect = self.location_rects.get(location)
        if rect is None:
            bounds = self.scaled_bounds()
            return bounds.center()
        return rect.center()

    def normalized_position(self, point: QPoint) -> Tuple[float, float]:
        bounds = self.scaled_bounds()
        x = 0.5 if bounds.width() <= 0 else (point.x() - bounds.left()) / bounds.width()
        y = 0.5 if bounds.height() <= 0 else (point.y() - bounds.top()) / bounds.height()
        return max(0.02, min(0.98, x)), max(0.02, min(0.98, y))

    def point_from_pallet(self, pallet: PalletRecord) -> QPoint:
        bounds = self.scaled_bounds()
        if pallet.map_x is not None and pallet.map_y is not None:
            x = bounds.left() + int(bounds.width() * pallet.map_x)
            y = bounds.top() + int(bounds.height() * pallet.map_y)
            return QPoint(x, y)
        return self.default_point_for_location(pallet.location_code)

    def nearest_location(self, point: QPoint) -> Optional[str]:
        if not self.location_rects:
            return None
        best_location = None
        best_distance = None
        for location, rect in self.location_rects.items():
            center = rect.center()
            distance = (center.x() - point.x()) ** 2 + (center.y() - point.y()) ** 2
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_location = location
            if rect.adjusted(-18, -18, 18, 18).contains(point):
                return location
        return best_location

    def tooltip_text(self, pallet: PalletRecord) -> str:
        lines = [f"パレット: {pallet.pallet_number}", f"位置: {pallet.location_code} / {pallet.stack_label}", f"向き: {orientation_label(pallet.orientation)}", f"概算高: {pallet.estimated_height_mm}mm"]
        lines.extend(f"- {item.identifier}" for item in pallet.items[:8])
        return "\n".join(lines)

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, rect: QRect) -> None:
        active = pallet.pallet_number in {self.selected_pallet, self.hover_pallet, self.dragging_pallet}
        color = pallet_color(pallet); fill = QColor(color); fill.setAlpha(42)
        painter.setBrush(fill); painter.setPen(QPen(QColor("#a8ecff") if active else color, 2 if active else 1))
        painter.drawRoundedRect(rect, 5, 5); painter.setPen(QColor("#dff6ff")); painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.drawText(rect.adjusted(6, 4, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.pallet_number)
        painter.setFont(QFont("Yu Gothic UI", 7)); painter.drawText(rect.adjusted(6, 18, -6, -6), Qt.AlignTop | Qt.AlignLeft, pallet.summary_text[:24])
        badge = QRect(rect.right() - 20, rect.bottom() - 16, 16, 12)
        painter.setBrush(color); painter.setPen(Qt.NoPen); painter.drawEllipse(badge)
        painter.setPen(QColor("#04111c")); painter.drawText(badge, Qt.AlignCenter, str(pallet.stack_order + 1))

    def paintEvent(self, event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.fillRect(self.rect(), QColor("#07111f"))
        self.location_rects.clear(); self.pallet_rects.clear(); bounds = self.scaled_bounds(); columns, rows = self.draw_grid(painter, bounds)
        for location, rect in self.compute_location_rects(bounds, columns, rows).items():
            self.location_rects[location] = rect; painter.setPen(QColor("#4b7fb3")); painter.setFont(QFont("Consolas", 8)); painter.drawText(rect.adjusted(4, 4, -4, -4), Qt.AlignTop | Qt.AlignLeft, location)
        for pallet in sorted(self.store.pallets, key=lambda p: (p.location_code, p.stack_order, p.pallet_number)):
            width_mm, depth_mm = footprint_mm(pallet)
            base_point = self.point_from_pallet(pallet)
            scale = min(bounds.width() / 42000.0, bounds.height() / 28000.0)
            scale = max(0.012, min(scale, 0.06))
            rect = QRect(base_point.x() - int(width_mm * scale / 2) + pallet.stack_order * 5, base_point.y() - int(depth_mm * scale / 2) - pallet.stack_order * 4, max(18, int(width_mm * scale)), max(14, int(depth_mm * scale)))
            if self.dragging_pallet == pallet.pallet_number:
                rect.moveTo(self.drag_point - self.drag_offset)
            self.pallet_rects[pallet.pallet_number] = rect; self.draw_pallet(painter, pallet, rect)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number; self.dragging_pallet = pallet_number; self.drag_offset = point - rect.topLeft(); self.drag_point = point
                self.palletSelected.emit(pallet_number); self.update(); return

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint(); self.drag_point = point; hit = None
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                hit = pallet_number; break
        self.hover_pallet = hit
        pallet = self.store.get_pallet(hit) if hit else None
        self.setToolTip(self.tooltip_text(pallet) if pallet else "")
        self.setCursor(Qt.PointingHandCursor if hit and not self.dragging_pallet else Qt.ArrowCursor); self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.dragging_pallet:
            return
        point = event.position().toPoint(); destination = self.nearest_location(point)
        map_x, map_y = self.normalized_position(point)
        if destination:
            self.palletMoved.emit(self.dragging_pallet, map_x, map_y, destination)
        self.dragging_pallet = None; self.update()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9))); self.update()

    def zoom_in(self) -> None:
        self.zoom = min(2.8, self.zoom * 1.15); self.update()

    def zoom_out(self) -> None:
        self.zoom = max(0.5, self.zoom / 1.15); self.update()

    def reset_zoom(self) -> None:
        self.zoom = 1.0; self.update()

class IsometricMapWidget(QWidget):
    palletSelected = Signal(str)

    def __init__(self, store: InventoryStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store; self.hover_pallet = None; self.selected_pallet = None; self.pallet_rects: Dict[str, QRect] = {}; self.zoom = 1.0
        self.setMinimumHeight(560); self.setMouseTracking(True)

    def scaled_bounds(self) -> QRect:
        base = self.rect().adjusted(22, 22, -22, -22); center = base.center()
        width = max(220, int(base.width() * self.zoom)); height = max(180, int(base.height() * self.zoom))
        return QRect(center.x() - width // 2, center.y() - height // 2, width, height)

    def draw_floor(self, painter: QPainter, bounds: QRect) -> None:
        cx = bounds.center().x(); cy = bounds.center().y() + 12; hw = bounds.width() * 0.33; hh = bounds.height() * 0.24
        floor = QPolygonF([QPointF(cx, cy - hh), QPointF(cx + hw, cy), QPointF(cx, cy + hh), QPointF(cx - hw, cy)])
        painter.setPen(QPen(QColor("#235f9e"), 2)); painter.drawPolygon(floor); painter.drawLine(QPointF(cx, cy - hh), QPointF(cx, cy + hh)); painter.drawLine(QPointF(cx - hw, cy), QPointF(cx + hw, cy))
        painter.setPen(QPen(QColor("#16385c"), 1))
        for i in range(1, 9):
            t = i / 9.0
            painter.drawLine(QPointF(cx - hw * (1 - t), cy - hh * t), QPointF(cx + hw * t, cy - hh * (1 - t)))
            painter.drawLine(QPointF(cx - hw * t, cy + hh * (1 - t)), QPointF(cx + hw * (1 - t), cy + hh * t))
            painter.drawLine(QPointF(cx - hw * (1 - t), cy + hh * t), QPointF(cx - hw * t, cy - hh * (1 - t)))
            painter.drawLine(QPointF(cx + hw * t, cy - hh * (1 - t)), QPointF(cx + hw * (1 - t), cy + hh * t))

    def draw_pallet(self, painter: QPainter, pallet: PalletRecord, base: QPointF) -> QRect:
        width_mm, depth_mm = footprint_mm(pallet); width = max(18.0, width_mm * 0.022); depth = max(10.0, depth_mm * 0.007); height = max(18.0, min(120.0, pallet.estimated_height_mm * 0.06))
        ox = base.x(); oy = base.y()
        top = QPolygonF([QPointF(ox, oy - height), QPointF(ox + width, oy - height - depth * 0.55), QPointF(ox + width + depth, oy - height), QPointF(ox + depth, oy - height + depth * 0.55)])
        left = QPolygonF([QPointF(ox, oy - height), QPointF(ox + depth, oy - height + depth * 0.55), QPointF(ox + depth, oy + depth * 0.55), QPointF(ox, oy)])
        right = QPolygonF([QPointF(ox + depth, oy - height + depth * 0.55), QPointF(ox + width + depth, oy - height), QPointF(ox + width + depth, oy), QPointF(ox + depth, oy + depth * 0.55)])
        color = pallet_color(pallet); active = pallet.pallet_number in {self.selected_pallet, self.hover_pallet}
        painter.setPen(QPen(QColor("#a2e8ff") if active else QColor("#2b73b2"), 2 if active else 1)); painter.setBrush(QColor(color.darker(135))); painter.drawPolygon(left)
        painter.setBrush(QColor(color.darker(118))); painter.drawPolygon(right); painter.setBrush(color); painter.drawPolygon(top)
        painter.setPen(QColor("#daf5ff")); painter.setFont(QFont("Consolas", 7, QFont.Bold)); painter.drawText(QPointF(ox + 4, oy - height + 13), pallet.pallet_number)
        painter.setFont(QFont("Yu Gothic UI", 6)); painter.drawText(QPointF(ox + 4, oy - height + 24), pallet.summary_text[:14])
        return QRect(int(ox - 2), int(oy - height - depth), int(width + depth + 8), int(height + depth + 10))

    def tooltip_text(self, pallet: PalletRecord) -> str:
        lines = [f"パレット: {pallet.pallet_number}", f"位置: {pallet.location_code} / {pallet.stack_label}", f"向き: {orientation_label(pallet.orientation)}", f"概算高: {pallet.estimated_height_mm}mm"]
        lines.extend(f"- {item.identifier}" for item in pallet.items[:8])
        return "\n".join(lines)

    def paintEvent(self, event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.fillRect(self.rect(), QColor("#07111f")); self.pallet_rects.clear(); bounds = self.scaled_bounds(); self.draw_floor(painter, bounds)
        locations = sorted(self.store.locations); prefixes = sorted({parse_location_code(location)[0] for location in locations}) or ["A"]; prefix_index = {prefix: index for index, prefix in enumerate(prefixes)}
        origin = QPointF(bounds.center().x(), bounds.center().y() + 8); step_x = min(72.0, bounds.width() / 14.0); step_y = min(34.0, bounds.height() / 16.0); points: Dict[str, QPointF] = {}
        for location in locations:
            prefix, number = parse_location_code(location); grid_col = prefix_index.get(prefix, 0) * 4 + ((number - 1) % 4); grid_row = max(0, (number - 1) // 4) * 2
            point = QPointF(origin.x() + (grid_col - grid_row) * step_x, origin.y() + (grid_col + grid_row) * step_y * 0.52)
            points[location] = point; painter.setPen(QColor("#427bb0")); painter.setFont(QFont("Consolas", 7)); painter.drawText(point + QPointF(-14, 18), location)
        for pallet in sorted(self.store.pallets, key=lambda p: (p.location_code, p.stack_order, p.pallet_number)):
            if pallet.map_x is not None and pallet.map_y is not None:
                grid_x = bounds.left() + bounds.width() * pallet.map_x
                grid_y = bounds.top() + bounds.height() * pallet.map_y
                gx = ((grid_x - bounds.left()) / max(bounds.width(), 1)) * 12.0
                gy = ((grid_y - bounds.top()) / max(bounds.height(), 1)) * 12.0
                base = QPointF(origin.x() + (gx - gy) * step_x * 0.55, origin.y() + (gx + gy) * step_y * 0.30)
            else:
                base = points.get(pallet.location_code)
                if base is None:
                    continue
            rect = self.draw_pallet(painter, pallet, QPointF(base.x() + pallet.stack_order * 14, base.y() - pallet.stack_order * 8)); self.pallet_rects[pallet.pallet_number] = rect
        painter.setPen(QColor("#6d90b5")); painter.setFont(QFont("Yu Gothic UI", 9)); painter.drawText(bounds.adjusted(6, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, "45度ビュー")

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint(); hit = None
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                hit = pallet_number; break
        self.hover_pallet = hit; pallet = self.store.get_pallet(hit) if hit else None; self.setToolTip(self.tooltip_text(pallet) if pallet else "")
        self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor); self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        for pallet_number, rect in self.pallet_rects.items():
            if rect.contains(point):
                self.selected_pallet = pallet_number; self.palletSelected.emit(pallet_number); self.update(); return

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.zoom = max(0.5, min(2.8, self.zoom * (1.1 if delta > 0 else 0.9))); self.update()

    def zoom_in(self) -> None:
        self.zoom = min(2.8, self.zoom * 1.15); self.update()

    def zoom_out(self) -> None:
        self.zoom = max(0.5, self.zoom / 1.15); self.update()

    def reset_zoom(self) -> None:
        self.zoom = 1.0; self.update()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.store = load_store(); self.current_pallet_number = None
        self.setWindowTitle("Warehouse Management App - PySide6"); self.resize(1480, 920); self.setMinimumSize(1180, 760)
        self.build_ui(); self.apply_theme(); self.refresh_all()

    def build_ui(self) -> None:
        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central); root.setContentsMargins(14, 14, 14, 14); root.setSpacing(10)
        header = QHBoxLayout(); title = QLabel("WAREHOUSE"); title.setStyleSheet("font:700 18px 'Consolas'; color:#7fd0ff;"); header.addWidget(title)
        self.summary_label = QLabel(); self.summary_label.setStyleSheet("color:#89a4c2;"); header.addWidget(self.summary_label); header.addStretch(1)
        self.new_button = QPushButton("新規登録"); self.new_button.clicked.connect(self.open_registration)
        self.rotate_button = QPushButton("向き変更"); self.rotate_button.clicked.connect(self.rotate_selected_pallet)
        self.zoom_in_button = QPushButton("拡大"); self.zoom_out_button = QPushButton("縮小"); self.zoom_reset_button = QPushButton("等倍")
        self.zoom_in_button.clicked.connect(self.zoom_in_current_view); self.zoom_out_button.clicked.connect(self.zoom_out_current_view); self.zoom_reset_button.clicked.connect(self.reset_zoom_current_view)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("パレット番号 / 品番 / 加工 / ロケーション検索"); self.search_input.textChanged.connect(self.refresh_all)
        export_button = QPushButton("Export"); export_button.clicked.connect(self.export_data); import_button = QPushButton("Import"); import_button.clicked.connect(self.import_data)
        for button in [self.new_button, self.rotate_button, self.zoom_in_button, self.zoom_out_button, self.zoom_reset_button, export_button, import_button]: button.setMinimumHeight(40)
        self.search_input.setMinimumHeight(40)
        for widget in [self.new_button, self.rotate_button, self.zoom_in_button, self.zoom_out_button, self.zoom_reset_button]: header.addWidget(widget)
        header.addWidget(self.search_input, 1); header.addWidget(export_button); header.addWidget(import_button); root.addLayout(header)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self.top_map = TopMapWidget(self.store); self.top_map.palletSelected.connect(self.select_pallet); self.top_map.palletMoved.connect(self.move_pallet); self.tabs.addTab(self.wrap_widget(self.top_map), "真上")
        self.iso_map = IsometricMapWidget(self.store); self.iso_map.palletSelected.connect(self.select_pallet); self.tabs.addTab(self.wrap_widget(self.iso_map), "左下45°")
        self.inventory_table = QTableWidget(0, 10); self.inventory_table.setHorizontalHeaderLabels(["識別", "品番", "サイズ", "厚み", "加工 / 裏表", "グレード", "総枚数", "総高さ", "パレット数", "保管場所"])
        self.inventory_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch); self.tabs.addTab(self.wrap_widget(self.inventory_table), "在庫一覧")
        self.detail_frame = QFrame(); self.detail_frame.setVisible(False); detail_layout = QVBoxLayout(self.detail_frame); detail_layout.setContentsMargins(12, 10, 12, 10)
        self.selection_title_label = QLabel(""); self.selection_title_label.setStyleSheet("font:700 11pt 'Yu Gothic UI'; color:#dff6ff;"); detail_layout.addWidget(self.selection_title_label)
        self.selection_detail_label = QLabel(""); self.selection_detail_label.setWordWrap(True); self.selection_detail_label.setStyleSheet("color:#9fc4e8;"); detail_layout.addWidget(self.selection_detail_label)
        actions = QHBoxLayout(); actions.addStretch(1); clear_button = QPushButton("選択解除"); clear_button.clicked.connect(self.clear_selection); actions.addWidget(clear_button); detail_layout.addLayout(actions)
        root.addWidget(self.detail_frame)

    def wrap_widget(self, widget: QWidget) -> QWidget:
        shell = QWidget(); layout = QVBoxLayout(shell); layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(widget); return shell

    def apply_theme(self) -> None:
        self.setStyleSheet("""QWidget { background:#091522; color:#e7f3ff; font:10pt 'Yu Gothic UI'; } QFrame { background:#0f1d2c; border:1px solid #163450; border-radius:8px; } QLineEdit, QComboBox, QSpinBox, QTableWidget { background:#06101c; color:#f6fbff; border:1px solid #254d77; border-radius:6px; padding:6px; } QPushButton { background:#1d5d99; color:white; border:none; border-radius:8px; padding:8px 14px; font-weight:600; } QPushButton:hover { background:#2675c2; } QHeaderView::section { background:#11253d; color:#9dd9ff; border:none; padding:6px; } QTabWidget::pane { border:1px solid #1a3c60; background:#07111f; } QTabBar::tab { background:#11253d; color:#88c3f0; padding:10px 16px; margin-right:4px; border-top-left-radius:6px; border-top-right-radius:6px; } QTabBar::tab:selected { background:#1d5d99; color:white; }""")

    def filtered_pallets(self) -> List[PalletRecord]:
        keyword = self.search_input.text().strip().lower()
        if not keyword:
            return list(self.store.pallets)
        result = []
        for pallet in self.store.pallets:
            if keyword in pallet.pallet_number.lower() or keyword in pallet.location_code.lower() or any(keyword in item.identifier.lower() or keyword in item.part_code.lower() or keyword in item.finish_text.lower() or keyword in item.grade.lower() for item in pallet.items): result.append(pallet)
        return result

    def refresh_all(self) -> None:
        self.store.ensure_defaults(); self.store.normalize_stacks(); save_store(self.store)
        self.summary_label.setText(f"パレット {len(self.store.pallets)} / 明細 {sum(len(p.items) for p in self.store.pallets)} / 総枚数 {sum(p.total_sheets for p in self.store.pallets)}")
        self.top_map.update(); self.iso_map.update(); self.refresh_inventory_table(); self.refresh_detail()

    def refresh_inventory_table(self) -> None:
        rows: Dict[Tuple[str, str, str, int, str, str], dict] = {}
        for pallet in self.filtered_pallets():
            for item in pallet.items:
                key = (item.identifier, item.part_code, item.size, item.thickness_mm, item.finish_text, item.grade)
                row = rows.setdefault(key, {"identifier": item.identifier, "part_code": item.part_code, "size": item.size, "thickness": item.thickness_mm, "finish": item.finish_text, "grade": item.grade, "sheets": 0, "height": 0, "pallets": set(), "locations": set()})
                row["sheets"] += item.sheet_count; row["height"] += item.height_mm; row["pallets"].add(pallet.pallet_number); row["locations"].add(pallet.location_code)
        ordered = sorted(rows.values(), key=lambda row: (row["part_code"], row["size"], row["thickness"]))
        self.inventory_table.setRowCount(len(ordered))
        for row_index, row in enumerate(ordered):
            for col, value in enumerate([row["identifier"], row["part_code"], row["size"], str(row["thickness"]), row["finish"], row["grade"], str(row["sheets"]), str(row["height"]), str(len(row["pallets"])), ", ".join(sorted(row["locations"]))]): self.inventory_table.setItem(row_index, col, QTableWidgetItem(value))

    def select_pallet(self, pallet_number: str) -> None:
        self.current_pallet_number = pallet_number; self.top_map.selected_pallet = pallet_number; self.iso_map.selected_pallet = pallet_number; self.top_map.update(); self.iso_map.update(); self.refresh_detail()

    def refresh_detail(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            self.detail_frame.setVisible(False); return
        items = [f"{item.identifier} ({item.height_mm}mm)" for item in pallet.items[:6]]
        if len(pallet.items) > 6: items.append(f"... 他{len(pallet.items) - 6}件")
        self.selection_title_label.setText(f"{pallet.pallet_number} を選択中")
        self.selection_detail_label.setText("\n".join([f"位置: {pallet.location_code} / {pallet.stack_label}", f"向き: {orientation_label(pallet.orientation)}", f"概算高: {pallet.estimated_height_mm}mm", f"総枚数: {pallet.total_sheets}", "明細: " + (" / ".join(items) if items else "なし")]))
        self.detail_frame.setVisible(True)

    def move_pallet(self, pallet_number: str, map_x: float, map_y: float, destination: str) -> None:
        pallet = self.store.get_pallet(pallet_number)
        if not pallet: return
        if destination not in self.store.locations: self.store.locations.append(destination)
        moved_between_locations = pallet.location_code != destination
        pallet.location_code = destination; pallet.map_x = map_x; pallet.map_y = map_y
        if moved_between_locations:
            pallet.stack_order = self.store.next_stack_order(destination, pallet.pallet_number)
        pallet.updated_at = now_text(); self.select_pallet(pallet_number); self.refresh_all()

    def rotate_selected_pallet(self) -> None:
        pallet = self.store.get_pallet(self.current_pallet_number or "")
        if not pallet:
            QMessageBox.information(self, "向き変更", "先にパレットを選択してください。")
            return
        pallet.orientation = 90 if pallet.orientation % 180 == 0 else 0; pallet.updated_at = now_text(); self.refresh_all()

    def open_registration(self) -> None:
        dialog = RegistrationDialog(self.store.locations, self)
        if dialog.exec() != QDialog.Accepted: return
        payload = dialog.payload()
        if payload is None: return
        pallet_number, location_code, orientation, items = payload
        if location_code not in self.store.locations: self.store.locations.append(location_code)
        pallet = self.store.get_pallet(pallet_number)
        if pallet is None:
            self.store.pallets.append(PalletRecord(pallet_number=pallet_number, location_code=location_code, stack_order=self.store.next_stack_order(location_code), orientation=orientation, items=items, updated_at=now_text()))
        else:
            pallet.location_code = location_code; pallet.orientation = orientation; pallet.items.extend(items); pallet.stack_order = self.store.next_stack_order(location_code, pallet.pallet_number); pallet.updated_at = now_text()
        self.select_pallet(pallet_number); self.refresh_all()

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


def main() -> int:
    app = QApplication(sys.argv); window = MainWindow(); window.show(); return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
