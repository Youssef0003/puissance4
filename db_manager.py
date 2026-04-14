import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json
import traceback
import numpy as np
import hashlib

# Constantes du jeu
EMPTY = 0
ROUGE = 1
JAUNE = 2

class DBManager:
    def __init__(self, db_name, user, password, host, port):
        self.db_name = db_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None
        self.connect()

    def connect(self):
        """Établit une connexion à la base de données"""
        try:
            self.conn = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            print("✅ Connexion à la base de données établie avec succès")
            return True
        except Exception as e:
            print(f"❌ Erreur de connexion à la base de données: {e}")
            traceback.print_exc()
            return False

    def test_connection(self):
        """Teste la connexion à la base de données"""
        try:
            if self.conn is None or self.conn.closed:
                self.connect()
            return self.conn is not None and not self.conn.closed
        except Exception as e:
            print(f"❌ Erreur lors du test de connexion: {e}")
            return False

    def _ensure_connection(self):
        """S'assure que la connexion est active"""
        if not self.test_connection():
            self.connect()
        return self.test_connection()

    def _board_to_hash(self, board):
        """Convertit un plateau en hash"""
        try:
            board_str = json.dumps(board)
            return hashlib.sha256(board_str.encode()).hexdigest()
        except Exception as e:
            print(f"❌ Erreur lors de la conversion du plateau en hash: {e}")
            return None

    def _is_symmetrical(self, board, existing_hashes):
        """Vérifie si le plateau est une symétrie d'un plateau existant"""
        try:
            board_array = np.array(board)

            symmetries = [
                ("horizontal", np.fliplr(board_array)),
                ("vertical", np.flipud(board_array)),
                ("rotation90", np.rot90(board_array)),
                ("rotation180", np.rot90(board_array, 2)),
                ("rotation270", np.rot90(board_array, 3)),
                ("diagonal1", np.transpose(board_array)),
                ("diagonal2", np.fliplr(np.transpose(board_array)))
            ]

            for sym_type, sym_board in symmetries:
                sym_hash = self._board_to_hash(sym_board.tolist())
                if sym_hash in existing_hashes:
                    return True, sym_type
            return False, None
        except Exception as e:
            print(f"❌ Erreur avec numpy: {e}")
            return False, None

    def _get_existing_board_hashes(self):
        """Récupère tous les hashs de plateaux existants"""
        if not self._ensure_connection():
            return set()

        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT board_hash FROM games WHERE board_hash IS NOT NULL")
                hashes = [row[0] for row in cur.fetchall()]
                return set(hashes)
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des hashs: {e}")
            traceback.print_exc()
            return set()

    def save_result(self, winner, mode, history, confidence, ai_type, winning_cells, board):
        """
        Sauvegarde le résultat d'une partie dans la base de données
        avec vérification des doublons et symétries
        """
        if not self._ensure_connection():
            return None

        try:
            # Calculer le hash du plateau pour référence future
            board_hash = self._board_to_hash(board)

            # Vérifier les doublons
            existing_hashes = self._get_existing_board_hashes()

            # Vérifier si le plateau existe déjà
            if board_hash in existing_hashes:
                print(f"⚠️ Plateau déjà existant (hash: {board_hash}), pas d'insertion.")
                return None

            # Vérifier les symétries
            is_symmetry, sym_type = self._is_symmetrical(board, existing_hashes)
            if is_symmetry:
                print(f"⚠️ Plateau symétrique détecté ({sym_type}), pas d'insertion.")
                return None

            # Déterminer les dimensions du plateau
            num_rows = len(board)
            num_columns = len(board[0]) if num_rows > 0 else 0

            with self.conn.cursor() as cur:
                # Insérer dans la table games
                cur.execute("""
                    INSERT INTO games (
                        winner, mode, status, confidence, ai_type, winning_cells,
                        board_hash, timestamp_end, num_rows, num_columns
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s)
                    RETURNING game_id
                """, (
                    winner,
                    mode,
                    "completed",
                    confidence,
                    ai_type,
                    json.dumps(winning_cells) if winning_cells else None,
                    board_hash,
                    num_rows,
                    num_columns
                ))

                game_id = cur.fetchone()[0]

                # Insérer les mouvements dans la table moves
                for move_order, (row, col, player) in enumerate(history):
                    cur.execute("""
                        INSERT INTO moves (
                            game_id, row, col, player, move_order
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (game_id, row, col, player, move_order))

                self.conn.commit()
                print(f"✅ Partie sauvegardée avec succès (ID: {game_id})")
                return game_id
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde du résultat: {e}")
            traceback.print_exc()
            self.conn.rollback()
            return None

    def get_all_games_paginated(self, page=1, per_page=20, sort_by='timestamp_end', sort_order='desc',
                               mode_filter=None, winner_filter=None):
        """Récupère les parties avec pagination et filtres"""
        if not self._ensure_connection():
            return [], 0

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Compter le nombre total de parties (avec filtres)
                count_query = "SELECT COUNT(DISTINCT g.game_id) FROM games g"
                count_params = []

                where_clauses = []
                if mode_filter is not None:
                    where_clauses.append("g.mode = %s")
                    count_params.append(mode_filter)
                if winner_filter is not None:
                    where_clauses.append("g.winner = %s")
                    count_params.append(winner_filter)

                if where_clauses:
                    count_query += " WHERE " + " AND ".join(where_clauses)

                cur.execute(count_query, count_params)
                total_games = cur.fetchone()['count']

                if total_games == 0:
                    return [], 0

                # Déterminer l'offset
                offset = (page - 1) * per_page

                # Construire la requête principale avec filtres
                query = """
                    SELECT
                        g.game_id,
                        g.winner,
                        g.mode,
                        g.confidence,
                        g.ai_type,
                        g.winning_cells,
                        g.board_hash,
                        g.timestamp_end,
                        COUNT(m.move_id) as move_count,
                        g.num_rows,
                        g.num_columns
                    FROM games g
                    LEFT JOIN moves m ON g.game_id = m.game_id
                """

                params = []
                where_clauses = []

                if mode_filter is not None:
                    where_clauses.append("g.mode = %s")
                    params.append(mode_filter)
                if winner_filter is not None:
                    where_clauses.append("g.winner = %s")
                    params.append(winner_filter)

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                query += " GROUP BY g.game_id"

                # Ajouter le tri
                valid_sort_columns = ['game_id', 'timestamp_end', 'move_count']
                if sort_by not in valid_sort_columns:
                    sort_by = 'timestamp_end'

                if sort_by == 'move_count':
                    query += f" ORDER BY COUNT(m.move_id) {'DESC' if sort_order == 'desc' else 'ASC'}"
                else:
                    query += f" ORDER BY g.{sort_by} {'DESC' if sort_order == 'desc' else 'ASC'}"

                # Ajouter la pagination
                query += " LIMIT %s OFFSET %s"
                params.extend([per_page, offset])

                cur.execute(query, params)
                games = cur.fetchall()

                # Pour chaque partie, récupérer l'historique complet
                for game in games:
                    cur.execute("""
                        SELECT row, col, player, move_order
                        FROM moves
                        WHERE game_id = %s
                        ORDER BY move_order
                    """, (game['game_id'],))

                    game['history'] = cur.fetchall()
                    game['move_count'] = len(game['history'])

                    # Convertir winning_cells de JSON à liste Python
                    if game['winning_cells']:
                        try:
                            game['winning_cells'] = json.loads(game['winning_cells'])
                        except:
                            game['winning_cells'] = []

                return games, total_games
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des parties: {e}")
            traceback.print_exc()
            return [], 0

    def get_all_games_no_limit(self, sort_by='timestamp_end', sort_order='desc',
                             mode_filter=None, winner_filter=None):
        """Récupère TOUTES les parties sans limite de pagination"""
        if not self._ensure_connection():
            return []

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Construire la requête avec filtres
                query = """
                    SELECT
                        g.game_id,
                        g.winner,
                        g.mode,
                        g.confidence,
                        g.ai_type,
                        g.winning_cells,
                        g.board_hash,
                        g.timestamp_end,
                        COUNT(m.move_id) as move_count,
                        g.num_rows,
                        g.num_columns
                    FROM games g
                    LEFT JOIN moves m ON g.game_id = m.game_id
                """

                params = []
                where_clauses = []

                if mode_filter is not None:
                    where_clauses.append("g.mode = %s")
                    params.append(mode_filter)
                if winner_filter is not None:
                    where_clauses.append("g.winner = %s")
                    params.append(winner_filter)

                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                query += " GROUP BY g.game_id"

                # Ajouter le tri
                valid_sort_columns = ['game_id', 'timestamp_end', 'move_count']
                if sort_by not in valid_sort_columns:
                    sort_by = 'timestamp_end'

                if sort_by == 'move_count':
                    query += f" ORDER BY COUNT(m.move_id) {'DESC' if sort_order == 'desc' else 'ASC'}"
                else:
                    query += f" ORDER BY g.{sort_by} {'DESC' if sort_order == 'desc' else 'ASC'}"

                cur.execute(query, params)
                games = cur.fetchall()

                # Pour chaque partie, récupérer l'historique complet
                for game in games:
                    cur.execute("""
                        SELECT row, col, player, move_order
                        FROM moves
                        WHERE game_id = %s
                        ORDER BY move_order
                    """, (game['game_id'],))

                    game['history'] = cur.fetchall()
                    game['move_count'] = len(game['history'])

                    # Convertir winning_cells de JSON à liste Python
                    if game['winning_cells']:
                        try:
                            game['winning_cells'] = json.loads(game['winning_cells'])
                        except:
                            game['winning_cells'] = []

                return games
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de toutes les parties: {e}")
            traceback.print_exc()
            return []

    def get_game_details(self, game_id):
        """Récupère les détails d'une partie spécifique"""
        if not self._ensure_connection():
            return None

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Récupérer les informations de base
                cur.execute("""
                    SELECT
                        game_id,
                        winner,
                        mode,
                        confidence,
                        ai_type,
                        winning_cells,
                        board_hash,
                        timestamp_end,
                        num_rows,
                        num_columns
                    FROM games
                    WHERE game_id = %s
                """, (game_id,))

                game = cur.fetchone()

                if not game:
                    return None

                # Récupérer l'historique des mouvements
                cur.execute("""
                    SELECT row, col, player, move_order
                    FROM moves
                    WHERE game_id = %s
                    ORDER BY move_order
                """, (game_id,))

                game['history'] = cur.fetchall()
                game['move_count'] = len(game['history'])

                # Reconstruire le plateau final
                board = [[EMPTY for _ in range(game['num_columns'])] for _ in range(game['num_rows'])]
                for move in game['history']:
                    row, col, player = move['row'], move['col'], move['player']
                    board[row][col] = player
                game['board'] = board

                # Convertir winning_cells de JSON à liste Python
                if game['winning_cells']:
                    try:
                        game['winning_cells'] = json.loads(game['winning_cells'])
                    except:
                        game['winning_cells'] = []

                return game
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des détails de la partie: {e}")
            traceback.print_exc()
            return None

    def get_statistics(self):
        """Récupère des statistiques sur les parties"""
        if not self._ensure_connection():
            return {}

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                stats = {}

                # Nombre total de parties
                cur.execute("SELECT COUNT(*) as total FROM games")
                total = cur.fetchone()['total']
                stats['total_games'] = total

                if total == 0:
                    return stats

                # Statistiques par mode
                cur.execute("""
                    SELECT
                        mode,
                        COUNT(*) as count,
                        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM games), 2) as percentage
                    FROM games
                    GROUP BY mode
                """)
                modes = cur.fetchall()
                stats['by_mode'] = {
                    mode['mode']: {
                        'count': mode['count'],
                        'percentage': mode['percentage']
                    }
                    for mode in modes
                }

                # Statistiques par vainqueur
                cur.execute("""
                    SELECT
                        winner,
                        COUNT(*) as count,
                        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM games), 2) as percentage
                    FROM games
                    GROUP BY winner
                """)
                winners = cur.fetchall()
                stats['by_winner'] = {
                    winner['winner']: {
                        'count': winner['count'],
                        'percentage': winner['percentage']
                    }
                    for winner in winners
                }

                # Statistiques par type d'IA
                cur.execute("""
                    SELECT
                        ai_type,
                        COUNT(*) as count,
                        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM games WHERE ai_type IS NOT NULL), 2) as percentage
                    FROM games
                    WHERE ai_type IS NOT NULL
                    GROUP BY ai_type
                """)
                ai_types = cur.fetchall()
                stats['by_ai_type'] = {
                    ai['ai_type']: {
                        'count': ai['count'],
                        'percentage': ai['percentage']
                    }
                    for ai in ai_types
                }

                # Nombre moyen de coups
                cur.execute("""
                    SELECT AVG(move_count) as avg_moves
                    FROM (
                        SELECT COUNT(*) as move_count
                        FROM moves
                        GROUP BY game_id
                    ) as move_counts
                """)
                avg_moves = cur.fetchone()['avg_moves']
                stats['avg_moves'] = round(avg_moves, 2) if avg_moves else 0

                return stats
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des statistiques: {e}")
            traceback.print_exc()
            return {}

    def clean_database(self):
        """Nettoie la base de données en supprimant les doublons et symétries"""
        if not self._ensure_connection():
            print("❌ Impossible de se connecter à la base de données")
            return False

        try:
            with self.conn.cursor() as cur:
                # Récupérer tous les jeux avec leur board_hash
                cur.execute("SELECT game_id, board_hash FROM games WHERE board_hash IS NOT NULL")
                games = cur.fetchall()

                # Créer un dictionnaire pour compter les occurrences de chaque hash
                hash_counts = {}
                for game_id, board_hash in games:
                    if board_hash not in hash_counts:
                        hash_counts[board_hash] = []
                    hash_counts[board_hash].append(game_id)

                # Identifier les doublons (hashs qui apparaissent plus d'une fois)
                duplicates = {h: ids for h, ids in hash_counts.items() if len(ids) > 1}

                # Pour chaque ensemble de doublons, garder le plus ancien et supprimer les autres
                for board_hash, game_ids in duplicates.items():
                    # Trouver le game_id le plus ancien (le plus petit)
                    game_ids.sort()
                    oldest_id = game_ids[0]

                    # Supprimer tous les autres
                    for game_id in game_ids[1:]:
                        # Supprimer d'abord les moves
                        cur.execute("DELETE FROM moves WHERE game_id = %s", (game_id,))
                        # Puis le game
                        cur.execute("DELETE FROM games WHERE game_id = %s", (game_id,))
                        print(f"✅ Suppression du doublon (ID: {game_id})")

                # Vérifier les symétries
                cur.execute("SELECT game_id, board_hash FROM games WHERE board_hash IS NOT NULL")
                games = cur.fetchall()

                # Pour chaque jeu, vérifier s'il a une symétrie déjà dans la base
                for i, (game_id, board_hash) in enumerate(games):
                    # Récupérer le plateau
                    cur.execute("""
                        SELECT row, col, player
                        FROM moves
                        WHERE game_id = %s
                        ORDER BY move_order
                    """, (game_id,))

                    moves = cur.fetchall()
                    board = [[EMPTY for _ in range(9)] for _ in range(9)]
                    for row, col, player in moves:
                        for r in range(8, -1, -1):
                            if board[r][col] == EMPTY:
                                board[r][col] = player
                                break

                    # Vérifier les symétries avec les autres plateaux
                    existing_hashes = self._get_existing_board_hashes()
                    existing_hashes.discard(board_hash)  # Exclure le plateau actuel

                    is_symmetry, sym_type = self._is_symmetrical(board, existing_hashes)
                    if is_symmetry:
                        # Supprimer ce jeu car c'est une symétrie
                        cur.execute("DELETE FROM moves WHERE game_id = %s", (game_id,))
                        cur.execute("DELETE FROM games WHERE game_id = %s", (game_id,))
                        print(f"✅ Suppression de la symétrie (ID: {game_id}, type: {sym_type})")

                self.conn.commit()
                print("✅ Nettoyage de la base de données terminé")
                return True
        except Exception as e:
            print(f"❌ Erreur lors du nettoyage: {e}")
            traceback.print_exc()
            self.conn.rollback()
            return False

    def close(self):
        """Ferme la connexion à la base de données"""
        if self.conn and not self.conn.closed:
            self.conn.close()
            print("Connexion à la base de données fermée")

    def __del__(self):
        """Destructeur pour fermer la connexion"""
        self.close()
