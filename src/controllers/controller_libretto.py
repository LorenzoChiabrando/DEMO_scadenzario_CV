from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando

class ControllerLibretto:
    def __init__(self, view, model_libretto):
        self.view = view
        self.model = model_libretto
        
        self.setup_connections()
        self.aggiorna_lista()

    def setup_connections(self):
        self.view.chk_attiva_molinette.stateChanged.connect(self.aggiorna_lista)
        self.view.chk_attiva_altre.stateChanged.connect(self.aggiorna_lista)
        self.view.chk_storico.stateChanged.connect(self.aggiorna_lista)
        self.view.search_bar.textChanged.connect(self.aggiorna_lista)
        self.view.lista_risultati.itemSelectionChanged.connect(self.gestisci_selezione)
        
        self.view.btn_aggiungi.clicked.connect(self.apri_form_aggiunta)
        
        self.view.btn_apri.clicked.connect(self.apri_dettaglio_libretto)
        self.view.btn_indietro.clicked.connect(self.torna_ad_anagrafica)

    def apri_dettaglio_libretto(self):
        """Passa alla visualizzazione del libretto popolando l'anagrafica"""
        selezionati = self.view.lista_risultati.selectedItems()
        if not selezionati:
            return
            
        item = selezionati[0]
        medico_id = item.data(Qt.ItemDataRole.UserRole)
        
        spec = self.model.get_specializzando_by_id(medico_id)
        if not spec:
            return
            
        nome_completo = f"{spec.get('cognome', '').upper()} {spec.get('nome', '')}"
        
        self.view.lbl_nome_medico.setText(f"Libretto di: {nome_completo}")
        self.view.val_matricola.setText(spec.get('matricola', 'N/D'))
        self.view.val_livello.setText(spec.get('livello', 'N/D'))
        self.view.val_stato.setText(spec.get('stato', 'N/D'))
        self.view.val_score.setText("TODO") 
        
        # TODO: Popolare la tabella con i dati del algoritmo di ottimizzazione
        
        self.view.stacked_widget.setCurrentIndex(1)

    def aggiorna_lista(self):
        self.view.lista_risultati.clear()
        tutti_specializzandi = self.model.get_tutti_specializzandi()
        testo_ricerca_raw = self.view.search_bar.text().lower().strip()
        termini_ricerca = testo_ricerca_raw.split() if testo_ricerca_raw else []
        
        stati_selezionati = []
        if self.view.chk_attiva_molinette.isChecked():
            stati_selezionati.append("Molinette")
        if self.view.chk_attiva_altre.isChecked():
            stati_selezionati.append("Altra Sede")
        if self.view.chk_storico.isChecked():
            stati_selezionati.append("Storico")

        from PySide6.QtWidgets import QListWidgetItem

        for spec in tutti_specializzandi:
            if spec.get("stato") not in stati_selezionati:
                continue
                
            if termini_ricerca:
                match_string = f"{spec.get('nome','')} {spec.get('cognome','')} {spec.get('matricola','')}".lower()
                match_fallito = False
                for termine in termini_ricerca:
                    if termine not in match_string:
                        match_fallito = True
                        break
                if match_fallito:
                    continue

            cognome = spec.get('cognome','').upper()
            nome = spec.get('nome','')
            matricola = spec.get('matricola', 'N/D')
            
            nome_display = f"Matricola: {matricola}   |   {cognome} {nome}"
            
            item = QListWidgetItem(nome_display)
            item.setData(Qt.ItemDataRole.UserRole, spec.get("id"))
            
            self.view.lista_risultati.addItem(item)
            
        self.view.btn_apri.setEnabled(False)

    def torna_ad_anagrafica(self):
        """Ritorna alla lista e pulisce la selezione per sicurezza"""
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    def apri_form_aggiunta(self):
        dialog = DialogNuovoSpecializzando(self.view)
        
        if dialog.exec():
            dati = dialog.get_dati()
            self.model.crea_nuovo_specializzando(dati)
            self.aggiorna_lista()


    def gestisci_selezione(self):
        selezionati = self.view.lista_risultati.selectedItems()
        if selezionati:
            self.view.btn_apri.setEnabled(True)
        else:
            self.view.btn_apri.setEnabled(False)
