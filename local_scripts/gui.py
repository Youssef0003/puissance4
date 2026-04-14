import os
import random
import tkinter as tk
from tkinter import ttk, messagebox
from .datetime import datetime
import hashlib
import subprocess
import sys
import traceback
from .board import Board, EMPTY, ROUGE, JAUNE, CELL_SIZE, PADDING, COLOR_BG, COLOR_GRID, COLOR_RED, COLOR_YELLOW
from .game_state import GameState
from .config_manager import ConfigManager
from .db_manager import DBManager

class Puissance4App:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_manager = ConfigManager(self.base_dir)
        config = self.config_manager.load_config()

        self.ROWS = config["rows"]
        self.COLS = config["cols"]
        self.START_COLOR = config["start_color"]

        self.root = tk.Tk()
        self.root.title("Puissance 4")
        self.root.configure(bg=COLOR_BG)

        self.frame_main = tk.Frame(self.root, bg=COLOR_BG)
        self.frame_main.pack(fill="both", expand=True)

        self.paused = False
        self.selected_depth = 4

        self.db_manager = DBManager(
            db_name="puissance4",
            user="youssef",
            password="Kassou00.",
            host="localhost",
            port="5432"
        )

        if not self.db_manager.connect():
            messagebox.showerror("Erreur", "Impossible de se connecter à la base de données PostgreSQL.")
            return

        if not self._verify_database_integrity():
            if not self._recreate_database():
                messagebox.showerror("Erreur", "Impossible de réinitialiser la base de données.")
                return

        self.initialize_database()

        self.game = GameState(
            rows=self.ROWS,
            cols=self.COLS,
            start_player=self.START_COLOR,
            mode=2,
            ai_type="minimax",
            ai_depth=self.selected_depth
        )

        self.canvas = None
        self.info_label = None
        self.confidence_label = None
        self.replay_history = []
        self.replay_step = 0
        self.results_listbox = None
        self.saves_listbox = None

        self.show_menu()
        self.root.mainloop()

    def _verify_database_integrity(self):
        try:
            query = """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public';
            """
            tables = self.db_manager.execute_query(query, fetch=True)
            tables = [t[0] for t in tables]

            required_tables = ['games', 'moves', 'mutualizations']
            for table in required_tables:
                if table not in tables:
                    print(f"Warning: Table {table} is missing", file=sys.stderr)
                    return False

            query = """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'games';
            """
            columns = self.db_manager.execute_query(query, fetch=True)
            columns = [col[0] for col in columns]
            required_columns = ['game_id', 'winner', 'mode', 'status', 'timestamp_start', 'num_columns', 'move_sequence_hash', 'confiance']
            for col in required_columns:
                if col not in columns:
                    print(f"Warning: Column {col} is missing in games table", file=sys.stderr)
                    return False

            return True
        except Exception as e:
            print(f"Error verifying database integrity: {e}", file=sys.stderr)
            traceback.print_exc()
            return False

    def _recreate_database(self):
        try:
            self.db_manager.close()

            if not self.db_manager.connect():
                raise Exception("Impossible de se reconnecter à la base de données")

            self.initialize_database()
            print("Base de données réinitialisée avec succès")
            return True
        except Exception as e:
            print(f"Erreur lors de la réinitialisation de la base de données: {e}", file=sys.stderr)
            traceback.print_exc()
            return False

    def initialize_database(self):
        self.db_manager.initialize_database()

    def launch_db_viewer(self):
        try:
            viewer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_viewer.py")

            cursor = self.db_manager.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM games")
            count = cursor.fetchone()[0]

            if count == 0:
                messagebox.showwarning("Avertissement", "Aucune partie n'a encore été enregistrée. Jouez une partie d'abord.")
                return

            if not os.path.exists(viewer_path):
                messagebox.showerror("Erreur", f"Le fichier {viewer_path} est introuvable.")
                return

            subprocess.Popen([sys.executable, viewer_path])
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lancer le visualisateur: {e}")
            traceback.print_exc()

    def clear_frame(self):
        for widget in self.frame_main.winfo_children():
            widget.destroy()

    def show_menu(self):
        self.clear_frame()
        tk.Label(self.frame_main, text="Puissance 4", fg="white", bg=COLOR_BG, font=("Arial", 24, "bold")).pack(pady=20)

        tk.Button(self.frame_main, text="Nouvelle partie", width=25, command=self.start_new_game_flow).pack(pady=10)
        tk.Button(self.frame_main, text="Importer une partie", width=25, command=self.import_game_flow).pack(pady=10)
        tk.Button(self.frame_main, text="Reprendre une sauvegarde", width=25, command=self.load_saved_game_flow).pack(pady=10)
        tk.Button(self.frame_main, text="Visualisateur de BD", width=25, command=self.launch_db_viewer).pack(pady=10)
        tk.Button(self.frame_main, text="Quitter", width=25, command=self.root.destroy).pack(pady=20)

    def start_new_game_flow(self):
        self.clear_frame()
        tk.Label(self.frame_main, text="Choisis un mode de jeu", fg="white", bg=COLOR_BG, font=("Arial", 18)).pack(pady=20)

        tk.Button(self.frame_main, text="IA vs IA", width=25, command=lambda: self.start_new_game(0)).pack(pady=5)
        tk.Button(self.frame_main, text="Joueur vs IA", width=25, command=self.choose_ai_type_for_player_vs_ai).pack(pady=5)
        tk.Button(self.frame_main, text="Joueur vs Joueur", width=25, command=lambda: self.start_new_game(2)).pack(pady=5)
        tk.Button(self.frame_main, text="Retour", width=25, command=self.show_menu).pack(pady=20)

    def choose_ai_type_for_player_vs_ai(self):
        self.clear_frame()
        tk.Label(self.frame_main, text="Choisis le type d'IA", fg="white", bg=COLOR_BG, font=("Arial", 18)).pack(pady=20)

        tk.Button(self.frame_main, text="IA aléatoire", width=25, command=lambda: self.start_new_game_with_ai_type("random")).pack(pady=10)
        tk.Button(self.frame_main, text="IA minimax (choisir profondeur)", width=25, command=self.ask_minimax_depth).pack(pady=10)
        tk.Button(self.frame_main, text="Retour", width=25, command=self.start_new_game_flow).pack(pady=20)

    def ask_minimax_depth(self):
        popup = tk.Toplevel(self.root)
        popup.title("Profondeur Minimax")
        popup.configure(bg=COLOR_BG)

        tk.Label(popup, text="Entrez la profondeur du Minimax :", bg=COLOR_BG, fg="white", font=("Arial", 14)).pack(pady=10)

        depth_var = tk.StringVar(value=str(self.selected_depth))
        depth_entry = tk.Entry(popup, textvariable=depth_var, bg="white", fg="black", font=("Arial", 14))
        depth_entry.pack(pady=10)

        def validate_depth():
            try:
                depth = int(depth_entry.get())
                if 1 <= depth <= 10:
                    self.selected_depth = depth
                    popup.destroy()
                    self.start_new_game_with_ai_type("minimax")
                else:
                    messagebox.showerror("Erreur", "La profondeur doit être un nombre entre 1 et 10.")
            except ValueError:
                messagebox.showerror("Erreur", "Veuillez entrer un nombre valide.")

        tk.Button(popup, text="Valider", command=validate_depth).pack(pady=10)

    def start_new_game(self, mode):
        try:
            last_id = self.config_manager.load_index()
            game_id = last_id + 1
            self.config_manager.save_index(game_id)

            self.game = GameState(
                rows=self.ROWS,
                cols=self.COLS,
                start_player=self.START_COLOR,
                mode=mode,
                ai_type="random" if mode == 0 else "minimax",
                ai_depth=self.selected_depth
            )

            self.game.reset_for_new_game(
                game_id=game_id,
                mode=mode,
                start_player=self.START_COLOR,
                ai_type="random" if mode == 0 else "minimax",
                ai_depth=self.selected_depth
            )

            self.show_game_screen()

            if self.game.mode == 0:
                self.root.after(500, self.play_ia_vs_ia)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de démarrer une nouvelle partie: {e}")
            traceback.print_exc()

    def start_new_game_with_ai_type(self, ai_type):
        try:
            last_id = self.config_manager.load_index()
            game_id = last_id + 1
            self.config_manager.save_index(game_id)

            self.game = GameState(
                rows=self.ROWS,
                cols=self.COLS,
                start_player=self.START_COLOR,
                mode=1,
                ai_type=ai_type,
                ai_depth=self.selected_depth
            )

            self.game.reset_for_new_game(
                game_id=game_id,
                mode=1,
                start_player=self.START_COLOR,
                ai_type=ai_type,
                ai_depth=self.selected_depth
            )

            self.show_game_screen()
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de démarrer une nouvelle partie: {e}")
            traceback.print_exc()

    def load_saved_game_flow(self):
        try:
            saves = self.config_manager.load_all_saves()
            self.clear_frame()
            tk.Label(self.frame_main, text="Choisir une sauvegarde", fg="white", bg=COLOR_BG, font=("Arial", 18)).pack(pady=10)

            if not saves:
                tk.Label(self.frame_main, text="Aucune sauvegarde disponible.", fg="white", bg=COLOR_BG, font=("Arial", 14)).pack(pady=10)
                tk.Button(self.frame_main, text="Retour", command=self.show_menu).pack(pady=10)
                return

            self.saves_listbox = tk.Listbox(self.frame_main, width=100, height=15)
            self.saves_listbox.pack(pady=10)

            for entry in saves:
                line = (
                    f"Sauvegarde {entry['save_id']} | "
                    f"Partie {entry['game_id']} | "
                    f"Mode: {entry['mode']} | "
                    f"Joueur actuel: {entry['current_player']} | "
                    f"Date: {entry['timestamp']}"
                )
                self.saves_listbox.insert(tk.END, line)

            tk.Button(self.frame_main, text="Charger", command=self.load_selected_save).pack(pady=5)
            tk.Button(self.frame_main, text="Retour", command=self.show_menu).pack(pady=10)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les sauvegardes: {e}")
            traceback.print_exc()

    def load_selected_save(self):
        try:
            index = self.saves_listbox.curselection()
            if not index:
                return

            saves = self.config_manager.load_all_saves()
            entry = saves[index[0]]

            self.game = GameState(
                rows=self.ROWS,
                cols=self.COLS,
                start_player=self.START_COLOR,
                mode=entry["mode"],
                ai_type="minimax",
                ai_depth=self.selected_depth
            )

            self.game.board.grid = entry["board"]
            self.game.current_player = entry["current_player"]
            self.game.mode = entry["mode"]
            self.game.game_id = entry["game_id"]
            self.game.move_history = entry["history"]
            self.game.last_confidence = entry.get("confidence", 0.5)

            self.show_game_screen()

            if self.game.mode == 0:
                self.root.after(500, self.play_ia_vs_ia)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger la sauvegarde: {e}")
            traceback.print_exc()

    def save_current_game(self):
        try:
            if self.game.board is None:
                return

            game_id = self.db_manager.save_result(winner=None, mode=self.game.mode, history=self.game.move_history, confiance=self.game.last_confidence)

            if game_id is None:
                messagebox.showerror("Erreur", "Impossible de sauvegarder la partie dans la base de données.")
                return

            saves = self.config_manager.load_all_saves()
            new_id = len(saves) + 1

            entry = {
                "save_id": new_id,
                "game_id": game_id,
                "mode": self.game.mode,
                "current_player": self.game.current_player,
                "board": self.game.board.grid,
                "history": self.game.move_history,
                "confidence": self.game.last_confidence,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            self.config_manager.save_game(entry)

            messagebox.showinfo("Succès", "Partie sauvegardée avec succès.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de sauvegarder la partie: {e}")
            traceback.print_exc()

    def show_game_screen(self):
        self.clear_frame()
        top_frame = tk.Frame(self.frame_main, bg=COLOR_BG)
        top_frame.pack(side="top", fill="x", pady=10)

        self.info_label = tk.Label(top_frame, text="", fg="white", bg=COLOR_BG, font=("Arial", 14))
        self.info_label.pack(side="left", padx=20)

        self.confidence_label = tk.Label(top_frame, text=f"Confiance: {self.game.last_confidence:.2f}", fg="white", bg=COLOR_BG, font=("Arial", 14))
        self.confidence_label.pack(side="left", padx=20)

        btn_frame = tk.Frame(top_frame, bg=COLOR_BG)
        btn_frame.pack(side="right", padx=20)

        tk.Button(btn_frame, text="Undo", command=self.undo_move).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Sauvegarder", command=self.save_current_game).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Menu", command=self.show_pause_popup).pack(side="left", padx=5)

        width = self.COLS * CELL_SIZE + 2 * PADDING
        height = self.ROWS * CELL_SIZE + 2 * PADDING

        self.canvas = tk.Canvas(self.frame_main, width=width, height=height, bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(pady=10)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.update_info_label()
        self.draw_board()

    def update_info_label(self):
        player = "Rouge" if self.game.current_player == ROUGE else "Jaune"
        mode_text = {0: " (IA vs IA)", 1: " (Joueur vs IA)", 2: " (Joueur vs Joueur)"}.get(self.game.mode, "")
        self.info_label.config(text=f"Au tour de {player}{mode_text}")

    def draw_board(self, win_cells=None):
        self.canvas.delete("all")

        for c in range(self.COLS):
            x = PADDING + c * CELL_SIZE + CELL_SIZE // 2
            y = PADDING - 15
            self.canvas.create_text(x, y, text=str(c + 1), fill="white", font=("Arial", 12, "bold"))

        for r in range(self.ROWS):
            for c in range(self.COLS):
                x1 = PADDING + c * CELL_SIZE
                y1 = PADDING + r * CELL_SIZE
                x2 = x1 + CELL_SIZE
                y2 = y1 + CELL_SIZE

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=COLOR_GRID, outline="#002244")

                cell = self.game.board.grid[r][c]
                if cell != EMPTY:
                    color = COLOR_RED if cell == ROUGE else COLOR_YELLOW
                    outline_color = "white" if win_cells and (r, c) in win_cells else "black"
                    outline_width = 4 if win_cells and (r, c) in win_cells else 2

                    self.canvas.create_oval(
                        x1 + 8, y1 + 8, x2 - 8, y2 - 8,
                        fill=color, outline=outline_color, width=outline_width
                    )

        if hasattr(self.game, "last_minimax_scores") and self.game.last_minimax_scores:
            self.canvas.create_text(
                PADDING + self.COLS * CELL_SIZE // 2,
                PADDING + self.ROWS * CELL_SIZE + 40,
                text="Scores Minimax (vert=bon, rouge=mauvais, blanc=neutre)",
                fill="white", font=("Arial", 10)
            )

            for col, score in self.game.last_minimax_scores.items():
                x = PADDING + col * CELL_SIZE + CELL_SIZE // 2
                y = PADDING + self.ROWS * CELL_SIZE + 15

                if score > 0:
                    color = "green"
                elif score < 0:
                    color = "red"
                else:
                    color = "white"

                self.canvas.create_text(x, y, text=f"{score:.0f}",
                                       fill=color, font=("Arial", 10, "bold"))

    def on_canvas_click(self, event):
        if self.game.mode == 0:
            return

        col = (event.x - PADDING) // CELL_SIZE
        if col < 0 or col >= self.COLS:
            return

        if self.game.mode == 1 and self.game.current_player == JAUNE:
            return

        row, win_cells = self.game.play_move(col)

        if row is None:
            return

        if win_cells:
            self.draw_board(win_cells)
            winner = "Rouge" if self.game.winner == ROUGE else "Jaune"
            game_id = self.db_manager.save_result(winner, self.game.mode, self.game.move_history, confiance=self.game.last_confidence)
            if game_id is None:
                messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
            self.show_end_message(f"{winner} a gagné !")
            return

        if self.game.board.is_full():
            self.draw_board()
            game_id = self.db_manager.save_result("Nul", self.game.mode, self.game.move_history, confiance=self.game.last_confidence)
            if game_id is None:
                messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
            self.show_end_message("Match nul !")
            return

        self.update_info_label()
        self.draw_board()

        if self.game.mode == 1 and self.game.current_player == JAUNE:
            self.root.after(500, self.play_ai_turn)

    def play_ai_turn(self):
        try:
            col, scores, confidence = self.game.ai_choose_move()
            self.game.last_confidence = confidence
            self.confidence_label.config(text=f"Confiance: {confidence:.2f}")

            if col is None:
                return

            row, win_cells = self.game.play_move(col)

            if win_cells:
                self.draw_board(win_cells)
                winner = "Rouge" if self.game.winner == ROUGE else "Jaune"
                game_id = self.db_manager.save_result(winner, self.game.mode, self.game.move_history, confiance=confidence)
                if game_id is None:
                    messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
                self.show_end_message(f"{winner} a gagné !")
                return

            if self.game.board.is_full():
                self.draw_board()
                game_id = self.db_manager.save_result("Nul", self.game.mode, self.game.move_history, confiance=confidence)
                if game_id is None:
                    messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
                self.show_end_message("Match nul !")
                return

            self.update_info_label()
            self.draw_board()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du tour de l'IA: {e}")
            traceback.print_exc()

    def play_ia_vs_ia(self):
        if self.paused or self.game.board is None:
            return

        try:
            col, scores, confidence = self.game.ai_choose_move()
            self.game.last_confidence = confidence
            self.confidence_label.config(text=f"Confiance: {confidence:.2f}")

            if col is None:
                return

            row, win_cells = self.game.play_move(col)

            if win_cells:
                self.draw_board(win_cells)
                winner = "Rouge" if self.game.winner == ROUGE else "Jaune"
                game_id = self.db_manager.save_result(winner, self.game.mode, self.game.move_history, confiance=confidence)
                if game_id is None:
                    messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
                self.show_end_message(f"{winner} a gagné !")
                return

            if self.game.board.is_full():
                self.draw_board()
                game_id = self.db_manager.save_result("Nul", self.game.mode, self.game.move_history, confiance=confidence)
                if game_id is None:
                    messagebox.showerror("Erreur", "Impossible de sauvegarder le résultat de la partie.")
                self.show_end_message("Match nul !")
                return

            if not self.paused and self.game.board is not None:
                if (not self.game.board.is_full() and
                    self.game.board.check_win(ROUGE) is None and
                    self.game.board.check_win(JAUNE) is None):
                    self.root.after(500, self.play_ia_vs_ia)
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la partie IA vs IA: {e}")
            traceback.print_exc()

    def undo_move(self):
        try:
            if not self.game.move_history:
                return

            if self.game.undo_move():
                self.update_info_label()
                self.draw_board()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'annulation du coup: {e}")
            traceback.print_exc()

    def calculate_move_sequence_hash(self, moves):
        if not moves:
            return hashlib.sha256("".encode()).hexdigest()
        move_sequence = ",".join(str(move) for move in moves)
        return hashlib.sha256(move_sequence.encode()).hexdigest()

    def show_end_message(self, text):
        try:
            popup = tk.Toplevel(self.root)
            popup.title("Fin de partie")

            tk.Label(popup, text=text, font=("Arial", 16)).pack(pady=10)

            winner = text.split(" ")[0] if "a gagné" in text else "Nul"
            self.update_game_completed(self.game.game_id, winner)

            tk.Button(popup, text="Retour au menu",
                      command=lambda: (popup.destroy(), self.show_menu())).pack(pady=5)
            tk.Button(popup, text="Rejouer",
                      command=lambda: (popup.destroy(), self.start_new_game_flow())).pack(pady=5)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'afficher le message de fin: {e}")
            traceback.print_exc()

    def update_game_completed(self, game_id, winner):
        try:
            query = """
            UPDATE games
            SET winner = %s, status = %s, timestamp_end = %s
            WHERE game_id = %s;
            """
            params = (winner, "completed", datetime.now(), game_id)
            return self.db_manager.execute_query(query, params)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de mettre à jour la partie: {e}")
            traceback.print_exc()
            return False

    def show_pause_popup(self):
        try:
            self.paused = True
            popup = tk.Toplevel(self.root)
            popup.title("Pause")
            popup.configure(bg=COLOR_BG)
            popup.grab_set()

            tk.Label(popup, text="Menu Pause", fg="white", bg=COLOR_BG, font=("Arial", 16, "bold")).pack(pady=10)

            tk.Button(popup, text="Reprendre la partie", width=25,
                      command=lambda: (popup.destroy(), self.resume_game())).pack(pady=5)
            tk.Button(popup, text="Sauvegarder et quitter vers le menu", width=25,
                      command=lambda: (self.save_current_game(), popup.destroy(), self.show_menu())).pack(pady=5)
            tk.Button(popup, text="Quitter vers le menu", width=25,
                      command=lambda: (popup.destroy(), self.show_menu())).pack(pady=5)
            tk.Button(popup, text="Quitter le jeu", width=25, command=self.root.destroy).pack(pady=10)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'afficher le menu pause: {e}")
            traceback.print_exc()

    def resume_game(self):
        self.paused = False

    def close(self):
        try:
            self.db_manager.close()
        except Exception as e:
            print(f"Erreur lors de la fermeture de la base de données: {e}", file=sys.stderr)
            traceback.print_exc()

    def __del__(self):
        self.close()

    def import_game_flow(self):
        try:
            self.clear_frame()
            tk.Label(self.frame_main, text="Importer une partie", fg="white", bg=COLOR_BG, font=("Arial", 18, "bold")).pack(pady=20)

            tk.Label(self.frame_main, text="Chemin du fichier (ex: 3131313.txt) :", fg="white", bg=COLOR_BG, font=("Arial", 14)).pack(pady=10)

            entry = tk.Entry(self.frame_main, width=50, font=("Arial", 12))
            entry.pack(pady=5)

            def validate_import():
                file_path = entry.get()
                if not file_path:
                    messagebox.showerror("Erreur", "Veuillez entrer un chemin de fichier.")
                    return
                self.import_game_from_file(file_path)

            tk.Button(self.frame_main, text="Importer", command=validate_import, width=15).pack(pady=10)
            tk.Button(self.frame_main, text="Retour", command=self.show_menu, width=15).pack(pady=10)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'afficher l'interface d'import: {e}")
            traceback.print_exc()

    def import_game_from_file(self, file_path):
        try:
            if not os.path.exists(file_path):
                messagebox.showerror("Erreur", "Fichier introuvable.")
                return False

            with open(file_path, "r") as file:
                content = file.read().strip()
                moves = [col.strip() for col in content.split(" ") if col.strip()]

            if not moves:
                messagebox.showerror("Erreur", "Le fichier est vide ou invalide.")
                return False

            try:
                moves = [int(col) for col in moves]
            except ValueError as e:
                messagebox.showerror("Erreur", f"Le fichier contient des valeurs invalides : {e}")
                return False

            existing_id = self.db_manager.check_if_exists(moves)
            if existing_id:
                messagebox.showwarning("Doublon", f"Cette partie (ou sa symétrie) existe déjà (ID: {existing_id}).")
                return False

            temp_board = Board(self.ROWS, self.COLS)
            history = []
            current_player = ROUGE

            for move_order, col in enumerate(moves, start=1):
                if col < 1 or col > self.COLS:
                    messagebox.showerror("Erreur", f"La colonne {col} est hors des limites du plateau.")
                    return False

                row = temp_board.place_token(col - 1, current_player)
                if row is None:
                    messagebox.showerror("Erreur", f"La colonne {col} est pleine.")
                    return False

                history.append((row, col, current_player))
                current_player = JAUNE if current_player == ROUGE else ROUGE

            winner = None
            for player in [ROUGE, JAUNE]:
                if temp_board.check_win(player):
                    winner = "Rouge" if player == ROUGE else "Jaune"
                    break

            if temp_board.is_full() and winner is None:
                winner = "Nul"

            game_id = self.db_manager.save_result(winner, 2, history, os.path.basename(file_path))

            if game_id is None:
                return False

            saves = self.config_manager.load_all_saves()
            new_id = len(saves) + 1
            entry = {
                "save_id": new_id,
                "game_id": game_id,
                "mode": 2,
                "current_player": JAUNE if len(history) % 2 == 0 else ROUGE,
                "board": temp_board.grid,
                "history": history,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            self.config_manager.save_game(entry)

            messagebox.showinfo("Succès", f"La partie {os.path.basename(file_path)} a été importée avec succès.")
            return True
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'importer la partie: {e}")
            traceback.print_exc()
            return False

if __name__ == "__main__":
    try:
        app = Puissance4App()
    except Exception as e:
        messagebox.showerror("Erreur", f"Impossible de démarrer l'application: {e}")
        traceback.print_exc()
