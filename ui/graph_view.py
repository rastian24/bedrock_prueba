"""Graph view panel: ego-graph of the currently selected note (2-hop)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.vault import Vault
    from core.backlinks import VaultIndex

# ── colours ─────────────────────────────────────────────────────────────────
NODE_DEFAULT_COLOR   = QColor("#7f6df2")
NODE_CURRENT_COLOR   = QColor("#c6b9ff")
NODE_DISTANT_COLOR   = QColor("#4a4a72")   # muted for 2-hop nodes
EDGE_COLOR           = QColor("#444455")
EDGE_DISTANT_COLOR   = QColor("#333344")   # dimmer edges to 2-hop nodes
BG_COLOR             = QColor("#1a1a1a")
LABEL_COLOR          = QColor("#aaaaaa")
LABEL_DISTANT_COLOR  = QColor("#666677")

NODE_RADIUS          = 11
NODE_CURRENT_RADIUS  = 15


# ── layout algorithm ─────────────────────────────────────────────────────────

def _radial_layout(
    center: str,
    level1: list[str],
    level2: list[str],
    width: float,
    height: float,
) -> dict[str, tuple[float, float]]:
    """Two-ring radial layout: center → level1 ring → level2 ring."""
    cx, cy = width / 2, height / 2
    positions: dict[str, tuple[float, float]] = {center: (cx, cy)}

    margin = 50
    max_r = min(width - 2 * margin, height - 2 * margin) / 2

    if level2:
        r1 = max_r * 0.42
        r2 = max_r * 0.88
    else:
        r1 = max_r * 0.88
        r2 = 0.0

    for i, name in enumerate(level1):
        n = len(level1)
        angle = 2 * math.pi * i / n - math.pi / 2
        positions[name] = (cx + r1 * math.cos(angle), cy + r1 * math.sin(angle))

    for i, name in enumerate(level2):
        n = len(level2)
        angle = 2 * math.pi * i / n - math.pi / 2
        positions[name] = (cx + r2 * math.cos(angle), cy + r2 * math.sin(angle))

    return positions


# ── graphics items ────────────────────────────────────────────────────────────

class NodeItem(QGraphicsEllipseItem):
    """A circular node representing one note in the graph."""

    def __init__(self, note_path: Path, label: str, r: float = NODE_RADIUS) -> None:
        super().__init__(-r, -r, r * 2, r * 2)
        self.note_path = note_path
        self._label = label
        self._radius = r
        self._is_current = False

        self.setBrush(QBrush(NODE_DEFAULT_COLOR))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(2)
        self.setToolTip(label)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        # Label below the node
        self._text = QGraphicsTextItem(label, self)
        font = QFont("Inter, Segoe UI, sans-serif", 7)
        self._text.setFont(font)
        self._text.setDefaultTextColor(LABEL_COLOR)
        self._reposition_label()

    def _reposition_label(self) -> None:
        br = self._text.boundingRect()
        self._text.setPos(-br.width() / 2, self._radius + 1)

    def set_current(self, is_current: bool) -> None:
        self._is_current = is_current
        r = NODE_CURRENT_RADIUS if is_current else NODE_RADIUS
        self.setRect(-r, -r, r * 2, r * 2)
        self._radius = r
        if is_current:
            self.setBrush(QBrush(NODE_CURRENT_COLOR))
            self.setPen(QPen(QColor("white"), 1.5))
            self.setZValue(3)
        else:
            self.setBrush(QBrush(NODE_DEFAULT_COLOR))
            self.setPen(QPen(Qt.PenStyle.NoPen))
            self.setZValue(2)
        self._reposition_label()

    def set_distant(self, distant: bool) -> None:
        """Style this node as a 2-hop (distant) neighbor."""
        if not self._is_current:
            self.setBrush(QBrush(NODE_DISTANT_COLOR if distant else NODE_DEFAULT_COLOR))
            self._text.setDefaultTextColor(
                LABEL_DISTANT_COLOR if distant else LABEL_COLOR
            )


# ── canvas (QGraphicsView) ────────────────────────────────────────────────────

class GraphCanvas(QGraphicsView):
    """Interactive graph canvas."""

    node_clicked = Signal(object)  # emits Path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(BG_COLOR))
        self.setScene(self._scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(self.Shape.NoFrame)

        self._nodes: dict[str, NodeItem] = {}   # stem_lower → NodeItem
        self._edges_items: list[QGraphicsLineItem] = []
        self._current_stem: str | None = None

    # ── public API ────────────────────────────────────────────────────────────

    def set_positions(
        self,
        positions: dict[str, tuple[float, float]],
        edges: list[tuple[str, str]],
        name_to_path: dict[str, Path],
        distant_stems: set[str],
    ) -> None:
        """Rebuild the scene from computed positions."""
        self._scene.clear()
        self._nodes.clear()
        self._edges_items.clear()

        # Draw edges first (lower z-value); dim edges that touch a 2-hop node
        normal_pen = QPen(EDGE_COLOR, 1.0)
        normal_pen.setCosmetic(True)
        distant_pen = QPen(EDGE_DISTANT_COLOR, 1.0)
        distant_pen.setCosmetic(True)

        for u, v in edges:
            if u not in positions or v not in positions:
                continue
            x1, y1 = positions[u]
            x2, y2 = positions[v]
            pen = distant_pen if (u in distant_stems or v in distant_stems) else normal_pen
            line = self._scene.addLine(x1, y1, x2, y2, pen)
            line.setZValue(1)
            self._edges_items.append(line)

        # Draw nodes
        for stem, (x, y) in positions.items():
            path = name_to_path.get(stem)
            if path is None:
                continue
            node = NodeItem(path, path.stem)
            node.setPos(x, y)
            if stem in distant_stems:
                node.set_distant(True)
            self._scene.addItem(node)
            self._nodes[stem] = node

        # Re-apply current highlight
        if self._current_stem and self._current_stem in self._nodes:
            self._nodes[self._current_stem].set_current(True)

        self.fitInView(
            self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def highlight_node(self, path: Path) -> None:
        """Highlight the node for the given note path."""
        new_stem = path.stem.lower()

        if self._current_stem and self._current_stem in self._nodes:
            self._nodes[self._current_stem].set_current(False)

        self._current_stem = new_stem

        if new_stem in self._nodes:
            self._nodes[new_stem].set_current(True)

    # ── interaction ───────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if isinstance(item, NodeItem):
                self.node_clicked.emit(item.note_path)
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click on empty area → reset zoom to fit all nodes."""
        item = self.itemAt(event.pos())
        if item is None:
            self.fitInView(
                self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        else:
            super().mouseDoubleClickEvent(event)


# ── top-level widget ──────────────────────────────────────────────────────────

class GraphView(QWidget):
    """Container widget: ego-graph of the current note (2-hop neighbors)."""

    note_clicked = Signal(str)      # emits str(path) to match other panels
    maximize_toggled = Signal(bool)  # True = maximize, False = restore

    _BTN_STYLE = (
        "QPushButton { background: transparent; color: #aaaaaa; border: none;"
        " padding: 0px; margin: 0px; font-size: 15px;"
        " font-family: 'Segoe UI Symbol', 'Noto Sans Symbols', 'DejaVu Sans', sans-serif; }"
        "QPushButton:hover { color: #dcddde; background: transparent; }"
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault: "Vault | None" = None
        self._vault_index: "VaultIndex | None" = None
        self._current_path: Path | None = None
        self._name_to_path: dict[str, Path] = {}
        self._maximized: bool = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header row
        header_row = QWidget()
        header_row.setFixedHeight(32)
        hlayout = QHBoxLayout(header_row)
        hlayout.setContentsMargins(12, 0, 8, 0)

        hlayout.addStretch()

        self._maximize_btn = QPushButton("↗")
        self._maximize_btn.setFixedSize(22, 22)
        self._maximize_btn.setToolTip("Expand graph to editor area")
        self._maximize_btn.setStyleSheet(self._BTN_STYLE)
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        hlayout.addWidget(self._maximize_btn)

        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("Refresh graph layout")
        self._refresh_btn.setStyleSheet(self._BTN_STYLE)
        self._refresh_btn.clicked.connect(self._rebuild)
        hlayout.addWidget(self._refresh_btn)

        layout.addWidget(header_row)

        # Canvas
        self._canvas = GraphCanvas()
        self._canvas.node_clicked.connect(self._on_node_clicked)
        layout.addWidget(self._canvas)

    # ── public API ────────────────────────────────────────────────────────────

    def set_graph(self, vault: "Vault", vault_index: "VaultIndex") -> None:
        """Connect vault + index. Rebuilds if a note is already selected."""
        self._vault = vault
        self._vault_index = vault_index
        self._rebuild()

    def set_current_note(self, path: Path) -> None:
        """Show the 2-hop ego-graph for the given note."""
        self._current_path = path
        self._rebuild()

    # ── maximize / restore ───────────────────────────────────────────────────

    def toggle_maximize(self) -> None:
        """Public entry point — used by keyboard shortcut."""
        self._toggle_maximize()

    def _toggle_maximize(self) -> None:
        self._maximized = not self._maximized
        self._maximize_btn.setText("↙" if self._maximized else "↗")
        self._maximize_btn.setToolTip(
            "Restore to sidebar" if self._maximized else "Expand graph to editor area"
        )
        self.maximize_toggled.emit(self._maximized)

    def _on_node_clicked(self, path: Path) -> None:
        if self._maximized:
            self._maximized = False
            self._maximize_btn.setText("↗")
            self._maximize_btn.setToolTip("Expand graph to editor area")
            self.maximize_toggled.emit(False)
        self.note_clicked.emit(str(path))

    # ── internal ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        if self._vault is None or self._vault_index is None:
            return
        if self._current_path is None:
            self._canvas.set_positions({}, [], {}, set())
            return

        all_links = self._vault_index.get_all_outgoing_links()
        all_notes = self._vault.list_notes()

        name_to_path: dict[str, Path] = {note.stem.lower(): note for note in all_notes}
        self._name_to_path = name_to_path

        current_stem = self._current_path.stem.lower()
        if current_stem not in name_to_path:
            self._canvas.set_positions({}, [], {}, set())
            return

        # Level 1: direct neighbors (outgoing + incoming)
        level1: set[str] = set()
        for src_path, targets in all_links.items():
            src_stem = src_path.stem.lower()
            if src_stem == current_stem:
                for tgt in targets:
                    if tgt in name_to_path and tgt != current_stem:
                        level1.add(tgt)
            elif current_stem in targets and src_stem in name_to_path:
                level1.add(src_stem)

        # Level 2: neighbors of level1, not already in level0/level1
        level2: set[str] = set()
        for src_path, targets in all_links.items():
            src_stem = src_path.stem.lower()
            if src_stem in level1:
                for tgt in targets:
                    if tgt in name_to_path and tgt != current_stem and tgt not in level1:
                        level2.add(tgt)
            elif src_stem in name_to_path and src_stem != current_stem and src_stem not in level1:
                for tgt in targets:
                    if tgt in level1:
                        level2.add(src_stem)
                        break

        visible = {current_stem} | level1 | level2

        # Build edges between all visible nodes
        edges: list[tuple[str, str]] = []
        seen: set[frozenset] = set()
        for src_path, targets in all_links.items():
            src_stem = src_path.stem.lower()
            if src_stem not in visible:
                continue
            for tgt in targets:
                if tgt not in visible:
                    continue
                key = frozenset([src_stem, tgt])
                if key not in seen:
                    edges.append((src_stem, tgt))
                    seen.add(key)

        w = max(self._canvas.width(), 400)
        h = max(self._canvas.height(), 300)

        positions = _radial_layout(
            current_stem,
            sorted(level1),
            sorted(level2),
            float(w),
            float(h),
        )

        self._canvas._current_stem = current_stem
        self._canvas.set_positions(positions, edges, name_to_path, level2)
