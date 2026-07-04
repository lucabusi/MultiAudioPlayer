# Lessons

## 2026-07-04 — Volumi accoppiati tra player VLC (bug segnalato dall'utente)

**Sintomo:** file A in play a volume 50, si avvia file B a 100 → anche A sale.

**Root cause (misurata con python-vlc puro, senza codice app):** su questa
macchina con libVLC 3.0.23, l'output di default `mmdevice` applica
`audio_set_volume` al volume di **sessione audio di Windows**, condiviso da
tutti i player del processo (log VLC: "version 2 session control unavailable").
Accoppia anche con `vlc.Instance()` separate e con `waveout` (emulato su
WASAPI → stessa sessione). Non era la logica Python dell'app (stub test:
pulita). L'utente riferisce che con mmdevice i volumi sono sempre stati
indipendenti: probabile cambiamento lato VLC/driver (libvlc.dll del
2025-12-31), non risolto con certezza.

**Fix:** `player.audio_output_set('directsound')` su Windows — DirectSound
attenua per-stream → volumi realmente indipendenti (verificato:
A=8 stabile mentre B suona a 12, a livello app).

**Errori commessi durante la diagnosi (da non ripetere):**
1. **Primo fix inefficace:** `audio_output_set` chiamato PRIMA di
   `set_media()` — `set_media` RESETTA la scelta dell'output e VLC è tornato
   a mmdevice in silenzio. Verificare SEMPRE nei log verbosi
   (`--verbose=2`, riga "using audio output module ...") quale modulo è
   davvero attivo, non fidarsi del valore di ritorno di `audio_output_set`.
2. **Silenzio totale causato dai test:** `audio_set_mute(True)` con mmdevice
   muta la SESSIONE Windows, che PERSISTE tra processi → l'app dell'utente è
   rimasta muta anche dopo. MAI mutare nei test: usare volumi bassi (8-12).
   Rimedio: `audio_set_mute(False)` + volume 100 per ripristinare.
3. Il primo test A/B "mutato" ha dato letture fuorvianti (mute e volume di
   sessione si intrecciano). I test audio vanno fatti non mutati.

**Lezioni generali:**
- Le API "per-player" di un backend possono agire su stato condiviso a
  livello OS: l'indipendenza va verificata sul backend reale; lo stub non
  può rivelarlo.
- Davanti a "hai rotto X": riprodurre in harness A/B (nuovo vs vecchio,
  stesse condizioni). Qui il vecchio codice accoppiava uguale a livello raw,
  ma il confronto ha guidato la diagnosi fino al fix.
- I fix su sistemi audio vanno confermati A ORECCHIO dall'utente: "riproduce
  e la posizione avanza" non implica che esca suono.
