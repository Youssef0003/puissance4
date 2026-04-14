import random
import math
import numpy as np
from game.board import EMPTY, ROUGE, JAUNE

class AIPlayer:
    def __init__(self, ai_type='random', depth=3):
        self.ai_type = ai_type
        self.depth = depth

    def evaluate_position(self, board, depth, is_maximizing, alpha, beta):
        """Évalue une position du plateau avec une heuristique améliorée"""
        if self.ai_type == 'random':
            return random.random()

        # Vérifier si la partie est terminée
        if board.is_full():
            return 0  # Match nul

        # Évaluation basée sur plusieurs critères
        score = 0

        # 1. Évaluer les alignements potentiels
        score += self.evaluate_alignments(board, is_maximizing) * 10

        # 2. Évaluer le contrôle du centre
        score += self.evaluate_center_control(board, is_maximizing) * 5

        # 3. Évaluer les colonnes presque pleines (pour bloquer l'adversaire)
        score += self.evaluate_column_threats(board, is_maximizing) * 8

        # 4. Évaluer la profondeur (plus on est profond, moins la position est intéressante)
        score -= depth * 0.1

        return score

    def evaluate_alignments(self, board, is_maximizing):
        """Évalue les alignements potentiels de 2, 3 ou 4 pions"""
        player = JAUNE if is_maximizing else ROUGE
        opponent = ROUGE if is_maximizing else JAUNE
        score = 0

        # Directions: horizontale, verticale, diagonale descendante, diagonale montante
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

        for row in range(9):
            for col in range(9):
                if board.grid[row][col] == EMPTY:
                    continue

                for dr, dc in directions:
                    # Vérifier les alignements de 4
                    if self.check_alignment(board, row, col, dr, dc, player, 4):
                        score += 1000
                    elif self.check_alignment(board, row, col, dr, dc, opponent, 4):
                        score -= 800

                    # Vérifier les alignements de 3 (avec un trou)
                    if self.check_alignment_with_gap(board, row, col, dr, dc, player, 3):
                        score += 100
                    elif self.check_alignment_with_gap(board, row, col, dr, dc, opponent, 3):
                        score -= 80

                    # Vérifier les alignements de 2 (avec un trou)
                    if self.check_alignment_with_gap(board, row, col, dr, dc, player, 2):
                        score += 10
                    elif self.check_alignment_with_gap(board, row, col, dr, dc, opponent, 2):
                        score -= 8

                    # Vérifier les alignements de 3 sans trou
                    if self.check_alignment(board, row, col, dr, dc, player, 3):
                        score += 50
                    elif self.check_alignment(board, row, col, dr, dc, opponent, 3):
                        score -= 40

                    # Vérifier les alignements de 2 sans trou
                    if self.check_alignment(board, row, col, dr, dc, player, 2):
                        score += 5
                    elif self.check_alignment(board, row, col, dr, dc, opponent, 2):
                        score -= 4

        return score

    def check_alignment(self, board, row, col, dr, dc, player, length):
        """Vérifie s'il y a un alignement de 'length' pions du joueur"""
        count = 0

        # Compter dans la direction positive
        r, c = row, col
        for _ in range(length):
            if 0 <= r < 9 and 0 <= c < 9 and board.grid[r][c] == player:
                count += 1
            else:
                break
            r += dr
            c += dc

        # Compter dans la direction négative (sans compter deux fois le point de départ)
        r, c = row - dr, col - dc
        for _ in range(length - 1):
            if 0 <= r < 9 and 0 <= c < 9 and board.grid[r][c] == player:
                count += 1
            else:
                break
            r -= dr
            c -= dc

        return count >= length

    def check_alignment_with_gap(self, board, row, col, dr, dc, player, length):
        """Vérifie s'il y a un alignement de 'length' pions avec un trou"""
        # Vérifier dans la direction positive
        r, c = row, col
        count = 0
        gap_found = False

        for _ in range(length):
            if 0 <= r < 9 and 0 <= c < 9:
                if board.grid[r][c] == player:
                    count += 1
                elif board.grid[r][c] == EMPTY and not gap_found:
                    gap_found = True
                else:
                    break
            else:
                break
            r += dr
            c += dc

        # Vérifier dans la direction négative
        r, c = row - dr, col - dc
        for _ in range(length - count):
            if 0 <= r < 9 and 0 <= c < 9:
                if board.grid[r][c] == player:
                    count += 1
                elif board.grid[r][c] == EMPTY and not gap_found:
                    gap_found = True
                else:
                    break
            else:
                break
            r -= dr
            c -= dc

        return count >= length - 1 and gap_found

    def evaluate_center_control(self, board, is_maximizing):
        """Évalue le contrôle des colonnes centrales (plus importantes stratégiquement)"""
        player = JAUNE if is_maximizing else ROUGE
        opponent = ROUGE if is_maximizing else JAUNE
        score = 0

        # Les colonnes centrales sont plus importantes
        column_weights = [1, 2, 3, 4, 3, 2, 1]

        for col in range(9):
            # Compter les pions du joueur et de l'adversaire dans chaque colonne
            player_count = 0
            opponent_count = 0

            for row in range(9):
                if board.grid[row][col] == player:
                    player_count += 1
                elif board.grid[row][col] == opponent:
                    opponent_count += 1

            # Calculer le score basé sur le contrôle de la colonne
            if player_count > opponent_count:
                score += player_count * column_weights[col]
            elif opponent_count > player_count:
                score -= opponent_count * column_weights[col]

        return score

    def evaluate_column_threats(self, board, is_maximizing):
        """Évalue les menaces de victoire immédiate ou les colonnes presque pleines"""
        player = JAUNE if is_maximizing else ROUGE
        opponent = ROUGE if is_maximizing else JAUNE
        score = 0

        # Vérifier les colonnes presque pleines (pour bloquer l'adversaire)
        for col in range(9):
            empty_count = 0
            player_count = 0
            opponent_count = 0

            for row in range(9):
                if board.grid[row][col] == EMPTY:
                    empty_count += 1
                elif board.grid[row][col] == player:
                    player_count += 1
                else:
                    opponent_count += 1

            # Si la colonne est presque pleine et que l'adversaire a des pions, c'est une menace
            if empty_count == 1 and opponent_count >= 3:
                score -= 50  # Il faut bloquer cette colonne

            # Si la colonne est presque pleine et que nous avons des pions, c'est une opportunité
            if empty_count == 1 and player_count >= 3:
                score += 50  # Nous pouvons gagner en jouant ici

        return score

    def check_immediate_win(self, board, player):
        """Vérifie si un coup peut gagner immédiatement"""
        for col in range(9):
            if board.is_valid_move(col):
                row = board.place_token(col, player)
                if row is not None:
                    if self.check_win({'grid': board.grid}, row, col, player)[0]:
                        board.grid[row][col] = EMPTY
                        return col
                    board.grid[row][col] = EMPTY
        return None

    def check_immediate_loss(self, board, player):
        """Vérifie si un coup adverse peut gagner immédiatement (pour le bloquer)"""
        opponent = ROUGE if player == JAUNE else JAUNE
        for col in range(9):
            if board.is_valid_move(col):
                row = board.place_token(col, opponent)
                if row is not None:
                    if self.check_win({'grid': board.grid}, row, col, opponent)[0]:
                        board.grid[row][col] = EMPTY
                        return col
                    board.grid[row][col] = EMPTY
        return None

    def minimax(self, board, depth, is_maximizing, alpha, beta, player):
        """Algorithme Minimax avec élagage alpha-bêta et priorités"""
        # Vérifier d'abord les coups gagnants immédiats
        if is_maximizing:
            winning_move = self.check_immediate_win(board, player)
            if winning_move is not None:
                return float('inf'), winning_move

            # Vérifier les coups perdants immédiats à bloquer
            opponent = ROUGE if player == JAUNE else JAUNE
            blocking_move = self.check_immediate_loss(board, player)
            if blocking_move is not None:
                return float('inf') - 1, blocking_move  # Juste en dessous d'un coup gagnant

        if depth == 0 or board.is_full():
            return self.evaluate_position(board, self.depth - depth, is_maximizing, alpha, beta), None

        if is_maximizing:
            best_score = -float('inf')
            best_move = None
            for col in range(9):
                if board.is_valid_move(col):
                    row = board.place_token(col, player)
                    if row is not None:
                        score, _ = self.minimax(board, depth - 1, False, alpha, beta, player)
                        board.grid[row][col] = EMPTY  # Annuler le coup

                        if score > best_score:
                            best_score = score
                            best_move = col

                        alpha = max(alpha, best_score)
                        if beta <= alpha:
                            break  # Élagage beta
            return best_score, best_move
        else:
            best_score = float('inf')
            best_move = None
            opponent = ROUGE if player == JAUNE else JAUNE
            for col in range(9):
                if board.is_valid_move(col):
                    row = board.place_token(col, opponent)
                    if row is not None:
                        score, _ = self.minimax(board, depth - 1, True, alpha, beta, player)
                        board.grid[row][col] = EMPTY  # Annuler le coup

                        if score < best_score:
                            best_score = score
                            best_move = col

                        beta = min(beta, best_score)
                        if beta <= alpha:
                            break  # Élagage alpha
            return best_score, best_move

    def choose_move(self, board, current_player):
        """Choisit le meilleur coup en utilisant Minimax avec élagage alpha-bêta et priorités"""
        if self.ai_type == 'random':
            valid_moves = [col for col in range(board.cols) if board.is_valid_move(col)]
            return random.choice(valid_moves), None, None

        # 1. D'abord vérifier si on peut gagner immédiatement
        winning_move = self.check_immediate_win(board, current_player)
        if winning_move is not None:
            scores = {col: 0.0 for col in range(9)}
            scores[winning_move] = float('inf')
            return winning_move, float('inf'), scores

        # 2. Ensuite vérifier si on doit bloquer un coup gagnant de l'adversaire
        opponent = ROUGE if current_player == JAUNE else JAUNE
        blocking_move = self.check_immediate_loss(board, current_player)
        if blocking_move is not None:
            scores = {col: 0.0 for col in range(9)}
            scores[blocking_move] = float('inf') - 1
            return blocking_move, float('inf') - 1, scores

        # 3. Sinon utiliser Minimax pour trouver le meilleur coup
        best_score = -float('inf')
        best_move = None
        scores = {}

        for col in range(board.cols):
            if board.is_valid_move(col):
                row = board.place_token(col, current_player)
                if row is not None:
                    score, _ = self.minimax(board, self.depth - 1, False, -float('inf'), float('inf'), current_player)
                    board.grid[row][col] = EMPTY  # Annuler le coup

                    scores[col] = score

                    if score > best_score:
                        best_score = score
                        best_move = col

        return best_move, best_score, scores

    def check_win(self, board_obj, row, col, player):
        """Vérifie si le dernier coup est gagnant (copie de la fonction du module principal)"""
        board = board_obj.grid if hasattr(board_obj, 'grid') else board_obj
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

        for dr, dc in directions:
            count = 1
            r, c = row + dr, col + dc

            while 0 <= r < 9 and 0 <= c < 9 and board[r][c] == player:
                count += 1
                r += dr
                c += dc

            r, c = row - dr, col - dc
            while 0 <= r < 9 and 0 <= c < 9 and board[r][c] == player:
                count += 1
                r -= dr
                c -= dc

            if count >= 4:
                return True

        return False
