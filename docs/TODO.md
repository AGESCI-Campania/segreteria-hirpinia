# Todolist delle cose da implementare/correggere durante il beta testing

Questo è un elenco di modifiche da fare aggiornato man mano che vanno avanti i test, Quelli marcati con [x] sono comletati

## Primo beta test

- [x] Implementare interfaccia AllowlistGruppo accessibile da segreteria e RdZ e SuperAdmin
- [x] Aggiungere filtro ricerca e ordinamento colonne premendo sulle stesse, per ogni tabella del sito
- [x] Implementare breadcrumb per tutte le pagine dopo login (deve contenere almeno home)
- [x] Eliminare Home in alto a destra nelle pagine, non più necessario
- [x] In http://127.0.0.1:8000/anagrafica/export/ Gruppo e Unità e Livello FoCa (da scrivere Livello Fo.Ca., Fo.Ca. va scritto sempre così) deve essere un menu a tendina con i valori attivi (gruppo) o presenti nelle anagrafiche (Unità, Livello Fo.Ca.)

## Interfaccia

- [x] Tab anagrafica:
  - [x] "Importa anagrafica soci" e "Importa autorizzazioni" devono essere raggruppate in un unica voce "Importa" che rimanda ad una view che permette di eseguire entrambe i flussi e mostra un riepilogo degli import (quello che ora viene visualizzatop dalle due view separatamente)
  - [x] "Cerca capo censito altrove" diventa "Cerca capo in servizio esterno al gruppo" e va spostato come pulsante in "Esporta anagrafica"
  - [x] "Registro esportazioni" va spostato come pulsante in "Esporta anagrafica"
  - [x] "Esporta anagrafica" diventa "Visualizza anagrafica"
  - [x] "Assegna incarico" va spostato nella nuova funzione "Gestione gruppo" (vedi dettagli successivamente)
  - [x] "Allowlist gruppi" va spostato nel tab "Amministrazione"
- [x] Tab "Contributi" diventa "Moduli"
  - [x] "Campagne Fo.Ca." Diventa "Contributo Fo.Ca."
- [x] In home, dopo login, nei tab vanno inseriti gli stessi bsicon e/o md icon che sono nel menu della sidebar
- [ ] In http://127.0.0.1:8000/impostazioni/template-email/ deve essere presente un pulsante per tornare a impostazioni (http://127.0.0.1:8000/impostazioni/). Inoltre manca il breadcrumb
- [ ] Nel breadcrumb "Home" deve essere sempre rappresentato con l'icona della home prima del testo Home

## Altre modifiche
- [x] Assegna incarico manuale deve funzionare per mettendo di selezionare un socio con ricerca con autocompletion per nome, cognome, gruppo, o codice socio. A questo vien poi assegnato una funzione (e se è capo unità o aiuto capo unità anche una branca, che altriumenti non è obbligatoria). Come gruppo in cui si presta servizio di default viene selzionato quello di appartenza del capo, ma si può selezionare eventualmente un altro se incarico esterno in altro gruppo.

## Nuove funzionalità
- [x] "Gestione gruppo"
  - [x] Contiene i dati del gruppo e permette di modificarli, Email di default (quella da import su dominio campania.agesci.it) non può essere modificata, ma si può inserire una email alternativa. Il capogruppo o un suo delegato può inserire e\o modificare:
    - la mail alternativa
    - indirizzo della sede del gruppo
    - Codice fiscale del gruppo
  - [x] Segreteria, RdZ e superadmin possono fare lo stesso, ma per tutti i gruppi. Accedono cliccando sul nome di un gruppo nell'anagrafica "Gruppi", tramite la voce "Gestione Gruppo" vedono il gruppo COM ZONA HIRPINIA
  - [x] Deve avere una subview per vedere tutti gli incarichi di quel gruppo
- [x] In "impostazioni" deve essere possibile impostare il template delle mail inviate dalla piattaforma nelle varie funzioni. I template devono essere impostabili con tag per inserimento di variabili e con html (rich text editor)
- [x] in inviti nuovo (http://127.0.0.1:8000/accounts/inviti/nuovo/) va corretto il breadcrumb e deve servire solo ad invitare un utente per i ruoli di amministratore e segreteria (RdZ può solo delegare)
- [x] Inviti va spostato come pulsante in ruoli (definisce un nuovo ruolo tramite invito)
- [x] In "Ruoli" va aggiunta una funzionalità per aggiungere ruoli direttamente (senza invito) ad utenti già attivi sulla piattaforma
- [x] Per gli utenti che ne hanno il permesso deve essere visibile un elenco degli altri utenti che posso inpersonificare con un pulsante per impersonare quell'utente di fianco al nome

## Modulo contributo Fo.Ca.
- [ ] in inserisci partecipazione:
  - [ ] "Codice socio" deve essere un campo di ricerca con autocompletamento tra i soci del gruppo (se CG) o di tutta la zona se il ruolo prevede la possibilità di inserire anche partecipazioni di altri gruppi. Sarà poi visualizzato come "[Nome] [Cognome] ([Codice Socio])"
  - [ ] "Tipologia partecipazione" deve prevedere anche "Altro (specificare)", in questo caso compare subito sotto un altro field che sarà obbligatorio
  - [ ] "Data fine" deve essere successiva a "Data inizio" (al massimo stessa data, non precedente)
  - [ ] "Luogo" non è obbligatorio
  - [ ] "Quota versata" è obbligatorio, ma con le tipologie CCG, CFM e CFA viene inzializzato a 51,50€
  - [ ] Serve un campo "Note" dove inserire note libere