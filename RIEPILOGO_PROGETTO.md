# Riepilogo del Progetto — MMSD CV Demo

**Corso:** Modelli e Metodi per il Supporto alle Decisioni (MMSD)
**Università:** Università degli Studi di Torino — A.A. 2025–2026
**Docente:** Prof. Roberto Aringhieri
**Repository branch corrente:** `incontro_3`

---

## 1. Contesto e obiettivo

Il progetto nasce dall'esigenza reale del reparto di **Chirurgia Vascolare U (Universitaria)** dell'Ospedale Molinette di Torino (A.O.U. Città della Salute e della Scienza) di gestire in modo strutturato le attività degli specializzandi.

Il sistema ha due macro-obiettivi:

1. **Organizzazione operativa mensile** — gestione del calendario dei turni degli specializzandi (guardia, sala operatoria, giro di reparto, day hospital, day surgery).
2. **Monitoraggio formativo** — generazione e consultazione del libretto individuale della carriera di ogni specializzando, con tracciamento delle procedure chirurgiche osservate ed eseguite.

Il contesto operativo di riferimento è quello osservato **dal 2018 ad oggi**: mediamente 7 specializzandi per ciclo, due sale operatorie con orari variabili per giorno della settimana.

---

## 2. Modulo 1 — Scadenzario (Calendario mensile dei turni)

### 2.1 Struttura dei turni

Ogni mese viene pianificato un calendario con le seguenti righe di attività:

| Attività        | Regole principali |
|-----------------|-------------------|
| **Guardia I Rep** | Sempre presente (118, PI o Liscia) |
| **Guardia II Rep** | Solo per guardie 118 e Pronto Intervento |
| **Sala Op. I/II** | Due specializzandi al giorno (un senior + un junior) |
| **Giro Visite** | Turno settimanale continuo (lun–ven), un solo specializzando |
| **Day Hospital** | Coppie fisse mercoledì–giovedì, solo specializzandi junior |
| **Day Surgery** | Assegnazione giornaliera |

### 2.2 Tipologie di guardia

- **118** — Emergenza territoriale; richiede sempre I e II reperibilità.
- **Pronto Intervento (PI)** — Attività ospedaliera in urgenza; richiede I e II reperibilità.
- **Liscia (L)** — Attività routinaria; solo I reperibilità.

Nei weekend la guardia è coperta dallo stesso specializzando (o coppia) per entrambi i giorni consecutivi.

### 2.3 Modalità di visualizzazione implementate

La vista è strutturata su tre card di accesso:

- **Storico** — Consultazione in sola lettura dei mesi passati e convalidati.
- **Mese Corrente** — Visualizzazione e modifica del mese in corso, con tracciamento delle variazioni dell'eseguito.
- **Pianificazione** — Bozza e inserimento turni per i mesi futuri.

Una volta selezionata la modalità, si accede a una tabella scorrevole con colonne per ogni giorno del mese e righe per ogni tipologia di turno. Il mese può essere **convalidato definitivamente** tramite apposito bottone.

### 2.4 Persistenza dati

I dati di ogni mese sono salvati in file JSON nella directory `mock_data/scadenzario/` con naming `YYYY-MM.json`. Ogni file contiene:

```json
{
  "metadata": { "stato": "BOZZA" | "STAMPA" },
  "turni": {
    "YYYY-MM-DD": {
      "Tipo Guardia": "...",
      "Reparto I": "...",
      ...
    }
  }
}
```

Il `DataManager` gestisce lettura, scrittura e una cache in memoria per evitare accessi ripetuti al disco.

---

## 3. Modulo 2 — Sale Operatorie

### 3.1 Orari di apertura delle sale

| Giorno | Orario |
|--------|--------|
| Lunedì | Solo mattina (08:00–14:00) |
| Martedì | Intera giornata (08:00–19:00) |
| Mercoledì | Solo mattina; in caso di trapianti la sala non è disponibile |
| Giovedì | Intera giornata |
| Venerdì | Alternato: una settimana intera giornata, la successiva solo mattina |

### 3.2 Struttura della vista settimanale

La tabella delle sale operatorie mostra, per ogni giorno della settimana, i seguenti slot temporali:

- Specializzandi assegnati al giorno
- Slot 08:00–10:00
- Slot 10:00–12:00
- Slot 14:00–16:00
- Slot 16:00–18:00

Ogni slot contiene le informazioni del paziente programmato: diagnosi, interventi (codice ICD-9-CM + descrizione testuale), primo chirurgo, secondo chirurgo (opzionale), specializzandi assegnati con anno di corso e note.

### 3.3 Modalità disponibili

Analogamente allo scadenzario, la vista espone tre card:
- **Storico** — sola lettura.
- **Settimana Corrente** — pianificazione proposta.
- **Pianificazione** — eventuali modifiche.

### 3.4 Ottimizzazione (componente futura)

Il modello di ottimizzazione settimanale dovrà assegnare i pazienti ai blocchi operativi in modo da:
- rispettare il livello di esperienza degli specializzandi previsti in sala;
- tenere conto della tipologia e complessità degli interventi;
- considerare la priorità clinica dei pazienti (urgenza A/B/C);
- massimizzare l'utilizzo della risorsa sala.

---

## 4. Modulo 3 — Libretto della Carriera

### 4.1 Scopo

