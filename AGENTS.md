# AGENTS.md

## Scopo del progetto

Questa applicazione PySide6 gestisce scadenze, turni e pianificazione delle sale
operatorie di un reparto di chirurgia. Il layer di ottimizzazione deve tradurre il
modello matematico di riferimento in un modello Pyomo risolvibile con HiGHS,
senza accoppiare la formulazione alla GUI o ai file JSON usati per la demo.

Queste istruzioni si applicano all'intero repository.

## Riservatezza e dati sanitari

- Il paper di riferimento e qualsiasi file marcato come riservato o "DA NON
  CONDIVIDERE" non devono essere copiati nel repository, pubblicati, allegati a
  issue o inclusi nei log.
- Non inserire dati personali o sanitari reali in sorgenti, fixture, snapshot,
  messaggi di errore o output del solver. Usare solo identificativi sintetici e
  dataset minimali anonimizzati.
- Non stampare payload completi provenienti dalla GUI o dai JSON applicativi.
  Nei log usare conteggi, identificativi tecnici e messaggi sintetici.

## Versione Python e dipendenze

- Supportare Python 3.10 o superiore, coerentemente con il progetto esistente.
- Dichiarare esplicitamente le dipendenze runtime e di sviluppo. Per
  l'ottimizzazione usare `pyomo` e `highspy`; non richiedere un eseguibile HiGHS
  installato separatamente quando l'interfaccia Python è disponibile.
- Non aggiungere dipendenze senza una motivazione concreta. Mantenere versioni e
  vincoli compatibili documentati e riproducibili.
- Non importare PySide6 nel package di ottimizzazione.

## Architettura del layer di ottimizzazione

Separare almeno queste responsabilità:

1. **Dati di dominio**: dataclass o modelli tipizzati, immutabili quando
   possibile, con identificativi stabili e unità di misura esplicite.
2. **Validazione**: controlli fail-fast prima di costruire il modello (insiemi
   vuoti, riferimenti inesistenti, durate negative, disponibilità incoerenti,
   limiti incompatibili).
3. **Formulazione**: funzione pura che riceve dati validati e restituisce un
   `ConcreteModel`; nessun accesso a file, GUI, orologio o stato globale.
4. **Solver**: adapter dedicato per HiGHS, configurazione tipizzata, controllo di
   disponibilità, time limit, mip gap, logging e interpretazione robusta dello
   stato di terminazione.
5. **Risultati**: estrazione in oggetti di dominio indipendenti da Pyomo, con
   obiettivo, stato, bound/gap quando disponibili e assegnazioni ordinate in
   modo deterministico.
6. **Integrazione**: mapper separati tra JSON/UI e oggetti di dominio. La GUI non
   deve manipolare direttamente variabili o componenti Pyomo.

Non nascondere regole di business in coefficienti numerici senza nome. Centralizzare
pesi, capacità, orizzonti temporali e unità in configurazioni esplicite.

## Regole di modellazione matematica

- Conservare una corrispondenza leggibile tra paper e codice: documentare ogni
  insieme, parametro, variabile, termine dell'obiettivo e famiglia di vincoli.
- Usare nomi descrittivi in inglese nel codice; riportare nella docstring la
  notazione del paper e, quando utile, il numero dell'equazione.
- Evitare indici cartesiani inutili: costruire insiemi sparsi di combinazioni
  ammissibili prima di creare variabili e vincoli.
- Specificare domini e bounds di tutte le variabili. Usare coefficienti interi o
  scalati quando riduce problemi numerici senza alterare la formulazione.
- Non usare costanti "big-M" arbitrarie. Derivare il valore più stretto possibile
  dai dati e testarne la validità; preferire formulazioni più forti quando sono
  disponibili.
