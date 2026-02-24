from board import Board, EMPTY, ROUGE, JAUNE
from ai_module import AIPlayer

class GameState:
    def __init__(self, rows=9, cols=9, start_player=1, mode=0, ai_type="random", ai_depth=3):
        self.board = Board(rows, cols)
        self.current_player = start_player
        self.mode = mode
        self.winner = None
        self.move_history = []
        self.ai_player = AIPlayer(ai_type, ai_depth)
        self.last_minimax_scores = {}
        self.last_confidence = 0.5
        self.game_id = None

    def reset_for_new_game(self, game_id, mode, start_player, ai_type, ai_depth):
        self.board = Board(self.board.rows, self.board.cols)
        self.current_player = start_player
        self.mode = mode
        self.winner = None
        self.move_history = []
        self.ai_player = AIPlayer(ai_type, ai_depth)
        self.last_minimax_scores = {}
        self.last_confidence = 0.5
        self.game_id = game_id

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

        self.switch_player()
        return row, None

    def switch_player(self):
        self.current_player = JAUNE if self.current_player == ROUGE else ROUGE

    def ai_choose_move(self):
        if self.ai_player.ai_type == "random":
            col = self.ai_player.get_ai_move_random(self.board)
            return col, {}, 0.5
        col, scores, confidence = self.ai_player.choose_move(self.board, self.current_player)
        self.last_minimax_scores = scores
        self.last_confidence = confidence
        return col, scores, confidence

    def undo_move(self):
        if not self.move_history:
            return False

        old_history = list(self.move_history)
        self.move_history.pop()

        self.board = Board(self.board.rows, self.board.cols)
        self.current_player = ROUGE
        for row, col, player in old_history:
            self.board.place_token(col, player)

        return True
