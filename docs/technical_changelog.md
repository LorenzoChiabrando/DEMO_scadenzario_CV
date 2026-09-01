# Changelog tecnico

## 2026-08-27 - Feedback Valdossi

- Rinominata la presentazione delle reperibilità senza cambiare le chiavi JSON legacy e
  uniformati i colori con `Tipo Guardia`.
- Aggiunte viste mensili compatte, dettaglio al click ed esportazione PDF mese/settimana per
  Scadenziario e Sale operatorie.
- Rimossa la visualizzazione del training score, chiarita la persistenza di orario/sede del
  giorno e aggiunto il livello formativo `Intermediate`.
- Chiariti identificativo paziente, data dell'operazione, specializzandi e data di inserimento
  nel dettaglio delle Sale operatorie.
- Resi strutturati codice e descrizione diagnosi e sostituita la durata a scelta fissa con un
  campo numerico in minuti.
- Separati stato, data di inserimento e data di intervento del paziente; lo stato pianificato
  dipende soltanto dai collegamenti stabili presenti nelle bozze operatorie.
- Introdotto un adapter CSV per template nativi e TrackCare con riconoscimento di separatore,
  encoding, alias delle colonne, priorità e riepilogo dei valori mancanti.
- Aggiunti test di regressione per parsing CSV, stato paziente, diagnosi strutturata, livello
  intermedio, controlli delle viste ed esportazione PDF.
