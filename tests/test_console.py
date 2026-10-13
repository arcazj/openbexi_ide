from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from openbexi_ide.console import OutputConsole


def test_running_input_routing_preserves_read_only_copy_and_disabled_input(app):
    console, target = OutputConsole(), QLineEdit()
    console.input_target = target
    console.show(); target.show()
    try:
        console.append_output('Choose: ')
        console.setFocus()
        QTest.keyClicks(console, '42')
        assert target.text() == '42' and console.toPlainText() == 'Choose: '
        QTest.keyClick(console, Qt.Key_Backspace)
        assert target.text() == '4'
        sent = []
        target.returnPressed.connect(lambda: sent.append(target.text()))
        QTest.keyClick(console, Qt.Key_Return)
        assert sent == ['4']
        console.selectAll()
        QTest.keyClick(console, Qt.Key_C, Qt.ControlModifier)
        assert QApplication.clipboard().text() == 'Choose: '
        assert target.text() == '4' and console.textCursor().hasSelection()
        target.setEnabled(False)
        QTest.keyClicks(console, '6')
        QTest.keyClick(console, Qt.Key_Return)
        assert target.text() == '4' and sent == ['4']
        assert console.toPlainText() == 'Choose: '
    finally:
        console.close(); target.close()


def test_read_select_scroll_and_resume_during_output(app):
    console = OutputConsole()
    console.resize(640, 160)
    console.show()
    try:
        console.append_output(''.join(f'line {i:04d}\n' for i in range(300)))
        app.processEvents()
        bar = console.verticalScrollBar()
        assert bar.maximum() > 100 and bar.value() == bar.maximum()
        console.setFocus()
        QTest.keyClick(console, Qt.Key_PageUp)
        app.processEvents()
        assert bar.value() < bar.maximum()
        cursor = QTextCursor(console.document().findBlockByNumber(40))
        cursor.select(QTextCursor.LineUnderCursor)
        console.setTextCursor(cursor)
        bar.setValue(35)
        before = bar.value()
        for i in range(300, 350):
            console.append_output(f'line {i:04d}\n')
            app.processEvents()
        assert console.textCursor().selectedText() == 'line 0040'
        assert bar.value() == before
        bar.setValue(50)
        console.append_output('still reading\n')
        assert bar.value() == 50
        console.show_latest()
        console.append_output('newest\n')
        assert not console.textCursor().hasSelection()
        assert bar.value() == bar.maximum()
    finally:
        console.close()


def test_trimming_preserves_retained_selection_and_bounds_memory(app):
    console = OutputConsole()
    console.resize(640, 160)
    console.show()
    try:
        console.setMaximumBlockCount(100)
        console.append_output(''.join(f'line {i:04d}\n' for i in range(99)))
        app.processEvents()
        cursor = QTextCursor(console.document().findBlockByNumber(50))
        cursor.select(QTextCursor.LineUnderCursor)
        console.setTextCursor(cursor)
        console.verticalScrollBar().setValue(45)
        visible = console.firstVisibleBlock().text()
        console.append_output(''.join(f'line {i:04d}\n' for i in range(99, 109)))
        assert console.document().blockCount() == 100
        assert console.textCursor().selectedText() == 'line 0050'
        assert console.firstVisibleBlock().text() == visible
        console.show_latest()
        console.append_output('x' * 600_000 + 'TAIL')
        assert console.document().characterCount() <= 500_000
        assert console.toPlainText().endswith('TAIL')
    finally:
        console.close()


def test_wrapped_history_stays_at_the_same_text_when_old_blocks_expire(app):
    console = OutputConsole()
    console.resize(400,160)
    console.setMaximumBlockCount(100)
    console.show()
    try:
        console.append_output(''.join(f'line {i:04d} ' + 'long output ' * 20 + '\n' for i in range(99)))
        app.processEvents()
        bar = console.verticalScrollBar()
        bar.setValue(bar.maximum() // 2)
        app.processEvents()
        visible = console.firstVisibleBlock().text()
        offset = console.blockBoundingGeometry(console.firstVisibleBlock()).translated(console.contentOffset()).top()
        console.append_output(''.join('new wrapped output ' * 20 + '\n' for _ in range(10)))
        app.processEvents()
        assert console.firstVisibleBlock().text() == visible
        assert console.blockBoundingGeometry(console.firstVisibleBlock()).translated(console.contentOffset()).top() == offset
    finally:
        console.close()
