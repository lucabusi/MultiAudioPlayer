# Come modificare posizione e dimensione dei pulsanti

I layout dei widget si trovano in `LAYOUT_SPECS`, nel file `MultiPlayer/fluid_layout.py`.

Immagina un **foglio a quadretti** con sopra degli **adesivi**: ogni adesivo è un pulsante.

## Il foglio

Il foglio è `ref`. In `COMPACT` è largo 626 quadretti e alto 99:

```python
'ref': (626, 99)
```

## L'adesivo

Ogni adesivo ha quattro numeri:

```python
'btnPlay': (44, 10, 80, 25)
```

| Numero | Domanda | Qui |
|---|---|---|
| 1° | Quanti quadretti dal bordo **sinistro**? | 44 |
| 2° | Quanti quadretti dal bordo **in alto**? | 10 |
| 3° | Quanto è **largo**? | 80 |
| 4° | Quanto è **alto**? | 25 |

```text
          44 quadretti
      ◄────────────────►┌──────────┐ ▲
                        │   PLAY   │ │ alto 25
                        └──────────┘ ▼
                        ◄── 80 ────►
```

## Cosa puoi fare

Cambia un numero alla volta:

| Vuoi che il pulsante... | Cosa fai | Esempio |
|---|---|---|
| vada a **destra** | aumenti il 1° | `(64, 10, 80, 25)` |
| vada a **sinistra** | diminuisci il 1° | `(24, 10, 80, 25)` |
| vada **giù** | aumenti il 2° | `(44, 20, 80, 25)` |
| vada **su** | diminuisci il 2° | `(44, 5, 80, 25)` |
| sia più **largo** | aumenti il 3° | `(44, 10, 100, 25)` |
| sia più **alto** | aumenti il 4° | `(44, 10, 80, 30)` |

Attenzione: per scendere il numero **aumenta**, perché si conta partendo dall'alto.

## Le due regole

**1. Gli adesivi non si mettono uno sopra l'altro.** Se allarghi un adesivo, quello accanto va spostato. Per sapere dove finisce un adesivo, fai 1° numero + 3° numero:

```python
'btnPlay': (44, 10, 100, 25),   # finisce a 44 + 100 = 144
'btnStop': (150, 10, 48, 25),   # parte a 150: 6 quadretti di spazio
```

**2. Gli adesivi devono restare dentro il foglio.** Se finiscono oltre il bordo, si esce dal widget.

## La magia

Il foglio è **elastico**. Quando la finestra si allarga, il foglio si allarga e tutti gli adesivi crescono insieme, restando nello stesso ordine. Tu li sistemi una volta sola e al resto pensa il programma.

**Eccezione: `TOUCH`.** Ha anche la tabella `narrow`, con posizione e larghezza `(x, larghezza)` dei controlli quando il widget è largo quanto `min`. Tra `min` e `ref` gli adesivi passano gradualmente da `narrow` a `items`. Se in `TOUCH` sposti o allarghi un controllo in `items`, controlla anche la sua riga in `narrow`.

## Come provare

1. Apri `MultiPlayer/fluid_layout.py` e trova il layout, per esempio `'COMPACT'`.
2. Cambia un numero e salva.
3. Avvia `python MultiPlayer/MultiPlayer.py` e guarda il risultato.
4. Lancia `pytest tests/`: controlla, tra le altre cose, se gli adesivi si sovrappongono o escono dal foglio.
