EMPTY = 0
ROUGE = 1
JAUNE = 2

# Constantes pour l'interface graphique
CELL_SIZE = 60
PADDING = 20
COLOR_BG = "#0033cc"
COLOR_GRID = "#000000"
COLOR_RED = "#ff3b30"
COLOR_YELLOW = "#ffcc00"

class Board:
    def __init__(self, rows=9, cols=9):
        self.rows = rows
        self.cols = cols
        self.grid = [[EMPTY for _ in range(cols)] for _ in range(rows)]

    def is_valid_move(self, col):
        return 0 <= col < self.cols and self.grid[0][col] == EMPTY

    def place_token(self, col, player):
        if not self.is_valid_move(col):
            return None
        for row in range(self.rows-1, -1, -1):
            if self.grid[row][col] == EMPTY:
                self.grid[row][col] = player
                return row
        return None

    def is_full(self):
        return all(self.grid[0][col] != EMPTY for col in range(self.cols))

    def check_win(self, player):
        # Vérification horizontale
        for row in range(self.rows):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row][col+1] == player and
                    self.grid[row][col+2] == player and
                    self.grid[row][col+3] == player):
                    return [(row, col+i) for i in range(4)]

        # Vérification verticale
        for row in range(self.rows - 3):
            for col in range(self.cols):
                if (self.grid[row][col] == player and
                    self.grid[row+1][col] == player and
                    self.grid[row+2][col] == player and
                    self.grid[row+3][col] == player):
                    return [(row+i, col) for i in range(4)]

        # Vérification diagonale (haut-gauche à bas-droite)
        for row in range(self.rows - 3):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row+1][col+1] == player and
                    self.grid[row+2][col+2] == player and
                    self.grid[row+3][col+3] == player):
                    return [(row+i, col+i) for i in range(4)]

        # Vérification diagonale (bas-gauche à haut-droite)
        for row in range(3, self.rows):
            for col in range(self.cols - 3):
                if (self.grid[row][col] == player and
                    self.grid[row-1][col+1] == player and
                    self.grid[row-2][col+2] == player and
                    self.grid[row-3][col+3] == player):
                    return [(row-i, col+i) for i in range(4)]

        return None
