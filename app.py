#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, send_from_directory
from flask_session import Session
import os
import random
import json
import copy
from datetime import datetime
import uuid
import math
import time
import traceback
import csv
from io import StringIO
from queue import Queue
from threading import Thread
from werkzeug.routing import BuildError

# Import du DBManager
from db_manager import DBManager, EMPTY, ROUGE, JAUNE

# Configuration de l'application
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'votre_cle_secrete_ici'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
Session(app)

# Constantes du jeu - 9x9
BOARD_ROWS = 9
BOARD_COLS = 9
LEARNING_WEIGHTS_FILE = 'minimax_config.json'
GENERATION_QUEUE = Queue()
SCRAPE_QUEUE = Queue()

# Initialisation du DBManager
db_manager = DBManager(
    db_name='dbp4',
    user='youssef',
    password='Kassou00.',
    host='localhost',
    port=5432
)

# ====================== FONCTIONS UTILITAIRES GLOBALES ======================
def safe_max(iterable, default=None):
    """Fonction sécurisée pour trouver le maximum"""
    if not iterable:
        return default
    try:
        filtered = [x for x in iterable if x is not None and not math.isinf(x) and x != -float('inf')]
        return max(filtered) if filtered else default
    except (TypeError, ValueError):
        return default

def safe_min(iterable, default=None):
    """Fonction sécurisée pour trouver le minimum"""
    if not iterable:
        return default
    try:
        filtered = [x for x in iterable if x is not None and not math.isinf(x) and x != float('inf')]
        return min(filtered) if filtered else default
    except (TypeError, ValueError):
        return default

def safe_get(dictionary, key, default=None):
    """Fonction sécurisée pour accéder à un dictionnaire"""
    try:
        return dictionary.get(key, default) if dictionary else default
    except Exception:
        return default

def safe_divide(numerator, denominator, default=0):
    """Division sécurisée"""
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except Exception:
        return default

# ====================== CLASSES DE JEU ======================
class AIPlayer:
    """
    IA Puissance 4 — Minimax + Alpha-Beta + Optimisations
    - Heuristique par fenetres de 4 (scan complet)
    - Table de transposition avec flags exact/lower/upper
    - Killer moves
    - Pas de deepcopy — modification en place
    - Approfondissement iteratif pour utiliser le temps au mieux
    """

    def __init__(self, ai_type="random", depth=5):
        self.ai_type = ai_type
        self.depth   = depth
        self.tt      = {}   # Transposition table : key -> (score, flag, depth, move)
        self.killers = [[None, None] for _ in range(30)]
        self.pos_w   = self._pos_weights()

    # ------------------------------------------------------------------
    def _pos_weights(self):
        w = []
        for r in range(BOARD_ROWS):
            row = []
            for c in range(BOARD_COLS):
                dr = BOARD_ROWS // 2 - abs(r - BOARD_ROWS // 2)
                dc = BOARD_COLS // 2 - abs(c - BOARD_COLS // 2)
                row.append(dr + dc)
            w.append(row)
        return w

    def _key(self, board):
        return tuple(cell for row in board for cell in row)

    # ------------------------------------------------------------------
    def _eval_window(self, w, player, opp):
        p = w.count(player)
        o = w.count(opp)
        e = w.count(EMPTY)
        if o > 0 and p > 0:
            return 0
        if p == 4: return  500000
        if p == 3: return    2000
        if p == 2: return     100
        if p == 1: return       5
        if o == 4: return -600000
        if o == 3: return  -3000
        if o == 2: return   -150
        if o == 1: return     -6
        return 0

    def heuristic(self, board, player):
        """Scan de toutes les fenetres de 4 — horizontal / vertical / diagonales"""
        opp   = ROUGE if player == JAUNE else JAUNE
        score = 0

        # Horizontal
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS - 3):
                score += self._eval_window([board[r][c+i] for i in range(4)], player, opp)

        # Vertical
        for c in range(BOARD_COLS):
            for r in range(BOARD_ROWS - 3):
                score += self._eval_window([board[r+i][c] for i in range(4)], player, opp)

        # Diag descendante
        for r in range(BOARD_ROWS - 3):
            for c in range(BOARD_COLS - 3):
                score += self._eval_window([board[r+i][c+i] for i in range(4)], player, opp)

        # Diag montante
        for r in range(3, BOARD_ROWS):
            for c in range(BOARD_COLS - 3):
                score += self._eval_window([board[r-i][c+i] for i in range(4)], player, opp)

        # Bonus positionnel
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                if board[r][c] == player:
                    score += self.pos_w[r][c]
                elif board[r][c] == opp:
                    score -= self.pos_w[r][c]

        return score

    # ------------------------------------------------------------------
    def _win_col(self, board, player):
        """Retourne la premiere colonne gagnante ou None"""
        for col in range(BOARD_COLS):
            if is_valid_move(board, col):
                row = get_next_open_row(board, col)
                if row is not None:
                    board[row][col] = player
                    win = check_win(board, row, col, player)[0]
                    board[row][col] = EMPTY
                    if win:
                        return col
        return None

    def _count_threats(self, board, player):
        """Nombre de coups gagnants disponibles"""
        n = 0
        for col in range(BOARD_COLS):
            if is_valid_move(board, col):
                row = get_next_open_row(board, col)
                if row is not None:
                    board[row][col] = player
                    if check_win(board, row, col, player)[0]:
                        n += 1
                    board[row][col] = EMPTY
        return n

    # ------------------------------------------------------------------
    def _order(self, board, moves, player, ply):
        """Trie les coups : killer > centre > score rapide"""
        opp = ROUGE if player == JAUNE else JAUNE
        scored = []
        k0 = self.killers[ply][0] if ply < len(self.killers) else None
        k1 = self.killers[ply][1] if ply < len(self.killers) else None

        for col in moves:
            row = get_next_open_row(board, col)
            if row is None:
                continue
            s = self.pos_w[row][col] * 3
            if col == k0: s += 8000
            elif col == k1: s += 4000

            # Fenetre rapide autour du coup
            board[row][col] = player
            for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                w = []
                for i in range(-3, 4):
                    r2, c2 = row+i*dr, col+i*dc
                    if 0 <= r2 < BOARD_ROWS and 0 <= c2 < BOARD_COLS:
                        w.append(board[r2][c2])
                for i in range(len(w)-3):
                    seg = w[i:i+4]
                    pc = seg.count(player)
                    ec = seg.count(EMPTY)
                    if pc == 3 and ec == 1: s += 900
                    elif pc == 2 and ec == 2: s += 80
            board[row][col] = EMPTY

            board[row][col] = opp
            for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                w = []
                for i in range(-3, 4):
                    r2, c2 = row+i*dr, col+i*dc
                    if 0 <= r2 < BOARD_ROWS and 0 <= c2 < BOARD_COLS:
                        w.append(board[r2][c2])
                for i in range(len(w)-3):
                    seg = w[i:i+4]
                    oc = seg.count(opp)
                    ec = seg.count(EMPTY)
                    if oc == 3 and ec == 1: s += 1100
                    elif oc == 2 and ec == 2: s += 90
            board[row][col] = EMPTY

            scored.append((col, s))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored]

    # ------------------------------------------------------------------
    def minimax(self, board, depth, ply, maximizing, player,
                alpha=-float("inf"), beta=float("inf")):
        opp = ROUGE if player == JAUNE else JAUNE
        cur = player if maximizing else opp

        # Table de transposition
        key = self._key(board)
        if key in self.tt:
            s, flag, d, m = self.tt[key]
            if d >= depth:
                if flag == 0:   return s, m        # Exact
                elif flag == 1: alpha = max(alpha, s)  # Lower bound
                elif flag == 2: beta  = min(beta,  s)  # Upper bound
                if alpha >= beta:
                    return s, m

        # Victoire immediate du joueur courant
        wc = self._win_col(board, cur)
        if wc is not None:
            sc = (500000 + depth * 10) if maximizing else -(500000 + depth * 10)
            return sc, wc

        # Bloquer victoire adverse
        bc = self._win_col(board, opp if maximizing else player)
        if bc is not None:
            sc = (499000 + depth * 10) if maximizing else -(499000 + depth * 10)
            return sc, bc

        if depth == 0 or is_board_full(board):
            sc = self.heuristic(board, player if maximizing else opp)
            return sc, None

        moves = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
        if not moves:
            return 0, None

        ordered   = self._order(board, moves, cur, ply)
        best_move = ordered[0]
        orig_alpha = alpha

        if maximizing:
            best = -float("inf")
            for col in ordered:
                row = get_next_open_row(board, col)
                if row is None: continue
                board[row][col] = player
                if check_win(board, row, col, player)[0]:
                    board[row][col] = EMPTY
                    sc = 500000 + depth * 10
                    self.tt[key] = (sc, 0, depth, col)
                    return sc, col
                sc, _ = self.minimax(board, depth-1, ply+1, False, opp, alpha, beta)
                board[row][col] = EMPTY
                if sc > best:
                    best = sc
                    best_move = col
                alpha = max(alpha, best)
                if alpha >= beta:
                    if ply < len(self.killers) and self.killers[ply][0] != col:
                        self.killers[ply][1] = self.killers[ply][0]
                        self.killers[ply][0] = col
                    break
        else:
            best = float("inf")
            for col in ordered:
                row = get_next_open_row(board, col)
                if row is None: continue
                board[row][col] = opp
                if check_win(board, row, col, opp)[0]:
                    board[row][col] = EMPTY
                    sc = -(500000 + depth * 10)
                    self.tt[key] = (sc, 0, depth, col)
                    return sc, col
                sc, _ = self.minimax(board, depth-1, ply+1, True, player, alpha, beta)
                board[row][col] = EMPTY
                if sc < best:
                    best = sc
                    best_move = col
                beta = min(beta, best)
                if alpha >= beta:
                    if ply < len(self.killers) and self.killers[ply][0] != col:
                        self.killers[ply][1] = self.killers[ply][0]
                        self.killers[ply][0] = col
                    break

        # Stocker dans la table de transposition avec flag
        flag = 0 if best > orig_alpha and best < beta else (1 if best >= beta else 2)
        self.tt[key] = (best, flag, depth, best_move)
        if len(self.tt) > 500000:
            self.tt.clear()

        return best, best_move

    # ------------------------------------------------------------------
    def choose_move(self, board, current_player):
        if self.ai_type == "random":
            valid = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
            return (random.choice(valid) if valid else None), None, {}

        self.tt.clear()
        self.killers = [[None, None] for _ in range(30)]
        opp = ROUGE if current_player == JAUNE else JAUNE

        # 1. Victoire immediate
        wc = self._win_col(board, current_player)
        if wc is not None:
            return wc, float("inf"), {wc: float("inf")}

        # 2. Bloquer victoire adverse
        bc = self._win_col(board, opp)
        if bc is not None:
            return bc, float("inf")-1, {bc: float("inf")-1}

        # 3. Double menace — creer une position avec 2 coups gagnants
        best_dt, best_dt_n = None, 0
        for col in range(BOARD_COLS):
            if is_valid_move(board, col):
                row = get_next_open_row(board, col)
                if row is not None:
                    board[row][col] = current_player
                    n = self._count_threats(board, current_player)
                    board[row][col] = EMPTY
                    if n >= 2 and n > best_dt_n:
                        best_dt_n = n
                        best_dt = col
        if best_dt is not None:
            return best_dt, float("inf")-2, {best_dt: float("inf")-2}

        # 4. Approfondissement iteratif — on commence a depth=2 et on monte
        #    jusqu a self.depth. Ca permet d avoir toujours un bon coup meme
        #    si le temps manque, et l elagage est plus efficace.
        valid  = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
        best_col   = valid[0]
        best_score = -float("inf")
        scores     = {}

        for d in range(2, self.depth + 1):
            sc, mv = self.minimax(board, d, 0, True, current_player,
                                   -float("inf"), float("inf"))
            if mv is not None:
                best_col   = mv
                best_score = sc

        # Scores pour affichage
        for col in valid:
            row = get_next_open_row(board, col)
            if row is not None:
                board[row][col] = current_player
                sc, _ = self.minimax(board, max(1, self.depth-2), 0, False,
                                      opp, -float("inf"), float("inf"))
                board[row][col] = EMPTY
                scores[col] = -sc

        return best_col, best_score, scores

