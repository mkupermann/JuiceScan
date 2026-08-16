"""Interaktiver Rahmen-Editor: Rechtecke auf dem Scan ziehen, verschieben,
löschen. Koordinaten sind Bildpixel, unabhängig von der Anzeige-Skalierung."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView)

MIN_SIZE = 12          # Bildpixel, kleinere Ziehversuche werden verworfen
PEN = QPen(QColor(255, 80, 40), 0)
PEN.setCosmetic(True)
PEN.setWidth(2)


class FrameEditor(QGraphicsView):
    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pix_item = None
        self._draft = None
        self._origin = None
        self.setRenderHint(self.renderHints())

    # --- API --------------------------------------------------------------
    def set_image(self, pixmap: QPixmap):
        self._scene.clear()
        self._pix_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pix_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def set_frames(self, boxes):
        for x, y, w, h in boxes:
            self._add_rect(QRectF(x, y, w, h))

    def frames(self):
        out = []
        for item in self._scene.items():
            if isinstance(item, QGraphicsRectItem):
                r = item.mapRectToScene(item.rect())
                out.append((int(r.x()), int(r.y()),
                            int(r.width()), int(r.height())))
        return sorted(out, key=lambda b: (b[1], b[0]))

    def clear_frames(self):
        for item in list(self._scene.items()):
            if isinstance(item, QGraphicsRectItem):
                self._scene.removeItem(item)

    # --- intern -----------------------------------------------------------
    def _add_rect(self, rect: QRectF):
        item = QGraphicsRectItem(rect)
        item.setPen(PEN)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        return item

    # --- Interaktion ------------------------------------------------------
    def mousePressEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        hit = self.itemAt(event.position().toPoint())
        if isinstance(hit, QGraphicsRectItem):
            super().mousePressEvent(event)
            return
        if self._pix_item is not None:
            self._origin = pos
            self._draft = self._add_rect(QRectF(pos, pos))
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._draft is not None:
            pos = self.mapToScene(event.position().toPoint())
            self._draft.setRect(QRectF(self._origin, pos).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._draft is not None:
            r = self._draft.rect()
            if r.width() < MIN_SIZE or r.height() < MIN_SIZE:
                self._scene.removeItem(self._draft)
            self._draft = None
            self._origin = None
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            for item in self._scene.selectedItems():
                self._scene.removeItem(item)
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pix_item is not None:
            self.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