Strumento di monitoraggio formativo individuale per i docenti responsabili. Permette di verificare l'omogeneità delle opportunità offerte e la varietà delle procedure osservate/eseguite da ogni specializzando nel corso dei 5 anni di specializzazione.

### 4.2 Struttura delle informazioni

Per ogni giorno del mese il libretto registra:

| Campo | Fonte |
|-------|-------|
| Mese | Calendario mensile |
| Ora inizio / fine | Calendario mensile |
| Sede (A.O.U.) | Calendario mensile |
| Tipologia attività | Calendario mensile |
| Procedure eseguite / osservate | Programmazione sale operatorie |
| Livello di responsabilità (I/II op.) | Sala operatoria |

### 4.3 Classificazione delle procedure chirurgiche

- **Chirurgia aperta**: isolamento, accesso percutaneo, endoarterectomia, sutura, sutura con patch, anastomosi, chiusura addome, chiusura sito chirurgico.
- **Chirurgia aperta – varici**: crossectomia, flebectomia.
- **Chirurgia aperta – amputazioni**: nessuna suddivisione procedurale specifica.
- **Chirurgia endovascolare**: puntura, accesso ProGlide, diagnostica angiografica, PTA, impianto stent, rilascio endoprotesi.
- **Chirurgia endovascolare – varici**: accesso endovascolare, ablazione, flebectomia.

Gli interventi vengono identificati tramite codice **ICD-9-CM**.

### 4.4 Registro delle prestazioni minime

Il percorso formativo prevede soglie minime di interventi per anno e semestre, distinte per:
- Ruolo: **I operatore** / **II operatore**
- Complessità: **Alta / Media / Bassa**
- Tipo: **Chirurgia aperta** / **Chirurgia endovascolare**

Il libretto mostra i totali progressivi e le prestazioni ancora mancanti al raggiungimento degli obiettivi normativi.

### 4.5 Funzionalità implementate nella vista

- Ricerca specializzando per nome, cognome o matricola.
- Filtro per stato: Attivi (Molinette), Attivi (Altra sede), Storico/Terminati.
- Apertura del libretto individuale con anagrafica (matricola, livello formativo, stato attuale, Training Score).
- Tabella delle attività operative (colonne: Data, Tipo Intervento, Sede, Ruolo, Complessità).

---

## 5. Modulo 4 — Pazienti in Lista d'Attesa

### 5.1 Scopo

Gestione del registro dei pazienti in attesa di intervento, necessario per alimentare la programmazione ottimizzata delle sale operatorie.

### 5.2 Funzionalità implementate

- Lista pazienti con ricerca per nome, cognome o codice intervento.
- Filtro per classe di urgenza: **Alta (A)**, **Media (B)**, **Bassa (C)**.
- Scheda dettaglio paziente con: codice intervento, classe di urgenza, data inserimento in lista, note cliniche/preparazione.
- Inserimento di nuovi pazienti tramite form dedicato.

---

## 6. Architettura software

Il progetto segue il pattern architetturale **MVC (Model – View – Controller)**:

```
src/
├── models/
│   ├── data_manager.py              # Gestione scadenzario (JSON per mese)
│   ├── data_manager_pazienti.py     # Gestione anagrafica pazienti
│   ├── data_manager_libretto.py     # Gestione libretti specializzandi
│   └── data_manager_sale_operatorie.py
├── views/
│   ├── view_sidebar.py              # Navigazione laterale
│   ├── view_scadenzario.py          # UI calendario mensile
│   ├── view_sale_operatorie.py      # UI sale operatorie settimanale
│   ├── view_libretto.py             # UI libretto della carriera
│   ├── view_pazienti.py             # UI lista pazienti
│   ├── view_nuovo_paziente.py       # Form inserimento paziente
│   ├── view_nuovo_specializzando.py # Form inserimento specializzando
│   └── components/
│       └── combo_delegate.py        # Delegate per QComboBox nelle tabelle
└── controllers/
    ├── controller_scadenzario.py
    ├── controller_pazienti.py
    ├── controller_libretto.py
    └── controller_sale_operatorie.py
```

**Stack tecnologico:**
- **Python** (runtime principale)
- **PySide6** (framework GUI Qt per Python)
- **JSON** (persistenza dati mock)

**Dati mock:**
```
mock_data/
├── scadenzario/       # File YYYY-MM.json per ogni mese
├── libretti/          # File SP00X.json per ogni specializzando
└── pazienti/          # File PZ00XX.json per ogni paziente
```

---

## 7. Stato di avanzamento (branch `incontro_3`)

| Modulo | Vista | Controller | Modello | Note |
|--------|-------|------------|---------|------|
| Scadenzario | Completata | Completato | Completato | Convalida mese implementata |
| Sale Operatorie | Completata | In sviluppo | In sviluppo | Mock data presenti |
| Libretto | Completata (parziale) | Completato | Completato | Training Score e tabella attività da completare |
| Pazienti | Completata | Completato | Completato | |

---

## 8. Sviluppi futuri

- Implementazione del **modello di ottimizzazione** per l'assegnazione pazienti–blocchi operativi (es. con Pyomo).
- Completamento della sezione **Training Score** nel libretto.
- Popolamento dinamico della **tabella attività operative** nel libretto a partire dai dati delle sale operatorie.
- Integrazione tra i moduli: dal calendario mensile → sale operatorie → libretto individuale.
- Esportazione dei dati (stampa/PDF) del calendario mensile e del libretto.
