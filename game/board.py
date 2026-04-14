EMPTY = 0
ROUGE = 1
JAUNE = 2

class Board:
    def __init__(self, rows=9, cols=9):
        self.rows = rows
        self.cols = cols
        self.grid = [[EMPTY for _ in range(cols)] for _ in range(rows)]

    def is_valid_move(self, col):
        """Vérifie si un coup est valide dans une colonne."""
        return 0 <= col < self.cols and self.grid[0][col] == EMPTY

    def place_token(self, col, player):
        """Place un jeton dans une colonne et retourne la ligne où il est placé."""
        if not self.is_valid_move(col):
            return None
        for row in range(self.rows-1, -1, -1):
            if self.grid[row][col] == EMPTY:
                self.grid[row][col] = player
                return row
        return None

    def get_next_open_row(self, col):
        """Retourne la prochaine ligne disponible dans une colonne."""
        for row in range(self.rows-1, -1, -1):
            if self.grid[row][col] == EMPTY:
                return row
        return None

    def is_full(self):
        """Vérifie si le plateau est plein."""
        return all(self.grid[0][col] != EMPTY for col in range(self.cols))

    def check_win(self, player):
        """Vérifie si un joueur a gagné et retourne les cellules gagnantes."""
        # Vérifie les lignes
        for row in range(self.rows):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row][col+1] == player and
                    self.grid[row][col+2] == player and
                    self.grid[row][col+3] == player):
                    return [(row, col+i) for i in range(4)]

        # Vérifie les colonnes
        for row in range(self.rows - 3):
            for col in range(self.cols):
                if (self.grid[row][col] == player and
                    self.grid[row+1][col] == player and
                    self.grid[row+2][col] == player and
                    self.grid[row+3][col] == player):
                    return [(row+i, col) for i in range(4)]

        # Vérifie les diagonales descendantes
        for row in range(self.rows - 3):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row+1][col+1] == player and
                    self.grid[row+2][col+2] == player and
                    self.grid[row+3][col+3] == player):
                    return [(row+i, col+i) for i in range(4)]

        # Vérifie les diagonales ascendantes
        for row in range(3, self.rows):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row-1][col+1] == player and
                    self.grid[row-2][col+2] == player and
                    self.grid[row-3][col+3] == player):
                    return [(row-i, col+i) for i in range(4)]

        return None
