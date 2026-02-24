import os
import json

class ConfigManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, "config.json")
        self.saves_file = os.path.join(base_dir, "saves.json")
        self.index_file = os.path.join(base_dir, "index.json")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        if not os.path.exists(self.config_file):
            default_config = {"rows": 9, "cols": 9, "start_color": 1}
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
        if not os.path.exists(self.saves_file):
            with open(self.saves_file, 'w') as f:
                json.dump([], f, indent=4)
        if not os.path.exists(self.index_file):
            with open(self.index_file, 'w') as f:
                json.dump({"last_id": 0}, f, indent=4)

    def load_config(self):
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def load_all_saves(self):
        with open(self.saves_file, 'r') as f:
            return json.load(f)

    def save_game(self, entry):
        saves = self.load_all_saves()
        saves.append(entry)
        with open(self.saves_file, 'w') as f:
            json.dump(saves, f, indent=4)

    def load_index(self):
        with open(self.index_file, 'r') as f:
            data = json.load(f)
            return data.get("last_id", 0)

    def save_index(self, index):
        with open(self.index_file, 'w') as f:
            json.dump({"last_id": index}, f, indent=4)
