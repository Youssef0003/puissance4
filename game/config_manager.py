import os
import json

class ConfigManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.index_file = os.path.join(base_dir, 'index.json')
        self.saves_file = os.path.join(base_dir, 'saves.json')

        # Initialiser les fichiers s'ils n'existent pas
        if not os.path.exists(self.index_file):
            with open(self.index_file, 'w') as f:
                json.dump({'index': 0}, f)

        if not os.path.exists(self.saves_file):
            with open(self.saves_file, 'w') as f:
                json.dump([], f)

    def load_index(self):
        with open(self.index_file, 'r') as f:
            data = json.load(f)
            return data['index']

    def save_index(self, index):
        with open(self.index_file, 'w') as f:
            json.dump({'index': index}, f)

    def load_all_saves(self):
        with open(self.saves_file, 'r') as f:
            return json.load(f)

    def save_game(self, entry):
        saves = self.load_all_saves()
        saves.append(entry)
        with open(self.saves_file, 'w') as f:
            json.dump(saves, f, indent=4)
