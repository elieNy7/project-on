from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QStyle


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=-1, hSpacing=-1, vSpacing=-1):
        super().__init__(parent)
        # heightForWidth is asked many times per resize; each answer walks
        # every item (a styled button's sizeHint is costly). Cached per width.
        self._hfw_cache: dict[int, int] = {}
        self._hints: list[QSize] | None = None  # item size hints, same reason
        self.itemList = []
        if margin != -1:
            self.setContentsMargins(margin, margin, margin, margin)
        self.m_hSpace = hSpacing
        self.m_vSpace = vSpacing

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)
        self._forget_sizes()

    def invalidate(self):
        self._forget_sizes()
        super().invalidate()

    def _forget_sizes(self):
        self._hfw_cache.clear()
        self._hints = None

    def horizontalSpacing(self):
        if self.m_hSpace >= 0:
            return self.m_hSpace
        return self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self.m_vSpace >= 0:
            return self.m_vSpace
        return self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            self._forget_sizes()
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._hfw_cache.get(width)
        if height is None:
            height = self.doLayout(QRect(0, 0, width, 0), True)
            self._hfw_cache[width] = height
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        spaceX = self.m_hSpace
        spaceY = self.m_vSpace
        if self._hints is None or len(self._hints) != len(self.itemList):
            self._hints = [item.sizeHint() for item in self.itemList]
        for item, hint in zip(self.itemList, self._hints):
            nextX = x + hint.width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + hint.width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = nextX
            lineHeight = max(lineHeight, hint.height())

        return y + lineHeight - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        if parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        return parent.spacing()
