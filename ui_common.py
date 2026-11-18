# -*- coding: utf-8 -*-
"""ما تشترك فيه نوافذ الأدوات كلّها (الاستوديو، تطبيق جديد، محرّر النصوص، الرفع، البناء والرفع).

install_wheel_guard(app): عجلة الفأرة لا تغيّر خيارًا. حين يمرّ المؤشّر على قائمة منسدلة أو خانة أرقام أو منزلق أو شريط
تبويبات أثناء تمرير الصفحة، تذهب حركة العجلة إلى منطقة التمرير التي تحويها (فتُمرَّر الصفحة) ولا تتغيّر قيمة العنصر.
القيمة تُغيَّر بالنقر أو بلوحة المفاتيح فقط. يُستدعى مرّة واحدة بعد إنشاء QApplication في كل أداة.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QSlider, QTabBar

GUARDED = (QComboBox, QAbstractSpinBox, QSlider, QTabBar)

# أثر الضغط على الأزرار وشكل التلميح (شرح الزرّ عند التأشير عليه). يُلحق بورقة أنماط كل نافذة: STYLE + FEEDBACK_CSS
# (ورقة النافذة تغلب ورقة التطبيق، فلا يكفي وضعه على QApplication).
FEEDBACK_CSS = """
QPushButton:pressed, QToolButton:pressed { background:#1b2024; border:2px solid #5fd08a; color:#c9f5dc; }
QPushButton#primary:pressed, QPushButton:checked:pressed { background:#1d6b52; border:2px solid #c9f5dc; }
QPushButton:hover, QToolButton:hover { border-color:#7d8791; }
QToolTip { background:#fff8dc; color:#1b1b1b; border:1px solid #b8a15a; padding:6px; font-size:13px; }
"""


class WheelGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel or not isinstance(watched, GUARDED):
            return False
        if isinstance(watched, QComboBox) and watched.view().isVisible():
            return False                       # القائمة مفتوحة: العجلة تمرّر عناصرها
        parent = watched.parentWidget()
        while parent is not None:              # أقرب منطقة تمرير تحوي العنصر تأخذ الحركة
            if isinstance(parent, QAbstractScrollArea):
                QApplication.sendEvent(parent.viewport(), event)
                break
            parent = parent.parentWidget()
        event.accept()
        return True


def install_wheel_guard(app: QApplication) -> None:
    if getattr(app, "_wheel_guard", None) is None:
        app._wheel_guard = WheelGuard(app)
        app.installEventFilter(app._wheel_guard)
