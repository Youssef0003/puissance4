import psycopg2
import hashlib
import sys
import traceback
from datetime import datetime

# Constantes pour les joueurs
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
        self.connection = None
        self.COLS = 9  # Nombre de colonnes par défaut pour Puissance 4

    def connect(self):
        """Établit une connexion à la base de données PostgreSQL."""
        try:
            self.connection = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )
            print("Connexion à la base de données réussie.")
            return True
        except Exception as e:
            print(f"Erreur lors de la connexion à la base de données: {e}", file=sys.stderr)
            traceback.print_exc()
            return False

    def close(self):
        """Ferme la connexion à la base de données."""
        if self.connection:
            self.connection.close()
            self.connection = None
            print("Connexion à la base de données fermée.")

    def execute_query(self, query, params=None, fetch=False):
        """Exécute une requête SQL."""
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            if fetch:
                result = cursor.fetchall()
            else:
                result = None
            self.connection.commit()
            cursor.close()
            return result
        except Exception as e:
            print(f"Erreur lors de l'exécution de la requête: {e}", file=sys.stderr)
            print(f"Requête: {query}", file=sys.stderr)
            print(f"Paramètres: {params}", file=sys.stderr)
            traceback.print_exc()
            self.connection.rollback()
            return None

    def initialize_database(self):
        """Initialise les tables de la base de données."""
        try:
            cursor = self.connection.cursor()

            # Table games
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id SERIAL PRIMARY KEY,
                    winner VARCHAR(20),
                    mode INTEGER,
                    status VARCHAR(20),
                    timestamp_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    timestamp_end TIMESTAMP,
                    num_columns INTEGER,
                    move_sequence_hash VARCHAR(255),
                    is_mutualized BOOLEAN DEFAULT FALSE,
                    confiance FLOAT DEFAULT 0.5
                )
            """)

            # Table moves
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS moves (
                    move_id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(game_id) ON DELETE CASCADE,
                    row INTEGER,
                    col INTEGER,
                    player INTEGER,
                    move_order INTEGER,
                    UNIQUE(game_id, move_order)
                )
            """)

            # Table mutualizations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mutualizations (
                    mutualization_id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(game_id),
                    mutualized_game_id INTEGER REFERENCES games(game_id),
                    UNIQUE(game_id, mutualized_game_id)
                )
            """)

            self.connection.commit()
            cursor.close()
            print("Tables créées avec succès.")
            return True
        except Exception as e:
            print(f"Erreur lors de l'initialisation de la base de données: {e}", file=sys.stderr)
            traceback.print_exc()
            self.connection.rollback()
            return False

    def set_permissions(self):
        """Accorde les permissions nécessaires à l'utilisateur."""
        try:
            cursor = self.connection.cursor()

            # Accorder les permissions sur les tables
            cursor.execute(f"GRANT ALL PRIVILEGES ON TABLE games TO {self.user};")
            cursor.execute(f"GRANT ALL PRIVILEGES ON TABLE moves TO {self.user};")
            cursor.execute(f"GRANT ALL PRIVILEGES ON TABLE mutualizations TO {self.user};")

            # Accorder les permissions sur les séquences
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE games_game_id_seq TO {self.user};")
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE moves_move_id_seq TO {self.user};")
            cursor.execute(f"GRANT USAGE, SELECT ON SEQUENCE mutualizations_mutualization_id_seq TO {self.user};")

            self.connection.commit()
            cursor.close()
            print("Permissions accordées avec succès.")
            return True
        except Exception as e:
            print(f"Erreur lors de l'attribution des permissions: {e}", file=sys.stderr)
            traceback.print_exc()
            self.connection.rollback()
            return False

    def save_game(self, game_state):
        """Sauvegarde une partie en cours dans la base de données."""
        try:
            print("Début de la sauvegarde de la partie.")
            moves = [move[1] for move in game_state['move_history']]
            print(f"Mouvements: {moves}")
            move_sequence = ",".join(str(move) for move in moves)
            print(f"Séquence de mouvements: {move_sequence}")
            move_sequence_hash = hashlib.sha256(move_sequence.encode()).hexdigest()
            print(f"Hash de la séquence: {move_sequence_hash}")

            # Sauvegarde dans la table games
            query = """
            INSERT INTO games (winner, mode, status, num_columns, move_sequence_hash, confiance)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING game_id;
            """
            params = (None, game_state['mode'], "in_progress", self.COLS, move_sequence_hash, game_state.get('last_confiance', 0.5))
            print(f"Exécution de la requête: {query} avec les paramètres: {params}")

            result = self.execute_query(query, params, fetch=True)
            if not result:
                print("Erreur lors de l'insertion dans la table games.")
                return None

            game_id = result[0][0]
            print(f"ID de la partie sauvegardée: {game_id}")

            # Supprimer les mouvements existants pour ce game_id
            delete_query = "DELETE FROM moves WHERE game_id = %s;"
            self.execute_query(delete_query, (game_id,))

            # Sauvegarde dans la table moves
            for move_order, (row, col, player) in enumerate(game_state['move_history'], start=1):
                query = """
                INSERT INTO moves (game_id, row, col, player, move_order)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (game_id, move_order)
                DO UPDATE SET row = EXCLUDED.row, col = EXCLUDED.col, player = EXCLUDED.player;
                """
                params = (game_id, row, col, player, move_order)
                print(f"Exécution de la requête: {query} avec les paramètres: {params}")
                if not self.execute_query(query, params):
                    print(f"Erreur lors de l'insertion du mouvement {move_order}.")
                    return None

            print("Partie sauvegardée avec succès.")
            return game_id
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de la partie: {e}", file=sys.stderr)
            traceback.print_exc()
            return None

    def save_result(self, winner, mode, history, filename=None, confiance=0.5):
        """Sauvegarde le résultat d'une partie dans la base de données."""
        try:
            moves = [move[1] for move in history]
            move_sequence = ",".join(str(move) for move in moves)
            move_sequence_hash = hashlib.sha256(move_sequence.encode()).hexdigest()

            query = """
            INSERT INTO games (winner, mode, status, timestamp_end, num_columns, move_sequence_hash, confiance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING game_id;
            """
            params = (winner, mode, "completed", datetime.now(), self.COLS, move_sequence_hash, confiance)
            print(f"Exécution de la requête: {query} avec les paramètres: {params}")

            result = self.execute_query(query, params, fetch=True)
            if not result:
                print("Erreur lors de l'insertion dans la table games.")
                return None

            game_id = result[0][0]
            print(f"ID de la partie sauvegardée: {game_id}")

            for move_order, (row, col, player) in enumerate(history, start=1):
                query = """
                INSERT INTO moves (game_id, row, col, player, move_order)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (game_id, move_order)
                DO UPDATE SET row = EXCLUDED.row, col = EXCLUDED.col, player = EXCLUDED.player;
                """
                params = (game_id, row, col, player, move_order)
                print(f"Exécution de la requête: {query} avec les paramètres: {params}")
                if not self.execute_query(query, params):
                    print(f"Erreur lors de l'insertion du mouvement {move_order}.")
                    return None

            return game_id
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du résultat: {e}", file=sys.stderr)
            traceback.print_exc()
            return None

    def load_games(self):
        """Charge toutes les parties sauvegardées depuis la base de données."""
        try:
            query = """
            SELECT game_id, winner, mode, status, timestamp_start, confiance
            FROM games
            ORDER BY timestamp_start DESC;
            """
            result = self.execute_query(query, fetch=True)
            if result:
                games = []
                for row in result:
                    game_id, winner, mode, status, timestamp_start, confiance = row
                    games.append({
                        'id': game_id,
                        'winner': winner,
                        'mode': mode,
                        'status': status,
                        'timestamp': timestamp_start,
                        'confiance': confiance
                    })
                return games
            return []
        except Exception as e:
            print(f"Erreur lors du chargement des parties: {e}", file=sys.stderr)
            traceback.print_exc()
            return []

    def load_game(self, game_id):
        """Charge une partie spécifique depuis la base de données."""
        try:
            # Charger les informations de la partie
            query = """
            SELECT winner, mode, num_columns, confiance
            FROM games
            WHERE game_id = %s;
            """
            game_info = self.execute_query(query, (game_id,), fetch=True)
            if not game_info:
                print(f"Aucune partie trouvée avec l'ID {game_id}.")
                return None

            # Charger les coups de la partie
            query = """
            SELECT row, col, player, move_order
            FROM moves
            WHERE game_id = %s
            ORDER BY move_order;
            """
            moves = self.execute_query(query, (game_id,), fetch=True)
            if not moves:
                print(f"Aucun mouvement trouvé pour la partie avec l'ID {game_id}.")
                return None

            # Construire l'état de la partie
            board = [[EMPTY for _ in range(self.COLS)] for _ in range(9)]
            move_history = []
            current_player = JAUNE  # Par défaut, commence avec le joueur jaune

            for row, col, player, move_order in moves:
                board[row][col] = player
                move_history.append((row, col, player))
                current_player = player

            game_state = {
                'board': board,
                'current_player': current_player,
                'mode': game_info[0][1],
                'ai_type': 'minimax',  # Par défaut
                'ai_depth': 3,  # Par défaut
                'move_history': move_history,
                'last_confiance': game_info[0][3]
            }

            return game_state
        except Exception as e:
            print(f"Erreur lors du chargement de la partie: {e}", file=sys.stderr)
            traceback.print_exc()
            return None