# ====================== FONCTIONS UTILITAIRES ======================
def create_board():
    """Crée un nouveau plateau de jeu vide"""
    return [[EMPTY for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)]

def is_valid_move(board, col):
    """Vérifie si un coup est valide dans la colonne spécifiée"""
    return 0 <= col < BOARD_COLS and board[0][col] == EMPTY

def get_next_open_row(board, col):
    """Trouve la prochaine rangée disponible dans la colonne spécifiée"""
    for r in range(BOARD_ROWS - 1, -1, -1):
        if board[r][col] == EMPTY:
            return r
    return None

def drop_piece(board, row, col, piece):
    """Place un jeton dans le plateau"""
    if row is not None and 0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS:
        if board[row][col] == EMPTY:
            board[row][col] = piece
            return True
    return False

def check_win(board, row, col, player):
    """Vérifie si le dernier coup est gagnant"""
    if row is None or col is None:
        return False, []

    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

    for dr, dc in directions:
        count = 1
        current_cells = [(row, col)]

        r, c = row + dr, col + dc
        while 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS and board[r][c] == player:
            count += 1
            current_cells.append((r, c))
            r += dr
            c += dc

        r, c = row - dr, col - dc
        while 0 <= r < BOARD_ROWS and 0 <= c < BOARD_COLS and board[r][c] == player:
            count += 1
            current_cells.append((r, c))
            r -= dr
            c -= dc

        if count >= 4:
            return True, current_cells

    return False, []

def is_board_full(board):
    """Vérifie si le plateau est plein"""
    return all(cell != EMPTY for row in board for cell in row)

def determine_current_player(board, move_history=None):
    """Détermine le joueur courant en fonction de l'état du plateau"""
    rouge_count = sum(row.count(ROUGE) for row in board)
    jaune_count = sum(row.count(JAUNE) for row in board)
    if rouge_count == jaune_count:
        return ROUGE
    return JAUNE

def validate_and_fix_game_state(game_state):
    """Valide et corrige l'état du jeu si nécessaire"""
    board = game_state['board']
    move_history = game_state.get('move_history', [])
    current_player = game_state.get('current_player', ROUGE)
    correct_player = determine_current_player(board, move_history)
    if current_player != correct_player:
        game_state['current_player'] = correct_player
    return game_state

def play_ai_random_move(game_state):
    """Joue un coup aléatoire pour l'IA"""
    board = game_state['board']
    valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]

    if not valid_cols:
        return False

    col = random.choice(valid_cols)
    row = get_next_open_row(board, col)
    if not drop_piece(board, row, col, JAUNE):
        return False

    is_win, winning_cells = check_win(board, row, col, JAUNE)
    game_over = is_win or is_board_full(board)

    game_state.update({
        'last_move': [row, col],
        'winning_cells': winning_cells,
        'game_over': game_over,
        'winner': JAUNE if is_win else 0 if game_over else None,
        'current_player': ROUGE if not game_over else None
    })
    game_state['move_history'].append([row, col, JAUNE])
    return True

def play_ai_minimax_move(game_state):
    """Joue un coup en utilisant l'algorithme Minimax"""
    board = game_state['board']
    valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]

    if not valid_cols:
        return False

    ai_player = AIPlayer(ai_type='minimax', depth=game_state['ai_depth'])
    col, score, scores = ai_player.choose_move(board, JAUNE)

    if col is None:
        col = random.choice(valid_cols) if valid_cols else None
    if col is None:
        return False

    row = get_next_open_row(board, col)
    if row is None:
        return False

    if not drop_piece(board, row, col, JAUNE):
        return False

    is_win, winning_cells = check_win(board, row, col, JAUNE)
    game_over = is_win or is_board_full(board)

    game_state.update({
        'last_move': [row, col],
        'winning_cells': winning_cells,
        'game_over': game_over,
        'winner': JAUNE if is_win else 0 if game_over else None,
        'current_player': ROUGE if not game_over else None,
        'minimax_scores': scores
    })
    game_state['move_history'].append([row, col, JAUNE])
    return True

def calculate_minimax_scores(board, player, depth=None, weights=None):
    """Calcule les scores Minimax pour chaque colonne avec gestion des erreurs"""
    if weights is None:
        weights = load_learning_weights()
    depth = depth if depth is not None else weights.get('depth', 5)

    scores = []
    opponent = JAUNE if player == ROUGE else ROUGE

    for col in range(BOARD_COLS):
        if not is_valid_move(board, col):
            scores.append(-float('inf'))
            continue

        row = get_next_open_row(board, col)
        if row is None:
            scores.append(-float('inf'))
            continue

        temp_board = copy.deepcopy(board)
        drop_piece(temp_board, row, col, player)

        if check_win(temp_board, row, col, player)[0]:
            scores.append(1000000)
            continue

        opponent_winning_move = False
        for c in range(BOARD_COLS):
            if is_valid_move(temp_board, c):
                test_row = get_next_open_row(temp_board, c)
                test_board_copy = copy.deepcopy(temp_board)
                drop_piece(test_board_copy, test_row, c, opponent)
                if check_win(test_board_copy, test_row, c, opponent)[0]:
                    opponent_winning_move = True
                    break

        if opponent_winning_move:
            scores.append(-10000)
            continue

        try:
            ai_player = AIPlayer(depth=depth)
            score = ai_player.evaluate_position(temp_board, depth - 1, player == JAUNE)
            scores.append(score if not math.isinf(score) else -1000000)
        except Exception as e:
            print(f"Erreur de calcul Minimax pour colonne {col}: {e}")
            scores.append(0)

    while len(scores) < BOARD_COLS:
        scores.append(-float('inf'))

    return scores

