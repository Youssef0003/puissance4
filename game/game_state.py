import os
import json
import copy
from datetime import datetime
from .board import Board, EMPTY, ROUGE, JAUNE

class GameState:
    SAVE_DIR = os.path.join(os.path.dirname(__file__), '../saves')

    def __init__(self, rows=9, cols=9, start_player=ROUGE, mode=2, ai_type='random', ai_depth=3, game_id=None):
        self.board = Board(rows, cols)
        self.current_player = start_player
        self.mode = mode
        self.ai_type = ai_type
        self.ai_depth = ai_depth
        self.game_id = game_id or str(datetime.now().timestamp())
        self.move_history = []
        self.last_confidence = 0.5
        self.last_minimax_scores = {}
        self.winner = None
        self.timestamp = datetime.now()
        self.undo_count = 0

    def save_game(self):
        """Sauvegarde l'état du jeu"""
        if not os.path.exists(self.SAVE_DIR):
            os.makedirs(self.SAVE_DIR, exist_ok=True)

        save_data = {
            'board': self.board.grid,
            'current_player': self.current_player,
            'mode': self.mode,
            'ai_type': self.ai_type,
            'ai_depth': self.ai_depth,
            'game_id': self.game_id,
            'move_history': self.move_history,
            'last_confidence': self.last_confidence,
            'last_minimax_scores': self.last_minimax_scores,
            'winner': self.winner,
            'timestamp': self.timestamp.isoformat(),
            'undo_count': self.undo_count
        }

        save_path = os.path.join(self.SAVE_DIR, f"{self.game_id}.json")
        with open(save_path, 'w') as f:
            json.dump(save_data, f, indent=2)

        return save_path

    @classmethod
    def load_game(cls, game_id):
        """Charge un jeu sauvegardé"""
        save_path = os.path.join(cls.SAVE_DIR, f"{game_id}.json")
        if not os.path.exists(save_path):
            raise FileNotFoundError(f"Partie {game_id} non trouvée")

        with open(save_path, 'r') as f:
            save_data = json.load(f)

        game = cls(
            rows=9, cols=9,
            start_player=save_data['current_player'],
            mode=save_data['mode'],
            ai_type=save_data['ai_type'],
            ai_depth=save_data['ai_depth'],
            game_id=save_data['game_id']
        )

        game.board.grid = save_data['board']
        game.current_player = save_data['current_player']
        game.move_history = save_data['move_history']
        game.last_confidence = save_data['last_confidence']
        game.last_minimax_scores = save_data['last_minimax_scores']
        game.winner = save_data['winner']
        game.timestamp = datetime.fromisoformat(save_data['timestamp'])
        game.undo_count = save_data.get('undo_count', 0)

        return game

    @classmethod
    def get_saved_games(cls):
        """Récupère toutes les parties sauvegardées"""
        if not os.path.exists(cls.SAVE_DIR):
            return []

        games = []
        for filename in os.listdir(cls.SAVE_DIR):
            if filename.endswith('.json'):
                game_id = filename[:-5]
                try:
                    game = cls.load_game(game_id)
                    games.append(game)
                except:
                    continue

        return sorted(games, key=lambda g: g.timestamp, reverse=True)

    def can_undo(self):
        """Vérifie si on peut annuler un coup"""
        return len(self.move_history) > 0 and self.undo_count < 3

    def undo_move(self):
        """Annule le dernier coup"""
        if not self.can_undo():
            return False

        last_row, last_col, last_player = self.move_history.pop()
        self.board.grid[last_row][last_col] = EMPTY
        self.current_player = last_player
        self.undo_count += 1

        if (self.mode == 1 and last_player == JAUNE) or self.mode == 0:
            if len(self.move_history) > 0:
                prev_row, prev_col, prev_player = self.move_history.pop()
                self.board.grid[prev_row][prev_col] = EMPTY
                self.current_player = prev_player
                self.undo_count += 1

        return True
