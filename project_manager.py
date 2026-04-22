import json
import logging
from datetime import datetime


class ProjectManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

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
            files.append({
                'file_path': widget.mp3file.file_name,
                'volume': widget.mp3file.get_volume(),
                'fade_time': widget.fade_time,
                'gain': widget.mp3file.gain,
                'row': row,
                'col': col,
                'layout': widget.widgetLayout.name,
            })

        project_data = {
            'version': '1.2',
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
        self.logger.info(f"Project saved to {path}")

    def load(self, path: str) -> dict:
        with open(path, 'r') as f:
            project_data = json.load(f)
        if 'version' not in project_data or 'files' not in project_data:
            raise ValueError("Invalid project file format")
        return project_data
