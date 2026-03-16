import os
import json
from datetime import datetime

class DataManagerPazienti:
    def __init__(self, dir_pazienti="mock_data/pazienti"):
        self.dir_pazienti = dir_pazienti
        
        if not os.path.exists(self.dir_pazienti):
            os.makedirs(self.dir_pazienti, exist_ok=True)

    def get_tutti_pazienti(self):
        """Legge tutti i file JSON presenti nella cartella pazienti"""
        pazienti = []
        for filename in os.listdir(self.dir_pazienti):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_pazienti, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        pazienti.append(data)
                    except json.JSONDecodeError:
                        pass 
        
        return sorted(pazienti, key=lambda x: x.get('cognome', ''))

    def crea_nuovo_paziente(self, dati_form):
        """Salva il nuovo paziente in un file JSON dedicato"""
        file_esistenti = [f for f in os.listdir(self.dir_pazienti) if f.endswith(".json")]
        nuovo_id = f"PZ{len(file_esistenti) + 1:04d}"
        
        data_odierna = datetime.now().strftime("%d/%m/%Y")

        nuovo_paziente = {
            "id": nuovo_id,
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "codice_intervento": dati_form["codice_intervento"],
            "urgenza": dati_form["urgenza"],
            "data_inserimento": data_odierna,
            "note": dati_form["note"]
        }

        filepath = os.path.join(self.dir_pazienti, f"{nuovo_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nuovo_paziente, f, indent=4)
            
        return nuovo_paziente

    def get_paziente_by_id(self, paziente_id):
        filepath = os.path.join(self.dir_pazienti, f"{paziente_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
