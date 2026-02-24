import random
from board import EMPTY, ROUGE, JAUNE

class AIPlayer:
    def __init__(self, ai_type="random", depth=3):
        self.ai_type = ai_type
        self.depth = depth

    def get_ai_move_random(self, board):
        valid_moves = [col for col in range(board.cols) if board.is_valid_move(col)]
        return random.choice(valid_moves) if valid_moves else None

    def minimax(self, board, depth, alpha, beta, maximizing_player):
        win_rouge = board.check_win(ROUGE)
        win_jaune = board.check_win(JAUNE)

        if depth == 0 or board.is_full() or win_rouge or win_jaune:
            return self.evaluate_board(board)

        if maximizing_player:
            max_eval = float('-inf')
            best_confidence = 0.5
            for col in range(board.cols):
                if board.is_valid_move(col):
                    row = board.place_token(col, ROUGE)
                    eval_score, eval_confidence = self.minimax(board, depth - 1, alpha, beta, False)
                    board.grid[row][col] = EMPTY
                    if eval_score > max_eval:
                        max_eval = eval_score
                        best_confidence = eval_confidence
                    alpha = max(alpha, eval_score)
                    if beta <= alpha:
                        break
            return max_eval, best_confidence
        else:
            min_eval = float('inf')
            best_confidence = 0.5
            for col in range(board.cols):
                if board.is_valid_move(col):
                    row = board.place_token(col, JAUNE)
                    eval_score, eval_confidence = self.minimax(board, depth - 1, alpha, beta, True)
                    board.grid[row][col] = EMPTY
                    if eval_score < min_eval:
                        min_eval = eval_score
                        best_confidence = eval_confidence
                    beta = min(beta, eval_score)
                    if beta <= alpha:
                        break
            return min_eval, best_confidence

    def evaluate_board(self, board):
        score = 0
        center_array = [board.grid[i][board.cols//2] for i in range(board.rows)]
        score += center_array.count(ROUGE) * 3
        score -= center_array.count(JAUNE) * 3

        max_possible_score = 100
        confiance = 0.5 + (score / (2 * max_possible_score))
        confiance = max(0, min(1, confiance))

        return score, confiance

    def choose_move(self, board, player):
        best_col = None
        best_score = float('-inf') if player == ROUGE else float('inf')
        scores = {}
        confiances = {}

        valid_moves = [c for c in range(board.cols) if board.is_valid_move(c)]
        if not valid_moves:
            return None, {}, 0.5

        for col in valid_moves:
            row = board.place_token(col, player)
            is_maximizing = (player == ROUGE)
            score, confiance = self.minimax(board, self.depth - 1, float('-inf'), float('inf'), not is_maximizing)
            board.grid[row][col] = EMPTY
            scores[col] = score
            confiances[col] = confiance

            if player == ROUGE and score > best_score:
                best_score = score
                best_col = col
            elif player == JAUNE and score < best_score:
                best_score = score
                best_col = col

        return best_col, scores, confiances.get(best_col, 0.5)