- Stabilire una convenzione unica per il tempo (preferibilmente minuti interi da
  un'origine documentata) e non confrontare direttamente float non scalati.
- Rendere deterministici ordinamento degli insiemi, fixture e output. Impostare
  un seed solo dove esiste davvero una componente stocastica.
- Distinguere vincoli hard da preferenze soft. Ogni violazione soft deve avere
  una variabile di scostamento e un peso configurabile e spiegato.
- Non estrarre valori delle variabili se il risultato non contiene una soluzione
  ammissibile. Gestire esplicitamente ottimo, feasible con limite, infeasible,
  unbounded, errore e interruzione.

## Convenzioni Python

- Aggiungere `from __future__ import annotations` ai nuovi moduli.
- Usare type hints completi sulle API pubbliche e dataclass con `slots=True`
  quando appropriate.
- Preferire funzioni piccole, pure e facilmente testabili. Evitare singleton,
  mutable default arguments, import con wildcard e side effect all'import.
- Le API pubbliche devono avere docstring concise che descrivono input, output,
  unità, eccezioni e assunzioni non ovvie.
- Sollevare eccezioni specifiche del package con messaggi operativi; non catturare
  `Exception` se non al boundary applicativo, dove va preservata la causa.
- Usare `logging`, non `print`, nel codice di libreria. Non configurare il root
  logger dentro il package.
- Usare `pathlib.Path` per i path nuovi e UTF-8 per file di testo e JSON.
- Mantenere i nuovi moduli conformi a Ruff e formattabili con Black (line length
  100), senza imporre una riscrittura meccanica dei file legacy non correlati.

## Test e verifica

- Ogni modifica al modello richiede test unitari su validazione, numero/indice
  dei componenti Pyomo, segno dei coefficienti e risultato di piccole istanze
  verificabili a mano.
- Aggiungere almeno un test end-to-end che costruisca e risolva un'istanza
  sintetica con HiGHS, marcandolo chiaramente se il solver non è disponibile.
- Per ogni vincolo importante includere almeno un caso che lo renda attivo e un
  caso che ne violerebbe la regola se il vincolo fosse assente.
- Includere casi infeasible e controllare che l'applicazione non presenti una
  soluzione parziale come valida.
- Confrontare numeri floating point con tolleranze esplicite.
- Prima della consegna eseguire, quando disponibili:

  ```bash
  python -m compileall src tests
  python -m pytest
  python -m ruff check .
  ```

- Eseguire anche uno smoke solve con HiGHS e verificare stato di terminazione,
  ammissibilità della soluzione e coerenza dell'obiettivo.

## Integrazione con l'applicazione esistente

- Preservare il comportamento della GUI finché il nuovo planner non è collegato
  esplicitamente e coperto da test.
- Non sovrascrivere un piano convalidato. La scrittura di un nuovo piano deve
  avvenire solo dopo soluzione ammissibile e validazione dell'output.
- Separare calcolo e persistenza: risolvere in memoria, validare il risultato e
  solo dopo aggiornare i file JSON tramite i data manager.
- Le operazioni di pianificazione potenzialmente lunghe non devono bloccare il
  thread UI; l'integrazione finale dovrà prevedere un worker e cancellazione
  cooperativa.
- Mantenere compatibilità dei file JSON oppure introdurre una migrazione
  esplicita e versionata.

## Documentazione e tracciabilità

- Mantenere un documento di formulazione vicino al codice con tabella di
  corrispondenza paper-codice, assunzioni adottate e punti ancora da confermare.
- Documentare setup, comando di esecuzione, configurazione solver, formato input
  e interpretazione dell'output con un esempio sintetico riproducibile.
- Se il paper è ambiguo, non inventare silenziosamente una regola: implementare
  l'interpretazione più conservativa, isolarla in configurazione e registrarla
  tra le assunzioni aperte.
- Ogni cambio a obiettivo o vincoli deve aggiornare formulazione, test e changelog
  tecnico nella stessa modifica.

## Limiti delle modifiche

- Non modificare file legacy non correlati solo per uniformarne lo stile.
- Non correggere dati demo o bug preesistenti salvo quando impediscono di
  verificare il nuovo layer; in tal caso documentare separatamente il problema.
- Non includere artefatti temporanei, file del solver, virtual environment,
  cache, PDF riservati o output contenenti dati sensibili nel repository.
