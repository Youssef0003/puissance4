import random
import time
from datetime import datetime
import hashlib
import psycopg2
from psycopg2.extras import DictCursor

# Constantes
EMPTY = 0
ROUGE = 1
JAUNE = 2

# Configuration de la base
DB_CONFIG = {
    "database": "puissance4",
    "user": "youssef",
    "password": "Kassou00.",
    "host": "localhost",
    "port": "5432"
}

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
        # Implémente la logique de victoire (comme dans ton code)
        return None  # À compléter

class AIPlayer:
    def __init__(self, ai_type="random", depth=3):
        self.ai_type = ai_type
        self.depth = depth

    def get_ai_move_random(self, board):
        valid_moves = [col for col in range(board.cols) if board.is_valid_move(col)]
        return random.choice(valid_moves) if valid_moves else None

    def choose_move(self, board, player):
        return self.get_ai_move_random(board), {}

class GameState:
    def __init__(self, rows=9, cols=9, start_player=1, mode=0, ai_type="random", ai_depth=3):
        self.board = Board(rows, cols)
        self.current_player = start_player
        self.mode = mode
        self.winner = None
        self.move_history = []
        self.ai_player = AIPlayer(ai_type, ai_depth)

    def play_move(self, col):
        if not self.board.is_valid_move(col):
            return None, None
        row = self.board.place_token(col, self.current_player)
        if row is None:
            return None, None
        self.move_history.append((row, col, self.current_player))
        win_cells = self.board.check_win(self.current_player)
        if win_cells:
            self.winner = self.current_player
            return row, win_cells
        if self.board.is_full():
            self.winner = "Nul"
            return row, None
        self.current_player = JAUNE if self.current_player == ROUGE else ROUGE
        return row, None

    def ai_choose_move(self):
        return self.ai_player.choose_move(self.board, self.current_player)

class DBManager:
    def __init__(self, db_name="puissance4", user="youssef", password="Kassou00.", host="localhost", port="5432"):
        self.connection = psycopg2.connect(dbname=db_name, user=user, password=password, host=host, port=port)

    def execute_query(self, query, params=None, fetch=False):
        with self.connection.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            self.connection.commit()

    def check_if_exists(self, moves):
        m_hash = hashlib.sha256(",".join(map(str, moves)).encode()).hexdigest()
        res = self.execute_query("SELECT game_id FROM games WHERE move_sequence_hash = %s", (m_hash,), fetch=True)
        return res[0]['game_id'] if res else None

    def close(self):
        self.connection.close()

def generate_random_game(db_manager, mode=0, start_player=1, ai_type="random", ai_depth=3):
    """Génère une partie aléatoire et l'enregistre dans la base."""
    game = GameState(rows=9, cols=9, start_player=start_player, mode=mode, ai_type=ai_type, ai_depth=ai_depth)
    moves = []
    while True:
        if game.mode == 0:  # IA vs IA
            col, _ = game.ai_choose_move()
        else:  # Aléatoire
            valid_moves = [c for c in range(game.board.cols) if game.board.is_valid_move(c)]
            if not valid_moves:
                break
            col = random.choice(valid_moves)
        row, win_cells = game.play_move(col)
        moves.append(col)
        if win_cells or game.board.is_full():
            break
    winner = game.winner
    if winner == ROUGE:
        winner = "Rouge"
    elif winner == JAUNE:
        winner = "Jaune"
    else:
        winner = "Nul"
    return save_game_to_db(db_manager, winner, mode, game.move_history)

def save_game_to_db(db_manager, winner, mode, history, file_reference=None):
    """Enregistre une partie dans la base."""
    moves = [move[1] for move in history]
    existing_id = db_manager.check_if_exists(moves)
    if existing_id:
        return existing_id
    move_sequence_hash = hashlib.sha256(",".join(map(str, moves)).encode()).hexdigest()
    query = """
    INSERT INTO games (winner, mode, status, timestamp_end, file_reference, move_sequence_hash, num_columns)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING game_id;
    """
    params = (winner, mode, "completed", datetime.now(), file_reference, move_sequence_hash, 9)
    result = db_manager.execute_query(query, params, fetch=True)
    game_id = result[0][0]
    for move_order, (row, col, player) in enumerate(history, start=1):
        query = """
        INSERT INTO moves (game_id, row, col, player, move_order)
        VALUES (%s, %s, %s, %s, %s);
        """
        db_manager.execute_query(query, (game_id, row, col, player, move_order))
    return game_id

def main():
    db_manager = DBManager()
    try:
        for i in range(100):  # Génère 100 parties
            mode = random.choice([0, 1, 2])  # 0: IA vs IA, 1: Joueur vs IA, 2: Joueur vs Joueur
            start_player = random.choice([1, 2])  # 1: Rouge, 2: Jaune
            ai_type = random.choice(["random", "minimax"])
            ai_depth = random.randint(1, 5) if ai_type == "minimax" else 3
            game_id = generate_random_game(db_manager, mode, start_player, ai_type, ai_depth)
            print(f"Partie {i+1} enregistrée avec l'ID {game_id}")
    finally:
        db_manager.close()

if __name__ == "__main__":
    main()