def load_learning_weights():
    """Charge les poids d'apprentissage avec des valeurs optimisées"""
    try:
        if os.path.exists(LEARNING_WEIGHTS_FILE):
            with open(LEARNING_WEIGHTS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des poids: {e}")
    return {
        'center_weight': 6.0,
        'three_in_row_weight': 100.0,
        'two_in_row_weight': 10.0,
        'opponent_three_weight': -200.0,
        'depth': 5,
        'learning_rate': 0.1,
        'exploration_rate': 0.1
    }

def save_learning_weights(weights):
    """Sauvegarde les poids d'apprentissage dans un fichier"""
    try:
        with open(LEARNING_WEIGHTS_FILE, 'w') as f:
            json.dump(weights, f, indent=2)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des poids: {e}")

def learn_from_database(max_games=500):
    """Apprend depuis les parties de la BDD et ajuste les poids"""
    try:
        if not db_manager.test_connection():
            print("Apprentissage annule - BDD non disponible")
            return

        # Recuperer les parties terminees avec un vainqueur
        games, total = db_manager.get_all_games_paginated(
            page=1, per_page=max_games,
            sort_by='timestamp_end', sort_order='desc'
        )

        if not games:
            print("Aucune partie trouvee pour l apprentissage")
            return

        weights = load_learning_weights()
        lr = weights.get('learning_rate', 0.01)

        jaune_wins = 0
        rouge_wins = 0
        total_center_moves = 0
        total_moves = 0
        total_game_length = 0
        counted = 0

        for game in games:
            winner = game.get('winner')
            history = game.get('history') or []

            if not history or not winner:
                continue

            # Compter victoires
            if winner == 'Jaune' or winner == JAUNE:
                jaune_wins += 1
            elif winner == 'Rouge' or winner == ROUGE:
                rouge_wins += 1

            # Analyser les coups
            for move in history:
                col = move[1] if isinstance(move, list) else move.get('col', 4)
                total_moves += 1
                # Coup au centre (colonnes 3,4,5)
                if 3 <= col <= 5:
                    total_center_moves += 1

            total_game_length += len(history)
            counted += 1

        if counted == 0:
            return

        avg_game_length = total_game_length / counted
        center_ratio = total_center_moves / max(total_moves, 1)

        # Ajuster center_weight selon l usage du centre dans les victoires
        if center_ratio > 0.4:
            weights['center_weight'] = min(10.0, weights['center_weight'] + lr)
        else:
            weights['center_weight'] = max(3.0, weights['center_weight'] - lr)

        # Ajuster three_in_row selon longueur moyenne des parties
        # Parties courtes = victoires rapides = alignements de 3 importants
        if avg_game_length < 20:
            weights['three_in_row_weight'] = min(200.0, weights['three_in_row_weight'] + lr * 10)
        elif avg_game_length > 40:
            weights['three_in_row_weight'] = max(50.0, weights['three_in_row_weight'] - lr * 5)

        # Ajuster opponent_three_weight selon ratio victoires adverses
        total_w = jaune_wins + rouge_wins
        if total_w > 0:
            rouge_ratio = rouge_wins / total_w
            # Si rouge gagne beaucoup, l IA doit mieux defendre
            if rouge_ratio > 0.6:
                weights['opponent_three_weight'] = max(-400.0, weights['opponent_three_weight'] - lr * 20)
            elif rouge_ratio < 0.3:
                weights['opponent_three_weight'] = min(-100.0, weights['opponent_three_weight'] + lr * 10)

        save_learning_weights(weights)
        print(f"Apprentissage termine sur {counted} parties")
        print(f"  Victoires Jaune: {jaune_wins} | Rouge: {rouge_wins}")
        print(f"  Longueur moyenne: {avg_game_length:.1f} coups")
        print(f"  Nouveaux poids: center={weights['center_weight']:.2f}, three={weights['three_in_row_weight']:.2f}, opp={weights['opponent_three_weight']:.2f}")

    except Exception as e:
        print(f"Erreur lors de l apprentissage: {e}")
        traceback.print_exc()

def save_finished_game_to_db(game_state):
    """Sauvegarde une partie terminée dans la base de données"""
    try:
        if not db_manager.test_connection():
            print("❌ Impossible de se connecter à la base de données")
            return False

        winner = game_state['winner']
        mode = game_state['mode']
        history = game_state['move_history']
        ai_type = game_state.get('ai_type', 'random')
        board = game_state['board']
        winning_cells = game_state.get('winning_cells', [])

        winner_str = "Rouge" if winner == ROUGE else "Jaune" if winner == JAUNE else "Nul"
        confidence = 0.9 if ai_type == "minimax" else 0.5

        result = db_manager.save_result(
            winner=winner_str,
            mode=mode,
            history=history,
            confidence=confidence,
            ai_type=ai_type,
            winning_cells=winning_cells,
            board=board
        )

        if result:
            print(f"✅ Partie sauvegardée dans la BDD (ID: {result})")
            return True
        else:
            print("❌ Échec de la sauvegarde de la partie")
            return False
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde de la partie terminée: {e}")
        traceback.print_exc()
        return False

def process_import_file(file_content, mode=2):
    """Traite le contenu d'un fichier texte contenant une séquence de coups"""
    try:
        moves_str = file_content.replace('\n', ' ').replace('\r', ' ')
        moves = []
        for num_str in moves_str.split():
            if num_str.strip() and num_str.isdigit():
                num = int(num_str)
                if 1 <= num <= BOARD_COLS:
                    moves.append(num - 1)

        if not moves:
            return None, "Aucun coup valide trouvé dans le fichier"

        board = create_board()
        move_history = []
        current_player = ROUGE
        game_over = False
        winner = None
        winning_cells = []

        for move_col in moves:
            if game_over:
                break
            if not is_valid_move(board, move_col):
                return None, f"Colonne {move_col + 1} pleine ou invalide au coup {len(move_history) + 1}"

            row = get_next_open_row(board, move_col)
            drop_piece(board, row, move_col, current_player)
            move_history.append([row, move_col, current_player])

            is_win, winning_cells = check_win(board, row, move_col, current_player)
            if is_win:
                game_over = True
                winner = current_player
            elif is_board_full(board):
                game_over = True
                winner = 0

            current_player = JAUNE if current_player == ROUGE else ROUGE

        ai_type = None
        if mode == 0:
            ai_type = 'random'
        elif mode == 1:
            ai_type = 'minimax'

        return {
            'board': board,
            'move_history': move_history,
            'game_over': game_over,
            'winner': winner,
            'winning_cells': winning_cells,
            'mode': mode,
            'ai_type': ai_type,
            'current_player': current_player if not game_over else None
        }, None
    except Exception as e:
        return None, f"Erreur lors du traitement du fichier: {str(e)}"

def prepare_game_for_display(game):
    """Prépare un jeu pour l'affichage avec gestion sécurisée des données"""
    if not game:
        return {
            'game_id': 'N/A',
            'mode': 2,
            'mode_name': "Inconnu",
            'winner': None,
            'ai_type': 'N/A',
            'winning_cells': [],
            'timestamp_end': datetime.now(),
            'num_rows': BOARD_ROWS,
            'num_columns': BOARD_COLS,
            'history': [],
            'board': [[EMPTY for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)],
            'winner_class': 'bg-secondary',
            'formatted_date': "Inconnu",
            'move_count': 0
        }

    game.setdefault('mode', 2)
    game.setdefault('winner', None)
    game.setdefault('ai_type', 'random')
    game.setdefault('winning_cells', [])
    game.setdefault('timestamp_end', datetime.now())
    game.setdefault('num_rows', BOARD_ROWS)
    game.setdefault('num_columns', BOARD_COLS)
    game.setdefault('history', [])
    game.setdefault('board', [[EMPTY for _ in range(BOARD_COLS)] for _ in range(BOARD_ROWS)])

    game['mode_name'] = {
        0: "IA vs IA",
        1: "Joueur vs IA",
        2: "Joueur vs Joueur"
    }.get(game['mode'], "Inconnu")

    game['ai_type_display'] = None if game['mode'] == 2 else game.get('ai_type', 'N/A')

    winner = game['winner']
    if isinstance(winner, int):
        winner = "Rouge" if winner == ROUGE else "Jaune" if winner == JAUNE else "Nul"

    game['winner_class'] = {
        'Rouge': 'bg-danger',
        'Jaune': 'bg-warning text-dark',
        'Nul': 'bg-secondary',
        None: 'bg-secondary'
    }.get(winner, 'bg-secondary')

    try:
        game['formatted_date'] = game['timestamp_end'].strftime('%d/%m/%Y %H:%M') if game['timestamp_end'] else "Inconnu"
    except Exception:
        game['formatted_date'] = "Inconnu"

    game['move_count'] = len(game.get('history', []))

    return game


# ====================== FILTRES DE TEMPLATE ======================
@app.template_filter('date')
def format_datetime(value, format='%d/%m/%Y %H:%M'):
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            value = datetime.fromtimestamp(value)
        return value.strftime(format)
    except Exception:
        return ""

@app.template_filter('player_name')
def player_name(value):
    if value == ROUGE:
        return "Rouge"
    elif value == JAUNE:
        return "Jaune"
    return "Inconnu"

@app.template_filter('player_color')
def player_color(value):
    if value == ROUGE:
        return "text-danger"
    elif value == JAUNE:
        return "text-warning"
    return ""

@app.template_filter('player_icon')
def player_icon(value):
    if value == ROUGE:
        return "fa-circle text-danger"
    elif value == JAUNE:
        return "fa-circle text-warning"
    return "fa-question"

@app.template_filter('max_score_index')
def max_score_index(scores):
    """Retourne l'index du score maximum de manière sécurisée"""
    if not scores:
        return -1
    max_val = None
    max_index = -1
    for i, score in enumerate(scores):
        if score is not None and not math.isinf(score) and score != -float('inf'):
            if max_val is None or score > max_val:
                max_val = score
                max_index = i
    return max_index


# ====================== ROUTES PRINCIPALES ======================
@app.route('/')
def index():
    """Page d'accueil avec gestion sécurisée des variables"""
    try:
        current_year = datetime.now().year
        saved_games_count = 0
        db_games_count = 0
        db_connected = False

        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        if os.path.exists(save_dir):
            saved_games_count = len([f for f in os.listdir(save_dir) if f.endswith('.json')])

        try:
            db_connected = db_manager.test_connection()
            if db_connected:
                games, _ = db_manager.get_all_games_paginated(page=1, per_page=1)
                db_games_count = len(games) if games else 0
        except Exception as e:
            print(f"Erreur lors du comptage des parties: {e}")
            db_connected = False

        return render_template('index.html',
                               saved_games_count=saved_games_count,
                               db_games_count=db_games_count,
                               db_connected=db_connected,
                               current_year=current_year,
                               BOARD_ROWS=BOARD_ROWS,
                               BOARD_COLS=BOARD_COLS)
    except Exception as e:
        print(f"Erreur dans la route index: {e}")
        return render_template('index.html',
                               saved_games_count=0,
                               db_games_count=0,
                               db_connected=False,
                               current_year=datetime.now().year,
                               BOARD_ROWS=BOARD_ROWS,
                               BOARD_COLS=BOARD_COLS)

@app.route('/favicon.ico')
def favicon():
    """Retourne le favicon"""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')


# ====================== ROUTES POUR LA BASE DE DONNÉES ======================
@app.route('/view_database')
def view_database():
    """Affiche les parties de la base de données avec gestion sécurisée des statistiques"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('index'))

        page = max(1, request.args.get('page', 1, type=int))
        per_page = max(1, min(100, request.args.get('per_page', 20, type=int)))
        sort_by = request.args.get('sort_by', 'timestamp_end')
        sort_order = request.args.get('sort_order', 'desc')

        mode_filter = request.args.get('mode_filter')
        if mode_filter and mode_filter.isdigit():
            mode_filter = int(mode_filter)
        else:
            mode_filter = None

        winner_filter = request.args.get('winner_filter')
        if winner_filter not in ['Rouge', 'Jaune', 'Nul']:
            winner_filter = None

        games = []
        total_games = 0
        try:
            games, total_games = db_manager.get_all_games_paginated(
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
                mode_filter=mode_filter,
                winner_filter=winner_filter
            )
        except Exception as e:
            print(f"Erreur lors de la récupération des parties: {e}")
            flash("Erreur lors de la récupération des données", "error")
            return redirect(url_for('index'))

        prepared_games = []
        for game in games:
            try:
                prepared_games.append(prepare_game_for_display(game))
            except Exception as e:
                print(f"Erreur lors de la préparation du jeu {game.get('game_id', 'inconnu')}: {e}")
                continue

        stats = {
            'total_games': total_games,
            'avg_moves': 0,
            'by_mode': {0: {'count': 0, 'percentage': 0},
                        1: {'count': 0, 'percentage': 0},
                        2: {'count': 0, 'percentage': 0}},
            'by_winner': {'Rouge': {'count': 0, 'percentage': 0},
                          'Jaune': {'count': 0, 'percentage': 0},
                          'Nul': {'count': 0, 'percentage': 0}},
            'by_ai_type': {}
        }

        if total_games > 0:
            total_moves = sum(len(safe_get(g, 'history', [])) for g in games)
            stats['avg_moves'] = round(safe_divide(total_moves, total_games), 1)

            for mode in [0, 1, 2]:
                count = sum(1 for g in games if safe_get(g, 'mode') == mode)
                stats['by_mode'][mode] = {'count': count, 'percentage': round(safe_divide(count, total_games) * 100, 1)}

            winner_counts = {'Rouge': 0, 'Jaune': 0, 'Nul': 0}
            for g in games:
                w = safe_get(g, 'winner')
                if isinstance(w, int):
                    w = "Rouge" if w == ROUGE else "Jaune" if w == JAUNE else "Nul"
                if w in winner_counts:
                    winner_counts[w] += 1
            for w, count in winner_counts.items():
                stats['by_winner'][w] = {'count': count, 'percentage': round(safe_divide(count, total_games) * 100, 1)}

            ai_types = {}
            for g in games:
                at = safe_get(g, 'ai_type', 'N/A')
                ai_types[at] = ai_types.get(at, 0) + 1
            for at, count in ai_types.items():
                stats['by_ai_type'][at] = {'count': count, 'percentage': round(safe_divide(count, total_games) * 100, 1)}

        total_pages = max(1, (total_games + per_page - 1) // per_page) if per_page > 0 else 1

        return render_template('view_database.html',
                               games=prepared_games,
                               stats=stats,
                               total_games=total_games,
                               current_page=page,
                               total_pages=total_pages,
                               per_page=per_page,
                               sort_by=sort_by,
                               sort_order=sort_order,
                               mode_filter=mode_filter,
                               winner_filter=winner_filter)

    except Exception as e:
        print(f"Erreur dans view_database: {e}")
        traceback.print_exc()
        flash(f"Erreur: {str(e)}", "error")
        return redirect(url_for('index'))


@app.route('/view_game_detail/<int:game_id>')
def view_game_detail(game_id):
    """Affiche les détails d'une partie spécifique"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('view_database'))

        game = db_manager.get_game_details(game_id)
        if not game:
            flash("Partie non trouvée dans la base de données", "error")
            return redirect(url_for('view_database'))

        game = prepare_game_for_display(game)

        # Securiser history et board (peuvent etre None depuis la BDD)
        history = game.get('history') or []
        board   = game.get('board')   or [[EMPTY]*BOARD_COLS for _ in range(BOARD_ROWS)]
        game['board']   = board
        game['history'] = history

        # Securiser winning_cells : convertir en liste de [row,col]
        raw_wc = game.get('winning_cells') or []
        winning_cells = [[wc[0], wc[1]] for wc in raw_wc if wc and len(wc) >= 2]
        game['winning_cells'] = winning_cells

        moves_history = []
        for i, move in enumerate(history):
            try:
                if isinstance(move, dict):
                    player = move.get('player', EMPTY)
                    row    = move.get('row', 0)
                    col    = move.get('col', 0)
                elif hasattr(move, '__len__') and len(move) >= 3:
                    player, row, col = move[2], move[0], move[1]
                else:
                    continue

                pname = "Rouge" if player == ROUGE else "Jaune"
                moves_history.append({
                    'index':  i + 1,
                    'player': pname,
                    'col':    col + 1,
                    'row':    game['num_rows'] - row,
                    'color':  "red" if player == ROUGE else "yellow"
                })
            except Exception as e:
                print(f"Erreur mouvement {i}: {e}")
                continue

        game['move_count'] = len(moves_history)

        return render_template('view_game_detail.html',
                               game=game,
                               board_grid=board,
                               moves_history=moves_history,
                               ROUGE=ROUGE,
                               JAUNE=JAUNE)
    except Exception as e:
        print(f"Erreur dans view_game_detail: {e}")
        traceback.print_exc()
        flash(f"Erreur: {str(e)}", "error")
        return redirect(url_for('view_database'))


@app.route('/load_game_from_db/<int:game_id>')
def load_game_from_db(game_id):
    """Charge une partie depuis la base de données"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('view_database'))

        game = db_manager.get_game_details(game_id)
        if not game:
            flash("Partie non trouvée dans la base de données", "error")
            return redirect(url_for('view_database'))

        new_mode = request.args.get('mode')
        if new_mode and new_mode.isdigit():
            new_mode = int(new_mode)
            if new_mode not in [0, 1, 2]:
                new_mode = game.get('mode', 2)
        else:
            new_mode = game.get('mode', 2)

        new_game_id = str(uuid.uuid4())
        board = [[EMPTY for _ in range(game.get('num_columns', BOARD_COLS))]
                 for _ in range(game.get('num_rows', BOARD_ROWS))]

        move_history = []
        for move in game.get('history', []):
            try:
                if isinstance(move, dict) and 'row' in move and 'col' in move and 'player' in move:
                    r, c, p = move['row'], move['col'], move['player']
                    if 0 <= r < game.get('num_rows', BOARD_ROWS) and 0 <= c < game.get('num_columns', BOARD_COLS):
                        board[r][c] = p
                        move_history.append([r, c, p])
            except Exception as e:
                print(f"Erreur lors de la reconstruction du plateau: {e}")
                continue

        current_player = determine_current_player(board)

        ai_type = game.get('ai_type', 'random')
        if new_mode == 0:
            ai_type = 'random'
        elif new_mode == 1:
            ai_type = request.args.get('ai_type', ai_type)

        ai_depth = 5
        if new_mode == 1 and ai_type == 'minimax':
            ai_depth = game.get('ai_depth', 5)

        game_state = {
            'board': copy.deepcopy(board),
            'current_player': current_player,
            'mode': new_mode,
            'ai_type': ai_type if new_mode != 2 else None,
            'ai_depth': ai_depth if new_mode == 1 and ai_type == 'minimax' else 5,
            'move_history': copy.deepcopy(move_history),
            'game_over': False,
            'winner': None,
            'last_move': move_history[-1] if move_history else None,
            'winning_cells': game.get('winning_cells', []),
            'game_id': new_game_id
        }

        if move_history:
            try:
                last_row, last_col, last_player = move_history[-1]
                is_win, winning_cells = check_win(board, last_row, last_col, last_player)
                if is_win:
                    game_state['game_over'] = True
                    game_state['winner'] = last_player
                    game_state['winning_cells'] = winning_cells
                elif is_board_full(board):
                    game_state['game_over'] = True
                    game_state['winner'] = 0
            except Exception as e:
                print(f"Erreur lors de la vérification de la fin de partie: {e}")

        if game.get('winner') in ["Rouge", "Jaune"]:
            game_state['game_over'] = True
            game_state['winner'] = ROUGE if game['winner'] == "Rouge" else JAUNE
        elif game.get('winner') == "Nul":
            game_state['game_over'] = True
            game_state['winner'] = 0

        game_state = validate_and_fix_game_state(game_state)

        if new_mode == 1 and game_state['ai_type'] == 'minimax' and not game_state['game_over']:
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                print(f"Erreur lors du calcul des scores Minimax: {e}")
                game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state

        if not game_state['game_over'] and new_mode == 1 and game_state['current_player'] == JAUNE:
            if game_state['ai_type'] == 'minimax':
                play_ai_minimax_move(game_state)
            else:
                play_ai_random_move(game_state)

        flash(f"Partie {game_id} chargée avec succès (Nouvel ID: {new_game_id})", "success")

        if new_mode == 0:
            return redirect(url_for('game_ia_vs_ia'))
        elif new_mode == 1:
            if game_state['ai_type'] == 'minimax':
                return redirect(url_for('game_player_vs_minimax_ia'))
            else:
                return redirect(url_for('game_player_vs_random_ia'))
        else:
            return redirect(url_for('game_player_vs_player'))

    except Exception as e:
        print(f"Erreur dans load_game_from_db: {e}")
        traceback.print_exc()
        flash(f"Erreur: {str(e)}", "error")
        return redirect(url_for('view_database'))


# ====================== ROUTES POUR L'EXPORT CSV ======================
@app.route('/export_database')
def export_database():
    """Exporte toute la base de données en CSV par streaming (pagination)"""
    from flask import stream_with_context, Response

    if not db_manager.test_connection():
        flash("Impossible de se connecter à la base de données", "error")
        return redirect(url_for('view_database'))

    def generate():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Gagnant", "Mode", "Type IA", "Profondeur", "Date",
                         "Nombre de coups", "Lignes", "Colonnes", "Confiance"])
        yield output.getvalue()

        page = 1
        per_page = 500
        while True:
            try:
                games, total = db_manager.get_all_games_paginated(page=page, per_page=per_page)
                if not games:
                    break
                for game in games:
                    try:
                        output = StringIO()
                        writer = csv.writer(output)
                        winner = game.get('winner', 'N/A')
                        if isinstance(winner, int):
                            winner = "Rouge" if winner == ROUGE else "Jaune" if winner == JAUNE else "Nul"
                        writer.writerow([
                            game.get('game_id', 'N/A'),
                            winner,
                            {0: "IA vs IA", 1: "Joueur vs IA", 2: "Joueur vs Joueur"}.get(game.get('mode', 2), "Inconnu"),
                            game.get('ai_type', 'N/A'),
                            game.get('ai_depth', 'N/A'),
                            game.get('timestamp_end', 'N/A'),
                            len(game.get('history', [])),
                            game.get('num_rows', BOARD_ROWS),
                            game.get('num_columns', BOARD_COLS),
                            game.get('confidence', 'N/A')
                        ])
                        yield output.getvalue()
                    except Exception as e:
                        print(f"Erreur export jeu: {e}")
                        continue
                if len(games) < per_page:
                    break
                page += 1
            except Exception as e:
                print(f"Erreur export page {page}: {e}")
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment; filename=puissance4_export_all_games.csv"}
    )


@app.route('/export_game/<int:game_id>')
def export_game(game_id):
    """Exporte une partie spécifique en CSV"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('view_database'))

        game = db_manager.get_game_details(game_id)
        if not game:
            flash("Partie non trouvée dans la base de données", "error")
            return redirect(url_for('view_database'))

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Gagnant", "Mode", "Type IA", "Profondeur", "Date",
                         "Nombre de coups", "Lignes", "Colonnes", "Cellules gagnantes", "Confiance"])

        winner = game.get('winner', 'N/A')
        if isinstance(winner, int):
            winner = "Rouge" if winner == ROUGE else "Jaune" if winner == JAUNE else "Nul"

        writer.writerow([
            game.get('game_id', 'N/A'), winner,
            {0: "IA vs IA", 1: "Joueur vs IA", 2: "Joueur vs Joueur"}.get(game.get('mode', 2), "Inconnu"),
            game.get('ai_type', 'N/A'), game.get('ai_depth', 'N/A'), game.get('timestamp_end', 'N/A'),
            len(game.get('history', [])), game.get('num_rows', BOARD_ROWS), game.get('num_columns', BOARD_COLS),
            json.dumps(game.get('winning_cells', [])) if game.get('winning_cells') else '[]',
            game.get('confidence', 'N/A')
        ])

        writer.writerow([])
        writer.writerow(["Numéro", "Joueur", "Ligne", "Colonne", "Couleur"])

        for i, move in enumerate(game.get('history', [])):
            try:
                if isinstance(move, dict):
                    player = move.get('player', EMPTY)
                    row = move.get('row', 0)
                    col = move.get('col', 0)
                else:
                    player = move[2] if len(move) > 2 else EMPTY
                    row = move[0] if len(move) > 0 else 0
                    col = move[1] if len(move) > 1 else 0
                pname = "Rouge" if player == ROUGE else "Jaune" if player == JAUNE else "Inconnu"
                color = "Rouge" if player == ROUGE else "Jaune" if player == JAUNE else "Aucun"
                writer.writerow([i + 1, pname, row + 1, col + 1, color])
            except Exception as e:
                print(f"Erreur lors de l'export du mouvement {i}: {e}")
                continue

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=puissance4_game_{game_id}.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    except Exception as e:
        print(f"Erreur dans export_game: {e}")
        traceback.print_exc()
        flash(f"Erreur lors de l'export: {str(e)}", "error")
        return redirect(url_for('view_database'))


