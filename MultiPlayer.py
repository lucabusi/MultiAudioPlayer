import sys
import os
import vlc
import time
import numpy as np
import matplotlib.pyplot as plt
import librosa
import urllib.parse
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QScrollArea, QCheckBox,QApplication, QMainWindow, QMenuBar, QAction, QVBoxLayout, QWidget, QLabel, QProgressBar, QFileDialog, QPushButton, QGridLayout, QFrame, QStatusBar, QSlider
from tempfile import NamedTemporaryFile
from PyQt5.QtGui import QIcon, QImage


# Definisci la classe principale dell'app
class MultiThreadedApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.instance = vlc.Instance('--no-xlib')  # Inizializza l'istanza VLC senza supporto GUI
        self.media_players = []
        self.init_ui()

    def init_ui(self):
        # Configura la finestra principale
        self.setWindowTitle('MultiPlayer Eden Edition')
        self.setGeometry(100, 100, 800, 600)

        # Crea la barra dei menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        
        open_action = QAction('Apri MP3', self)
        open_action.triggered.connect(self.open_mp3)
        file_menu.addAction(open_action)

        exit_action = QAction('Esci', self)
        exit_action.triggered.connect(self.close)  # Collega l'azione alla chiusura dell'app
        file_menu.addAction(exit_action)

        # Crea il layout principale
        main_layout = QVBoxLayout()

        # Utilizza uno scroll area per aggiungere una scrollbar verticale
        scroll_area = QScrollArea()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setWidgetResizable(True)

        # Crea un widget per contenere il layout principale
        scroll_widget = QWidget()
        scroll_widget.setLayout(main_layout)

        # Imposta il widget all'interno dell'area di scorrimento
        scroll_area.setWidget(scroll_widget)

        # Imposta il widget di scorrimento come contenuto centrale della finestra
        self.setCentralWidget(scroll_area)

        # Crea un layout per i frame dei file
        self.file_frames = QVBoxLayout()
        main_layout.addLayout(self.file_frames)
        self.file_frames.addStretch(0)

        
        # Crea la barra di stato
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Lista dei file MP3 caricati
        self.loaded_mp3_files = []

        # Crea un timer per aggiornare le barre di avanzamento
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress_bars)
        self.timer.start(100)

    def open_mp3(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly

        file_dialog = QFileDialog()
        file_dialog.setNameFilter("File MP3 (*.mp3)")
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_names, _ = file_dialog.getOpenFileNames(self, "Apri File MP3", "", "File MP3 (*.mp3)", options=options)

        for idx, file_name in enumerate(file_names):  # Aggiungi l'indice all'iterazione
            # Crea un nuovo frame per ogni file
            file_frame = QFrame()
            # Imposta lo stile del frame con l'ombreggiatura leggera
            frame_style = "QFrame { background-color: #4A5662; border: 1px solid #5D6D7E; border-radius: 5px; }"
            file_frame.setStyleSheet(frame_style)

            file_frame_layout = QGridLayout()  # Utilizza un layout a griglia per i pulsanti

            label = QLabel(f"File: {os.path.basename(file_name)}")
            waveform_image_path_normal, waveform_image_path_normalized = self.generate_waveform(file_name)
            progress_bar = self.create_progress_bar(waveform_image_path_normal)
            button_play_pause = QPushButton()
            button_play_pause.setIcon(QIcon.fromTheme("media-playback-start"))  # Aggiungi un'icona di play
            button_pause = QPushButton()
            button_pause.setIcon(QIcon.fromTheme("media-playback-pause"))  # Aggiungi un'icona di play
            button_stop = QPushButton()
            button_stop.setIcon(QIcon.fromTheme("media-playback-stop"))  # Aggiungi un'icona di stop
            button_waveform = QPushButton("Forma d'onda")
            button_remove = QPushButton()
            button_remove.setIcon(QIcon.fromTheme("user-trash"))  # Aggiungi un'icona del cestino
 
            # Crea uno slider per il controllo del volume
            volume_slider = QSlider(Qt.Vertical)
            volume_slider.setMinimum(0)
            volume_slider.setMaximum(99)
            volume_slider.setValue(99)  # Imposta il valore iniziale del volume

            volume_slider.valueChanged.connect(lambda value, idx=idx: self.update_volume(idx, value))  # Passa l'indice esplicitamente))
            
            # Crea una QLabel per visualizzare il valore del volume
            volume_label = QLabel("99")  # Imposta il valore iniziale sulla label
            volume_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)  # Allinea il testo a destra

            # Imposta il volume predefinito al 100%
            media = self.instance.media_new(file_name)
            media_player = self.instance.media_player_new()
            media_player.set_media(media)
            media_player.audio_set_volume(99)
            
            file_frame_layout.addWidget(button_remove, 0, 0)
            file_frame_layout.addWidget(label, 0, 1, 1, 4)
            file_frame_layout.addWidget(button_play_pause, 0, 5)
            file_frame_layout.addWidget(button_stop, 0, 6)
            # file_frame_layout.addWidget(button_waveform, 0, 5)
            self.view_normalizedWave_checkbox = QCheckBox("Norm")
            file_frame_layout.addWidget(self.view_normalizedWave_checkbox, 0, 7)
            file_frame_layout.addWidget(volume_slider, 0, 8, 3, 1)  # Aggiungi lo slider del volume
            file_frame_layout.addWidget(volume_label, 0, 8)  # Aggiungi la label del volume
            file_frame_layout.addWidget(progress_bar, 1, 0, 1, 8)
            
