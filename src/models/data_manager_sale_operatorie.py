import json
import os
from datetime import datetime


class DataManagerSaleOperatorie:
    def __init__(self, dir_sale_operatorie="mock_data/sale_operatorie",
                 filepath_anagrafica="mock_data/static_data/anagrafica_specializzandi.json"):
        self.dir_sale_operatorie = dir_sale_operatorie
        self.filepath_anagrafica = filepath_anagrafica
        self.specializzandi = self.load_anagrafica()

        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

        if not os.path.exists(self.dir_sale_operatorie):
            os.makedirs(self.dir_sale_operatorie, exist_ok=True)

    def _get_filepath(self, anno, mese):
        return os.path.join(self.dir_sale_operatorie, f"{anno:04d}-{mese:02d}.json")

    def load_mese(self, anno, mese):
        """Carica il mese specifico, usando la cache se possibile."""
        if self._cached_anno == anno and self._cached_mese == mese:
            return self._cached_data

        filepath = self._get_filepath(anno, mese)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {
                "metadata": {"stato": "BOZZA"},
                "turni": {}
            }

        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data
        return data

    def save_mese(self, anno, mese, data):
        """Salva i dati di un mese specifico e aggiorna la cache."""
        filepath = self._get_filepath(anno, mese)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data

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
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        return data["turni"].get(data_str, {}).get(nome_riga, "")

    def get_specializzandi(self, data_str):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        turno = data["turni"].get(data_str, {})

        or1 = turno.get("specializzandi").get("OR I", "")
        or2 = turno.get("specializzandi").get("OR II", "")

        return f"{or1}\n{or2}".strip()

    def get_slot(self, data_str, nome_riga):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        turno = data["turni"].get(data_str, {})

        slot = turno.get(nome_riga, {})

        if not slot:
            return ""

        paziente = slot.get("nome_paziente", "")
        diagnosi = slot.get("diagnosi", "")
        intervento = slot.get("intervento", "")
        chirurgo = slot.get("chirurgo", "")

        return f"{paziente} Dia: {diagnosi}\nInt: {intervento} {chirurgo}".strip()

    def set_valore_cella(self, data_str, nome_riga, valore):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        if data_str not in data["turni"]:
            data["turni"][data_str] = {}

        data["turni"][data_str][nome_riga] = valore
        self.save_mese(anno, mese, data)

    def get_mesi_disponibili(self):
        """Ritorna una lista di tuple (anno, mese) analizzando i file salvati."""
        disponibili = []
        if not os.path.exists(self.dir_sale_operatorie):
            return disponibili

        for filename in os.listdir(self.dir_sale_operatorie):
            if filename.endswith(".json") and len(filename) == 12:  # pattern YYYY-MM.json
                try:
                    anno = int(filename[0:4])
                    mese = int(filename[5:7])
                    disponibili.append((anno, mese))
                except ValueError:
                    pass
        return sorted(disponibili)

    def get_stato_mese(self, anno, mese):
        """Recupera lo stato attuale dal blocco metadata del JSON."""
        data = self.load_mese(anno, mese)
        return data.get("metadata", {}).get("stato", "BOZZA")

    def set_stato_mese(self, anno, mese, stato):
        """Forza un nuovo stato (es. STAMPA) nel JSON del mese."""
        data = self.load_mese(anno, mese)
        data["metadata"]["stato"] = stato
        self.save_mese(anno, mese, data)
