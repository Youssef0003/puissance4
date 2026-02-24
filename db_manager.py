import psycopg2
import hashlib
import sys
import traceback
from datetime import datetime

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
                    game_id INTEGER REFERENCES games(game_id),
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
            return True
        except Exception as e:
            print(f"Erreur lors de l'initialisation de la base de données: {e}", file=sys.stderr)
            traceback.print_exc()
            self.connection.rollback()
            return False

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
            result = self.execute_query(query, params, fetch=True)
            game_id = result[0][0]

            for move_order, (row, col, player) in enumerate(history, start=1):
                query = """
                INSERT INTO moves (game_id, row, col, player, move_order)
                VALUES (%s, %s, %s, %s, %s);
                """
                params = (game_id, row, col - 1, player, move_order)
                self.execute_query(query, params)

            return game_id
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du résultat: {e}", file=sys.stderr)
            traceback.print_exc()
            return None

    def are_sequences_symmetric(self, seq1, seq2):
        """Vérifie si deux séquences de coups sont symétriques."""
        if len(seq1) != len(seq2):
            return False

        for i in range(len(seq1)):
            if seq1[i] != (self.COLS + 1 - seq2[i]):
                return False
        return True

    def check_if_exists(self, moves):
        """Vérifie si une partie ou sa symétrie existe déjà dans la base de données."""
        try:
            move_sequence = ",".join(str(move) for move in moves)
            move_sequence_hash = hashlib.sha256(move_sequence.encode()).hexdigest()

            # Vérifier si la séquence de coups existe déjà
            query = """
            SELECT game_id FROM games
            WHERE move_sequence_hash = %s;
            """
            params = (move_sequence_hash,)
            result = self.execute_query(query, params, fetch=True)

            if result:
                return result[0][0]

            # Vérifier si la symétrie de la séquence de coups existe déjà
            symmetric_moves = [self.COLS + 1 - move for move in moves]
            symmetric_move_sequence = ",".join(str(move) for move in symmetric_moves)
            symmetric_move_sequence_hash = hashlib.sha256(symmetric_move_sequence.encode()).hexdigest()

            query = """
            SELECT game_id FROM games
            WHERE move_sequence_hash = %s;
            """
            params = (symmetric_move_sequence_hash,)
            result = self.execute_query(query, params, fetch=True)

            if result:
                return result[0][0]

            return None
        except Exception as e:
            print(f"Erreur lors de la vérification de l'existence de la partie: {e}", file=sys.stderr)
            traceback.print_exc()
            return None
