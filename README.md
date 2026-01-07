# MP3 Player (refactored)

Questo repository contiene la versione refactorizzata del progetto `MultiPlayer`.

File principali:
- `mainapp.py` - finestra principale e gestione layout
- `mp3widget.py` - widget per singolo file audio
- `mp3file.py` - wrapper su `vlc.MediaPlayer` (play/stop/volume/fade)
- `fadecontroller.py` - controller per fade in/out
- `utils.py` - enum e funzioni di utilità
- `MultiPlayer.py` - script di avvio

Installare dipendenze:
```bash
pip install -r requirements.txt
```

Avviare l'app (da questa cartella):
```bash
python MultiPlayer.py
```
