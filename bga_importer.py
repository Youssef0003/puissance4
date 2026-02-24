import tkinter as tk
from tkinter import ttk, messagebox
import time
import logging
import traceback
import psycopg2
import pickle
import os
import re
from psycopg2 import sql, OperationalError
from selenium import webdriver
from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from datetime import datetime
from bs4 import BeautifulSoup

# Configuration du logging
logging.basicConfig(
    filename='bga_automation.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration PostgreSQL
PG_HOST = "localhost"
PG_PORT = "5432"
PG_USER = "youssef"
PG_PASSWORD = "Kassou00."
PG_DB = "puissance4"

# Configuration BGA
CLIENT_ID = "98887363"

class BGAImporter:
    def __init__(self, root):
        self.root = root
        self.root.title("BGA Connexion & Scraping")
        self.root.geometry("1200x800")

        # Variables d'état
        self.driver = None
        self.connected = False
        self.conn = None
        self.current_game_id = None

        # Initialiser la base de données
        self.init_db()

        # Interface utilisateur
        self.setup_ui()

    def setup_ui(self):
        """Configure l'interface utilisateur."""
        self.status_var = tk.StringVar(value="Statut: Déconnecté")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Onglet Connexion
        self.connection_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.connection_tab, text="Connexion")
        self.setup_connection_tab()

        # Onglet Parties
        self.games_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.games_tab, text="Parties")
        self.setup_games_tab()

        # Onglet Coups
        self.moves_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.moves_tab, text="Coups")
        self.setup_moves_tab()

        # Onglet Import HTML
        self.import_html_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.import_html_tab, text="Import HTML")
        self.setup_import_html_tab()

        # Statut
        self.status_label = tk.Label(self.root, textvariable=self.status_var, fg="red", font=("Arial", 12, "bold"))
        self.status_label.pack(pady=5)

    def setup_import_html_tab(self):
        """Configure l'onglet pour l'importation de HTML."""
        tk.Label(self.import_html_tab, text="Coller le contenu HTML de la page de replay :", font=("Arial", 12)).pack(pady=10)

        self.html_text = tk.Text(self.import_html_tab, width=100, height=20, font=("Arial", 10))
        self.html_text.pack(pady=10)

        tk.Button(self.import_html_tab, text="Importer depuis HTML", command=lambda: self.import_game_from_html(), width=20).pack(pady=5)

        tk.Label(self.import_html_tab, text="Ou entrez un table_id :", font=("Arial", 12)).pack(pady=10)

        self.table_id_entry = tk.Entry(self.import_html_tab, width=20, font=("Arial", 12))
        self.table_id_entry.pack(pady=5)

        tk.Button(self.import_html_tab, text="Importer depuis table_id", command=self.import_game_from_table_id, width=20).pack(pady=10)

    def setup_connection_tab(self):
        """Configure l'onglet de connexion."""
        button_frame = tk.Frame(self.connection_tab)
        button_frame.pack(pady=10)

        self.connect_button = tk.Button(button_frame, text="Connecter avec Email/Mot de passe", command=self.connect, width=30)
        self.connect_button.pack(side=tk.LEFT, padx=10)

        self.save_cookies_button = tk.Button(button_frame, text="Sauvegarder les Cookies", command=self.save_cookies, width=30)
        self.save_cookies_button.pack(side=tk.LEFT, padx=10)

        self.load_cookies_button = tk.Button(button_frame, text="Charger les Cookies", command=self.connect_with_cookies, width=30)
        self.load_cookies_button.pack(side=tk.LEFT, padx=10)

        # Champ pour l'ID du joueur
        frame_player = tk.Frame(self.connection_tab)
        frame_player.pack(pady=10)
        tk.Label(frame_player, text="ID Joueur BGA :").pack(side=tk.LEFT)
        self.player_entry = tk.Entry(frame_player, width=20)
        self.player_entry.pack(side=tk.LEFT, padx=10)
        self.player_entry.insert(0, CLIENT_ID)

        # Bouton pour scruter les tables
        self.scrute_button = tk.Button(self.connection_tab, text="Scruter les tables & Sauvegarder", command=self.scrute_tables, width=30, state=tk.DISABLED)
        self.scrute_button.pack(pady=10)

        # Bouton de déconnexion
        self.disconnect_button = tk.Button(self.connection_tab, text="Déconnecter", command=self.disconnect, width=30)
        self.disconnect_button.pack(pady=20)

    def setup_games_tab(self):
        """Configure l'onglet pour les parties."""
        columns = ("ID", "Table ID", "Gagnant", "Mode", "Statut", "Colonnes", "Début", "Fin", "Hash", "Mutualisé", "Nb Coups")
        self.games_tree = ttk.Treeview(self.games_tab, columns=columns, show="headings")

        for col in columns:
            self.games_tree.heading(col, text=col)
            self.games_tree.column(col, width=100)

        self.games_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Bouton pour voir les coups
        ttk.Button(self.games_tab, text="Voir les coups", command=self.show_game_moves).pack(pady=5)

    def setup_moves_tab(self):
        """Configure l'onglet pour les coups."""
        columns = ("ID Coup", "ID Partie", "Ligne", "Colonne", "Joueur", "Ordre")
        self.moves_tree = ttk.Treeview(self.moves_tab, columns=columns, show="headings")

        for col in columns:
            self.moves_tree.heading(col, text=col)
            self.moves_tree.column(col, width=100)

        self.moves_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def log(self, message, level=logging.INFO):
        """Journalise un message."""
        logging.log(level, message)
        print(f"[LOG] {message}")

    def init_db(self):
        """Initialise les tables PostgreSQL."""
        try:
            self.conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                user=PG_USER,
                password=PG_PASSWORD,
                database=PG_DB
            )

            cursor = self.conn.cursor()

            # Table games
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id SERIAL PRIMARY KEY,
                    table_id VARCHAR(50) UNIQUE,
                    winner VARCHAR(20),
                    mode INTEGER,
                    status VARCHAR(20),
                    num_columns INTEGER,
                    timestamp_start TIMESTAMP,
                    timestamp_end TIMESTAMP,
                    move_sequence_hash VARCHAR(255),
                    is_mutualized BOOLEAN,
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

            self.conn.commit()
            cursor.close()
            self.log("Tables PostgreSQL prêtes.")
        except OperationalError as e:
            self.log(f"Erreur init_db : {e}", logging.ERROR)
            messagebox.showerror("Erreur SQL", f"Impossible d'initier la BDD : {e}")

    def _get_browser(self):
        """Retourne un navigateur Firefox configuré."""
        try:
            options = FirefoxOptions()
            options.headless = False
            service = Service(GeckoDriverManager().install())
            driver = Firefox(service=service, options=options)
            driver.set_window_size(1200, 800)
            return driver
        except Exception as e:
            self.log(f"Erreur lors de la création du navigateur : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Impossible de créer le navigateur : {e}")
            return None

    def connect(self):
        """Se connecte à BGA avec email/mot de passe."""
        try:
            self.connect_button.config(state=tk.DISABLED)
            self.status_var.set("Statut: Connexion en cours...")
            self.root.update()

            # Lire les credentials
            with open("credentials.txt", "r") as f:
                credentials = f.read().splitlines()
                if len(credentials) < 2:
                    raise Exception("Format de credentials.txt invalide")
                email = credentials[0].strip()
                password = credentials[1].strip()

            # Lancer le navigateur
            self.driver = self._get_browser()
            if not self.driver:
                raise Exception("Impossible de créer le navigateur.")

            # Naviguer vers la page de connexion
            self.driver.get('https://fr.boardgamearena.com/account')

            # Remplir l'email
            email_field = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[type="email"], input[name="email"]'))
            )
            email_field.send_keys(email)

            # Cliquer sur "Suivant"
            next_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Suivant")] | //a[contains(., "Suivant")]'))
            )
            next_button.click()

            # Attendre le champ mot de passe
            password_field = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
            )
            password_field.send_keys(password)

            # Cliquer sur "Se connecter"
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Se connecter")] | //a[contains(., "Se connecter")]'))
            )
            login_button.click()

            # Attendre la connexion réussie
            WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, 'div#account_menu'))
            )

            self.connected = True
            self.status_var.set("Statut: Connecté (Email/Mot de passe)")
            self.status_label.config(fg="green")
            self.scrute_button.config(state=tk.NORMAL)
            self.log("Connexion réussie avec email/mot de passe.")
        except Exception as e:
            self.log(f"ERREUR: {str(e)}", logging.ERROR)
            self.log(traceback.format_exc(), logging.ERROR)
            messagebox.showerror("Erreur", f"Échec de la connexion: {str(e)}")
            self.status_var.set("Statut: Déconnecté")
            self.status_label.config(fg="red")
            if self.driver:
                self.driver.quit()
                self.driver = None
        finally:
            self.connect_button.config(state=tk.NORMAL)

    def save_cookies(self):
        """Sauvegarde les cookies après une connexion manuelle."""
        try:
            self.log("Début de la sauvegarde des cookies...")
            self.save_cookies_button.config(state=tk.DISABLED)

            browser = self._get_browser()
            if not browser:
                messagebox.showerror("Erreur", "Impossible de créer le navigateur.")
                self.save_cookies_button.config(state=tk.NORMAL)
                return

            browser.get("https://boardgamearena.com")
            messagebox.showinfo("Info", "Connecte-toi manuellement à BGA, puis appuie sur OK.")

            # Attendre que l'utilisateur se connecte manuellement
            popup = tk.Toplevel(self.root)
            popup.title("Attente de connexion")
            tk.Label(popup, text="Connecte-toi à BGA, puis appuie sur OK.").pack(pady=10)
            ok_button = tk.Button(popup, text="OK", command=popup.destroy)
            ok_button.pack(pady=10)
            ok_button.wait_window(popup)

            # Sauvegarder les cookies
            cookies = browser.get_cookies()
            with open("bga_cookies.pkl", "wb") as file:
                pickle.dump(cookies, file)

            self.log(f"Cookies sauvegardés (nombre : {len(cookies)})")
            messagebox.showinfo("Succès", f"Cookies sauvegardés ! (Nombre : {len(cookies)})")
            browser.quit()
        except Exception as e:
            self.log(f"Erreur lors de la sauvegarde des cookies : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Erreur : {e}")
        finally:
            self.save_cookies_button.config(state=tk.NORMAL)

    def load_cookies(self, driver, filename="bga_cookies.pkl"):
        """Charge les cookies depuis un fichier."""
        if os.path.exists(filename):
            with open(filename, "rb") as file:
                cookies = pickle.load(file)
            self.log(f"Nombre de cookies dans le fichier : {len(cookies)}")
            if len(cookies) == 0:
                self.log("Aucun cookie trouvé dans le fichier.", logging.WARNING)
                return False
            for cookie in cookies:
                try:
                    if cookie.get('sameSite') == 'None' and not cookie.get('secure'):
                        continue
                    driver.add_cookie(cookie)
                except Exception as e:
                    self.log(f"Erreur lors de l'ajout du cookie: {e}", logging.WARNING)
            self.log(f"Cookies ajoutés au driver : {len(driver.get_cookies())}")
            return True
        self.log(f"Aucun fichier de cookies trouvé : {filename}", logging.WARNING)
        return False

    def connect_with_cookies(self):
        """Se connecte à BGA en utilisant les cookies sauvegardés."""
        try:
            self.load_cookies_button.config(state=tk.DISABLED)
            self.status_var.set("Statut: Connexion via cookies...")

            browser = self._get_browser()
            if not browser:
                messagebox.showerror("Erreur", "Impossible de créer le navigateur.")
                return

            self.driver = browser
            self.driver.get("https://boardgamearena.com")

            if self.load_cookies(self.driver):
                self.driver.refresh()
                time.sleep(3)

                # Vérifier si la connexion a réussi
                page_source = self.driver.page_source
                connection_indicators = ["account_menu", "Mon compte", "Logout", "Déconnexion", "My account", "Welcome"]
                connected = any(indicator in page_source for indicator in connection_indicators)

                if connected:
                    self.connected = True
                    self.status_var.set("Statut: Connecté (via cookies)")
                    self.status_label.config(fg="green")
                    self.scrute_button.config(state=tk.NORMAL)
                    messagebox.showinfo("Info", "Connexion réussie avec les cookies !")
                else:
                    self.log("Échec de la connexion : aucun indicateur de connexion trouvé.", logging.ERROR)
                    messagebox.showerror("Erreur", "Échec de la connexion avec les cookies.")
            else:
                messagebox.showerror("Erreur", "Aucun cookie trouvé. Utilise 'Sauvegarder les Cookies' d'abord.")
        except Exception as e:
            self.log(f"Erreur lors de la connexion avec cookies : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Erreur : {e}")
            self.status_var.set("Statut: Déconnecté")
            self.status_label.config(fg="red")
            self.cleanup_driver()
        finally:
            self.load_cookies_button.config(state=tk.NORMAL)

    def insert_game(self, table_id, winner, mode, status, num_columns, start_time, end_time, move_sequence_hash, is_mutualized, confiance=0.5):
        """Insère une partie dans la table games."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO games (table_id, winner, mode, status, num_columns, timestamp_start, timestamp_end, move_sequence_hash, is_mutualized, confiance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (table_id) DO NOTHING
                RETURNING game_id;
            """, (table_id, winner, mode, status, num_columns, start_time, end_time, move_sequence_hash, is_mutualized, confiance))
            game_id = cursor.fetchone()
            if game_id is not None:
                game_id = game_id[0]
            else:
                cursor.execute("SELECT game_id FROM games WHERE table_id = %s;", (table_id,))
                game_id = cursor.fetchone()[0]
            self.conn.commit()
            cursor.close()
            return game_id
        except OperationalError as e:
            self.log(f"Erreur insertion game : {e}", logging.ERROR)
            return None

    def insert_move(self, game_id, row, col, player, move_order):
        """Insère un coup dans la table moves."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO moves (game_id, row, col, player, move_order)
                VALUES (%s, %s, %s, %s, %s);
            """, (game_id, row, col, player, move_order))
            self.conn.commit()
            cursor.close()
            return True
        except OperationalError as e:
            self.log(f"Erreur insertion move : {e}", logging.ERROR)
            return False

    def get_replay_html(self, table_id):
        """Récupère le contenu HTML d'une page de replay."""
        try:
            replay_url = f"https://boardgamearena.com/gamereview?table={table_id}"
            self.driver.get(replay_url)

            # Attendre que la page soit chargée
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#gamelogs"))
            )

            # Récupérer le contenu HTML de la page
            html_content = self.driver.page_source
            return html_content
        except Exception as e:
            self.log(f"Erreur lors de la récupération du contenu HTML : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Impossible de récupérer le contenu HTML : {e}")
            return None

    def extract_moves_and_winner_from_html(self, html_content):
        """Extrait les coups et le gagnant depuis le contenu HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extraire tous les logs de coups
        move_logs = soup.find_all('div', class_='gamelogreview')

        moves = []
        winner = None

        for log in move_logs:
            log_text = log.get_text(strip=True)

            # Utiliser une expression régulière pour capturer les coups
            move_match = re.search(r'^(.*?)\s+place un pion dans la colonne (\d+)$', log_text)
            if move_match:
                player = move_match.group(1).strip()
                column = int(move_match.group(2).strip())
                moves.append((player, column))

            # Détecter une victoire
            elif "a aligné quatre pions" in log_text:
                parts = log_text.split("a aligné quatre pions")
                winner = parts[0].strip()

        return moves, winner

    def import_game_from_html(self, table_id=None):
        """Importe une partie depuis le contenu HTML d'une page de replay."""
        try:
            if table_id:
                # Récupérer le contenu HTML de la page de replay
                html_content = self.get_replay_html(table_id)
                if not html_content:
                    messagebox.showerror("Erreur", "Impossible de récupérer le contenu HTML.")
                    return
            else:
                # Utiliser le contenu HTML collé
                html_content = self.html_text.get("1.0", tk.END)
                if not html_content.strip():
                    messagebox.showerror("Erreur", "Veuillez coller le contenu HTML ou fournir un table_id.")
                    return

            moves, winner = self.extract_moves_and_winner_from_html(html_content)

            if not moves:
                messagebox.showerror("Erreur", "Aucun coup trouvé dans le log.")
                return

            # Générer un table_id unique pour cette importation si non fourni
            if not table_id:
                table_id = f"imported_{int(time.time())}"

            # Insérer la partie dans la base de données
            game_id = self.insert_game(
                table_id=table_id,
                winner=winner,
                mode=2,
                status="completed",
                num_columns=9,
                start_time=datetime.now(),
                end_time=datetime.now(),
                move_sequence_hash="",
                is_mutualized=False,
                confiance=0.5
            )

            if not game_id:
                messagebox.showerror("Erreur", "Impossible d'insérer la partie dans la base de données.")
                return

            # Simuler le plateau de jeu de 9x9
            board = [[0 for _ in range(9)] for _ in range(9)]  # 9 lignes et 9 colonnes

            # Insérer les coups dans la base de données
            player_mapping = {}
            player_id = 1
            for move_order, (player_name, col) in enumerate(moves, start=1):
                if player_name not in player_mapping:
                    player_mapping[player_name] = player_id
                    player_id += 1
                player = player_mapping[player_name]

                # Trouver la première ligne vide dans la colonne
                row = 0
                while row < 9 and board[row][col - 1] != 0:
                    row += 1
                if row < 9:
                    board[row][col - 1] = player
                    success = self.insert_move(game_id, row, col - 1, player, move_order)
                    if not success:
                        self.log(f"Échec de l'insertion du coup : game_id={game_id}, row={row}, col={col - 1}, player={player}, move_order={move_order}", logging.ERROR)
                else:
                    self.log(f"Colonne pleine pour le coup {move_order} dans la colonne {col - 1}", logging.WARNING)

            # Afficher la partie dans l'interface
            self.games_tree.insert("", "end", values=(
                game_id, table_id, winner, "Joueur vs Joueur", "completed", 9,
                datetime.now().strftime("%Y-%m-%d %H:%M"), datetime.now().strftime("%Y-%m-%d %H:%M"),
                "", "Non", len(moves)
            ))

            messagebox.showinfo("Succès", f"La partie a été importée avec succès. {len(moves)} coups importés.")
        except Exception as e:
            self.log(f"Erreur lors de l'importation de la partie : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Erreur lors de l'importation : {e}")

    def import_game_from_table_id(self):
        """Importe une partie depuis un table_id."""
        try:
            table_id = self.table_id_entry.get().strip()
            if not table_id.isdigit():
                messagebox.showerror("Erreur", "ID de table invalide.")
                return

            self.import_game_from_html(table_id)
        except Exception as e:
            self.log(f"Erreur lors de l'importation depuis table_id : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Erreur lors de l'importation : {e}")

    def scrute_tables(self):
        """Scrute les tables de jeux et sauvegarde les résultats."""
        try:
            player_id = self.player_entry.get().strip()
            if not player_id.isdigit():
                messagebox.showerror("Erreur", "ID joueur invalide")
                return

            for item in self.games_tree.get_children():
                self.games_tree.delete(item)

            self.status_var.set(f"Scan du joueur {player_id} en cours...")
            self.root.update()

            url = f"https://boardgamearena.com/gamestats?player={player_id}"
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.statstable"))
                )
            except Exception as e:
                self.log(f"Erreur lors de l'attente de la table des statistiques : {e}", logging.ERROR)
                messagebox.showerror("Erreur", f"Impossible de trouver la table des statistiques : {e}")
                return

            table = self.driver.find_element(By.CSS_SELECTOR, "table.statstable")
            rows = table.find_elements(By.TAG_NAME, "tr")
            found = 0

            for row in rows:
                try:
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if not tds or len(tds) < 3:
                        continue
                    game_link = tds[0].find_element(By.CSS_SELECTOR, "a.table_name.gamename")
                    game_name = game_link.text
                    if "Puissance" not in game_name and "Connect Four" not in game_name:
                        continue
                    table_url = game_link.get_attribute("href")
                    if "table=" not in table_url:
                        continue
                    table_id = table_url.split("table=")[1].split("&")[0]

                    # Importer la partie depuis le table_id
                    self.import_game_from_html(table_id)
                    found += 1
                except Exception as e:
                    self.log(f"Erreur lors du traitement d'une ligne de la table : {e}", logging.ERROR)

            self.status_var.set(f"Terminé : {found} tables traitées.")
            if found == 0:
                messagebox.showinfo("Résultat", "Aucune table de Puissance 4 trouvée.")
        except Exception as e:
            self.log(f"Erreur scrutation : {e}", logging.ERROR)
            messagebox.showerror("Erreur Scan", str(e))

    def show_game_moves(self):
        """Affiche les coups de la partie sélectionnée."""
        selected_items = self.games_tree.selection()
        if not selected_items:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner une partie.")
            return

        selected_item = selected_items[0]
        values = self.games_tree.item(selected_item)["values"]
        game_id = values[0]

        # Effacer les anciens coups
        for item in self.moves_tree.get_children():
            self.moves_tree.delete(item)

        # Charger les coups de la partie
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT move_id, game_id, row, col, player, move_order
                FROM moves
                WHERE game_id = %s
                ORDER BY move_order;
            """, (game_id,))
            moves = cursor.fetchall()

            for move in moves:
                player_text = "Rouge" if move[4] == 1 else "Jaune"
                self.moves_tree.insert("", "end", values=(
                    move[0], move[1], move[2], move[3] + 1, player_text, move[5]  # Ajouter 1 à la colonne pour l'affichage
                ))
        except OperationalError as e:
            self.log(f"Erreur chargement coups : {e}", logging.ERROR)
            messagebox.showerror("Erreur", f"Erreur lors du chargement des coups: {e}")

    def cleanup_driver(self):
        """Nettoie le driver Selenium."""
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
            self.driver = None
        self.connected = False
        self.scrute_button.config(state=tk.DISABLED)

    def disconnect(self):
        """Déconnecte et ferme le navigateur."""
        self.cleanup_driver()
        self.status_var.set("Statut: Déconnecté")
        self.status_label.config(fg="red")

    def on_closing(self):
        """Fermeture propre de l'application."""
        self.disconnect()
        if self.conn:
            self.conn.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = BGAImporter(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