#            file_frame_layout.addWidget(button_pause, 2, 1)
            
            file_frame.setLayout(file_frame_layout)
            self.file_frames.addWidget(file_frame)


            # Aggiungi il file alla lista dei file caricati
            self.loaded_mp3_files.append({
                'frame': file_frame,
                'progress_bar': progress_bar,
                'button_play_pause': button_play_pause,
                'button_pause': button_pause,
                'button_stop': button_stop,
                'button_waveform': button_waveform,
                'button_remove': button_remove,
                'file_name': file_name,
                'media_player': media_player,
                'waveform_image_path_normal': waveform_image_path_normal,
                'waveform_image_path_normalized': waveform_image_path_normalized,
                'volume_slider': volume_slider,  # Aggiungi lo slider del volume all'elenco
                'volume_label': volume_label,  # Aggiungi la label del volume all'elenco
                'volume_value': 99  # Imposta il valore iniziale del volume              
            })

            # Collega i pulsanti alle rispettive funzioni
            button_play_pause.clicked.connect(lambda _, idx=len(self.loaded_mp3_files)-1: self.play_pause_file(idx))
            button_pause.clicked.connect(lambda _, idx=len(self.loaded_mp3_files)-1: self.pause_file(idx))
            button_stop.clicked.connect(lambda _, idx=len(self.loaded_mp3_files)-1: self.stop_file(idx))
            # button_waveform.clicked.connect(lambda _, idx=len(self.loaded_mp3_files)-1: self.show_waveform(idx))
            button_remove.clicked.connect(lambda _, idx=len(self.loaded_mp3_files)-1: self.remove_file(idx))
            self.view_normalizedWave_checkbox.toggled.connect(lambda checked, idx=len(self.loaded_mp3_files)-1: self.show_waveform(idx, checked))

            
            self.debug(f"Loaded volume media: {media_player.audio_get_volume()}")
            print(vars(media_player))

    def remove_file(self, idx):
        file_info = self.loaded_mp3_files[idx]
        if file_info['media_player']:
            file_info['media_player'].release()
        if file_info['waveform_image_path_normalized']:
            os.remove(file_info['waveform_image_path_normalized'])
        self.file_frames.removeWidget(file_info['frame'])
        file_info['frame'].deleteLater()
        del self.loaded_mp3_files[idx]

    def create_progress_bar(self, waveform_image_path_normal):
        progress_bar_style = f"""
        QProgressBar {{
            border: 1px solid grey;
            background-color: transparent;
            border-image: url({waveform_image_path_normal}) 0 0 0 0 stretch stretch;
            background-repeat: no-repeat;
            background-position: left center;
            text-align: center;
        }}
        QProgressBar::chunk {{
            border: 1px solid grey;
            background-color: rgba(0,255,0,100);
        }}
        """

        progress_bar = QProgressBar()
        progress_bar.setFixedHeight(48)
        progress_bar.setStyleSheet(progress_bar_style)
        return progress_bar

