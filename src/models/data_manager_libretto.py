import os
import json
import random

class DataManagerLibretto:
    def __init__(self, dir_libretti="mock_data/libretti"):
        self.dir_libretti = dir_libretti
        
        if not os.path.exists(self.dir_libretti):
            os.makedirs(self.dir_libretti, exist_ok=True)

    def get_tutti_specializzandi(self):
        """Legge tutti i file JSON presenti nella cartella libretti e ne fa una lista"""
        specializzandi = []
        for filename in os.listdir(self.dir_libretti):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_libretti, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        specializzandi.append(data)
                    except json.JSONDecodeError:
                        pass 
        
        return sorted(specializzandi, key=lambda x: x.get('cognome', ''))
        
    def get_specializzando_by_id(self, spec_id):
        """Cerca e restituisce il dizionario del medico dato il suo ID"""
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def crea_nuovo_specializzando(self, dati_form):
        """Riceve un dizionario dal form e salva il nuovo JSON"""
        file_esistenti = [f for f in os.listdir(self.dir_libretti) if f.endswith(".json")]
        nuovo_id = f"SP{len(file_esistenti) + 1:03d}"
        
        nuovo_specializzando = {
            "id": nuovo_id,
            "matricola": dati_form["matricola"],
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "livello": dati_form["livello"],
            "stato": dati_form["stato"]
        }

        filepath = os.path.join(self.dir_libretti, f"{nuovo_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nuovo_specializzando, f, indent=4)
            
        return nuovo_specializzando
