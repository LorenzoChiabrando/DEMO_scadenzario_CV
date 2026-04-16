from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando


class ControllerLibretto:
    def __init__(self, view, model_libretto):
        self.view = view
        self.model = model_libretto
        self._spec_corrente = None  # spec dict dello specializzando aperto in dettaglio
        self.setup_connections()
        self.aggiorna_lista()

    def setup_connections(self):
        self.view.chk_attiva_molinette.toggled.connect(self.aggiorna_lista)
        self.view.chk_attiva_altre.toggled.connect(self.aggiorna_lista)
        self.view.chk_storico.toggled.connect(self.aggiorna_lista)
        self.view.search_bar.textChanged.connect(self.aggiorna_lista)
        self.view.lista_risultati.itemSelectionChanged.connect(self.gestisci_selezione)
        self.view.btn_aggiungi.clicked.connect(self.apri_form_aggiunta)
        self.view.btn_apri.clicked.connect(self.apri_dettaglio_libretto)
        self.view.btn_indietro.clicked.connect(self.torna_ad_anagrafica)
        self.view.btn_modifica.clicked.connect(self.modifica_specializzando)
        self.view.btn_elimina.clicked.connect(self.elimina_specializzando)

    # ─── Navigazione ──────────────────────────────────────────────────────────

    def apri_dettaglio_libretto(self):
        selezionati = self.view.lista_risultati.selectedItems()
        if not selezionati:
            return
        medico_id = selezionati[0].data(Qt.ItemDataRole.UserRole)
        spec = self.model.get_specializzando_by_id(medico_id)
        if not spec:
            return
        self._spec_corrente = spec
        self.view.imposta_dettaglio(spec)
        self.view.stacked_widget.setCurrentIndex(1)

    def torna_ad_anagrafica(self):
        self._spec_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    # ─── Lista ────────────────────────────────────────────────────────────────

    def aggiorna_lista(self):
        self.view.lista_risultati.clear()
        tutti = self.model.get_tutti_specializzandi()
        testo = self.view.search_bar.text().lower().strip()
        termini = testo.split() if testo else []

        stati = []
        if self.view.chk_attiva_molinette.isChecked():
            stati.append("Molinette")
        if self.view.chk_attiva_altre.isChecked():
            stati.append("Altra Sede")
        if self.view.chk_storico.isChecked():
            stati.append("Storico")

        for spec in tutti:
            if spec.get("stato") not in stati:
                continue
            if termini:
                match_str = (
                    f"{spec.get('nome','')} {spec.get('cognome','')} "
                    f"{spec.get('matricola','')}".lower()
                )
                if any(t not in match_str for t in termini):
                    continue

            item, widget = self.view.crea_item_lista(
                cognome=spec.get("cognome", "").upper(),
                nome=spec.get("nome", ""),
                matricola=spec.get("matricola", "N/D"),
                livello=spec.get("livello", ""),
                stato=spec.get("stato", ""),
            )
            item.setData(Qt.ItemDataRole.UserRole, spec.get("id"))
            self.view.lista_risultati.addItem(item)
            self.view.lista_risultati.setItemWidget(item, widget)

        self.view.btn_apri.setEnabled(False)

    def gestisci_selezione(self):
        lista = self.view.lista_risultati

        for i in range(lista.count()):
            w = lista.itemWidget(lista.item(i))
            if w:
                w.setProperty("selected", False)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()

        selezionati = lista.selectedItems()
        if selezionati:
            w = lista.itemWidget(selezionati[0])
            if w:
                w.setProperty("selected", True)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
            self.view.btn_apri.setEnabled(True)
        else:
            self.view.btn_apri.setEnabled(False)

    # ─── Aggiunta ─────────────────────────────────────────────────────────────

    def apri_form_aggiunta(self):
        dialog = DialogNuovoSpecializzando(self.view)
        if dialog.exec():
            self.model.crea_nuovo_specializzando(dialog.get_dati())
            self.aggiorna_lista()

    # ─── Modifica ─────────────────────────────────────────────────────────────

    def modifica_specializzando(self):
        if not self._spec_corrente:
            return
        dialog = DialogNuovoSpecializzando(self.view, spec_dati=self._spec_corrente)
        if dialog.exec():
            spec_aggiornato = self.model.aggiorna_specializzando(
                self._spec_corrente["id"], dialog.get_dati()
            )
            if spec_aggiornato:
                self._spec_corrente = spec_aggiornato
                self.view.imposta_dettaglio(spec_aggiornato)
            self.aggiorna_lista()

    # ─── Eliminazione ─────────────────────────────────────────────────────────

    def elimina_specializzando(self):
        if not self._spec_corrente:
            return
        nome_display = (
            f"{self._spec_corrente.get('cognome','').upper()} "
            f"{self._spec_corrente.get('nome','')}"
        )
        risposta = QMessageBox.question(
            self.view,
            "Conferma Eliminazione",
            f"Vuoi eliminare definitivamente il libretto di {nome_display}?\n\n"
            "Questa operazione non è reversibile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if risposta == QMessageBox.StandardButton.Yes:
            self.model.elimina_specializzando(self._spec_corrente["id"])
            self._spec_corrente = None
            self.aggiorna_lista()
            self.torna_ad_anagrafica()
