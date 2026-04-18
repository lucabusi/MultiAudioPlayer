import sys
import os
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QWidget, QGridLayout, QScrollArea, QMessageBox, QAction
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPen
from mp3file import Mp3File
from mp3widget import Mp3Widget
from utils import WidgetLayout
from project_manager import ProjectManager
from grid_manager import GridManager


class _HighlightOverlay(QWidget):
    """Transparent overlay that draws the drop-target highlight on top of all grid children."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self._rect = None

    def set_highlight(self, rect):
        self._rect = rect
        self.update()

    def clear_highlight(self):
        if self._rect is not None:
            self._rect = None
            self.update()

    def paintEvent(self, event):
        if self._rect is None:
            return
        painter = QPainter(self)
        painter.fillRect(self._rect, QColor(80, 200, 80, 70))
        painter.setPen(QPen(QColor(60, 180, 60), 2))
        painter.drawRect(self._rect.adjusted(1, 1, -2, -2))
        painter.end()


class _DropContainer(QWidget):
    """QWidget subclass with proper drag/drop override and cell-highlight feedback."""

    def __init__(self, on_drag_enter, on_get_target_rect, on_drop):
        super().__init__()
        self._on_drag_enter = on_drag_enter
        self._on_get_target_rect = on_get_target_rect
        self._on_drop = on_drop
        self.setAcceptDrops(True)
        self._overlay = _HighlightOverlay(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()

    def dragEnterEvent(self, event):
        self._on_drag_enter(event)

    def dragMoveEvent(self, event):
        rect = self._on_get_target_rect(event.pos())
        if rect is not None:
            self._overlay.set_highlight(rect)
            event.acceptProposedAction()
        else:
            self._overlay.clear_highlight()
            event.ignore()

    def dragLeaveEvent(self, event):
        self._overlay.clear_highlight()

    def dropEvent(self, event):
        self._overlay.clear_highlight()
        self._on_drop(event)


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.mp3_widgets = []
        self.logger = logging.getLogger(__name__)
        self.project_manager = ProjectManager()

        self.initial_rows = 5
        self.initial_cols = 2
        self.backend = 'mpv'

#       self.backend = 'vlc'        # default
#       self.backend = 'gstreamer'
#       self.backend = 'mpv'

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('MultiPlayer Eden Edition')
        self.setGeometry(100, 100, 1080, 600)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        open_file_action = QAction("Open MP3 Files", self)
        open_file_action.triggered.connect(self.open_files)
        file_menu.addAction(open_file_action)
        save_project_action = QAction("Save Project", self)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        load_project_action = QAction("Load Project", self)
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.container_widget = _DropContainer(
            self._on_container_drag_enter,
            self._get_drop_target_rect,
            self._on_container_drop,
        )
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        self.grid_manager = GridManager(self.grid_layout, self.initial_cols)

        for r in range(self.initial_rows):
            self.grid_layout.setRowStretch(r, 1)

        self.container_widget.setLayout(self.grid_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.container_widget)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)

        # Set up initial column layout (all empty at startup)
        self.grid_manager.update_column_stretches()

        self.show()

    def _on_container_drag_enter(self, event):
        from mp3widget import Mp3WidgetMimeData
        if isinstance(event.mimeData(), Mp3WidgetMimeData):
            event.acceptProposedAction()

    def _get_drop_target_rect(self, pos):
        """Return the cellRect for the cell under pos, or None if outside the grid."""
        r, c = self.grid_manager.get_cell_at_pos(pos)
        if r == -1:
            return None
        return self.grid_layout.cellRect(r, c)

    def _on_container_drop(self, event):
        from mp3widget import Mp3WidgetMimeData
        if not isinstance(event.mimeData(), Mp3WidgetMimeData):
            event.ignore()
            return

        source_widget = event.mimeData().getWidget()
        target_pos = event.pos()
        target_row, target_col = self.grid_manager.get_cell_at_pos(target_pos)
        if target_row == -1:
            event.ignore()
            return

        item = self.grid_layout.itemAtPosition(target_row, target_col)

        if item and item.widget() != source_widget:
            displaced_widget = item.widget()
            self.logger.info(f"Cell ({target_row}, {target_col}) is occupied by {os.path.basename(displaced_widget.mp3file.file_name)}. Finding new spot.")
            new_row, new_col = self.grid_manager.find_nearest_free_cell(target_row, target_col)
            if new_row != -1:
                self.logger.info(f"Moving displaced widget to ({new_row}, {new_col}).")
                self.grid_layout.removeWidget(displaced_widget)
                self.grid_layout.addWidget(displaced_widget, new_row, new_col)
            else:
                self.logger.warning("Could not find a free cell for the displaced widget. Aborting drop.")
                event.ignore()
                return

        self.logger.info(f"Moving {os.path.basename(source_widget.mp3file.file_name)} to ({target_row}, {target_col}).")
        self.grid_layout.removeWidget(source_widget)
        self.grid_layout.addWidget(source_widget, target_row, target_col)
        self.grid_manager.update_column_stretches()
        event.acceptProposedAction()

    def open_files(self):
        options = QFileDialog.Options()
        file_names, _ = QFileDialog.getOpenFileNames(self, "Open MP3 Files", "", "MP3 Files (*.mp3)", options=options)
        for file_name in file_names:
            if file_name:
                row, col = self.grid_manager.find_next_available_cell()
                if row == -1:
                    QMessageBox.warning(self, "Grid Full", "The layout grid is full. Cannot add more files.")
                    break

                mp3_audio_file = Mp3File(file_name, backend=self.backend)
                mp3_widget = Mp3Widget(mp3_audio_file)
                mp3_widget.remove_requested.connect(lambda w=mp3_widget: self.remove_widget(w))

                self.mp3_widgets.append(mp3_widget)
                self.grid_layout.addWidget(mp3_widget, row, col)
                self.grid_manager.update_column_stretches()

    def save_project(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Project Files (*.mpp)", options=options)

        if file_name:
            try:
                self.project_manager.save(self.mp3_widgets, self.grid_layout, self.geometry(), file_name)
                self.logger.info(f"Project saved successfully to {file_name}")
            except Exception as e:
                self.logger.error(f"Error saving project: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")

    def load_project(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Project Files (*.mpp)", options=options)

        if file_name:
            try:
                project_data = self.project_manager.load(file_name)

                self.clear_layout()

                if 'grid_state' in project_data:
                    rows = project_data['grid_state'].get('rows', self.initial_rows)
                    for r in range(rows):
                        self.grid_layout.setRowStretch(r, 1)

                successful_loads = []
                for file_data in project_data['files']:
                    try:
                        if not os.path.exists(file_data['file_path']):
                            raise FileNotFoundError(f"File not found: {file_data['file_path']}")

                        mp3_audio_file = Mp3File(file_data['file_path'], backend=self.backend)
                        layout = WidgetLayout[file_data.get('layout', 'TOUCH')]
                        mp3_widget = Mp3Widget(mp3_audio_file, layout=layout)
                        mp3_widget.remove_requested.connect(lambda w=mp3_widget: self.remove_widget(w))
                        mp3_widget.set_volume(file_data['volume'])
                        mp3_widget.set_fade_time(file_data['fade_time'])

                        row = file_data.get('row', -1)
                        col = file_data.get('col', -1)
                        successful_loads.append((mp3_widget, row, col))

                    except Exception as e:
                        self.logger.error(f"Error loading file {file_data['file_path']}: {e}")
                        QMessageBox.warning(self, "Warning", f"Error loading file {os.path.basename(file_data['file_path'])}: {str(e)}")

                for widget, row, col in successful_loads:
                    self.mp3_widgets.append(widget)
                    if row != -1 and col != -1:
                        self.grid_layout.addWidget(widget, row, col)
                    else:
                        r, c = self.grid_manager.find_next_available_cell()
                        self.grid_layout.addWidget(widget, r, c)
                self.grid_manager.update_column_stretches()

                self.logger.info(f"Project loaded successfully from {file_name}")

                if 'window_state' in project_data:
                    ws = project_data['window_state']
                    screen = QApplication.primaryScreen().geometry()
                    x = min(max(0, ws['x']), screen.width() - ws['width'])
                    y = min(max(0, ws['y']), screen.height() - ws['height'])
                    self.setGeometry(x, y, ws['width'], ws['height'])
            except Exception as e:
                self.logger.error(f"Error loading project data: {e}")
                QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")

    def clear_layout(self):
        for widget in self.mp3_widgets:
            widget.mp3file.cleanup()
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
        self.mp3_widgets.clear()
        self.grid_manager.update_column_stretches()

    def remove_widget(self, widget):
        if widget in self.mp3_widgets:
            self.mp3_widgets.remove(widget)
            self.grid_layout.removeWidget(widget)
            self.logger.info(f"Removed widget for {os.path.basename(widget.mp3file.file_name)}.")
            self.grid_manager.update_column_stretches()


def run_app():
    app = QApplication(sys.argv)
    main_app = MainApp()
    return app, main_app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app, main_app = run_app()
    sys.exit(app.exec_())
