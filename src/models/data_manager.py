import json
import os


class DataManager:
    def __init__(self, filepath_turni="mock_data/scadenzario/scadenzario.json",
                 filepath_anagrafica="mock_data/static_data/anagrafica_specializzandi.json"):
        self.filepath_turni = filepath_turni
        self.filepath_anagrafica = filepath_anagrafica
        self.data_turni = self.load_turni()
        self.specializzandi = self.load_anagrafica()

    def load_turni(self):
        if os.path.exists(self.filepath_turni):
            with open(self.filepath_turni, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_turni(self):
        os.makedirs(os.path.dirname(self.filepath_turni), exist_ok=True)
        with open(self.filepath_turni, 'w', encoding='utf-8') as f:
            json.dump(self.data_turni, f, indent=4)

    def load_anagrafica(self):
        if os.path.exists(self.filepath_anagrafica):
            with open(self.filepath_anagrafica, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def get_specializzandi_attivi(self):
        attivi = []
        for spec in self.specializzandi:
            if spec.get("attivo", False):
                nome_formattato = f"{spec['cognome']} {spec['nome'][0]}."
                attivi.append(nome_formattato)
        return attivi

    def get_valore_cella(self, data_str, nome_riga):
        return self.data_turni.get(data_str, {}).get(nome_riga, "")

    def set_valore_cella(self, data_str, nome_riga, valore):
        if data_str not in self.data_turni:
            self.data_turni[data_str] = {}

        self.data_turni[data_str][nome_riga] = valore
        self.save_turni()
