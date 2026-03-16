from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem
from src.views.view_nuovo_paziente import DialogNuovoPaziente

class ControllerPazienti:
    def __init__(self, view, model_pazienti):
        self.view = view
        self.model = model_pazienti
        
        self.setup_connections()
        self.aggiorna_lista()

    def setup_connections(self):
        self.view.chk_urg_alta.stateChanged.connect(self.aggiorna_lista)
        self.view.chk_urg_media.stateChanged.connect(self.aggiorna_lista)
        self.view.chk_urg_bassa.stateChanged.connect(self.aggiorna_lista)
        
        self.view.search_bar.textChanged.connect(self.aggiorna_lista)
        self.view.lista_risultati.itemSelectionChanged.connect(self.gestisci_selezione)
        
        self.view.btn_aggiungi.clicked.connect(self.apri_form_aggiunta)
        self.view.btn_apri.clicked.connect(self.apri_dettaglio_paziente)
        self.view.btn_indietro.clicked.connect(self.torna_alla_lista)

    def apri_dettaglio_paziente(self):
        selezionati = self.view.lista_risultati.selectedItems()
        if not selezionati:
            return
            
        paziente_id = selezionati[0].data(Qt.ItemDataRole.UserRole)
        paziente = self.model.get_paziente_by_id(paziente_id)
        
        if not paziente:
            return


        nome_completo = f"{paziente.get('cognome', '')} {paziente.get('nome', '')}".upper()
        self.view.lbl_nome_paziente.setText(f"Dettaglio Paziente: {nome_completo}")
        
        self.view.val_codice.setText(paziente.get('codice_intervento', ''))
        
        urgenza = paziente.get('urgenza', '')
        self.view.val_urgenza.setText(f"Priorità: {urgenza}")
        

        base_style = "font-size: 18px; font-weight: bold; background-color: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; "
        if urgenza == "Alta":
            self.view.val_urgenza.setStyleSheet(base_style + "color: #dc3545;") 
        elif urgenza == "Media":
            self.view.val_urgenza.setStyleSheet(base_style + "color: #fd7e14;") 
        else:
            self.view.val_urgenza.setStyleSheet(base_style + "color: #198754;") 
            
        self.view.val_data.setText(paziente.get('data_inserimento', ''))
        
        note = paziente.get('note', '')
        if not note:
            note = "Nessuna nota clinica inserita."
        self.view.txt_note.setText(note)


        self.view.stacked_widget.setCurrentIndex(1)

    def torna_alla_lista(self):
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    def apri_form_aggiunta(self):
        dialog = DialogNuovoPaziente(self.view)
        
        if dialog.exec():
            dati = dialog.get_dati()
            self.model.crea_nuovo_paziente(dati)
            self.aggiorna_lista()

    def aggiorna_lista(self):
        self.view.lista_risultati.clear()
        
        tutti_pazienti = self.model.get_tutti_pazienti()
        
        testo_ricerca_raw = self.view.search_bar.text().lower().strip()
        termini_ricerca = testo_ricerca_raw.split() if testo_ricerca_raw else []
        
        urgenze_selezionate = []
        if self.view.chk_urg_alta.isChecked():
            urgenze_selezionate.append("Alta")
        if self.view.chk_urg_media.isChecked():
            urgenze_selezionate.append("Media")
        if self.view.chk_urg_bassa.isChecked():
            urgenze_selezionate.append("Bassa")

        for paz in tutti_pazienti:
            urgenza_paz = paz.get("urgenza")
            if urgenza_paz not in urgenze_selezionate:
                continue
                
            if termini_ricerca:
                match_string = f"{paz.get('nome','')} {paz.get('cognome','')} {paz.get('codice_intervento','')}".lower()
                
                match_fallito = False
                for termine in termini_ricerca:
                    if termine not in match_string:
                        match_fallito = True
                        break
                        
                if match_fallito:
                    continue

            cognome = paz.get('cognome','').upper()
            nome = paz.get('nome','')
            codice = paz.get('codice_intervento', '')
            
            nome_display = f"{cognome} {nome}      |      Cod. {codice} ({urgenza_paz})"
            
            item = QListWidgetItem(nome_display)
            item.setData(Qt.ItemDataRole.UserRole, paz.get("id"))
            
            self.view.lista_risultati.addItem(item)
            
        self.view.btn_apri.setEnabled(False)

    def gestisci_selezione(self):
        selezionati = self.view.lista_risultati.selectedItems()
        self.view.btn_apri.setEnabled(bool(selezionati))
