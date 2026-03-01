"""Graph view panel: interactive node-link diagram of vault note connections."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    Qt,
    QThread,
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
    QLabel,
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
NODE_ISOLATED_COLOR  = QColor("#555566")
EDGE_COLOR           = QColor("#444455")
BG_COLOR             = QColor("#1a1a1a")
LABEL_COLOR          = QColor("#aaaaaa")

NODE_RADIUS          = 7
NODE_CURRENT_RADIUS  = 10


# ── layout algorithm ─────────────────────────────────────────────────────────

def _fruchterman_reingold(
    node_names: list[str],
    edges: list[tuple[str, str]],
    width: float,
    height: float,
    iterations: int = 150,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """Force-directed layout (Fruchterman-Reingold).

    Returns a dict mapping node name → (x, y) within [0, width] × [0, height].
    """
    n = len(node_names)
    if n == 0:
        return {}
    if n == 1:
        return {node_names[0]: (width / 2, height / 2)}

    rng = random.Random(seed)
    pos: dict[str, list[float]] = {
        name: [rng.uniform(width * 0.1, width * 0.9),
               rng.uniform(height * 0.1, height * 0.9)]
        for name in node_names
    }

    # Ideal edge length
    area = width * height
    k = math.sqrt(area / n)

    # Adaptive iteration count for large vaults
    iters = min(iterations, max(50, 300 - n))

    temperature = width / 10.0
    cooling = temperature / (iters + 1)

    name_list = node_names  # stable order

    for _ in range(iters):
        disp: dict[str, list[float]] = {name: [0.0, 0.0] for name in name_list}

        # Repulsion (all pairs)
        for i in range(n):
            u = name_list[i]
            for j in range(i + 1, n):
                v = name_list[j]
                dx = pos[u][0] - pos[v][0]
                dy = pos[u][1] - pos[v][1]
                dist = math.sqrt(dx * dx + dy * dy) or 0.01
                force = k * k / dist
                nx, ny = dx / dist * force, dy / dist * force
                disp[u][0] += nx
                disp[u][1] += ny
                disp[v][0] -= nx
                disp[v][1] -= ny

        # Attraction (edges)
        for u, v in edges:
            if u not in pos or v not in pos:
                continue
            dx = pos[u][0] - pos[v][0]
            dy = pos[u][1] - pos[v][1]
            dist = math.sqrt(dx * dx + dy * dy) or 0.01
            force = dist * dist / k
            nx, ny = dx / dist * force, dy / dist * force
            disp[u][0] -= nx
            disp[u][1] -= ny
            disp[v][0] += nx
            disp[v][1] += ny

        # Apply displacement with cooling
        for name in name_list:
            dx, dy = disp[name]
            dist = math.sqrt(dx * dx + dy * dy) or 0.01
            scale = min(dist, temperature) / dist
            pos[name][0] = max(20.0, min(width - 20.0,  pos[name][0] + dx * scale))
            pos[name][1] = max(20.0, min(height - 20.0, pos[name][1] + dy * scale))

        temperature -= cooling

    return {name: (pos[name][0], pos[name][1]) for name in name_list}


# ── worker thread ─────────────────────────────────────────────────────────────

class GraphLayoutWorker(QThread):
    """Runs the layout algorithm in a background thread."""

    layout_ready = Signal(dict, list)  # positions dict, edges list

    def __init__(
        self,
        node_names: list[str],
        edges: list[tuple[str, str]],
        width: float,
        height: float,
    ) -> None:
        super().__init__()
        self._node_names = node_names
        self._edges = edges
        self._width = width
        self._height = height

    def run(self) -> None:
        positions = _fruchterman_reingold(
            self._node_names,
            self._edges,
            self._width,
            self._height,
        )
        self.layout_ready.emit(positions, self._edges)


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

    def set_isolated(self, isolated: bool) -> None:
        if not self._is_current:
            color = NODE_ISOLATED_COLOR if isolated else NODE_DEFAULT_COLOR
            self.setBrush(QBrush(color))


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
        self._edges: list[tuple[str, str]] = []

    # ── public API ────────────────────────────────────────────────────────────

    def set_positions(
        self,
        positions: dict[str, tuple[float, float]],
        edges: list[tuple[str, str]],
        name_to_path: dict[str, Path],
    ) -> None:
        """Rebuild the scene from computed positions."""
        self._scene.clear()
        self._nodes.clear()
        self._edges_items.clear()
        self._edges = edges

        # Determine isolated nodes (no connections)
        connected: set[str] = set()
        for u, v in edges:
            connected.add(u)
            connected.add(v)

        # Draw edges first (lower z-value)
        edge_pen = QPen(EDGE_COLOR, 1.0)
        edge_pen.setCosmetic(True)
        for u, v in edges:
            if u not in positions or v not in positions:
                continue
            x1, y1 = positions[u]
            x2, y2 = positions[v]
            line = self._scene.addLine(x1, y1, x2, y2, edge_pen)
            line.setZValue(1)
            self._edges_items.append(line)

        # Draw nodes
        for stem, (x, y) in positions.items():
            path = name_to_path.get(stem)
            if path is None:
                continue
            label = path.stem
            node = NodeItem(path, label)
            node.setPos(x, y)
            if stem not in connected:
                node.set_isolated(True)
            self._scene.addItem(node)
            self._nodes[stem] = node

        # Re-apply current highlight
        if self._current_stem and self._current_stem in self._nodes:
            self._nodes[self._current_stem].set_current(True)

        self.fitInView(
            self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def highlight_node(self, path: Path) -> None:
        """Highlight the node for the given note path."""
        new_stem = path.stem.lower()

        # Reset previous
        if self._current_stem and self._current_stem in self._nodes:
            self._nodes[self._current_stem].set_current(False)

        self._current_stem = new_stem

        if new_stem in self._nodes:
            node = self._nodes[new_stem]
            node.set_current(True)
            # Smoothly scroll to show the node
            self.ensureVisible(node, 40, 40)

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
                self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        else:
            super().mouseDoubleClickEvent(event)


# ── top-level widget ──────────────────────────────────────────────────────────

class GraphView(QWidget):
    """Container widget: header + GraphCanvas."""

    note_clicked = Signal(str)  # emits str(path) to match other panels

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vault: "Vault | None" = None
        self._vault_index: "VaultIndex | None" = None
        self._worker: GraphLayoutWorker | None = None
        self._name_to_path: dict[str, Path] = {}
        self._pending_edges: list[tuple[str, str]] = []

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

        title = QLabel("GRAPH")
        title.setObjectName("section_header")
        hlayout.addWidget(title)
        hlayout.addStretch()

        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("Refresh graph layout")
        self._refresh_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999999; border: none; font-size: 14px; }"
            "QPushButton:hover { color: #dcddde; }"
        )
        self._refresh_btn.clicked.connect(self._rebuild)
        hlayout.addWidget(self._refresh_btn)

        layout.addWidget(header_row)

        # Canvas
        self._canvas = GraphCanvas()
        self._canvas.node_clicked.connect(lambda p: self.note_clicked.emit(str(p)))
        layout.addWidget(self._canvas)

    # ── public API ────────────────────────────────────────────────────────────

    def set_graph(self, vault: "Vault", vault_index: "VaultIndex") -> None:
        """Build graph from vault + index data. Runs layout in background."""
        self._vault = vault
        self._vault_index = vault_index
        self._rebuild()

    def set_current_note(self, path: Path) -> None:
        """Highlight the node corresponding to the currently open note."""
        self._canvas.highlight_node(path)

    # ── internal ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        if self._vault is None or self._vault_index is None:
            return

        # Stop any running worker
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)

        # Build node + edge data from index
        all_links = self._vault_index.get_all_outgoing_links()
        all_notes = self._vault.list_notes()

        # name_to_path: stem_lower → Path (only real notes in the vault)
        name_to_path: dict[str, Path] = {
            note.stem.lower(): note for note in all_notes
        }
        self._name_to_path = name_to_path

        node_names = list(name_to_path.keys())

        # Edges: only between notes that actually exist in the vault
        edges: list[tuple[str, str]] = []
        seen_edges: set[frozenset] = set()
        for src_path, targets in all_links.items():
            src_stem = src_path.stem.lower()
            if src_stem not in name_to_path:
                continue
            for tgt_stem in targets:
                if tgt_stem not in name_to_path:
                    continue
                key = frozenset([src_stem, tgt_stem])
                if key not in seen_edges:
                    edges.append((src_stem, tgt_stem))
                    seen_edges.add(key)

        self._pending_edges = edges

        if not node_names:
            self._canvas.set_positions({}, [], {})
            return

        # Canvas size for layout (use actual widget size, fallback to 600×400)
        w = max(self._canvas.width(), 400)
        h = max(self._canvas.height(), 300)

        self._worker = GraphLayoutWorker(node_names, edges, float(w), float(h))
        self._worker.layout_ready.connect(self._on_layout_ready)
        self._worker.start()

    def _on_layout_ready(
        self,
        positions: dict[str, tuple[float, float]],
        edges: list[tuple[str, str]],
    ) -> None:
        self._canvas.set_positions(positions, edges, self._name_to_path)
