import os
import json
import configparser

class ConfigManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, 'config.ini')
        self.config = configparser.ConfigParser()

        if not os.path.exists(self.config_file):
            self._create_default_config()
        else:
            self.config.read(self.config_file)

    def _create_default_config(self):
        """Crée un fichier de configuration par défaut"""
        self.config['DATABASE'] = {
            'host': 'localhost',
            'port': '5432',
            'dbname': 'dbp4',
            'user': 'youssef',
            'password': 'Kassou00.'
        }

        self.config['GAME'] = {
            'default_mode': '2',
            'default_ai_type': 'random',
            'default_depth': '3'
        }

        with open(self.config_file, 'w') as f:
            self.config.write(f)

    def get(self, section, key, default=None):
        """Récupère une valeur de configuration"""
        try:
            return self.config.get(section, key)
        except:
            return default

    def set(self, section, key, value):
        """Définit une valeur de configuration"""
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        with open(self.config_file, 'w') as f:
            self.config.write(f)
