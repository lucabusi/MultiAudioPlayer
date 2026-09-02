import sys
import os
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QWidget, QGridLayout, QScrollArea, QMessageBox, QAction, QActionGroup
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QPainter, QColor, QPen
from mp3file import Mp3File, available_backends
from audio_warmup import AudioWarmup
from mp3widget import Mp3Widget, WidgetLayout
from project_manager import ProjectManager
from grid_manager import GridManager
from constants import (APP_VERSION, POLL_INTERVAL_MS, DEFAULT_BACKEND,
                       SETTINGS_ORG, SETTINGS_APP, SETTINGS_BACKEND_KEY)

logger = logging.getLogger(__name__)


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
        self.project_manager = ProjectManager()

        self.initial_rows = 5
        self.initial_cols = 2
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.backend = self._load_backend_preference()

        self.init_ui()

        # Tiene sveglio l'endpoint audio: senza, il PRIMO play dopo l'avvio
        # (o dopo un lungo idle) parte con 1-2s di ritardo su alcuni output
        # (HDMI/Bluetooth/USB) e l'attacco della cue va perso.
        self._audio_warmup = AudioWarmup(self)

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.start(POLL_INTERVAL_MS)

    def _tick_progress(self):
        for widget in self.mp3_widgets:
            try:
                widget.update_progress_bar()
            except Exception as e:
                # Stesso motivo di Mp3Widget._report_playback_error: un'eccezione
                # che esce da uno slot Qt fa abortire il processo. Un widget con
                # il backend rotto non deve fermare il poll degli altri; il poll
                # gira a 20Hz, quindi si logga una volta sola per widget.
                if not getattr(widget, '_poll_error_logged', False):
                    widget._poll_error_logged = True
                    logger.error(f"Progress poll failed for {widget.mp3file.file_name}: {e}")

    def init_ui(self):
        self.setWindowTitle(f'MultiPlayer Eden Edition {APP_VERSION}')
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

        tools_menu = menubar.addMenu("Strumenti")
        normalize_all_action = QAction("Normalize All", self)
        normalize_all_action.triggered.connect(self.normalize_all)
        tools_menu.addAction(normalize_all_action)

        config_menu = menubar.addMenu("Configura")
        self.backend_menu = config_menu.addMenu("Backend audio")
        self._backend_group = QActionGroup(self)
        self._backend_group.setExclusive(True)
        for name in available_backends():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == self.backend)
            action.triggered.connect(lambda _checked, n=name: self.set_backend(n))
            self._backend_group.addAction(action)
            self.backend_menu.addAction(action)

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

    def _load_backend_preference(self) -> str:
        """Backend salvato dall'ultima sessione, o DEFAULT_BACKEND.

        La preferenza viene validata: un file di configurazione scritto a mano,
        o un backend rimosso da una versione successiva, non deve far fallire
        l'avvio con il ValueError sollevato da Mp3File.
        """
        saved = str(self.settings.value(SETTINGS_BACKEND_KEY, DEFAULT_BACKEND))
        if saved not in available_backends():
            logger.warning("Backend salvato '%s' non riconosciuto: uso '%s'",
                           saved, DEFAULT_BACKEND)
            return DEFAULT_BACKEND
        return saved

    def set_backend(self, name: str) -> None:
        """Imposta il backend audio dei file aperti da qui in avanti.

        Le tracce già in griglia mantengono il backend con cui sono nate:
        sostituirlo a caldo vorrebbe dire distruggere e ricreare il player di
        ogni traccia, perdendo posizione e volume e interrompendo l'audio in
        scena. La scelta è persistita e vale anche ai riavvii successivi.
        """
        if name not in available_backends():
            logger.error("Backend '%s' non riconosciuto: ignorato", name)
            return
        if name == self.backend:
            return
        self.backend = name
        self.settings.setValue(SETTINGS_BACKEND_KEY, name)
        self.settings.sync()
        logger.info("Backend audio impostato su '%s'", name)
        if self.mp3_widgets:
            QMessageBox.information(
                self, "Backend audio",
                f"Backend impostato su '{name}'.\n\n"
                "Le tracce già aperte continuano con il backend precedente: "
                "il nuovo vale per i file e i progetti caricati d'ora in avanti.")

    def _on_container_drag_enter(self, event):
        # Drag interno alla stessa app: la sorgente è il widget stesso.
        if isinstance(event.source(), Mp3Widget):
            event.acceptProposedAction()

    def _get_drop_target_rect(self, pos):
        """Return the cellRect for the cell under pos, or None if outside the grid."""
        r, c = self.grid_manager.get_cell_at_pos(pos)
        if r == -1:
            return None
        return self.grid_layout.cellRect(r, c)

    def _on_container_drop(self, event):
        source_widget = event.source()
        if not isinstance(source_widget, Mp3Widget):
            event.ignore()
            return

        target_pos = event.pos()
        target_row, target_col = self.grid_manager.get_cell_at_pos(target_pos)
        if target_row == -1:
            event.ignore()
            return

        item = self.grid_layout.itemAtPosition(target_row, target_col)

        if item and item.widget() != source_widget:
            displaced_widget = item.widget()
            logger.info(f"Cell ({target_row}, {target_col}) is occupied by {os.path.basename(displaced_widget.mp3file.file_name)}. Finding new spot.")
            new_row, new_col = self.grid_manager.find_nearest_free_cell(target_row, target_col)
            if new_row != -1:
                logger.info(f"Moving displaced widget to ({new_row}, {new_col}).")
                self.grid_layout.removeWidget(displaced_widget)
                self.grid_layout.addWidget(displaced_widget, new_row, new_col)
            else:
                logger.warning("Could not find a free cell for the displaced widget. Aborting drop.")
                event.ignore()
                return

        logger.info(f"Moving {os.path.basename(source_widget.mp3file.file_name)} to ({target_row}, {target_col}).")
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
                mp3_widget.remove_requested.connect(self.remove_widget)

                self.mp3_widgets.append(mp3_widget)
                self.grid_layout.addWidget(mp3_widget, row, col)
                self.grid_manager.update_column_stretches()

    def save_project(self) -> bool:
        """Salva il progetto. Ritorna True solo a salvataggio riuscito
        (False se l'utente annulla il dialog o il salvataggio fallisce)."""
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Project Files (*.mpp)", options=options)

        if not file_name:
            return False
        try:
            self.project_manager.save(self.mp3_widgets, self.grid_layout, self.geometry(), file_name)
            logger.info(f"Project saved successfully to {file_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving project: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")
            return False

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
                failed_loads = []
                for file_data in project_data['files']:
                    try:
                        if not os.path.exists(file_data['file_path']):
                            raise FileNotFoundError(f"File not found: {file_data['file_path']}")

                        mp3_audio_file = Mp3File(file_data['file_path'], backend=self.backend)
                        layout = WidgetLayout[file_data.get('layout', 'TOUCH')]
                        mp3_widget = Mp3Widget(mp3_audio_file, layout=layout)
                        mp3_widget.remove_requested.connect(self.remove_widget)
                        mp3_widget.apply_state(file_data)

                        row = file_data.get('row', -1)
                        col = file_data.get('col', -1)
                        successful_loads.append((mp3_widget, row, col))

                    except Exception as e:
                        # Accumulati e mostrati in un unico avviso a fine ciclo:
                        # un progetto spostato tra macchine può avere decine di
                        # percorsi rotti e altrettanti popup modali da chiudere.
                        logger.error(f"Error loading file {file_data['file_path']}: {e}")
                        failed_loads.append(
                            f"{os.path.basename(file_data['file_path'])}: {e}")

                rejected = [os.path.basename(widget.mp3file.file_name)
                            for widget, row, col in successful_loads
                            if not self._place_loaded_widget(widget, row, col)]
                self.grid_manager.update_column_stretches()

                logger.info(f"Project loaded successfully from {file_name}")

                if failed_loads:
                    QMessageBox.warning(
                        self, "Warning",
                        "%d file non caricati:\n%s"
                        % (len(failed_loads), "\n".join(failed_loads)))

                if rejected:
                    QMessageBox.warning(
                        self, "Grid Full",
                        "La griglia è piena: %d file non caricati:\n%s"
                        % (len(rejected), "\n".join(rejected)))

                if 'window_state' in project_data:
                    self._restore_geometry_clamped(project_data['window_state'])
            except Exception as e:
                logger.error(f"Error loading project data: {e}")
                QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")

    def _place_loaded_widget(self, widget, row: int = -1, col: int = -1) -> bool:
        """Piazza nella griglia un widget caricato da progetto; True se riuscito.

        Se la cella non è indicata — o è già occupata, come capita nei progetti
        scritti a mano o salvati da versioni precedenti — cerca la prima libera:
        due widget nella stessa cella si sovrappongono e quello sotto resta
        invisibile. A griglia piena rilascia il widget invece di passare
        (-1, -1) a `addWidget`: Qt in quel caso scarta il widget in silenzio,
        lasciandolo invisibile ma ancora in `mp3_widgets` e con il backend
        audio aperto.
        """
        if row == -1 or col == -1 or self.grid_layout.itemAtPosition(row, col) is not None:
            row, col = self.grid_manager.find_next_available_cell()
        if row == -1 or col == -1:
            logger.warning("Grid full: %s non caricato",
                           os.path.basename(widget.mp3file.file_name))
            widget.shutdown()
            widget.deleteLater()
            return False
        self.mp3_widgets.append(widget)
        self.grid_layout.addWidget(widget, row, col)
        return True

    def _restore_geometry_clamped(self, ws: dict) -> None:
        """Restora geometria della finestra clampata all'`availableGeometry`.

        Usa `availableGeometry()` (esclude taskbar/dock) e tiene conto del
        fatto che su multi-monitor l'origine dello schermo primario può non
        essere (0,0). Width/height vengono clampate ai limiti dello schermo.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        w = max(400, min(avail.width(), int(ws.get('width', 1080))))
        h = max(300, min(avail.height(), int(ws.get('height', 600))))
        x = max(avail.x(), min(avail.right() - w, int(ws.get('x', avail.x()))))
        y = max(avail.y(), min(avail.bottom() - h, int(ws.get('y', avail.y()))))
        self.setGeometry(x, y, w, h)

    def normalize_all(self):
        """Avvia la normalizzazione RMS su tutti i widget aperti in parallelo."""
        for widget in self.mp3_widgets:
            widget.on_normalize_clicked()

    def clear_layout(self):
        for widget in self.mp3_widgets:
            widget.shutdown()
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
        self.mp3_widgets.clear()
        self.grid_manager.update_column_stretches()

    def closeEvent(self, event):
        if self.mp3_widgets:
            reply = QMessageBox.question(
                self,
                "Chiudi applicazione",
                "Ci sono file attivi. Vuoi salvare il progetto prima di uscire?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Save and not self.save_project():
                # Salvataggio annullato o fallito: non chiudere, altrimenti
                # l'utente perderebbe il progetto che ha chiesto di salvare.
                event.ignore()
                return
        self._progress_timer.stop()
        self._audio_warmup.stop()
        for widget in list(self.mp3_widgets):
            widget.shutdown()
        event.accept()

    def remove_widget(self, widget):
        if widget in self.mp3_widgets:
            self.mp3_widgets.remove(widget)
            self.grid_layout.removeWidget(widget)
            logger.info(f"Removed widget for {os.path.basename(widget.mp3file.file_name)}.")
            self.grid_manager.update_column_stretches()


def run_app():
    app = QApplication(sys.argv)
    main_app = MainApp()
    return app, main_app

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app, main_app = run_app()
    sys.exit(app.exec_())
