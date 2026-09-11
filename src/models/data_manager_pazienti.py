import os
import json
from datetime import datetime

from src.models.id_generator import next_available_id
from src.patient_fields import normalize_diagnosis
from src.planning_schema import (
    DEFAULT_MAX_WAIT_DAYS, OPTIMIZATION_KEY, default_patient_optimization,
)


def _diagnosis_fields(data: dict, existing: dict | None = None) -> tuple[str, str, str]:
    previous = existing or {}
    code = data.get("codice_diagnosi", previous.get("codice_diagnosi", ""))
    description = data.get("descrizione_diagnosi", data.get("diagnosi"))
    if description is None:
        description = previous.get("descrizione_diagnosi", previous.get("diagnosi", ""))
    return normalize_diagnosis(str(code), str(description))


class DataManagerPazienti:
    def __init__(
        self,
        dir_pazienti="mock_data/pazienti",
        dir_libretti=None,
    ):
        self.dir_pazienti = dir_pazienti
        self.dir_libretti = dir_libretti or os.path.join(
            os.path.dirname(os.path.abspath(dir_pazienti)),
            "libretti",
        )
        
        if not os.path.exists(self.dir_pazienti):
            os.makedirs(self.dir_pazienti, exist_ok=True)

    def get_tutti_pazienti(self):
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
        data_odierna = datetime.now().strftime("%d/%m/%Y")
        codice_diagnosi, descrizione_diagnosi, diagnosi = _diagnosis_fields(dati_form)

        interventi = dati_form.get("interventi", [])
        primo = interventi[0] if interventi else {}
        durata_tot = sum(i.get("durata", 0) for i in interventi) or dati_form.get("durata_intervento", 90)
        configurazione_modello = dati_form.get(OPTIMIZATION_KEY)
        if configurazione_modello is None:
            configurazione_modello = default_patient_optimization(
                dati_form["urgenza"],
                self._get_specializzandi_attivi_ids(),
            )

        nuovo_paziente = {
            "id": "",
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "codice_diagnosi": codice_diagnosi,
            "descrizione_diagnosi": descrizione_diagnosi,
            "diagnosi": diagnosi,
            "interventi": interventi,
            "codice_intervento": primo.get("codice", dati_form.get("codice_intervento", "")),
            "descrizione_intervento": primo.get("descrizione", dati_form.get("descrizione_intervento", "")),
            "durata_intervento": durata_tot,
            "tipo_chirurgia": dati_form.get("tipo_chirurgia", ""),
            "complessita": dati_form.get("complessita", ""),
            "urgenza": dati_form["urgenza"],
            "stato": dati_form.get("stato", "In Attesa"),
            "data_inserimento": data_odierna,
            "note": dati_form.get("note", ""),
            OPTIMIZATION_KEY: configurazione_modello,
        }

        # Il massimo suffisso evita collisioni quando la sequenza contiene buchi.
        while True:
            nuovo_id = next_available_id(self.dir_pazienti, "PZ", 4)
            nuovo_paziente["id"] = nuovo_id
            filepath = os.path.join(self.dir_pazienti, f"{nuovo_id}.json")
            payload = json.dumps(nuovo_paziente, indent=4)
            try:
                with open(filepath, 'x', encoding='utf-8') as f:
                    f.write(payload)
                break
            except FileExistsError:
                # Ricalcola l'ID in caso di scritture concorrenti.
                continue
            
        return nuovo_paziente

    def get_pazienti_in_attesa(self):
        """
        Restituisce i pazienti con stato 'In Attesa', ordinati per urgenza
        (Alta → Media → Bassa) e poi per cognome.
        """
        ordine_urgenza = {"Alta": 0, "Media": 1, "Bassa": 2}
        pazienti = [
            p for p in self.get_tutti_pazienti()
            if p.get("stato") == "In Attesa"
        ]
        pazienti.sort(key=lambda p: (
            ordine_urgenza.get(p.get("urgenza", "Bassa"), 2),
            p.get("cognome", ""),
        ))
        return pazienti

    def get_paziente_by_id(self, paziente_id):
        filepath = os.path.join(self.dir_pazienti, f"{paziente_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def aggiorna_paziente(self, paz_id, dati):
        filepath = os.path.join(self.dir_pazienti, f"{paz_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            paz = json.load(f)
        interventi = dati.get("interventi", paz.get("interventi", []))
        primo = interventi[0] if interventi else {}
        durata_tot = sum(i.get("durata", 0) for i in interventi) or dati.get("durata_intervento", paz.get("durata_intervento", 90))
        codice_diagnosi, descrizione_diagnosi, diagnosi = _diagnosis_fields(dati, paz)
        previous_urgency = paz.get("urgenza")

        paz.update({
            "nome": dati["nome"],
            "cognome": dati["cognome"],
            "codice_diagnosi": codice_diagnosi,
            "descrizione_diagnosi": descrizione_diagnosi,
            "diagnosi": diagnosi,
            "interventi": interventi,
            "codice_intervento": primo.get("codice", dati.get("codice_intervento", paz.get("codice_intervento", ""))),
            "descrizione_intervento": primo.get("descrizione", dati.get("descrizione_intervento", paz.get("descrizione_intervento", ""))),
            "durata_intervento": durata_tot,
            "tipo_chirurgia": dati.get("tipo_chirurgia", paz.get("tipo_chirurgia", "")),
            "complessita": dati.get("complessita", paz.get("complessita", "")),
            "urgenza": dati["urgenza"],
            "stato": dati.get("stato", paz.get("stato", "In Attesa")),
            "note": dati.get("note", paz.get("note", "")),
        })
        if OPTIMIZATION_KEY in dati:
            paz[OPTIMIZATION_KEY] = dati[OPTIMIZATION_KEY]
        elif previous_urgency != paz["urgenza"]:
            configuration = paz.get(OPTIMIZATION_KEY)
            if (
                isinstance(configuration, dict)
                and configuration.get("categoria_paper") == "I'"
                and configuration.get("attesa_massima_giorni")
                == DEFAULT_MAX_WAIT_DAYS.get(previous_urgency)
            ):
                configuration["attesa_massima_giorni"] = DEFAULT_MAX_WAIT_DAYS.get(paz["urgenza"])
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(paz, f, indent=4)
        return paz

    def _get_specializzandi_attivi_ids(self):
        """Restituisce gli ID degli specializzandi attivi."""

        if not os.path.exists(self.dir_libretti):
            return []
        resident_ids = []
        for filename in sorted(os.listdir(self.dir_libretti)):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.dir_libretti, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as stream:
                    record = json.load(stream)
            except (OSError, json.JSONDecodeError):
                continue
            resident_id = record.get("id")
            if record.get("stato") == "Molinette" and isinstance(resident_id, str):
                resident_ids.append(resident_id)
        return resident_ids

    def aggiorna_stato_paziente(self, paz_id: str, stato: str):
        filepath = os.path.join(self.dir_pazienti, f"{paz_id}.json")
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            paz = json.load(f)
        paz["stato"] = stato
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(paz, f, indent=4)

    def elimina_paziente(self, paz_id):
        filepath = os.path.join(self.dir_pazienti, f"{paz_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
