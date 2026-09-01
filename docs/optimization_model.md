# Modello di pianificazione chirurgica con Pyomo e HiGHS

## Ambito

Il package espone due costruttori distinti. `build_paper_model` implementa letteralmente il MILP
settimanale stampato nel paper: selezione dei pazienti, assegnazione a una sessione e assegnazione
di al massimo uno specializzando compatibile. `build_platform_model` conserva tutte le equazioni
del paper e aggiunge, in famiglie nominate separatamente, le regole operative richieste dai JSON
dell'applicazione. Un mapper deterministico ordina poi gli interventi scelti e calcola gli orari;
non esistono variabili decisionali di sequenza intra-giornaliera.

Il PDF è riservato e rimane esterno al repository. Questo documento contiene soltanto la
formalizzazione necessaria a comprendere e manutenere il codice.

Nel paper e nei nomi dell'API inglese, `Resident`/`resident` indica uno **specializzando**. Il
termine `roster` indica invece la **turnazione giornaliera** degli specializzandi assegnati a
`Sala Op. I` e `Sala Op. II`; non indica l'intero organico del reparto.

## Corrispondenza tra paper e codice

| Notazione | Significato | Componente Pyomo |
|---|---|---|
| `I'` | pazienti opzionali in waiting list | `WAITING_PATIENTS` |
| `I'' ∪ I'''` | pazienti obbligatori e ripianificati | `REQUIRED_PATIENTS` |
| `K`, `T`, `L` | sale, giorni e livelli | `ROOMS`, `DAYS`, `LEVELS` |
| `J` | specializzandi (`Resident` nell'API) | `RESIDENTS` |
| `p_i` | durata in minuti | `duration_minutes[i]` |
| `u_i = w_i / w_i_max` | urgenza normalizzata | `urgency[i]` |
| `v_kt` | capacità della sessione | `capacity_minutes[k,t]` |
| `h_jl` | abilitazione dello specializzando al livello | `resident_level_qualification[j,l]` |
| `s_ij` | abilitazione dello specializzando sul paziente | `patient_resident_qualification[i,j]` |
| `X_ikt` | paziente assegnato alla sessione | `x[i,k,t]` |
| `Y_ijkt` | specializzando assegnato all'intervento | `y[i,j,k,t]` |
| `ε_ikt` | intervento senza specializzando | `unassigned[i,k,t]` |
| `Z_f` | minimo workload fra specializzandi | `fairness_floor` |

`X` è definita sull'intero prodotto `I × K × T` e `Y` sull'intero prodotto `I × J × K × T`,
come nel paper. Le `Y` incompatibili esistono e sono portate a zero dal vincolo (`1d`).
`unassigned` e `fairness_floor` sono variabili intere non negative, senza upper bound aggiuntivi.

## Vincoli implementati

1. Ogni paziente in waiting list può essere pianificato al massimo una volta (`1a`).
2. Ogni paziente obbligatorio o ripianificato deve essere pianificato esattamente una volta (`1b`).
3. La somma delle durate non può superare i minuti disponibili nella sessione (`1c`).
4. Uno specializzando può essere assegnato solo se il paziente è pianificato e la coppia è
   compatibile (`1d`).
5. Ogni intervento pianificato ha uno specializzando oppure attiva `unassigned` (`1e`).
6. Ogni intervento ha al massimo uno specializzando (`1f`).
7. `fairness_floor` è minore o uguale al conteggio assegnato a ogni residente, escludendo i
   pazienti ripianificati (`1g`).

Le condizioni (`1d`), (`1e`) e (`1f`) restano tre famiglie distinte. In particolare (`1e`) è la
disuguaglianza `sum_j Y_ijkt + unassigned_ikt >= X_ikt`, non un'uguaglianza rafforzata. Questo
preserva anche i punti ammissibili ma subottimali nei quali `unassigned` supera il minimo; la
penalità negativa nell'obiettivo lo porta al minimo in una soluzione ottima.

## Obiettivo

Il preset del paper massimizza:

```text
C * treatment_efficiency + fairness_floor - unassigned_count
```

dove `C` è il massimo tempo di attesa ammesso fra i pazienti in waiting list. Il costruttore
letterale usa obbligatoriamente i coefficienti `C`, `+1`, `-1` dell'equazione (`6`). I coefficienti
configurabili tramite `ObjectiveWeights`, compreso `fairness=0` usato nell'esperimento del paper,
sono accettati soltanto dal costruttore esteso.

L'equazione (`2`) è costruita su tutto `I`, esattamente come stampata. Il testo definisce però
`u_i` soltanto per `I'`: per risolvere questa ambiguità interna senza inventare priorità, il
parametro esiste per tutti i pazienti ed è posto a zero su `I'' ∪ I'''`.

## Changeover

La sezione risultati usa 11 minuti fra due interventi, ma il vincolo (`1c`) stampato non li
include. Per questo `build_paper_model` richiede `changeover_minutes=0`. Il costruttore piattaforma
mantiene (`1c`) invariato e aggiunge la famiglia `platform_changeover_capacity`:

```text
sum_i (p_i + changeover) * X_ikt
    <= v_kt + changeover
```

Per una sessione non vuota con `n` interventi la formula conta esattamente `n-1` changeover; per
una sessione vuota la maggiorazione a destra è irrilevante. Non serve quindi una variabile
binaria di attivazione e l'estensione non è confusa con l'equazione del modello scientifico.

## Assunzioni e punti aperti

- Il paper non contiene disponibilità giornaliera degli specializzandi. `build_paper_model` la
  rifiuta esplicitamente; `build_platform_model` aggiunge
  `platform_resident_availability` usando due sessioni fisiche distinte: `OR-1`, associata a
  `Sala Op. I`, e `OR-2`, associata a `Sala Op. II`. La convalida vieta allo stesso
  specializzando di coprire entrambe le sale nello stesso giorno; ogni sala costruisce quindi una
  sequenza indipendente.
- La continuità dello stesso residente dopo una cancellazione è descritta ma non formulata.
- Le cancellazioni del 10/20/30% avvengono dopo l'ottimizzazione e non fanno parte del MILP.
- Non esistono variabili di sequenza, orario di inizio, overtime o deadline hard.
- La fairness è il minimo conteggio settimanale grezzo: non usa durata, valore formativo,
  storico o dispersione oltre il minimo.
- La frase del paper sul caso con meno interventi/residenti è invertita: il floor può restare
  zero quando gli interventi compatibili sono meno dei residenti, non quando sono di più.
- `C=max(w_i_max)` è un peso empirico, non una garanzia lessicografica. Per uso clinico i pesi
  vanno calibrati e sottoposti a sensitivity analysis.
- `u_i=w_i/w_i_max` non è limitata superiormente: un paziente oltre scadenza ha urgenza maggiore
  di uno. Questo segue la formula, ma la regola clinica deve essere confermata.
- Nei JSON applicativi `h_jl` è inferito dal campo `livello` del libretto: uno specializzando
  `Junior` è abilitato a `Bassa`, `Media` e `Alta`, un `Intermediate` a `Media` e `Alta`, mentre
  un `Senior` è abilitato ad `Alta`. Il livello intermedio conserva la policy annidata già
  adottata dall'applicazione; la corrispondenza clinica resta un'assunzione da confermare.
  Questa assunzione è isolata in `PlatformPlanningPolicy`; la formulazione Pyomo continua a
  ricevere e usare il parametro binario `resident_level_qualification[j,l]` del paper.
- La penalità unitaria può rendere conveniente selezionare un paziente urgente senza
  specializzando. Il builder letterale conserva il coefficiente unitario; quello esteso permette
  analisi di sensibilità con `unassigned_penalty`, che deve restare strettamente positiva.
- “Primarily assigned” è trasformato dal paper in compatibilità hard 0/1. Se la regola reale è
  una preferenza, servirà una variabile di deviazione soft separata.

## Mapping dei dati della piattaforma

L'integrazione è separata dalla formulazione Pyomo:

- `platform_io.py` legge i cataloghi pazienti e libretti, oltre ai turni dello scadenzario;
- `platform_mapping.py` traduce lo snapshot in oggetti di dominio e riconverte il risultato nel
  formato delle sale operatorie;
- `platform_service.py` usa `build_platform_model` e orchestra load, solve, validazione e
  persistenza opzionale;
- `platform_cli.py` espone lo stesso flusso per sviluppo e diagnostica;
- `platform_planning_worker.py` esegue il servizio in un thread Qt separato e comunica con il
  controller esclusivamente tramite segnali.

Il pulsante di pianificazione della GUI non costruisce direttamente componenti Pyomo e non
manipola i JSON. Il controller fotografa il lunedì selezionato e l'eventuale autorizzazione a
sovrascrivere la bozza, quindi affida al worker l'intero flusso `load → build → solve → map →
persist`. Durante l'esecuzione navigazione, convalida e modifica della tabella sono disabilitate;
il pulsante diventa il comando di annullamento.

Il blocco JSON versionato `modello_ottimizzazione` e la policy applicativa adottano queste regole:

| Dato piattaforma | Interpretazione nel modello |
|---|---|
| Stato paziente `In Attesa` | record candidato al modello |
| `categoria_paper` | partizione esplicita `I'`, `I''` o `I'''` |
| `attesa_massima_giorni` | `w_i_max` individuale per i pazienti `I'` |
| `specializzandi_abilitati` | matrice paziente-specializzando `s_ij` |
| `livello` (`Junior`/`Intermediate`/`Senior`) nel libretto | matrice `h_jl`, inferita dalla policy applicativa |
| `Sala Op. I` | specializzando disponibile esclusivamente nella sessione `OR-1` |
| `Sala Op. II` | specializzando disponibile esclusivamente nella sessione `OR-2` |
| `capacita_minuti` / `capacita_sessioni` | capacità `v_kt`, default 600 e override sala-giorno |
| Limite righe GUI | al massimo 12 interventi per ciascuna sala, 24 nel giorno |

I pazienti importati da sorgenti prive di complessità possono essere conservati come
`Da classificare`, ma il mapper li rifiuta prima di costruire il modello: nessuna compatibilità
formativa viene inferita silenziosamente da un dato clinico mancante.

I cataloghi applicativi sono stati migrati allo schema v1. I dati preesistenti non permettevano di
ricostruire storicamente categorie obbligatorie o ripianificate, quindi sono stati conservati
come `I'`; il formato e il mapper accettano però tutte e tre le categorie. Analogamente, per non
restringere silenziosamente le soluzioni precedenti, i record migrati inizializzano
`specializzandi_abilitati` con tutti gli specializzandi attivi. Le liste possono poi essere
ristrette per rappresentare `s_ij=0` sulle coppie non abilitate. `h_jl` non viene duplicato nei
libretti: è derivato da `livello` secondo la policy descritta sopra. Il chirurgo non ha una
sorgente affidabile e resta vuoto.

Il mapper assegna orari consecutivi e indipendenti dalle 08:00 in ciascuna sala e inserisce
esattamente 11 minuti fra due operazioni della stessa sala. Ogni record persistito contiene sala
fisica, identificativo stabile dello specializzando, nome di visualizzazione e ruolo `OR I`/`OR
II`. Gli interventi già presenti in altre settimane `BOZZA` sono esclusi dai candidati; le
settimane `CONVALIDATO` non vengono sovrascritte.

### Schema JSON v1

Ogni paziente contiene:

```json
"modello_ottimizzazione": {
    "versione_schema": 1,
    "categoria_paper": "I'",
    "attesa_massima_giorni": 30,
    "specializzandi_abilitati": ["SP001", "SP002"]
}
```

I libretti conservano il solo `livello` già gestito dalla piattaforma; non richiedono un blocco
di ottimizzazione. Ogni scadenzario definisce `OR-1` e `OR-2`, la riga turno associata, il ruolo
e la capacità. `capacita_sessioni` permette override puntuali per data e sala. Gli schemi formali
dei blocchi paziente e scadenzario sono in `schema/*_ottimizzazione.schema.json`. La migrazione è
idempotente, rimuove dai libretti il precedente campo derivabile e può essere verificata prima
della scrittura:

```bash
python scripts/migrate_platform_json_v1.py --project-root .
python scripts/migrate_platform_json_v1.py --project-root . --write
```

### Precondizioni dello scadenzario

La pianificazione richiede che ogni mese dello scadenzario toccato dai cinque giorni sia
esattamente nello stato `CONVALIDATO`. Una settimana a cavallo del mese viene quindi accettata
soltanto se entrambi i mesi sorgente sono convalidati. Prima di consentire la convalida mensile,
la GUI controlla che tutti i giorni dal lunedì al venerdì abbiano sia `Sala Op. I` sia
`Sala Op. II` e che siano assegnati a persone diverse; il loader ripete il controllo e verifica
anche che ogni nominativo sia risolvibile nel catalogo degli specializzandi.

Lo stato dello scadenzario viene controllato una prima volta durante il caricamento e una seconda
volta sotto lock, immediatamente prima della scrittura. Un mese riportato in bozza mentre il
solver è in esecuzione impedisce quindi il commit. Catalogo pazienti, libretti e scadenzario
restano input di sola lettura.

### Commit e aggiornamento della GUI

La persistenza rilegge sotto lock tutti i mesi delle sale operatorie interessati e rifiuta il
commit se una settimana o uno di tali mesi è `CONVALIDATO`. Una bozza che contiene già
interventi è sostituita soltanto dopo consenso esplicito. Il servizio crea backup con permessi
privati, scrive file temporanei e usa `os.replace` per la sostituzione atomica dei singoli JSON;
nel caso a cavallo di mese il commit coordinato avviene sotto lo stesso lock e prevede rollback
in caso di errore. Metadati, giorni estranei e chiavi sconosciute restano invariati.

Solo dopo un commit riuscito il controller invalida la cache di `DataManagerSaleOperatorie` e
ricarica la settimana, così la tabella mostra il piano appena prodotto senza riavviare
l'applicazione. Un errore, un modello infeasible o un annullamento lasciano invece invariati i
file e il piano precedentemente visualizzato.

## API minima

```python
from src.optimization import HighsSolver, build_paper_model

built = build_paper_model(scheduling_input)
result = HighsSolver().solve(built)

if result.has_solution:
    for surgery in result.schedule:
        print(surgery)
```

Per i dati applicativi, il servizio usa invece `build_platform_model`; non è possibile attivare
per errore changeover o turnazione dentro `build_paper_model`, perché tali input sono rifiutati.

Il package non carica mai valori delle variabili quando HiGHS dichiara il modello infeasible o
non dispone di un incumbent. L'integrazione piattaforma persiste soltanto un risultato feasible
già estratto e validato; un risultato infeasible o privo di incumbent lascia i JSON invariati.
Gli stati normalizzati distinguono ottimo, incumbent feasible, infeasible, unbounded, limite
raggiunto senza soluzione, interruzione e errore; la termination condition originale resta nel
risultato per la diagnostica.

Il `time_limit` limita la fase interna di HiGHS, non il tempo totale necessario a Pyomo per
costruire e trasferire il modello. La GUI aggiunge perciò una cancellazione cooperativa
end-to-end: un `Event` viene verificato ai confini tra le fasi del servizio e dai callback di
interruzione di `highspy` durante il solve. Uno stato HiGHS di interruzione non viene trattato
come incumbent utilizzabile e il servizio ricontrolla il token prima della persistenza. Anche la
chiusura dell'applicazione richiede l'interruzione del worker attivo prima di terminare Qt.

## Verifica locale

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
python -m src.optimization.example
```

L'esempio usa esclusivamente identificativi sintetici.

## Changelog tecnico

- **2026-08-26** — introdotto lo schema JSON `modello_ottimizzazione` v1 per categorie
  `I'`/`I''`/`I'''`, `w_i_max`, `s_ij` e `v_kt`; `h_jl` viene inferito da `livello` tramite una
  policy esplicita, senza duplicarlo nei libretti. Migrate in modo idempotente le schede
  esistenti. Sostituita la singola sessione applicativa con due sale fisiche `OR-1`/`OR-2`, con
  capacità, roster, sequenze e changeover indipendenti. La GUI mostra la sala sul record e le
  modifiche manuali rispettano il limite di ciascuna sessione. La CLI diagnostica è mantenuta.

- **2026-08-06** — aggiunti disponibilità per sessione, mapper dei dati applicativi,
  orchestrazione Pyomo/HiGHS, persistenza atomica con backup e campi per l'assegnazione
  individuale dello specializzando; mantenuto il calcolo fuori dal thread GUI.
- **2026-08-19** — ripristinata la corrispondenza letterale con (`1a`)-(`1g`): `Y` cartesiana,
  parametri `h` e `s` espliciti, `epsilon` intera non negativa e famiglie (`1d`)-(`1f`) separate.
  Changeover, turnazione giornaliera e limite righe sono ora estensioni nominate del solo builder
  piattaforma; eliminata la variabile ausiliaria non necessaria del changeover e preservata
  l'identità visiva con il progetto di riferimento.
- **2026-08-19, integrazione GUI** — collegato **Pianifica settimana** al servizio
  Pyomo/HiGHS tramite worker Qt, con annullamento cooperativo e arresto controllato alla chiusura.
  Resa obbligatoria la convalida completa dello scadenzario, inclusi entrambi i mesi per settimane
  a cavallo; aggiunti ricontrollo pre-commit, protezione dei mesi di sala convalidati, persistenza
  coordinata e refresh esplicito della cache dopo il salvataggio. Il lock usa `flock` su
  macOS/Linux e `msvcrt` su Windows, mantenendo compatibili entrambi gli script di avvio.
