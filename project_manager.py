import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

CURRENT_VERSION = '1.2'


class ProjectManager:
    def save(self, widgets: list, grid_layout, window_geometry, path: str) -> None:
        if not path.endswith('.mpp'):
            path += '.mpp'

        g = window_geometry
        window_state = {
            'x': g.x(), 'y': g.y(),
            'width': g.width(), 'height': g.height()
        }

        files = []
        for i in range(grid_layout.count()):
            item = grid_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget not in widgets:
                continue
            row, col, _, _ = grid_layout.getItemPosition(i)
            entry = widget.to_state()
            entry['row'] = row
            entry['col'] = col
            files.append(entry)

        project_data = {
            'version': CURRENT_VERSION,
            'saved_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'window_state': window_state,
            'grid_state': {
                'rows': grid_layout.rowCount(),
                'cols': grid_layout.columnCount(),
            },
            'files': files,
        }

        with open(path, 'w') as f:
            json.dump(project_data, f, indent=4)
        logger.info(f"Project saved to {path}")

    def load(self, path: str) -> dict:
        with open(path, 'r') as f:
            project_data = json.load(f)
        if 'files' not in project_data:
            raise ValueError("Invalid project file format: missing 'files'")

        version = project_data.get('version', '0.0')
        if version != CURRENT_VERSION:
            project_data = self._migrate(project_data, version)
        return project_data

    def _migrate(self, data: dict, from_version: str) -> dict:
        """Migra il progetto da versioni precedenti a CURRENT_VERSION.

        Aggiungere step di migrazione qui man mano che lo schema evolve.
        Ogni step trasforma `data` in-place e aggiorna `data['version']`.
        Esempio (per future modifiche):

            if from_version < '1.3':
                # trasformazione...
                data['version'] = '1.3'
                from_version = '1.3'
            if from_version < '1.4':
                ...
        """
        logger.warning(
            f"Loading project version '{from_version}'; "
            f"current is '{CURRENT_VERSION}' — migrating."
        )
        # Nessuna migrazione definita: lo schema non ha avuto breaking changes
        # dopo la 1.2. Se il file è più vecchio di 1.2 oggi viene caricato
        # best-effort (i campi mancanti vengono ignorati da apply_state).
        data['version'] = CURRENT_VERSION
        return data
