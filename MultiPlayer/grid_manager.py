from PyQt5.QtWidgets import QGridLayout

MAX_ROWS = 20


class GridManager:
    def __init__(self, grid_layout: QGridLayout, initial_cols: int):
        self._layout = grid_layout
        self._initial_cols = initial_cols

    def update_column_stretches(self):
        """Update column AND row stretches.

        Columns: occupied get stretch=1, unoccupied get stretch=0 + a small
        minimum width (60px) so they stay visible as drop targets without
        stealing space. Always shows at least initial_cols columns.

        Rows: all rows from 0 to max_occupied_row get stretch=1, ensuring no
        row between the top and the last widget collapses (e.g. when a drag
        places a widget at row=7 with no widgets in rows 5-6). Rows beyond
        max_occupied are left untouched so previously expanded rows aren't
        shrunk back when widgets above them are removed.
        """
        occupied_cols = set()
        occupied_rows = set()
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget():
                row, col, _, _ = self._layout.getItemPosition(i)
                occupied_cols.add(col)
                occupied_rows.add(row)

        max_col = max(occupied_cols, default=-1)
        num_cols = max(max_col + 1, self._initial_cols)

        for c in range(num_cols):
            if c in occupied_cols:
                self._layout.setColumnStretch(c, 1)
                self._layout.setColumnMinimumWidth(c, 0)
            else:
                self._layout.setColumnStretch(c, 0)
                self._layout.setColumnMinimumWidth(c, 60)

        max_row = max(occupied_rows, default=-1)
        for r in range(max_row + 1):
            self._layout.setRowStretch(r, 1)

    def get_cell_at_pos(self, pos) -> tuple[int, int]:
        for r in range(self._layout.rowCount()):
            for c in range(self._layout.columnCount()):
                if self._layout.cellRect(r, c).contains(pos):
                    return r, c
        return -1, -1

    def find_next_available_cell(self) -> tuple[int, int]:
        num_cols = max(self._layout.columnCount(), self._initial_cols)
        for r in range(MAX_ROWS):
            for c in range(num_cols):
                if self._layout.itemAtPosition(r, c) is None:
                    return r, c
        return -1, -1

    def find_nearest_free_cell(self, start_row: int, start_col: int) -> tuple[int, int]:
        max_search_dist = max(self._layout.rowCount(), self._layout.columnCount()) * 2
        for dist in range(1, max_search_dist):
            for i in range(-dist, dist + 1):
                cells_to_check = [
                    (start_row - dist, start_col + i), (start_row + dist, start_col + i),
                    (start_row + i, start_col - dist), (start_row + i, start_col + dist),
                ]
                for r, c in cells_to_check:
                    if 0 <= r < self._layout.rowCount() and 0 <= c < self._layout.columnCount():
                        if self._layout.itemAtPosition(r, c) is None:
                            return r, c
        new_row = self._layout.rowCount()
        if new_row >= MAX_ROWS:
            return -1, -1
        self._layout.setRowStretch(new_row, 1)
        return new_row, 0
