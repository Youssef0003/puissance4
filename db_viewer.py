import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import psycopg2
import sys
import traceback
from datetime import datetime

class DBViewer:
    def __init__(self, db_name="puissance4", user="youssef", password="Kassou00.", host="localhost", port="5432"):
        self.db_name = db_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port

        self.conn = None
        if not self.connect_to_db():
            return

        self.root = tk.Tk()
        self.root.title("Visualisateur de Base de Données - Puissance 4 (PostgreSQL)")
        self.root.geometry("1200x800")

        self.CELL_SIZE = 40
        self.PADDING = 10
        self.COLOR_BG = "blue"
        self.COLOR_GRID = "white"
        self.COLOR_RED = "red"
        self.COLOR_YELLOW = "yellow"

        self.current_game_id = None

        self.notebook = None
        self.create_widgets()
        self.root.mainloop()

    def connect_to_db(self):
        try:
            self.conn = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port
            )

            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN ('games', 'moves');
            """)
            tables = [row[0] for row in cursor.fetchall()]
            if 'games' not in tables or 'moves' not in tables:
                messagebox.showerror("Erreur", "Les tables 'games' ou 'moves' n'existent pas dans la base de données.")
                return False

            print(f"Connecté à la base de données PostgreSQL: {self.db_name}")
            return True
        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Impossible de se connecter à la base de données PostgreSQL: {e}")
            return False

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.games_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.games_tab, text="Parties")
        self.create_games_tab()

        self.moves_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.moves_tab, text="Coups")
        self.create_moves_tab()

        self.stats_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_tab, text="Statistiques")
        self.create_stats_tab()

        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=5)

        ttk.Button(toolbar, text="Rafraîchir", command=self.refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Exporter CSV", command=self.export_to_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Rechercher", command=self.search_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Ajouter/Modifier Coups", command=self.edit_game_moves).pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar()
        self.status_var.set(f"Base de données: {self.db_name} - Connecté")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).pack(fill=tk.X)

    def create_games_tab(self):
        filter_frame = ttk.LabelFrame(self.games_tab, text="Filtres", padding=10)
        filter_frame.pack(fill=tk.X, pady=5)

        ttk.Label(filter_frame, text="Gagnant:").grid(row=0, column=0, padx=5)
        self.winner_filter = ttk.Combobox(filter_frame, values=["Tous", "Rouge", "Jaune", "Nul"])
        self.winner_filter.grid(row=0, column=1, padx=5)
        self.winner_filter.current(0)

        ttk.Label(filter_frame, text="Mode:").grid(row=0, column=2, padx=5)
        self.mode_filter = ttk.Combobox(filter_frame, values=["Tous", "0 (IA vs IA)", "1 (Joueur vs IA)", "2 (Joueur vs Joueur)"])
        self.mode_filter.grid(row=0, column=3, padx=5)
        self.mode_filter.current(0)

        ttk.Label(filter_frame, text="Statut:").grid(row=0, column=4, padx=5)
        self.status_filter = ttk.Combobox(filter_frame, values=["Tous", "completed", "in_progress", "mutualized"])
        self.status_filter.grid(row=0, column=5, padx=5)
        self.status_filter.current(0)

        ttk.Button(filter_frame, text="Appliquer", command=self.filter_games).grid(row=0, column=6, padx=5)

        self.games_tree = ttk.Treeview(self.games_tab, columns=(
            "id", "table_id", "winner", "mode", "status", "num_columns", "start_time", "end_time", "hash", "mutualized", "confiance", "coups"
        ), show="headings", selectmode="browse")

        self.games_tree.heading("id", text="ID")
        self.games_tree.heading("table_id", text="Table ID")
        self.games_tree.heading("winner", text="Gagnant")
        self.games_tree.heading("mode", text="Mode")
        self.games_tree.heading("status", text="Statut")
        self.games_tree.heading("num_columns", text="Colonnes")
        self.games_tree.heading("start_time", text="Début")
        self.games_tree.heading("end_time", text="Fin")
        self.games_tree.heading("hash", text="Hash")
        self.games_tree.heading("mutualized", text="Mutualisé")
        self.games_tree.heading("confiance", text="Confiance")
        self.games_tree.heading("coups", text="Nb Coups")

        self.games_tree.column("id", width=50, anchor=tk.CENTER)
        self.games_tree.column("table_id", width=80, anchor=tk.CENTER)
        self.games_tree.column("winner", width=80, anchor=tk.CENTER)
        self.games_tree.column("mode", width=120, anchor=tk.CENTER)
        self.games_tree.column("status", width=100, anchor=tk.CENTER)
        self.games_tree.column("num_columns", width=80, anchor=tk.CENTER)
        self.games_tree.column("start_time", width=150, anchor=tk.CENTER)
        self.games_tree.column("end_time", width=150, anchor=tk.CENTER)
        self.games_tree.column("hash", width=150, anchor=tk.CENTER)
        self.games_tree.column("mutualized", width=80, anchor=tk.CENTER)
        self.games_tree.column("confiance", width=80, anchor=tk.CENTER)
        self.games_tree.column("coups", width=80, anchor=tk.CENTER)

        self.games_tree.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame = ttk.Frame(self.games_tab)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="Voir les coups", command=self.show_game_moves).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Rafraîchir", command=self.load_games_data).pack(side=tk.RIGHT, padx=5)

        self.games_tree.bind("<Double-1>", lambda e: self.show_game_moves())

        self.load_games_data()

    def load_games_data(self, filter_conditions=None):
        for item in self.games_tree.get_children():
            self.games_tree.delete(item)

        query = """SELECT g.game_id, g.table_id, g.winner, g.mode, g.status, g.num_columns,
                          g.timestamp_start, g.timestamp_end, g.move_sequence_hash, g.is_mutualized,
                          g.confiance,
                          COUNT(m.move_id) as move_count
                   FROM games g
                   LEFT JOIN moves m ON g.game_id = m.game_id"""

        params = []

        if filter_conditions:
            where_clauses = []
            if filter_conditions.get("winner") != "Tous":
                where_clauses.append("g.winner = %s")
                params.append(filter_conditions["winner"])
            if filter_conditions.get("mode") != "Tous":
                mode_value = int(filter_conditions["mode"].split()[0])
                where_clauses.append("g.mode = %s")
                params.append(mode_value)
            if filter_conditions.get("status") != "Tous":
                where_clauses.append("g.status = %s")
                params.append(filter_conditions["status"])

            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)

        query += " GROUP BY g.game_id ORDER BY g.game_id ASC;"

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            games = cursor.fetchall()

            for game in games:
                game_id = game[0]
                if game_id is None:
                    print("Warning: game_id is None in database record", file=sys.stderr)
                    game_id = "Erreur"
                else:
                    try:
                        game_id = int(game_id)
                    except (ValueError, TypeError):
                        print(f"Warning: Invalid game_id value: {game_id}", file=sys.stderr)
                        game_id = "Erreur"

                start_time = game[6].strftime("%Y-%m-%d %H:%M") if game[6] else ""
                end_time = game[7].strftime("%Y-%m-%d %H:%M") if game[7] else ""
                mutualized = "Oui" if game[8] else "Non"
                move_count = game[10] or 0

                mode_text = str(game[3])
                if game[3] == 0:
                    mode_text = "IA vs IA"
                elif game[3] == 1:
                    mode_text = "Joueur vs IA"
                elif game[3] == 2:
                    mode_text = "Joueur vs Joueur"

                hash_value = game[8] if game[8] else ""
                if len(hash_value) > 15:
                    hash_value = hash_value[:15] + "..."

                self.games_tree.insert("", tk.END, values=(
                    game_id,
                    game[1],
                    game[2],
                    mode_text,
                    game[4],
                    game[5],
                    start_time,
                    end_time,
                    hash_value,
                    mutualized,
                    f"{game[9]:.2f}",  # confiance
                    move_count
                ))
        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Impossible de charger les parties: {e}")
            traceback.print_exc()

    def create_moves_tab(self):
        main_frame = ttk.Frame(self.moves_tab)
        main_frame.pack(fill=tk.BOTH, expand=True)

        moves_frame = ttk.Frame(main_frame)
        moves_frame.pack(fill=tk.X, pady=5)

        self.moves_tree = ttk.Treeview(moves_frame, columns=(
            "id", "game_id", "row", "col", "player", "order"
        ), show="headings")

        self.moves_tree.heading("id", text="ID Coup")
        self.moves_tree.heading("game_id", text="ID Partie")
        self.moves_tree.heading("row", text="Ligne")
        self.moves_tree.heading("col", text="Colonne")
        self.moves_tree.heading("player", text="Joueur")
        self.moves_tree.heading("order", text="Ordre")

        self.moves_tree.column("id", width=80, anchor=tk.CENTER)
        self.moves_tree.column("game_id", width=80, anchor=tk.CENTER)
        self.moves_tree.column("row", width=60, anchor=tk.CENTER)
        self.moves_tree.column("col", width=60, anchor=tk.CENTER)
        self.moves_tree.column("player", width=80, anchor=tk.CENTER)
        self.moves_tree.column("order", width=60, anchor=tk.CENTER)

        self.moves_tree.pack(fill=tk.BOTH, expand=True)

        ttk.Button(moves_frame, text="Rafraîchir les coups", command=self.refresh_moves).pack(pady=5)

        self.board_frame = ttk.LabelFrame(main_frame, text="Plateau de jeu", padding=10)
        self.board_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.board_canvas = tk.Canvas(self.board_frame, bg=self.COLOR_BG, highlightthickness=0)
        self.board_canvas.pack(fill=tk.BOTH, expand=True)

        ttk.Button(main_frame, text="Réinitialiser le plateau", command=self.reset_board_display).pack(pady=5)

    def reset_board_display(self):
        self.board_canvas.delete("all")

    def show_game_moves(self, event=None):
        selected_items = self.games_tree.selection()

        if not selected_items:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner une partie.")
            return

        try:
            selected_item = selected_items[0]
            values = self.games_tree.item(selected_item)["values"]

            if not values or len(values) == 0:
                messagebox.showerror("Erreur", "Aucune donnée disponible pour cette partie.")
                return

            game_id_str = values[0]

            try:
                game_id = int(game_id_str)
                self.current_game_id = game_id
            except (ValueError, TypeError):
                messagebox.showerror("Erreur", f"ID de partie invalide: {game_id_str}")
                return

            self.notebook.select(1)

            self.refresh_moves(game_id)

        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'affichage des coups: {e}")
            traceback.print_exc()

    def refresh_moves(self, game_id=None):
        if not game_id and not self.current_game_id:
            messagebox.showwarning("Avertissement", "Aucune partie sélectionnée.")
            return

        game_id = game_id or self.current_game_id

        try:
            for item in self.moves_tree.get_children():
                self.moves_tree.delete(item)

            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT move_id, game_id, row, col, player, move_order
                FROM moves
                WHERE game_id = %s
                ORDER BY move_order;
            """, (game_id,))

            moves = cursor.fetchall()

            if not moves:
                messagebox.showinfo("Info", f"Aucun coup trouvé pour la partie {game_id}.")
                self.reset_board_display()
                return

            for move in moves:
                player_text = "Rouge" if move[4] == 1 else "Jaune"
                self.moves_tree.insert("", tk.END, values=(
                    move[0],
                    move[1],
                    move[2] + 1,
                    move[3] + 1,
                    player_text,
                    move[5]
                ))

            self.draw_game_board(moves)

        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Erreur lors du rafraîchissement des coups: {str(e)}")
            traceback.print_exc()

    def draw_game_board(self, moves):
        self.board_canvas.delete("all")

        cols = 7
        rows = 6
        cell_size = self.CELL_SIZE
        width = cols * cell_size + 20
        height = rows * cell_size + 20

        self.board_canvas.config(width=width, height=height)

        for c in range(cols):
            x = 10 + c * cell_size + cell_size // 2
            y = 5
            self.board_canvas.create_text(x, y, text=str(c + 1), fill="white", font=("Arial", 12, "bold"))

        for r in range(rows):
            x = 5
            y = 10 + r * cell_size + cell_size // 2
            self.board_canvas.create_text(x, y, text=str(rows - r), fill="white", font=("Arial", 12, "bold"))

        for r in range(rows):
            for c in range(cols):
                x1 = 10 + c * cell_size
                y1 = 10 + r * cell_size
                x2 = x1 + cell_size
                y2 = y1 + cell_size
                self.board_canvas.create_rectangle(x1, y1, x2, y2, fill=self.COLOR_GRID, outline="black")

        board = [[0 for _ in range(cols)] for _ in range(rows)]

        for move in moves:
            col, player = move[3], move[4]
            if 0 <= col < cols:
                for r in range(rows-1, -1, -1):
                    if board[r][col] == 0:
                        board[r][col] = player
                        break

        for r in range(rows):
            for c in range(cols):
                if board[r][c] != 0:
                    x = 10 + c * cell_size + cell_size // 2
                    y = 10 + r * cell_size + cell_size // 2
                    color = self.COLOR_RED if board[r][c] == 1 else self.COLOR_YELLOW
                    self.board_canvas.create_oval(x - 18, y - 18, x + 18, y + 18, fill=color, outline="black")

    def create_stats_tab(self):
        ttk.Button(self.stats_tab, text="Calculer les statistiques", command=self.calculate_stats).pack(pady=10)

        self.stats_text = tk.Text(self.stats_tab, height=20)
        self.stats_text.pack(fill=tk.BOTH, expand=True, pady=5)

    def filter_games(self):
        filters = {
            "winner": self.winner_filter.get(),
            "mode": self.mode_filter.get(),
            "status": self.status_filter.get()
        }
        self.load_games_data(filters)

    def refresh_data(self):
        self.load_games_data()
        messagebox.showinfo("Info", "Données rafraîchies.")

    def export_to_csv(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM games;")
            games = cursor.fetchall()

            games_file = filedialog.asksaveasfilename(
                title="Enregistrer les parties",
                defaultextension=".csv",
                filetypes=[("Fichiers CSV", "*.csv")],
                initialfile="puissance4_games"
            )

            if games_file:
                with open(games_file, 'w', newline='') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerow(["game_id", "table_id", "winner", "mode", "status", "num_columns", "timestamp_start",
                                    "timestamp_end", "move_sequence_hash", "is_mutualized", "confiance"])
                    writer.writerows(games)

                cursor.execute("SELECT * FROM moves;")
                moves = cursor.fetchall()

                moves_file = filedialog.asksaveasfilename(
                    title="Enregistrer les coups",
                    defaultextension=".csv",
                    filetypes=[("Fichiers CSV", "*.csv")],
                    initialfile="puissance4_moves"
                )

                if moves_file:
                    with open(moves_file, 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(["move_id", "game_id", "row", "col", "player", "move_order"])
                        writer.writerows(moves)

                messagebox.showinfo("Export terminé", "Les données ont été exportées avec succès.")

        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Impossible d'exporter les données: {e}")
            traceback.print_exc()

    def search_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Rechercher une partie")
        dialog.geometry("400x200")

        ttk.Label(dialog, text="ID de la partie:").pack(pady=5)
        id_entry = ttk.Entry(dialog)
        id_entry.pack(pady=5)

        def search():
            game_id_text = id_entry.get()
            if not game_id_text.isdigit():
                messagebox.showerror("Erreur", "L'ID doit être un nombre.")
                return

            try:
                game_id = int(game_id_text)
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM games WHERE game_id = %s;", (game_id,))
                game = cursor.fetchone()

                if not game:
                    messagebox.showinfo("Info", f"Aucune partie trouvée avec l'ID {game_id}.")
                    return

                for item in self.games_tree.get_children():
                    if int(self.games_tree.item(item)["values"][0]) == game_id:
                        self.games_tree.selection_set(item)
                        self.games_tree.see(item)
                        break

                self.show_game_details(game)

            except psycopg2.Error as e:
                messagebox.showerror("Erreur", f"Impossible de rechercher la partie: {e}")
            finally:
                dialog.destroy()

        ttk.Button(dialog, text="Rechercher", command=search).pack(pady=10)

    def show_game_details(self, game):
        details_window = tk.Toplevel(self.root)
        details_window.title(f"Détails de la partie {game[0]}")
        details_window.geometry("800x700")

        info_frame = ttk.LabelFrame(details_window, text="Informations", padding=10)
        info_frame.pack(fill=tk.X, pady=5)

        mode_text = str(game[3])
        if game[3] == 0:
            mode_text = "IA vs IA"
        elif game[3] == 1:
            mode_text = "Joueur vs IA"
        elif game[3] == 2:
            mode_text = "Joueur vs Joueur"

        ttk.Label(info_frame, text=f"ID: {game[0]}").grid(row=0, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Table ID: {game[1]}").grid(row=0, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Gagnant: {game[2]}").grid(row=1, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Mode: {mode_text}").grid(row=1, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Statut: {game[4]}").grid(row=2, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Colonnes: {game[5]}").grid(row=2, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Début: {game[6]}").grid(row=3, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Fin: {game[7] if game[7] else 'En cours'}").grid(row=3, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Hash: {game[8] if game[8] else 'Aucun'}").grid(row=4, column=0, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Mutualisé: {'Oui' if game[9] else 'Non'}").grid(row=4, column=1, sticky=tk.W, padx=10, pady=2)
        ttk.Label(info_frame, text=f"Confiance: {game[10]:.2f}").grid(row=5, column=0, sticky=tk.W, padx=10, pady=2)

        btn_frame = ttk.Frame(details_window)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="Voir les coups",
                  command=lambda: self.show_game_moves_from_details(game[0])).pack(side=tk.LEFT, padx=5)

        self.draw_game_board_in_details(details_window, game[0])

    def show_game_moves_from_details(self, game_id):
        try:
            game_id = int(game_id)
            self.current_game_id = game_id

            self.notebook.select(1)

            self.refresh_moves(game_id)

        except (ValueError, TypeError):
            messagebox.showerror("Erreur", "ID de partie invalide.")

    def draw_game_board_in_details(self, parent, game_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT row, col, player FROM moves WHERE game_id = %s ORDER BY move_order;", (game_id,))
            moves = cursor.fetchall()

            board_frame = ttk.LabelFrame(parent, text="Plateau de la partie", padding=10)
            board_frame.pack(fill=tk.X, pady=10)

            cell_size = 40
            cols = 7
            rows = 6
            canvas_width = cols * cell_size + 20
            canvas_height = rows * cell_size + 20

            canvas = tk.Canvas(board_frame, width=canvas_width, height=canvas_height, bg="blue")
            canvas.pack()

            for r in range(rows):
                for c in range(cols):
                    x1 = 10 + c * cell_size
                    y1 = 10 + r * cell_size
                    x2 = x1 + cell_size
                    y2 = y1 + cell_size
                    canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black")

            for c in range(cols):
                x = 10 + c * cell_size + cell_size // 2
                y = 5
                canvas.create_text(x, y, text=str(c + 1), fill="white", font=("Arial", 12, "bold"))

            for r in range(rows):
                x = 5
                y = 10 + r * cell_size + cell_size // 2
                canvas.create_text(x, y, text=str(rows - r), fill="white", font=("Arial", 12, "bold"))

            board = [[0 for _ in range(cols)] for _ in range(rows)]

            for row, col, player in moves:
                if 0 <= col < cols:
                    for r in range(rows-1, -1, -1):
                        if board[r][col] == 0:
                            board[r][col] = player
                            break

            for r in range(rows):
                for c in range(cols):
                    if board[r][c] != 0:
                        x = 10 + c * cell_size + cell_size // 2
                        y = 10 + r * cell_size + cell_size // 2
                        color = "red" if board[r][c] == 1 else "yellow"
                        canvas.create_oval(x - 18, y - 18, x + 18, y + 18, fill=color, outline="black")

        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Impossible de charger le plateau: {e}")

    def calculate_stats(self):
        self.stats_text.delete(1.0, tk.END)

        try:
            cursor = self.conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM games;")
            total_games = cursor.fetchone()[0]
            self.stats_text.insert(tk.END, f"Nombre total de parties: {total_games}\n\n")

            cursor.execute("SELECT mode, COUNT(*) FROM games GROUP BY mode;")
            modes = cursor.fetchall()
            self.stats_text.insert(tk.END, "Parties par mode:\n")
            for mode, count in modes:
                mode_text = {0: "IA vs IA", 1: "Joueur vs IA", 2: "Joueur vs Joueur"}.get(mode, f"Mode {mode}")
                self.stats_text.insert(tk.END, f"  {mode_text}: {count}\n")

            cursor.execute("SELECT winner, COUNT(*) FROM games WHERE winner IS NOT NULL GROUP BY winner;")
            winners = cursor.fetchall()
            self.stats_text.insert(tk.END, "\nParties par gagnant:\n")
            for winner, count in winners:
                self.stats_text.insert(tk.END, f"  {winner}: {count}\n")

            cursor.execute("SELECT COUNT(*) FROM games WHERE is_mutualized = TRUE;")
            mutualized_count = cursor.fetchone()[0]
            self.stats_text.insert(tk.END, f"\nNombre de parties mutualisées: {mutualized_count}\n")

            cursor.execute("""
                SELECT AVG(EXTRACT(EPOCH FROM (timestamp_end - timestamp_start))/60)
                FROM games
                WHERE timestamp_end IS NOT NULL;
            """)
            avg_duration = cursor.fetchone()[0]
            if avg_duration:
                self.stats_text.insert(tk.END, f"\nDurée moyenne des parties: {avg_duration:.1f} minutes\n")

            cursor.execute("""
                SELECT game_id, EXTRACT(EPOCH FROM (timestamp_end - timestamp_start))/60 as duration
                FROM games
                WHERE timestamp_end IS NOT NULL
                ORDER BY duration DESC
                LIMIT 5;
            """)
            longest_games = cursor.fetchall()
            if longest_games:
                self.stats_text.insert(tk.END, "\n5 parties les plus longues (en minutes):\n")
                for game_id, duration in longest_games:
                    self.stats_text.insert(tk.END, f"  Partie {game_id}: {duration:.1f} min\n")

            cursor.execute("""
                SELECT AVG(confiance) FROM games;
            """)
            avg_confidence = cursor.fetchone()[0]
            if avg_confidence:
                self.stats_text.insert(tk.END, f"\nConfiance moyenne: {avg_confidence:.2f}\n")

        except psycopg2.Error as e:
            messagebox.showerror("Erreur", f"Impossible de calculer les statistiques: {e}")
            traceback.print_exc()

    def edit_game_moves(self):
        selected_items = self.games_tree.selection()

        if not selected_items:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner une partie.")
            return

        try:
            selected_item = selected_items[0]
            values = self.games_tree.item(selected_item)["values"]
            game_id = values[0]
            table_id = values[1] if len(values) > 1 else "N/A"

            moves_input = simpledialog.askstring("Modifier les coups",
                f"Entrez les coups pour la partie {table_id} (ex: 1,3,2,4,5,3,2):\n"
                f"Les colonnes sont numérotées de 1 à 7.\n"
                f"Laissez vide pour supprimer tous les coups.")

            if moves_input is None:
                return

            with self.conn.cursor() as cursor:
                cursor.execute("DELETE FROM moves WHERE game_id = %s;", (game_id,))

                if moves_input.strip():
                    moves_str = moves_input.strip().replace(" ", "")
                    moves = []
                    for col_str in moves_str.split(','):
                        try:
                            col = int(col_str) - 1
                            if 0 <= col <= 6:
                                moves.append(col)
                            else:
                                messagebox.showwarning("Avertissement", f"Colonne invalide: {col_str}. Doit être entre 1 et 7.")
                                return
                        except ValueError:
                            messagebox.showwarning("Avertissement", f"Valeur invalide: {col_str}. Doit être un nombre.")
                            return

                    if moves:
                        winner = "Rouge" if len(moves) % 2 == 1 else "Jaune"
                        move_hash = self.calculate_move_sequence_hash(moves)
                        cursor.execute("""
                            UPDATE games
                            SET winner = %s, move_sequence_hash = %s
                            WHERE game_id = %s;
                        """, (winner, move_hash, game_id))

                        for move_order, move in enumerate(moves, start=1):
                            player = 1 if move_order % 2 == 1 else 2
                            row = len([m for m in moves[:move_order] if m == move]) - 1
                            cursor.execute("""
                                INSERT INTO moves (game_id, row, col, player, move_order)
                                VALUES (%s, %s, %s, %s, %s);
                            """, (game_id, row, move, player, move_order))

                self.conn.commit()

            self.load_games_data()
            messagebox.showinfo("Succès", f"Coups mis à jour avec succès pour la partie {table_id}.")

            if game_id:
                self.refresh_moves(game_id)

        except Exception as e:
            self.conn.rollback()
            messagebox.showerror("Erreur", f"Erreur lors de la mise à jour des coups: {str(e)}")
            traceback.print_exc()

    def calculate_move_sequence_hash(self, moves):
        if not moves:
            return hashlib.sha256("".encode()).hexdigest()
        move_sequence = ",".join(str(move) for move in moves)
        return hashlib.sha256(move_sequence.encode()).hexdigest()

if __name__ == "__main__":
    try:
        db_name = "puissance4"
        user = "youssef"
        password = "Kassou00."
        host = "localhost"
        port = "5432"
    except ImportError:
        db_name = "puissance4"
        user = "youssef"
        password = "Kassou00."
        host = "localhost"
        port = "5432"

    DBViewer(db_name=db_name, user=user, password=password, host=host, port=port)
