# DEMO_scadenzario_CV

## Requirements

You need Python 3.10 or higher and pip, which comes bundled with Python by default.

On Ubuntu / Debian, make sure `python3-venv` is available:
```bash
sudo apt install python3-venv
```

On Windows, download Python from [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"** during installation. `venv` is already included.

## Quick start

The `scripts/` folder contains launchers that take care of everything automatically. The first time you run them, they set up the virtual environment and install the dependencies. From the second run onwards, they just start the application.

### Linux / macOS

Make the script executable once:
```bash
chmod +x scripts/run.sh
```

Then run it:
```bash
bash scripts/run.sh
```

The first time you will see the installation progress in the terminal. The application opens automatically when it finishes.

### Windows

Open the project folder in File Explorer and double-click `scripts\run.bat`. A terminal window will appear showing the installation progress. The application opens automatically when it finishes.

If Windows shows a security warning, click **"Run anyway"**.

## Manual setup (development)

**Linux / macOS**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

If script execution is blocked, run this once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then:
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Windows (Command Prompt)**
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Daily use

Activate the virtual environment, then start the application.

**Linux / macOS**
```bash
source venv/bin/activate
python3 main.py
```

**Windows (PowerShell)**
```powershell
venv\Scripts\Activate.ps1
python main.py
```

**Windows (Command Prompt)**
```cmd
venv\Scripts\activate.bat
python main.py
```

When the environment is active, the prompt shows the `(venv)` prefix.

## Deactivate the virtual environment

```bash
deactivate
```

Works on all platforms. The `venv/` folder can be deleted and recreated at any time by repeating the setup steps.

## Calendari, PDF e importazione pazienti

Lo Scadenziario mantiene nei JSON le chiavi legacy `Reparto I` e `Reparto II`, ma le mostra
come **I Reperibilità** e **II Reperibilità**. I pulsanti **Dettaglio** e **Intero mese**
permettono rispettivamente di scorrere celle ampie o di adattare tutti i giorni alla finestra.
Nella vista mensile gli specializzandi sono mostrati tramite iniziali; un click sulla cella
visualizza il nome completo. Le Sale operatorie offrono lo stesso riepilogo mensile in sola
lettura, mentre gli spostamenti e la pianificazione restano disponibili nella vista settimanale.

Il giro visite ha una cella per ciascun giorno lavorativo. Le cinque celle condividono
l'assegnazione della settimana: la prima scelta riempie tutte le celle, mentre sostituzione
e cancellazione richiedono conferma. Il controllo dei conflitti considera tutti i giorni da
lunedì a venerdì, anche a cavallo di due mesi. Una settimana che comprende un mese convalidato
mantiene l'assegnazione già confermata. Nei libretti il riepilogo di orario e sede è in sola
lettura; la conferma delle singole attività resta disponibile. Le sale operatorie mostrano
i codici degli interventi e conservano l'ID paziente nei dati, senza visualizzarlo nelle schede.

Il comando **Esporta PDF** crea un documento da stampa per l'intero mese o una singola
settimana. I mesi usano A3 orizzontale, le settimane A4 orizzontale; la generazione usa Qt e
non richiede dipendenze aggiuntive.

L'inserimento multiplo riconosce sia i template nativi sia i CSV TrackCare, inclusi separatore
`;`, BOM, codifica UTF-8/Windows-1252 e intestazioni accentate o degradate come `Priorit�`
e `Prioritï¿½`. Il mapping è implementato in [`patient_csv.py`](src/importers/patient_csv.py):

| Campo applicativo | Colonna TrackCare | Trattamento |
| --- | --- | --- |
| `nome` | `Nome` | Obbligatorio. |
| `cognome` | `Cognome` | Obbligatorio. |
| `codice_diagnosi`, `descrizione_diagnosi` | `Diagnosi ICD9` | Separa il codice finale fra parentesi; un valore composto dal solo codice va nel campo codice. |
| `codice_intervento` | `codice intervento` | Mantiene codici e posizioni anche per più interventi. |
| `descrizione_intervento` | `Intervento/procedura ICD9` | Separa le procedure con `;` e ricava gli eventuali codici finali mancanti. |
| `tipo_chirurgia` | Assente | `Da classificare`; campo descrittivo, non richiesto dal solver. |
| `complessita` | Assente | `Da classificare`; da completare prima della pianificazione. |
| `urgenza` | `Priorità`, `urgenza` e varianti di codifica | A → Alta, B → Media, C/D → Bassa; valori assenti o sconosciuti → `Da classificare`, con avviso. |
| `durata_intervento` | Opzionale: `durata`, `durata_minuti`, `durata_intervento` | Minuti interi positivi; se assente propone 90 minuti e mostra un avviso. |

Il file originale non viene copiato nel repository.

Anche **Aggiungi Paziente** usa i dati disponibili nel CSV: nome, cognome, diagnosi,
codice/descrizione dell'intervento e priorità. Solo nome e cognome sono obbligatori,
come nel bulk. La diagnosi può essere descrittiva, contenere il codice fra parentesi
o essere composta dal solo codice; il campo codice separato resta facoltativo.

**Mostra dati aggiuntivi (facoltativi)** permette di impostare durata, tipo chirurgia,
complessità, stato e note. Tipo chirurgia, complessità e urgenza non specificati restano
`Da classificare`, senza attribuire automaticamente una classe clinica. La durata iniziale
è una stima di 90 minuti totali, ripartita fra le procedure e segnalata nel modulo.
La scheda nasce `In Attesa`. Quando la si riapre in modifica, i dati aggiuntivi sono visibili
e mantengono i valori salvati. Per il planner restano necessari i dati richiesti dal modello,
fra cui complessità e limite di attesa per i pazienti `I'`.

L'anteprima permette di digitare la durata totale. Se il CSV contiene più durate (`60;90`),
le conserva separatamente; una modifica del totale lo ripartisce fra le procedure, mantenendo
la somma esatta. Righe con nomi mancanti o durate non valide bloccano l'importazione fino alla
correzione. Un caricamento fallito svuota la precedente anteprima. I pazienti importati con
urgenza da classificare restano visibili in lista e hanno `attesa_massima_giorni: null`.
Modificando l'urgenza nella scheda, il data manager aggiorna l'attesa standard a 30, 60 o 180
giorni; conserva un eventuale limite personalizzato già presente.

Il paziente conserva separatamente `codice_diagnosi` e `descrizione_diagnosi`, mantenendo anche
il campo legacy `diagnosi` per compatibilità. **Data inserimento** e **Data intervento** sono
visualizzate separatamente: lo stato `Pianificato` viene derivato esclusivamente da un
collegamento esplicito tramite `id_paziente` in una bozza delle sale operatorie.

## Dati demo aggiornati

[`reset_demo_data.py`](scripts/reset_demo_data.py) genera 20 pazienti sintetici, 8 specializzandi,
tre mesi di calendari (precedente, corrente e successivo) e tre CSV di prova. Include attività
completate nella settimana precedente, operazioni pianificate vicine alla data di riferimento
e pazienti in attesa. Gli scadenzari corrente e futuro sono in bozza, così possono essere
modificati e poi convalidati prima di usare il planner.

Le anagrafiche sintetiche riprendono i nomi della demo precedente, fra cui Pippo VerdeScuro,
Mandringo Bello, Spirulina Alga e BAZZ JAZZ. Pino Silvestre completa il posto mancante
nell'anagrafica degli specializzandi. Questi nomi sono inclusi nel generatore, così un nuovo
reset non li sostituisce con etichette numerate. ID, riferimenti e date sono indipendenti dai nomi.

A programma chiuso, dalla radice del progetto:

```bash
venv/bin/python3 scripts/reset_demo_data.py --reference-date 2026-09-08
venv/bin/python3 scripts/reset_demo_data.py --reference-date 2026-09-08 --write
```

Senza `--reference-date`, lo script usa la data odierna. La prima riga mostra soltanto
un'anteprima; `--write` sostituisce `mock_data` e sposta i dati precedenti in
`.demo_backups/<data>-<identificativo>/`, esclusa da Git. Per ripristinarli, chiudere
l'applicazione, conservare a parte la cartella `mock_data` corrente e rimettere il backup
al suo posto. Il reset è un comando manuale e non viene eseguito all'avvio dell'applicazione.

## Ottimizzazione Pyomo + HiGHS

Il repository include ora un layer indipendente dalla GUI che implementa il MILP settimanale
per la selezione dei pazienti e l'assegnazione degli specializzandi descritta nel paper di
riferimento. Nel codice rimane il nome inglese `Resident`, usato dal paper, ma indica sempre uno
specializzando. Con *roster* si intende la turnazione giornaliera `Sala Op. I`/`Sala Op. II`.
Il costruttore scientifico riproduce letteralmente le equazioni stampate; changeover e turnazione
giornaliera sono estensioni applicative separate. La formulazione è implementata in
[`model.py`](src/optimization/model.py); i controlli sui dati sono in
[`validation.py`](src/optimization/validation.py).

`highspy` distribuisce i binding e la libreria HiGHS: non è necessario installare un eseguibile
separato con Homebrew. Usa Python 3.10 o superiore:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Verifica che il solver sia disponibile ed esegui l'istanza sintetica:

```bash
python -c "from src.optimization import HighsSolver; assert HighsSolver.is_available()"
python -m src.optimization.example
```

Test e lint del nuovo layer:

```bash
python -m pytest
python -m ruff check .
```

### Pianificazione dai dati della piattaforma

Il planner può leggere i JSON applicativi reali, risolvere una settimana dal lunedì al venerdì
su due sale fisiche (`OR-1` e `OR-2`) e produrre lo stesso formato letto dalla schermata delle
sale operatorie. `Sala Op. I` alimenta il roster di `OR-1`, mentre `Sala Op. II` alimenta quello
di `OR-2`; le due sale hanno capacità e sequenze orarie indipendenti. Lo scadenzario del
mese deve essere prima completato e `CONVALIDATO`: la convalida è rifiutata finché manca
l'assegnazione di `Sala Op. I` o `Sala Op. II` in almeno un giorno lavorativo, oppure se la stessa
persona copre entrambe. Se la settimana è a cavallo di due mesi, devono essere convalidati
entrambi gli scadenzari mensili.

I JSON usano il blocco versionato `modello_ottimizzazione` per rappresentare le categorie
`I'`/`I''`/`I'''`, l'attesa massima, le compatibilità paziente-specializzando e le capacità
sala-giorno. Le qualifiche per complessità sono invece inferite dal `livello`
`Junior`/`Intermediate`/`Senior`
del libretto. Per controllare o applicare la migrazione idempotente:

```bash
python scripts/migrate_platform_json_v1.py --project-root .
python scripts/migrate_platform_json_v1.py --project-root . --write
```

Il flusso ordinario è disponibile direttamente nella GUI:

1. compilare e convalidare lo scadenzario mensile;
2. aprire **Sale Operatorie → Pianificazione** e selezionare la settimana;
3. premere **Pianifica settimana**;
4. attendere il messaggio conclusivo oppure usare **Annulla pianificazione**.

Pyomo costruisce il modello e `highspy` esegue HiGHS in un worker separato, quindi la finestra
non viene bloccata. Durante il calcolo sono sospesi navigazione e modifica del piano. La
cancellazione è cooperativa e non salva risultati parziali. Se HiGHS restituisce una soluzione
ammissibile, il servizio la valida, aggiorna atomicamente i JSON delle sale operatorie, invalida
la cache applicativa e ricarica subito la tabella. La rigenerazione di una bozza esistente
richiede una conferma esplicita; settimane o mesi delle sale operatorie già `CONVALIDATO` non
sono mai sovrascritti.

Lo stesso flusso resta disponibile dalla CLI, utile per sviluppo e diagnostica. Per eseguire un
dry-run, che non modifica alcun file:

```bash
python -m src.optimization.platform_cli --week 2026-09-14 --project-root .
```

La scrittura è esplicita. `--overwrite` è necessario se la settimana in stato `BOZZA` contiene
già operazioni; una settimana o un mese `CONVALIDATO` viene sempre rifiutato:

```bash
python -m src.optimization.platform_cli \
  --week 2026-09-14 \
  --project-root . \
  --write \
  --overwrite
```

Il comando risolve e valida tutto in memoria prima della persistenza, crea un backup privato e
sostituisce atomicamente soltanto i cinque giorni interessati. L'output del comando contiene
solo conteggi e diagnostica aggregata, non dati clinici. Le regole di mapping adottate sono
implementate in [`platform_mapping.py`](src/optimization/platform_mapping.py).