@app.route('/export_game_moves/<int:game_id>')
def export_game_moves(game_id):
    """Exporte les mouvements d'une partie spécifique en CSV"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('view_database'))

        game = db_manager.get_game_details(game_id)
        if not game:
            flash("Partie non trouvée dans la base de données", "error")
            return redirect(url_for('view_database'))

        if not game.get('history'):
            flash("Aucun mouvement trouvé pour cette partie", "warning")
            return redirect(url_for('view_game_detail', game_id=game_id))

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Numéro de coup", "Joueur", "Ligne", "Colonne", "Couleur", "Profondeur IA"])

        for i, move in enumerate(game['history']):
            try:
                if isinstance(move, dict):
                    player = move.get('player', EMPTY)
                    row = move.get('row', 0)
                    col = move.get('col', 0)
                else:
                    player = move[2] if len(move) > 2 else EMPTY
                    row = move[0] if len(move) > 0 else 0
                    col = move[1] if len(move) > 1 else 0
                pname = "Rouge" if player == ROUGE else "Jaune" if player == JAUNE else "Inconnu"
                color = "Rouge" if player == ROUGE else "Jaune" if player == JAUNE else "Aucun"
                writer.writerow([i + 1, pname, row + 1, col + 1, color, game.get('ai_depth', 'N/A')])
            except Exception as e:
                print(f"Erreur lors de l'export du mouvement {i}: {e}")
                continue

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=puissance4_game_{game_id}_moves.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    except Exception as e:
        print(f"Erreur dans export_game_moves: {e}")
        traceback.print_exc()
        flash(f"Erreur lors de l'export: {str(e)}", "error")
        return redirect(url_for('view_game_detail', game_id=game_id))


@app.route('/clean_database')
def clean_database():
    """Nettoie la base de données en supprimant les doublons et symétries"""
    try:
        if not db_manager.test_connection():
            flash("Impossible de se connecter à la base de données", "error")
            return redirect(url_for('view_database'))

        success = db_manager.clean_database()
        if success:
            flash("Nettoyage de la base de données terminé avec succès", "success")
        else:
            flash("Échec du nettoyage de la base de données", "error")

        return redirect(url_for('view_database'))

    except Exception as e:
        print(f"Erreur dans clean_database: {e}")
        traceback.print_exc()
        flash(f"Erreur lors du nettoyage: {str(e)}", "error")
        return redirect(url_for('view_database'))


# ====================== ROUTES GÉNÉRATION & APPRENTISSAGE ======================
@app.route('/generate_games', methods=['GET', 'POST'])
def generate_games():
    """Génère des parties pour remplir la base de données"""
    if request.method == 'POST':
        try:
            num_games = int(request.form.get('num_games', 100))
            game_type = request.form.get('game_type', 'random')
            batch_size = int(request.form.get('batch_size', 10))
            minimax_depth = int(request.form.get('minimax_depth', 3))

            if num_games <= 0 or num_games > 10000:
                flash("Nombre de parties invalide (1-10000)", "error")
                return redirect(url_for('generate_games'))
            if batch_size <= 0 or batch_size > 100:
                flash("Taille de batch invalide (1-100)", "error")
                return redirect(url_for('generate_games'))
            if minimax_depth < 1 or minimax_depth > 7:
                flash("Profondeur Minimax invalide (1-7)", "error")
                return redirect(url_for('generate_games'))

            thread = Thread(target=generate_games_batch, args=(num_games, game_type, batch_size, minimax_depth))
            thread.daemon = True
            thread.start()

            flash(f"Génération de {num_games} parties {game_type} démarrée", "success")
            return redirect(url_for('view_generation_progress'))

        except Exception as e:
            flash(f"Erreur: {str(e)}", "error")
            traceback.print_exc()
            return redirect(url_for('generate_games'))

    return render_template('generate_games.html')


@app.route('/view_generation_progress')
def view_generation_progress():
    """Affiche la progression de la génération"""
    try:
        progress_data = None
        while not GENERATION_QUEUE.empty():
            progress_data = GENERATION_QUEUE.get()

        if not progress_data:
            progress_data = {'progress': 0, 'success': 0, 'total': 0, 'finished': False}

        db_count = 0
        if db_manager.test_connection():
            try:
                games, _ = db_manager.get_all_games_paginated(page=1, per_page=1)
                db_count = len(games) if games else 0
            except Exception as e:
                print(f"Erreur lors du comptage des parties: {e}")

        return render_template('generation_progress.html',
                               progress=progress_data['progress'],
                               success=progress_data['success'],
                               total=progress_data['total'],
                               current_batch=progress_data.get('current_batch', 0),
                               finished=progress_data.get('finished', False),
                               db_count=db_count)

    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('index'))


@app.route('/view_learning_weights')
def view_learning_weights():
    """Affiche les poids d'apprentissage actuels"""
    weights = load_learning_weights()
    return render_template('minimax_config.html', weights=weights)