#    def get_waveform_background_size(self, image_path):
#        image = QImage(image_path)
#        return f"{image.width()}px {image.height()}px"

    def play_pause_file(self, idx):
        file_info = self.loaded_mp3_files[idx]
        media_player = file_info['media_player']
        self.debug(f"play/pause before: {media_player.get_state()}")
        self.debug(f"play/pause before: {media_player}")
        if media_player:             
            if media_player.is_playing(): # media_player.get_state() == vlc.State.Playing:
                media_player.pause()
                time.sleep(0.2)
                file_info['button_play_pause'].setIcon(QIcon.fromTheme("media-playback-start"))
                file_info['button_play_pause'].setStyleSheet("background-color: red;")  # Imposta lo stile di lampeggiamento
            else:
                media_player.play()
                time.sleep(0.2)
                file_info['button_play_pause'].setIcon(QIcon.fromTheme("media-playback-pause"))
                file_info['button_play_pause'].setStyleSheet("background-color: blue;")  # Rimuovi lo stile di lampeggiamento
        self.debug(f"play/pause after: {media_player.get_state()}")


    def pause_file(self, idx):
        file_info = self.loaded_mp3_files[idx]
        if file_info['media_player']:
            file_info['media_player'].pause()

    def stop_file(self, idx):
        file_info = self.loaded_mp3_files[idx]
        if file_info['media_player']:
            file_info['media_player'].stop()
#            file_info['media_player'].vlm_stop_media(file_info['file_name'])
            file_info['progress_bar'].setValue(0)  # Reimposta il valore della progress bar
        self.status_bar.showMessage("Riproduzione interrotta")
        file_info['button_play_pause'].setStyleSheet("background-color: green;") 
        file_info['button_play_pause'].setIcon(QIcon.fromTheme("media-playback-start"))
        self.debug(f" Stop Media_player: {file_info['media_player']}")


    def update_progress_bars(self):
        for file_info in self.loaded_mp3_files:
            if file_info['media_player']:
                position = file_info['media_player'].get_time()
                duration = file_info['media_player'].get_length()
                if duration > 0:
                    progress = int((position / duration) * 100)  # Converti il valore in intero
                    file_info['progress_bar'].setValue(progress)


    def generate_waveform(self, file_name):
        audio, _ = librosa.load(file_name, sr=None, mono=True)
        duration = len(audio) / 44100  # Durata in secondi

        # Generate Normalized Waveform image
        plt.figure(figsize=(10, 0.5))
        plt.box(False)
        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)

        plt.plot(np.linspace(0, duration, len(audio)), librosa.util.normalize(audio), color='r', linewidth=0.1)
        waveform_image_path_normalized = f'{os.path.basename(file_name)}_normalized.jpg'
        plt.savefig(waveform_image_path_normalized, format='jpeg', dpi=150)
        plt.close()   # Chiude la figura per evitare sovrapposizioni

        # Generate Normal Waveform image
        plt.figure(figsize=(10, 0.5))
        plt.box(False)
        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)

        plt.plot(np.linspace(0, duration, len(audio)), audio, color='b', linewidth=0.1)
        waveform_image_path_normal = f'{os.path.basename(file_name)}_normal.jpg'
        plt.savefig(waveform_image_path_normal, format='jpeg', dpi=150)
        plt.close()

        return waveform_image_path_normal, waveform_image_path_normalized

#    def show_waveform(self, idx, checked):
#        file_info = self.loaded_mp3_files[idx]
#        if file_info['waveform_image_path_normalized']:
#            if checked:
#                # Visualizza l'immagine con il visualizzatore predefinito su Linux
#                os.system(f'xdg-open {file_info["waveform_image_path_normalized"]}')
#            else:
#                # Fai qualcos'altro se il checkbox non è selezionato
#                os.system(f'xdg-open {file_info["waveform_image_path_normalized"]}')
#                pass

    def update_volume(self, idx, value):
        file_info = self.loaded_mp3_files[idx]
        if file_info['media_player']:
            file_info['media_player'].audio_set_volume(value)
            file_info['volume_label'].setText(str(value))  # Aggiorna il testo della label del volume

        self.debug(f"{idx} - volume media: {file_info['media_player'].audio_get_volume()} - Nuovo Valore: {value}")
                
        self.debug(f"Updated Volume value: {file_info['file_name']} {value}")
#        self.debug(f" Update Media_player{file_info['media_player']}")
        print(vars(file_info['media_player']))

    def debug(self, message):
        print("[DEBUG]:", message)


# Esegui l'app
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MultiThreadedApp()
    window.show()
    sys.exit(app.exec_())
