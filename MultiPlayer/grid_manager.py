from PySide6.QtWidgets import QGridLayout

MAX_ROWS = 20
QWIDGETSIZE_MAX = 16777215
# Una riga di channel strip prende quasi tutta l'altezza, ma le righe vuote
# restano abbastanza alte da fare da drop target.
TALL_ROW_STRETCH = 30
# Durante un drag la griglia offre una colonna e una riga vuote in più, larghe
# abbastanza da essere un bersaglio comodo; a drag finito tornano a sparire.
DRAG_TARGET_SIZE = 200


class GridManager:
    def __init__(self, grid_layout: QGridLayout, initial_cols: int):
        self._layout = grid_layout
        self._initial_cols = initial_cols
        self._dragging = False

    def set_drag_active(self, active: bool) -> None:
        """Mostra (o toglie) le celle extra che fanno da bersaglio al drop."""
        self._dragging = active
        self.update_column_stretches()

    def update_column_stretches(self):
        """Update column AND row stretches.

        Columns: occupied get stretch=1, unoccupied get stretch=0 + a small
        minimum width (60px) so they stay visible as drop targets without
        stealing space. Always shows at least initial_cols columns.
        Le colonne oltre quelle correnti vengono azzerate: QGridLayout non
        rimpicciolisce mai columnCount(), quindi dopo un drag su una colonna
        alta e un ritorno indietro resterebbero prenotate a 60px per sempre.

        Rows: all rows from 0 to max_occupied_row get stretch=1, ensuring no
        row between the top and the last widget collapses (e.g. when a drag
        places a widget at row=7 with no widgets in rows 5-6). Empty rows below
        keep their height, so previously expanded rows aren't shrunk back when
        widgets above them are removed.

        Widget con una dimensione massima (DENSE_A, MIXER): se occupano da
        soli una riga o una colonna, questa si stringe al widget e lo spazio
        libero va a una riga o colonna vuota, altrimenti Qt li distanzierebbe.
        """
        occupied_cols = set()
        occupied_rows = set()
        wide_cols = set()    # colonne con almeno un widget senza larghezza massima
        tall_rows = set()    # righe con almeno un widget senza altezza massima
        strip_rows = set()   # righe con almeno un widget a larghezza limitata
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget():
                row, col, _, _ = self._layout.getItemPosition(i)
                occupied_cols.add(col)
                occupied_rows.add(row)
                if item.widget().maximumWidth() == QWIDGETSIZE_MAX:
                    wide_cols.add(col)
                else:
                    strip_rows.add(row)
                if item.widget().maximumHeight() == QWIDGETSIZE_MAX:
                    tall_rows.add(row)

        max_col = max(occupied_cols, default=-1)
        num_cols = max(max_col + 1, self._initial_cols) + (1 if self._dragging else 0)
        empty_width = DRAG_TARGET_SIZE if self._dragging else 60

        for c in range(max(num_cols, self._layout.columnCount())):
            if c in occupied_cols:
                self._layout.setColumnStretch(c, 1 if c in wide_cols else 0)
                self._layout.setColumnMinimumWidth(c, 0)
            else:
                self._layout.setColumnStretch(c, 0)
                # Drop target visibile solo dentro le colonne correnti; oltre
                # è un residuo di un layout precedente e deve collassare.
                self._layout.setColumnMinimumWidth(c, empty_width if c < num_cols else 0)

        if occupied_cols and not wide_cols:
            self._layout.setColumnStretch(num_cols, 1)

        max_row = max(occupied_rows, default=-1)
        for r in range(max_row + 1):
            if r in strip_rows:
                self._layout.setRowStretch(r, TALL_ROW_STRETCH)
            elif r in occupied_rows and r not in tall_rows:
                self._layout.setRowStretch(r, 0)
            else:
                self._layout.setRowStretch(r, 1)
        # Almeno una riga vuota sotto l'ultima assorbe lo spazio libero. Le
        # righe vuote tornano tutte a 1: una riga lasciata dalle strip
        # conserverebbe il loro stretch e ruberebbe metà dell'altezza.
        for r in range(max_row + 1, max(self._layout.rowCount(), max_row + 2)):
            self._layout.setRowStretch(r, 1)
        for r in range(self._layout.rowCount()):
            self._layout.setRowMinimumHeight(r, 0)
        if self._dragging and max_row + 1 < MAX_ROWS:
            self._layout.setRowMinimumHeight(max_row + 1, DRAG_TARGET_SIZE)

    def get_cell_at_pos(self, pos) -> tuple[int, int]:
        """Cella visibile più vicina a pos: lo spazio tra le celle e i margini
        non sono zone morte per il drop."""
        best, best_dist = (-1, -1), None
        for r in range(self._layout.rowCount()):
            for c in range(self._layout.columnCount()):
                rect = self._layout.cellRect(r, c)
                if rect.width() <= 0 or rect.height() <= 0:
                    continue  # colonna o riga collassata: non è un bersaglio
                dx = max(rect.left() - pos.x(), 0, pos.x() - rect.right())
                dy = max(rect.top() - pos.y(), 0, pos.y() - rect.bottom())
                dist = dx * dx + dy * dy
                if best_dist is None or dist < best_dist:
                    best, best_dist = (r, c), dist
        return best

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