@app.route('/update_learning_weights', methods=['POST'])
def update_learning_weights():
    """Met à jour les poids d'apprentissage"""
    try:
        weights = {
            'center_weight': float(request.form.get('center_weight', 6.0)),
            'three_in_row_weight': float(request.form.get('three_in_row_weight', 100.0)),
            'two_in_row_weight': float(request.form.get('two_in_row_weight', 10.0)),
            'opponent_three_weight': float(request.form.get('opponent_three_weight', -200.0)),
            'depth': int(request.form.get('depth', 5)),
            'learning_rate': float(request.form.get('learning_rate', 0.1)),
            'exploration_rate': float(request.form.get('exploration_rate', 0.1))
        }
        save_learning_weights(weights)
        flash("Poids d'apprentissage mis à jour avec succès", "success")
        return redirect(url_for('view_learning_weights'))
    except Exception as e:
        flash(f"Erreur lors de la mise à jour des poids: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('view_learning_weights'))


@app.route('/reset_learning_weights')
def reset_learning_weights():
    """Réinitialise les poids d'apprentissage"""
    default_weights = {
        'center_weight': 6.0,
        'three_in_row_weight': 100.0,
        'two_in_row_weight': 10.0,
        'opponent_three_weight': -200.0,
        'depth': 5,
        'learning_rate': 0.1,
        'exploration_rate': 0.1
    }
    save_learning_weights(default_weights)
    flash("Poids d'apprentissage réinitialisés aux valeurs par défaut", "success")
    return redirect(url_for('view_learning_weights'))


# ====================== ROUTES SCRAPING BGA ======================
@app.route('/scrape_bga')
def scrape_bga():
    """Page pour configurer et lancer le scraping BGA"""
    return render_template('scrape_bga.html',
                           default_rows=BOARD_ROWS,
                           default_cols=BOARD_COLS,
                           default_player_ids=["93463692"])


@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    """Lance le scraping BGA en arrière-plan"""
    try:
        rows = int(request.form.get('rows', BOARD_ROWS))
        cols = int(request.form.get('cols', BOARD_COLS))
        player_ids = [pid.strip() for pid in request.form.get('player_ids', "").split(",") if pid.strip()]

        if not player_ids:
            flash("Veuillez fournir au moins un ID de joueur", "error")
            return redirect(url_for('scrape_bga'))

        thread = Thread(target=scrape_bga_in_thread, args=(rows, cols, player_ids, SCRAPE_QUEUE))
        thread.daemon = True
        thread.start()

        flash(f"Scraping démarré pour {len(player_ids)} joueur(s)", "success")
        return redirect(url_for('scraping_progress'))

    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('scrape_bga'))


@app.route('/scraping_progress')
def scraping_progress():
    """Affiche la progression du scraping"""
    progress_data = []
    results = []
    error = None

    while not SCRAPE_QUEUE.empty():
        data = SCRAPE_QUEUE.get()
        if isinstance(data, dict):
            if 'finished' in data:
                if 'error' in data:
                    error = data['error']
                if 'results' in data:
                    results = data['results']
            else:
                progress_data.append(data)

    is_finished = any('finished' in data for data in progress_data) or error is not None

    return render_template('scraping_progress.html',
                           progress_data=progress_data,
                           results=results,
                           is_finished=is_finished,
                           error=error)


@app.route('/import_bga_sequence', methods=['POST'])
def import_bga_sequence():
    """Import une séquence depuis BGA dans une nouvelle partie"""
    try:
        sequence = request.form.get('sequence')
        mode = int(request.form.get('mode', 1))
        depth = int(request.form.get('depth', 3))

        if not sequence:
            flash("Aucune séquence fournie", "error")
            return redirect(url_for('scraping_progress'))

        game_state, error = process_import_file(sequence, mode)

        if error:
            flash(f"Erreur: {error}", "error")
            return redirect(url_for('scraping_progress'))

        if not game_state:
            flash("Impossible de traiter la séquence", "error")
            return redirect(url_for('scraping_progress'))

        game_id = str(uuid.uuid4())
        ai_type = 'minimax' if mode == 1 else 'random'

        session['game_state'] = {
            'board': game_state['board'],
            'current_player': game_state['current_player'],
            'mode': mode,
            'ai_type': ai_type,
            'ai_depth': depth,
            'move_history': game_state['move_history'],
            'game_over': game_state['game_over'],
            'winner': game_state['winner'],
            'last_move': game_state['move_history'][-1] if game_state['move_history'] else None,
            'winning_cells': game_state['winning_cells'],
            'game_id': game_id,
            'bga_sequence': sequence
        }

        session['game_state'] = validate_and_fix_game_state(session['game_state'])

        if not session['game_state']['game_over'] and mode == 1 and ai_type == 'random' and session['game_state']['current_player'] == JAUNE:
            play_ai_random_move(session['game_state'])

        if mode == 1 and ai_type == 'minimax':
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, depth, weights)
                session['game_state']['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                print(f"Erreur lors du calcul des scores Minimax après import: {e}")
                session['game_state']['minimax_scores'] = [0] * BOARD_COLS

        if game_state['game_over']:
            save_finished_game_to_db(session['game_state'])

        flash(f"Partie BGA importée avec succès (ID: {game_id})", "success")

        if mode == 0:
            return redirect(url_for('game_ia_vs_ia'))
        elif mode == 1:
            if ai_type == 'minimax':
                return redirect(url_for('game_player_vs_minimax_ia'))
            else:
                return redirect(url_for('game_player_vs_random_ia'))
        elif mode == 2:
            return redirect(url_for('game_player_vs_player'))
        else:
            return redirect(url_for('index'))

    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('scraping_progress'))


# ====================== FONCTIONS DE GÉNÉRATION DE PARTIES ======================
def play_random_game():
    """Joue une partie complète entre deux IA aléatoires"""
    try:
        board = create_board()
        move_history = []
        current_player = random.choice([ROUGE, JAUNE])
        game_over = False
        winner = None

        while not game_over:
            valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
            if not valid_cols:
                break
            col = random.choice(valid_cols)
            row = get_next_open_row(board, col)
            drop_piece(board, row, col, current_player)
            move_history.append([row, col, current_player])

            is_win, _ = check_win(board, row, col, current_player)
            if is_win:
                game_over = True
                winner = current_player
            elif is_board_full(board):
                game_over = True
                winner = 0

            current_player = JAUNE if current_player == ROUGE else ROUGE

        game_state_data = {
            'board': board,
            'move_history': move_history,
            'game_over': game_over,
            'winner': winner,
            'winning_cells': [],
            'mode': 0,
            'ai_type': 'random',
            'ai_depth': 5
        }
        save_finished_game_to_db(game_state_data)
        return True
    except Exception as e:
        print(f"Erreur dans play_random_game: {e}")
        traceback.print_exc()
        return False


def generate_games_batch(total_games, game_type, batch_size, minimax_depth=3):
    """Génère des parties par batches"""
    success_count = 0

    for batch in range(0, total_games, batch_size):
        current_batch = min(batch_size, total_games - batch)
        for i in range(current_batch):
            success = play_random_game()
            if success:
                success_count += 1

        GENERATION_QUEUE.put({
            'progress': min(100, (batch + current_batch) / total_games * 100),
            'success': success_count,
            'total': min(batch + current_batch, total_games),
            'current_batch': batch + current_batch
        })
        time.sleep(0.1)

    GENERATION_QUEUE.put({
        'progress': 100,
        'success': success_count,
        'total': total_games,
        'finished': True
    })


def scrape_bga_in_thread(rows, cols, player_ids, queue):
    """Fonction simulée pour le scraping BGA"""
    try:
        total_games = random.randint(5, 20)
        for i in range(total_games):
            time.sleep(0.5)
            queue.put({
                'progress': (i + 1) / total_games * 100,
                'current': i + 1,
                'total': total_games,
                'player_id': random.choice(player_ids)
            })

        results = []
        for _ in range(random.randint(2, 5)):
            moves = [random.randint(1, cols) for _ in range(random.randint(10, 30))]
            results.append({
                'sequence': ' '.join(map(str, moves)),
                'player': random.choice(player_ids),
                'result': random.choice(['Rouge', 'Jaune', 'Nul'])
            })

        queue.put({'finished': True, 'results': results})
    except Exception as e:
        queue.put({'finished': True, 'error': str(e)})


# ====================== GESTIONNAIRES D'ERREURS ======================
@app.errorhandler(BuildError)
def handle_build_error(e):
    print(f"Erreur de routing détectée: {e}")
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


# ====================== CONTEXT PROCESSOR & MIDDLEWARE ======================
@app.context_processor
def utility_processor():
    def safe_url_for(endpoint, **values):
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return url_for('index')

    def get_current_year():
        return datetime.now().year

    def get_board_dimensions():
        return {'rows': BOARD_ROWS, 'cols': BOARD_COLS}

    return dict(
        safe_url_for=safe_url_for,
        current_year=get_current_year,
        board_dimensions=get_board_dimensions,
        safe_max=safe_max,
        safe_min=safe_min,
        safe_get=safe_get,
        max=max,
        min=min
    )

@app.after_request
def handle_json_redirects(response):
    if response.status_code == 200 and response.content_type == 'application/json':
        try:
            data = json.loads(response.get_data())
            if 'redirect' in data and data['redirect']:
                response = make_response(json.dumps({'redirect': data['redirect']}))
                response.status_code = 303
                response.headers['Location'] = data['redirect']
        except Exception:
            pass
    return response

@app.before_request
def before_request():
    if not hasattr(app, 'db_checked'):
        try:
            app.db_checked = db_manager.test_connection()
        except Exception:
            app.db_checked = False
    # Apprentissage automatique au premier demarrage
    if not hasattr(app, 'learned'):
        app.learned = True
        thread = Thread(target=learn_from_database, args=(500,))
        thread.daemon = True
        thread.start()
        print("Apprentissage depuis la BDD lance en arriere-plan")


@app.route('/get_win_in', methods=['POST'])
def get_win_in():
    """Calcule en combien de coups Rouge et Jaune peuvent gagner"""
    if 'game_state' not in session:
        return jsonify({'error': 'Aucune partie'}), 400
    try:
        board = session['game_state']['board']

        def min_moves_to_win(board, player, max_depth=6):
            """Cherche le nombre minimum de coups pour gagner avec BFS iteratif"""
            import copy as cp
            opponent = ROUGE if player == JAUNE else JAUNE

            for depth in range(1, max_depth + 1):
                # DFS avec profondeur limitee pour trouver victoire en exactement depth coups
                def can_win_in(b, d, is_my_turn):
                    if d == 0:
                        return False
                    cur = player if is_my_turn else opponent
                    for col in range(BOARD_COLS):
                        if is_valid_move(b, col):
                            row = get_next_open_row(b, col)
                            if row is None:
                                continue
                            b[row][col] = cur
                            win = check_win(b, row, col, cur)[0]
                            if win and is_my_turn:
                                b[row][col] = EMPTY
                                return True
                            if not win:
                                result = can_win_in(b, d - 1, not is_my_turn)
                                if result and is_my_turn:
                                    b[row][col] = EMPTY
                                    return True
                            b[row][col] = EMPTY
                    return False

                board_copy = [row[:] for row in board]
                if can_win_in(board_copy, depth, True):
                    return depth
            return None  # Pas trouve dans max_depth coups

        rouge_in = min_moves_to_win(board, ROUGE, max_depth=5)
        jaune_in = min_moves_to_win(board, JAUNE, max_depth=5)

        return jsonify({
            'rouge_in': rouge_in,
            'jaune_in': jaune_in
        })
    except Exception as e:
        print(f'Erreur get_win_in: {e}')
        return jsonify({'rouge_in': None, 'jaune_in': None})


@app.route('/learn_from_db')
def learn_from_db():
    """Déclenche l apprentissage depuis la BDD manuellement"""
    try:
        thread = Thread(target=learn_from_database, args=(1000,))
        thread.daemon = True
        thread.start()
        flash("Apprentissage depuis la base de données lancé !", "success")
    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
    return redirect(url_for('view_learning_weights'))


# ====================== ROUTES DE JEU (AFFICHAGE) ======================
@app.route('/game_ia_vs_ia')
def game_ia_vs_ia():
    if 'game_state' not in session or session['game_state']['mode'] != 0:
        return redirect(url_for('start_game', mode=0))

    board = session['game_state']['board']
    if len(board) != BOARD_ROWS or any(len(row) != BOARD_COLS for row in board):
        session['game_state']['board'] = create_board()

    session['game_state'] = validate_and_fix_game_state(session['game_state'])
    return render_template('game_ia_vs_ia.html',
                           game_state=session['game_state'],
                           ROUGE=ROUGE, JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/game_player_vs_random_ia')
def game_player_vs_random_ia():
    if 'game_state' not in session or session['game_state']['mode'] != 1 or session['game_state'].get('ai_type') != 'random':
        return redirect(url_for('start_game', mode=1, ai_type='random'))

    board = session['game_state']['board']
    if len(board) != BOARD_ROWS or any(len(row) != BOARD_COLS for row in board):
        session['game_state']['board'] = create_board()

    session['game_state'] = validate_and_fix_game_state(session['game_state'])
    game_state = session['game_state']

    if not game_state['game_over'] and game_state['current_player'] == JAUNE:
        play_ai_random_move(game_state)
        session['game_state'] = game_state

    return render_template('game_player_vs_random_ia.html',
                           game_state=session['game_state'],
                           ROUGE=ROUGE, JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/game_player_vs_minimax_ia')
def game_player_vs_minimax_ia():
    if 'game_state' not in session:
        return redirect(url_for('start_game_minimax'))

    game_state = session['game_state']
    if game_state['mode'] != 1 or game_state.get('ai_type') != 'minimax':
        return redirect(url_for('start_game', mode=1, ai_type='minimax'))

    if len(game_state['board']) != BOARD_ROWS or any(len(row) != BOARD_COLS for row in game_state['board']):
        game_state['board'] = create_board()

    game_state = validate_and_fix_game_state(game_state)
    session['game_state'] = game_state

    if not game_state['game_over'] and 'minimax_scores' not in game_state:
        weights = load_learning_weights()
        try:
            scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
            game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            session['game_state'] = game_state
        except Exception as e:
            print(f"Erreur lors du calcul initial des scores Minimax: {e}")
            game_state['minimax_scores'] = [0] * BOARD_COLS
            session['game_state'] = game_state

    if not game_state['game_over'] and game_state['current_player'] == JAUNE:
        play_ai_minimax_move(game_state)
        session['game_state'] = game_state

    return render_template('game_player_vs_minimax_ia.html',
                           game_state=game_state,
                           ROUGE=ROUGE, JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/game_player_vs_player')
def game_player_vs_player():
    if 'game_state' not in session or session['game_state']['mode'] != 2:
        return redirect(url_for('start_game', mode=2))

    board = session['game_state']['board']
    if len(board) != BOARD_ROWS or any(len(row) != BOARD_COLS for row in board):
        session['game_state']['board'] = create_board()

    session['game_state'] = validate_and_fix_game_state(session['game_state'])
    return render_template('game_player_vs_player.html',
                           game_state=session['game_state'],
                           ROUGE=ROUGE, JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


# ====================== ROUTES DE JEU (ACTIONS) ======================
@app.route('/play', methods=['POST'])
def play():
    """Gère un coup joué avec une gestion robuste des erreurs"""
    if 'game_state' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400

    try:
        column = int(request.form.get('column', -1))
        game_state = session['game_state']
        board = game_state['board']

        if game_state['game_over']:
            return jsonify({'error': 'La partie est déjà terminée'}), 400

        current_player = game_state['current_player']
        mode = game_state['mode']
        ai_type = game_state.get('ai_type', 'random')

        if column != -1:
            # Coup du joueur humain
            if not is_valid_move(board, column):
                return jsonify({'error': 'Colonne pleine ou invalide'}), 400
            if mode == 1 and current_player != ROUGE:
                return jsonify({'error': "Ce n'est pas votre tour"}), 400

            row = get_next_open_row(board, column)
            if row is None:
                return jsonify({'error': 'Colonne pleine'}), 400
            if not drop_piece(board, row, column, current_player):
                return jsonify({'error': 'Impossible de placer le jeton'}), 400

            is_win, winning_cells = check_win(board, row, column, current_player)
            game_over = is_win or is_board_full(board)

            game_state['last_move'] = [row, column]
            game_state['winning_cells'] = winning_cells
            game_state['move_history'].append([row, column, current_player])
            game_state['game_over'] = game_over

            if game_over:
                game_state['winner'] = current_player if is_win else 0
            else:
                game_state['current_player'] = JAUNE if mode == 1 else (JAUNE if current_player == ROUGE else ROUGE)

            session['game_state'] = game_state

            response = {
                'success': True,
                'board': board,
                'current_player': game_state['current_player'],
                'last_move': game_state['last_move'],
                'game_over': game_state['game_over'],
                'winner': current_player if is_win else None,
                'winning_cells': game_state['winning_cells'] if is_win else [],
                'move_history': game_state['move_history'],
                'next_player_is_ai': mode == 1 and not game_over
            }

            if mode == 1 and ai_type == 'minimax' and not game_over and game_state['current_player'] == ROUGE:
                try:
                    weights = load_learning_weights()
                    scores = calculate_minimax_scores(board, ROUGE, game_state['ai_depth'], weights)
                    response['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
                    response['best_col'] = scores.index(max(scores)) if max(scores) != -float('inf') else -1
                except Exception as e:
                    print(f"Erreur lors du calcul des scores Minimax: {e}")
                    response['minimax_scores'] = [0] * BOARD_COLS
                    response['best_col'] = -1

            return jsonify(response)

        else:
            # Tour de l'IA
            if mode != 1:
                return jsonify({'error': "Mode de jeu invalide pour l'IA"}), 400
            if current_player != JAUNE:
                return jsonify({'error': "Ce n'est pas le tour de l'IA"}), 400

            valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
            if not valid_cols:
                return jsonify({'error': 'Aucun coup valide disponible'}), 400

            success = play_ai_minimax_move(game_state) if ai_type == 'minimax' else play_ai_random_move(game_state)
            if not success:
                return jsonify({'error': "Impossible de jouer le coup de l'IA"}), 400

            is_win = game_state['game_over'] and game_state['winner'] == JAUNE
            game_over = game_state['game_over']

            response = {
                'success': True,
                'board': game_state['board'],
                'current_player': game_state['current_player'],
                'last_move': game_state['last_move'],
                'game_over': game_state['game_over'],
                'winner': JAUNE if is_win else None,
                'winning_cells': game_state['winning_cells'] if is_win else [],
                'move_history': game_state['move_history']
            }

            if mode == 1 and ai_type == 'minimax' and not game_over and game_state['current_player'] == ROUGE:
                try:
                    weights = load_learning_weights()
                    scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
                    response['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
                    response['best_col'] = scores.index(max(scores)) if max(scores) != -float('inf') else -1
                except Exception as e:
                    print(f"Erreur lors du calcul des scores Minimax: {e}")
                    response['minimax_scores'] = [0] * BOARD_COLS
                    response['best_col'] = -1

            return jsonify(response)

    except Exception as e:
        print(f"Erreur dans /play: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Une erreur est survenue: {str(e)}'}), 500


@app.route('/play_ia_vs_ia', methods=['POST'])
def play_ia_vs_ia():
    """Gère les coups pour le mode IA vs IA avec une gestion robuste"""
    if 'game_state' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400

    try:
        game_state = session['game_state']
        board = game_state['board']

        if game_state['game_over']:
            return jsonify({'error': 'La partie est déjà terminée'}), 400

        current_player = game_state['current_player']
        valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]

        if not valid_cols:
            return jsonify({'error': 'Aucun coup valide disponible'}), 400

        weights = load_learning_weights()
        scores = calculate_minimax_scores(board, current_player, weights.get('depth', 5), weights)

        valid_scores = [(i, score) for i, score in enumerate(scores) if is_valid_move(board, i)]
        if not valid_scores:
            return jsonify({'error': 'Aucun coup valide disponible'}), 400

        if current_player == ROUGE:
            max_score = max(score for _, score in valid_scores)
            best_cols = [col for col, score in valid_scores if score == max_score]
        else:
            min_score = min(score for _, score in valid_scores)
            best_cols = [col for col, score in valid_scores if score == min_score]

        best_cols.sort(key=lambda col: abs(col - BOARD_COLS // 2))
        col = best_cols[0]

        row = get_next_open_row(board, col)
        if row is None:
            valid_cols = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
            if not valid_cols:
                return jsonify({'error': 'Aucun coup valide disponible'}), 400
            col = random.choice(valid_cols)
            row = get_next_open_row(board, col)

        if not drop_piece(board, row, col, current_player):
            return jsonify({'error': 'Impossible de placer le jeton'}), 400

        is_win, winning_cells = check_win(board, row, col, current_player)
        game_over = is_win or is_board_full(board)

        game_state['last_move'] = [row, col]
        game_state['winning_cells'] = winning_cells
        game_state['move_history'].append([row, col, current_player])
        game_state['game_over'] = game_over

        if game_over:
            game_state['winner'] = current_player if is_win else 0
        else:
            game_state['current_player'] = JAUNE if current_player == ROUGE else ROUGE

        session['game_state'] = game_state

        return jsonify({
            'board': board,
            'current_player': game_state['current_player'],
            'last_move': game_state['last_move'],
            'game_over': game_state['game_over'],
            'winner': current_player if is_win else None,
            'winning_cells': game_state['winning_cells'] if is_win else [],
            'move_history': game_state['move_history'],
            'delay': 1000
        })

    except Exception as e:
        print(f"Erreur dans play_ia_vs_ia: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/get_minimax_scores')
def get_minimax_scores():
    """Retourne les scores Minimax pour le plateau actuel"""
    if 'game_state' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400

    try:
        game_state = session['game_state']

        if game_state['mode'] != 1 or game_state.get('ai_type') != 'minimax':
            return jsonify({'error': 'Mode de jeu non compatible avec Minimax'}), 400
        if game_state['game_over']:
            return jsonify({'error': 'La partie est déjà terminée'}), 400
        if game_state['current_player'] != ROUGE:
            return jsonify({'error': "Ce n'est pas le tour du joueur"}), 400

        weights = load_learning_weights()
        try:
            scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
            formatted_scores = [-1000000 if s == -float('inf') else round(s, 1) for s in scores]
            max_score = max(formatted_scores)
            best_col = formatted_scores.index(max_score) if max_score != -1000000 else -1
            return jsonify({'success': True, 'minimax_scores': formatted_scores, 'best_col': best_col})
        except Exception as e:
            print(f"Erreur lors du calcul des scores Minimax: {e}")
            return jsonify({'success': True, 'minimax_scores': [-1000000] * BOARD_COLS, 'best_col': -1})

    except Exception as e:
        print(f"Erreur dans get_minimax_scores: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ====================== ROUTES DE GESTION DES PARTIES ======================
@app.route('/undo', methods=['POST'])
def undo():
    """Annule le dernier coup joue pour tous les modes"""
    if 'game_state' not in session or not session['game_state']['move_history']:
        return jsonify({'error': 'Aucun coup a annuler'}), 400

    try:
        game_state = session['game_state']
        board = game_state['board']
        mode = game_state['mode']

        if len(game_state['move_history']) == 0:
            return jsonify({'error': 'Aucun coup a annuler'}), 400

        # Enlever le dernier coup joue
        last_row, last_col, last_player = game_state['move_history'][-1]
        board[last_row][last_col] = EMPTY
        game_state['move_history'].pop()

        # Redonner le tour au joueur qui vient d annuler
        game_state['current_player'] = last_player

        game_state['game_over'] = False
        game_state['winner'] = None
        game_state['last_move'] = game_state['move_history'][-1] if game_state['move_history'] else None
        game_state['winning_cells'] = []

        game_state = validate_and_fix_game_state(game_state)

        # Recalculer les scores Minimax si mode 1
        if mode == 1 and game_state.get('ai_type') == 'minimax':
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                print(f"Erreur calcul scores Minimax apres annulation: {e}")
                game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state
        return jsonify({'success': True})

    except Exception as e:
        print(f"Erreur dans undo: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/undo_one', methods=['POST'])
def undo_one():
    """Annule le dernier coup joue et redonne le tour au joueur concerne"""
    if 'game_state' not in session or not session['game_state']['move_history']:
        return jsonify({'error': 'Aucun coup a annuler'}), 400

    try:
        game_state = session['game_state']
        board = game_state['board']

        if len(game_state['move_history']) == 0:
            return jsonify({'error': 'Aucun coup a annuler'}), 400

        # Enlever le dernier coup joue
        last_row, last_col, last_player = game_state['move_history'][-1]
        board[last_row][last_col] = EMPTY
        game_state['move_history'].pop()

        # Redonner le tour au joueur dont on vient d annuler le coup
        game_state['current_player'] = last_player
        game_state['game_over'] = False
        game_state['winner'] = None
        game_state['last_move'] = game_state['move_history'][-1] if game_state['move_history'] else None
        game_state['winning_cells'] = []

        game_state = validate_and_fix_game_state(game_state)

        # Recalculer scores Minimax si besoin
        if game_state['mode'] == 1 and game_state.get('ai_type') == 'minimax':
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state

        return jsonify({
            'success': True,
            'board': board,
            'current_player': game_state['current_player'],
            'move_history': game_state['move_history'],
            'last_move': game_state['last_move'],
            'minimax_scores': game_state.get('minimax_scores', [])
        })

    except Exception as e:
        print(f"Erreur dans undo_one: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/replay/<int:mode>')
def replay(mode):
    """Recommence une partie avec les mêmes paramètres"""
    return start_game(mode)


@app.route('/replay_current')
def replay_current():
    """Recommence la partie actuelle avec le même mode"""
    if 'game_state' not in session:
        flash("Aucune partie en cours", "error")
        return redirect(url_for('index'))
    mode = session['game_state']['mode']
    return replay(mode)


@app.route('/save_game')
def save_game():
    """Sauvegarde la partie en cours et redirige vers saved_games"""
    if 'game_state' not in session:
        flash("Aucune partie en cours", "error")
        return redirect(url_for('index'))

    try:
        game_state = session['game_state']

        # S'assurer qu'un game_id existe
        if not game_state.get('game_id'):
            game_state['game_id'] = str(uuid.uuid4())
            session['game_state'] = game_state

        # Sauvegarder en BDD si la partie est terminee
        if game_state['game_over']:
            save_finished_game_to_db(game_state)

        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        os.makedirs(save_dir, exist_ok=True)

        game_data = {
            'board': game_state['board'],
            'current_player': game_state['current_player'],
            'mode': game_state['mode'],
            'ai_type': game_state.get('ai_type'),
            'ai_depth': game_state.get('ai_depth', 5),
            'move_history': game_state.get('move_history', []),
            'game_over': game_state['game_over'],
            'winner': game_state['winner'],
            'last_move': game_state.get('last_move'),
            'winning_cells': game_state.get('winning_cells', []),
            'game_id': game_state['game_id'],
            'timestamp': datetime.now().isoformat()
        }
        if 'minimax_scores' in game_state:
            game_data['minimax_scores'] = game_state['minimax_scores']

        save_path = os.path.join(save_dir, f"{game_state['game_id']}.json")
        with open(save_path, 'w') as f:
            json.dump(game_data, f, indent=2)

        flash("Partie sauvegardee avec succes !", "success")
        return redirect(url_for('saved_games'))

    except Exception as e:
        flash(f"Erreur lors de la sauvegarde: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('index'))

@app.route('/custom_board')
def custom_board():
    """Page pour créer un plateau personnalisé"""
    return render_template('custom_board.html', BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/save_custom_board', methods=['POST'])
def save_custom_board():
    """Sauvegarde un plateau personnalisé avec correction du joueur courant"""
    try:
        data = request.get_json()
        if not data or 'board' not in data or 'mode' not in data:
            return jsonify({'status': 'error', 'message': 'Données incomplètes'}), 400

        board = data['board']
        mode = int(data['mode'])
        ai_type = data.get('ai_type', 'random')
        depth = int(data.get('depth', 5))
        game_id = str(uuid.uuid4())

        if len(board) != BOARD_ROWS or any(len(row) != BOARD_COLS for row in board):
            return jsonify({'status': 'error', 'message': 'Dimensions du plateau invalides'}), 400

        for row in board:
            for cell in row:
                if cell not in [EMPTY, ROUGE, JAUNE]:
                    return jsonify({'status': 'error', 'message': 'Valeurs du plateau invalides'}), 400

        move_history = []
        for row in range(BOARD_ROWS):
            for col in range(BOARD_COLS):
                if board[row][col] == ROUGE:
                    move_history.append([row, col, ROUGE])
                elif board[row][col] == JAUNE:
                    move_history.append([row, col, JAUNE])

        current_player = determine_current_player(board)

        game_over = False
        winner = None
        winning_cells = []

        if move_history:
            last_move = move_history[-1]
            is_win, winning_cells = check_win(board, last_move[0], last_move[1], last_move[2])
            if is_win:
                game_over = True
                winner = last_move[2]
            elif is_board_full(board):
                game_over = True
                winner = 0

        game_state = {
            'board': board,
            'current_player': current_player,
            'mode': mode,
            'ai_type': ai_type if mode != 2 else None,
            'ai_depth': depth if ai_type == 'minimax' else 5,
            'move_history': move_history,
            'game_over': game_over,
            'winner': winner,
            'last_move': move_history[-1] if move_history else None,
            'winning_cells': winning_cells,
            'game_id': game_id,
            'timestamp': datetime.now().isoformat()
        }

        game_state = validate_and_fix_game_state(game_state)

        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{game_id}.json")
        with open(save_path, 'w') as f:
            json.dump(game_state, f, indent=2)

        return jsonify({
            'status': 'success',
            'message': f'Plateau personnalisé sauvegardé avec succès (ID: {game_id})',
            'game_id': game_id,
            'current_player': game_state['current_player']
        })

    except Exception as e:
        print(f"Erreur dans save_custom_board: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Erreur: {str(e)}'}), 500


@app.route('/load_game/<game_id>')
def load_game(game_id):
    """Charge une partie sauvegardée localement avec changement de mode optionnel"""
    try:
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        filepath = os.path.join(save_dir, f"{game_id}.json")

        if not os.path.exists(filepath):
            flash(f"Partie {game_id} non trouvée", "error")
            return redirect(url_for('saved_games'))

        with open(filepath, 'r') as f:
            game_data = json.load(f)

        # Lire les paramètres de mode depuis l'URL (optionnels)
        new_mode_param = request.args.get('mode')
        if new_mode_param and new_mode_param.isdigit() and int(new_mode_param) in [0, 1, 2]:
            mode = int(new_mode_param)
        else:
            mode = game_data.get('mode', 2)

        # Type d'IA selon le mode
        if mode == 0:
            ai_type = 'random'
        elif mode == 1:
            ai_type = request.args.get('ai_type', game_data.get('ai_type', 'minimax'))
            if ai_type not in ['random', 'minimax']:
                ai_type = 'minimax'
        else:
            ai_type = None

        # Profondeur Minimax
        depth_param = request.args.get('depth')
        if depth_param and depth_param.isdigit():
            ai_depth = max(1, min(7, int(depth_param)))
        else:
            ai_depth = game_data.get('ai_depth', 5)

        board = game_data['board']
        move_history = game_data.get('move_history', [])

        # Déterminer le joueur courant correct depuis le board
        current_player = determine_current_player(board)

        game_state = {
            'board': copy.deepcopy(board),
            'current_player': current_player,
            'mode': mode,
            'ai_type': ai_type,
            'ai_depth': ai_depth,
            'move_history': copy.deepcopy(move_history),
            'game_over': game_data.get('game_over', False),
            'winner': game_data.get('winner'),
            'last_move': game_data.get('last_move'),
            'winning_cells': game_data.get('winning_cells', []),
            'game_id': game_id
        }

        # Recalculer l'état de fin de partie depuis le board pour être sûr
        if not game_state['game_over'] and move_history:
            try:
                last = move_history[-1]
                last_row, last_col, last_player = last[0], last[1], last[2]
                is_win, winning_cells = check_win(board, last_row, last_col, last_player)
                if is_win:
                    game_state['game_over'] = True
                    game_state['winner'] = last_player
                    game_state['winning_cells'] = winning_cells
                elif is_board_full(board):
                    game_state['game_over'] = True
                    game_state['winner'] = 0
            except Exception as e:
                print(f"Erreur vérification fin de partie: {e}")

        game_state = validate_and_fix_game_state(game_state)

        # Calculer les scores Minimax si nécessaire
        if mode == 1 and ai_type == 'minimax' and not game_state['game_over']:
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, ai_depth, weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                print(f"Erreur calcul scores Minimax: {e}")
                game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state

        # Si c'est au tour de l'IA (mode 1, joueur courant = JAUNE), jouer automatiquement
        if not game_state['game_over'] and mode == 1 and game_state['current_player'] == JAUNE:
            if ai_type == 'minimax':
                play_ai_minimax_move(game_state)
            else:
                play_ai_random_move(game_state)
            session['game_state'] = game_state

        mode_names = {0: "IA vs IA", 1: f"Joueur vs IA ({ai_type})", 2: "Joueur vs Joueur"}
        flash(f"Partie chargée en mode {mode_names.get(mode, 'inconnu')}", "success")

        if mode == 0:
            return redirect(url_for('game_ia_vs_ia'))
        elif mode == 1:
            if ai_type == 'minimax':
                return redirect(url_for('game_player_vs_minimax_ia'))
            else:
                return redirect(url_for('game_player_vs_random_ia'))
        elif mode == 2:
            return redirect(url_for('game_player_vs_player'))
        else:
            return redirect(url_for('index'))

    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
        traceback.print_exc()
        return redirect(url_for('saved_games'))


@app.route('/saved_games')
def saved_games():
    """Affiche les parties sauvegardees localement"""
    try:
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        games_list = []

        if os.path.exists(save_dir):
            for filename in sorted(os.listdir(save_dir), reverse=True):
                if not filename.endswith('.json'):
                    continue
                filepath = os.path.join(save_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        game_data = json.load(f)

                    # game_id = nom du fichier (source de verite)
                    game_id = filename.replace('.json', '')

                    # Timestamp: depuis le JSON, sinon depuis le fichier
                    timestamp = None
                    if game_data.get('timestamp'):
                        try:
                            timestamp = datetime.fromisoformat(str(game_data['timestamp']))
                        except (ValueError, TypeError):
                            timestamp = None
                    if timestamp is None:
                        timestamp = datetime.fromtimestamp(os.path.getmtime(filepath))

                    board = game_data.get('board')
                    if not board:
                        continue

                    current_player = determine_current_player(board)

                    # ai_type: None si PvP, sinon la valeur stockee
                    ai_type = game_data.get('ai_type')  # peut etre None
                    mode = game_data.get('mode', 2)

                    games_list.append({
                        'game_id': game_id,
                        'mode': mode,
                        'ai_type': ai_type,
                        'ai_depth': game_data.get('ai_depth', 5),
                        'timestamp': timestamp,
                        'current_player': "Rouge" if current_player == ROUGE else "Jaune",
                        'mode_name': {0: "IA vs IA", 1: "Joueur vs IA", 2: "Joueur vs Joueur"}.get(mode, "Inconnu"),
                        'winner': game_data.get('winner'),
                        'game_over': game_data.get('game_over', False),
                        'move_count': len(game_data.get('move_history', []))
                    })
                except Exception as e:
                    print(f"Erreur lecture {filename}: {e}")
                    continue

        # Trier par date decroissante
        games_list.sort(key=lambda x: x['timestamp'], reverse=True)
        return render_template('saved_games.html', games=games_list)

    except Exception as e:
        flash(f"Erreur: {str(e)}", "error")
        traceback.print_exc()
        return render_template('saved_games.html', games=[])


@app.route('/delete_game/<game_id>', methods=['DELETE'])
def delete_game(game_id):
    """Supprime une partie sauvegardée localement"""
    try:
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
        filepath = os.path.join(save_dir, f"{game_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"status": "success", "message": f"Partie {game_id} supprimée"})
        return jsonify({"status": "error", "message": f"Partie {game_id} non trouvée"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erreur: {str(e)}"}), 500


@app.route('/reset')
def reset():
    """Réinitialise la session"""
    session.clear()
    return redirect(url_for('index'))


@app.route('/start_game_minimax')
def start_game_minimax():
    """Page de sélection de la profondeur pour le mode Joueur vs IA Minimax"""
    return render_template('game_player_vs_minimax_ia.html',
                           BOARD_ROWS=BOARD_ROWS,
                           BOARD_COLS=BOARD_COLS,
                           show_depth_selection=True)


@app.route('/start_game_with_depth', methods=['POST'])
def start_game_with_depth():
    """Démarre une nouvelle partie avec une profondeur spécifique pour l'IA Minimax"""
    try:
        depth = int(request.form.get('depth', 3))
        if depth < 1 or depth > 7:
            return jsonify({'error': 'Profondeur invalide (doit être entre 1 et 7)'}), 400

        session.clear()

        game_state = {
            'board': create_board(),
            'current_player': ROUGE,
            'mode': 1,
            'ai_type': 'minimax',
            'ai_depth': depth,
            'move_history': [],
            'game_over': False,
            'winner': None,
            'last_move': None,
            'winning_cells': [],
            'game_id': str(uuid.uuid4())
        }

        weights = load_learning_weights()
        try:
            scores = calculate_minimax_scores(game_state['board'], ROUGE, depth, weights)
            game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
        except Exception as e:
            print(f"Erreur lors du calcul initial des scores Minimax: {e}")
            game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state

        return jsonify({'success': True, 'redirect': url_for('game_player_vs_minimax_ia')})

    except Exception as e:
        print(f"Erreur dans start_game_with_depth: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Erreur: {str(e)}'}), 500


@app.route('/start_game/<int:mode>')
def start_game(mode):
    """Démarre une nouvelle partie"""
    session.clear()

    ai_type = request.args.get('ai_type', 'random')

    game_state = {
        'board': create_board(),
        'current_player': ROUGE,
        'mode': mode,
        'move_history': [],
        'game_over': False,
        'winner': None,
        'last_move': None,
        'winning_cells': [],
        'game_id': str(uuid.uuid4())
    }

    if mode == 0:
        game_state['ai_type'] = 'random'
        game_state['ai_depth'] = 5
    elif mode == 1:
        game_state['ai_type'] = ai_type
        game_state['ai_depth'] = int(request.args.get('depth', 5))

        if ai_type == 'minimax':
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(game_state['board'], ROUGE, game_state['ai_depth'], weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception as e:
                print(f"Erreur lors du calcul initial des scores Minimax: {e}")
                game_state['minimax_scores'] = [0] * BOARD_COLS
    elif mode == 2:
        game_state['ai_type'] = None

    session['game_state'] = game_state

    if mode == 0:
        return redirect(url_for('game_ia_vs_ia'))
    elif mode == 1:
        if ai_type == 'minimax':
            return redirect(url_for('game_player_vs_minimax_ia'))
        else:
            return redirect(url_for('game_player_vs_random_ia'))
    elif mode == 2:
        return redirect(url_for('game_player_vs_player'))
    else:
        return redirect(url_for('index'))


@app.route('/import_choose_next', methods=['GET', 'POST'])
def import_choose_next():
    """Apres un import, choisir qui joue le prochain coup"""
    if 'imported_game' not in session:
        flash('Aucune partie importee', 'error')
        return redirect(url_for('import_game'))

    if request.method == 'POST':
        try:
            game = session['imported_game']
            next_player = int(request.form.get('next_player', ROUGE))

            # Appliquer le choix du joueur courant
            game['current_player'] = next_player
            game = validate_and_fix_game_state(game)
            session['game_state'] = game

            mode = game['mode']
            ai_type = game.get('ai_type')

            # Calculer scores Minimax si besoin
            if mode == 1 and ai_type == 'minimax':
                weights = load_learning_weights()
                try:
                    scores = calculate_minimax_scores(game['board'], ROUGE, game['ai_depth'], weights)
                    session['game_state']['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
                except Exception as e:
                    session['game_state']['minimax_scores'] = [0] * BOARD_COLS

            # Si c est le tour de l IA, la faire jouer
            if mode == 1 and next_player == JAUNE:
                if ai_type == 'minimax':
                    play_ai_minimax_move(session['game_state'])
                else:
                    play_ai_random_move(session['game_state'])

            flash(f"Partie importee avec succes !", "success")
            session.pop('imported_game', None)

            if mode == 0:
                return redirect(url_for('game_ia_vs_ia'))
            elif mode == 1:
                if ai_type == 'minimax':
                    return redirect(url_for('game_player_vs_minimax_ia'))
                else:
                    return redirect(url_for('game_player_vs_random_ia'))
            else:
                return redirect(url_for('game_player_vs_player'))

        except Exception as e:
            flash(f'Erreur: {str(e)}', 'error')
            traceback.print_exc()
            return redirect(url_for('import_game'))

    game = session['imported_game']
    return render_template('import_choose_next.html',
                           game=game,
                           board=game['board'],
                           move_count=len(game['move_history']),
                           ROUGE=ROUGE,
                           JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS,
                           BOARD_COLS=BOARD_COLS)


@app.route('/game_imported')
def game_imported():
    """Page de jeu speciale pour les parties importees — choix joueur/IA a chaque coup"""
    if 'game_state' not in session or not session['game_state'].get('is_imported'):
        return redirect(url_for('import_game'))
    game_state = session['game_state']
    game_state = validate_and_fix_game_state(game_state)
    session['game_state'] = game_state
    return render_template('game_imported.html',
                           game_state=game_state,
                           ROUGE=ROUGE, JAUNE=JAUNE,
                           BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/play_imported', methods=['POST'])
def play_imported():
    """Gere un coup dans le mode importe — joueur ou IA selon le choix"""
    if 'game_state' not in session:
        return jsonify({'error': 'Aucune partie en cours'}), 400

    try:
        game_state = session['game_state']
        board = game_state['board']
        who_plays = request.form.get('who_plays', 'player')  # 'player' ou 'ai'
        column = int(request.form.get('column', -1))

        if game_state['game_over']:
            return jsonify({'error': 'La partie est deja terminee'}), 400

        current_player = game_state['current_player']

        if who_plays == 'ai':
            # L IA joue avec la nouvelle IA performante
            depth = game_state.get('ai_depth', load_learning_weights().get('depth', 5))
            ai = AIPlayer(ai_type='minimax', depth=depth)

            # Priorites : gagner > bloquer > double menace > minimax
            col = ai._win_col(board, current_player)
            if col is None:
                opponent = ROUGE if current_player == JAUNE else JAUNE
                col = ai._win_col(board, opponent)
            if col is None:
                # Double menace
                best_double = None
                best_wins = 0
                for c in range(BOARD_COLS):
                    if is_valid_move(board, c):
                        r = get_next_open_row(board, c)
                        if r is not None:
                            board[r][c] = current_player
                            wins = ai._count_threats(board, current_player)
                            board[r][c] = EMPTY
                            if wins >= 2 and wins > best_wins:
                                best_wins = wins
                                best_double = c
                if best_double is not None:
                    col = best_double
            if col is None:
                col, _, _ = ai.choose_move(board, current_player)
            if col is None:
                valid = [c for c in range(BOARD_COLS) if is_valid_move(board, c)]
                col = random.choice(valid) if valid else None
            if col is None:
                return jsonify({'error': 'Aucun coup valide'}), 400
            row = get_next_open_row(board, col)
        else:
            # Le joueur joue
            if column == -1 or not is_valid_move(board, column):
                return jsonify({'error': 'Colonne invalide'}), 400
            col = column
            row = get_next_open_row(board, col)

        if row is None or not drop_piece(board, row, col, current_player):
            return jsonify({'error': 'Impossible de placer le jeton'}), 400

        is_win, winning_cells = check_win(board, row, col, current_player)
        game_over = is_win or is_board_full(board)

        game_state['last_move'] = [row, col]
        game_state['winning_cells'] = winning_cells
        game_state['move_history'].append([row, col, current_player])
        game_state['game_over'] = game_over

        if game_over:
            game_state['winner'] = current_player if is_win else 0
            game_state['current_player'] = None
            save_finished_game_to_db(game_state)
        else:
            # Alterner le joueur courant
            game_state['current_player'] = JAUNE if current_player == ROUGE else ROUGE

        # Recalculer scores minimax
        if not game_over:
            weights = load_learning_weights()
            try:
                scores_list = calculate_minimax_scores(board, game_state['current_player'], 5, weights)
                game_state['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores_list]
            except Exception:
                game_state['minimax_scores'] = [0] * BOARD_COLS

        session['game_state'] = game_state

        return jsonify({
            'success': True,
            'board': board,
            'current_player': game_state['current_player'],
            'last_move': [row, col],
            'game_over': game_over,
            'winner': current_player if is_win else (0 if game_over else None),
            'winning_cells': [[r, c] for r, c in winning_cells] if is_win else [],
            'move_history': game_state['move_history'],
            'played_col': col,
            'played_row': row,
            'played_by': who_plays,
            'minimax_scores': game_state.get('minimax_scores', [])
        })

    except Exception as e:
        print(f"Erreur dans play_imported: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/choose_mode')
def choose_mode():
    """Page pour choisir le mode de jeu"""
    return render_template('choose_mode.html', BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


@app.route('/import_game', methods=['GET', 'POST'])
def import_game():
    """Importe une partie depuis un fichier ou une sequence"""
    if request.method == 'POST':
        try:
            file_content = None

            if 'game_file' in request.files and request.files['game_file'].filename != '':
                file = request.files['game_file']
                if file and file.filename.endswith('.txt'):
                    file_content = file.read().decode('utf-8')
            elif 'game_sequence' in request.form and request.form['game_sequence'].strip():
                file_content = request.form['game_sequence']

            if not file_content:
                flash("Aucun fichier ou séquence fourni", "error")
                return redirect(url_for('import_game'))

            # On importe toujours en mode neutre (mode 2)
            # Le choix joueur/IA se fait coup par coup dans game_imported
            game_state, error = process_import_file(file_content, mode=2)

            if error:
                flash(f"Erreur: {error}", "error")
                return redirect(url_for('import_game'))

            if not game_state:
                flash("Impossible de traiter le fichier", "error")
                return redirect(url_for('import_game'))

            game_id = str(uuid.uuid4())

            session['game_state'] = {
                'board': game_state['board'],
                'current_player': game_state['current_player'],
                'mode': 1,
                'ai_type': 'minimax',
                'ai_depth': load_learning_weights().get('depth', 5),
                'move_history': game_state['move_history'],
                'game_over': game_state['game_over'],
                'winner': game_state['winner'],
                'last_move': game_state['move_history'][-1] if game_state['move_history'] else None,
                'winning_cells': game_state['winning_cells'],
                'game_id': game_id,
                'is_imported': True
            }

            session['game_state'] = validate_and_fix_game_state(session['game_state'])

            if game_state['game_over']:
                save_finished_game_to_db(session['game_state'])
                flash(f"Partie importee (terminee) — ID: {game_id}", "success")
                return redirect(url_for('game_imported'))

            # Calculer scores minimax pour affichage
            depth = session['game_state']['ai_depth']
            weights = load_learning_weights()
            try:
                scores = calculate_minimax_scores(session['game_state']['board'], ROUGE, depth, weights)
                session['game_state']['minimax_scores'] = [round(s, 1) if s != -float('inf') else -1000000 for s in scores]
            except Exception:
                session['game_state']['minimax_scores'] = [0] * BOARD_COLS

            flash(f"Partie importee avec succes (ID: {game_id})", "success")
            return redirect(url_for('game_imported'))

        except Exception as e:
            flash(f"Erreur: {str(e)}", "error")
            traceback.print_exc()
            return redirect(url_for('import_game'))

    return render_template('import_game.html', BOARD_ROWS=BOARD_ROWS, BOARD_COLS=BOARD_COLS)


# ====================== POINT D'ENTRÉE ======================
if __name__ == '__main__':
    for folder in ['saves', 'uploads', 'temp']:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
        os.makedirs(path, exist_ok=True)
        print(f"✅ Dossier {folder} créé: {path}")

    if not os.path.exists(LEARNING_WEIGHTS_FILE):
        default_weights = {
            'center_weight': 6.0,
            'three_in_row_weight': 100.0,
            'two_in_row_weight': 10.0,
            'opponent_three_weight': -200.0,
            'depth': 5,
            'learning_rate': 0.1,
            'exploration_rate': 0.1
        }
        save_learning_weights(default_weights)
        print("✅ Poids d'apprentissage initialisés")

    try:
        if not db_manager.test_connection():
            print("❌ Impossible de se connecter à la base de données!")
        else:
            print("✅ Connexion à la base de données établie")
    except Exception as e:
        print(f"❌ Erreur de connexion à la base de données: {e}")

    print("🚀 Démarrage du serveur...")
    print("🔗 Accédez à l'application sur http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)

# © Kassou Youssef
