import sys
import os
import vlc
import time
import numpy as np
import matplotlib.pyplot as plt
import librosa
import urllib.parse
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import QDoubleSpinBox, QScrollArea,QApplication, QMainWindow, QMenuBar, QAction, QVBoxLayout, QWidget, QLabel, QProgressBar, QFileDialog, QPushButton, QGridLayout, QFrame, QStatusBar, QSlider
from tempfile import NamedTemporaryFile
from PyQt5.QtGui import QIcon, QImage

class FaderThread(QThread):
    fade_finished = pyqtSignal()

    def __init__(self, media_player, start_volume, end_volume, duration):
        super().__init__()
        self.media_player = media_player
        self.start_volume = start_volume
        self.end_volume = end_volume
        self.duration = duration
        #self.idx = idx

    def run(self):
        steps = int(self.duration * 10)
        volume_increment = (self.end_volume - self.start_volume) / steps

        for _ in range(steps):
            self.start_volume += volume_increment
            # Apply the volume change to the correct media player using self.idx
            self.media_player.audio_set_volume(int(self.start_volume))
            time.sleep(0.1)
        # Set the final volume for the correct media player
        self.media_player.audio_set_volume(int(self.end_volume))
        self.fade_finished.emit()


#    def __init__(self, media_player, start_volume, end_volume, duration):
#        super().__init__()
#        self.media_player = media_player
#        self.start_volume = start_volume
#        self.end_volume = end_volume
#        self.duration = duration
#
#    def run(self):
#        steps = int(self.duration * 10)
#        volume_increment = (self.end_volume - self.start_volume) / steps
#
#        for _ in range(steps):
#            self.start_volume += volume_increment
#            self.media_player.audio_set_volume(int(self.start_volume))
#            self.debug(f"Change volume of:{self.media_player }, ToVolume:{file_info['volume_slider'].value()}, Durata:{fade_duration}")
#
#            time.sleep(0.1)
#
#        self.media_player.audio_set_volume(int(self.end_volume))
#        self.fade_finished.emit()


class MP3File:
    def __init__(self, parent, file_name):
        self.parent = parent
        self.file_name = file_name
        self.media_player = self.parent.instance.media_player_new()
        self.media = self.parent.instance.media_new(file_name)
        self.media_player.set_media(self.media)
        self.media_player.audio_set_volume(99)
        self.waveform_image_path = self.generate_waveform()
        self.fileDuration = self.get_duration()
        self.elapsedTime = 0
        self.remainingTime = self.fileDuration
        self.actualVolume = 100
        self.fader_threads = []
        self.ui_elements = {}


#        self.volume_slider = self.create_volume_slider()
#        self.volume_label = QLabel("99")
#        self.volume_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
#        self.volume_value = 99
#
#    def create_volume_slider(self):
#        volume_slider = QSlider(Qt.Vertical)
#        volume_slider.setMinimum(0)
#        volume_slider.setMaximum(99)
#        volume_slider.setValue(99)
#        volume_slider.valueChanged.connect(self.update_volume)
#        return volume_slider

    def remove_file(self):
        self.media_player.stop()
        self.media_player.release()
        self.instance.release()


    def generate_waveform(self):
        audio, _ = librosa.load(self.file_name, sr=None, mono=True)
        duration = len(audio) / 44100

        plt.figure(figsize=(10, 0.5))
        plt.box(False)
        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)
        plt.plot(np.linspace(0, duration, len(audio)), audio, color='b', linewidth=0.1)
        waveform_image_path = f'{os.path.basename(self.file_name)}_normal.jpg'
        plt.savefig(waveform_image_path, format='jpeg', dpi=150)
        plt.close()

        return waveform_image_path


    def update_volume(self):
        newVolume = self.ui_elements["volume_slider"].value()
        self.media_player.audio_set_volume(newVolume)
#        self.volume_label.setText(str(value))
        self.parent.debug(f"{self.file_name} - volume media: {self.media_player.audio_get_volume()} - Nuovo Valore: {newVolume}")

    def play_pause_file(self):
#        mp3_file = self.mp3_files[idx]
#        media_player = mp3_file.media_player
        self.debug(f"play/pause before: {self.media_player.get_state()}")
        self.debug(f"play/pause fileName: {self.file_name}")
        if self.media_player:
            if self.media_player.is_playing():
                self.media_player.pause()
                time.sleep(0.2)
                self.ui_elements["button_play_pause"].setIcon(QIcon.fromTheme("media-playback-start"))
                self.ui_elements["button_play_pause"].setStyleSheet("background-color: red;")
            else:
                self.media_player.play()
                time.sleep(0.2)
                self.ui_elements["button_play_pause"].setIcon(QIcon.fromTheme("media-playback-pause"))
                self.ui_elements["button_play_pause"].setStyleSheet("background-color: blue;")
        self.debug(f"play/pause after: {self.media_player.get_state()}")
        
            
    def stop_file(self):
#        mp3_file = self.loaded_mp3_files[idx]
        self.debug(f"stop fileName: {self.file_name}")
        if self.media_player:
            self.media_player.stop()
#            self.parent.progress_bar.setValue(0)
        self.parent.status_bar.showMessage("Riproduzione interrotta")
        self.ui_elements["button_play_pause"].setStyleSheet("background-color: green;")
        self.ui_elements["button_play_pause"].setIcon(QIcon.fromTheme("media-playback-start"))
        self.debug(f" Stop Media_player: {self.media_player}")

    def fade_in(self):
        startVolume = 0
        endVolume = self.ui_elements["volume_slider"].value()
        self.media_player.audio_set_volume(startVolume)
#        self.media_player.audio_get_volume()
#        self.media_player.play()
        self.play_pause_file()
        self.volume_fade(startVolume, endVolume, self.ui_elements["fade_duration_spinbox"].value())

    def fade_in_thread(self):
#        mp3_file = self.loaded_mp3_files[idx]
#        media_players = [mp3_file.media_player]
#        self.debug(f"FadeIn of:{mp3_file.file_name}, ToVolume:{mp3_file.volume_slider.value()}, Durata:{fade_duration}")

        if self.ui_elements["fade_duration_spinbox"].value() > 0: 
            startVolume = 0
            endVolume = self.ui_elements["volume_slider"].value()
            self.media_player.audio_set_volume(startVolume)
            self.play_pause_file()
            
            fadeIn_thread = FaderThread(self.media_player, startVolume, endVolume, self.ui_elements["fade_duration_spinbox"].value())
            fadeIn_thread.fade_finished.connect(self.fade_finished)
            fadeIn_thread.start()
            self.fader_threads.append(fadeIn_thread)
        else:
            self.play_pause_file()
        

    def fade_out_thread(self):
#        mp3_file = self.loaded_mp3_files[idx]
#        media_players = [mp3_file.media_player]
        
        if self.ui_elements["fade_duration_spinbox"].value() > 0:
            startVolume = self.ui_elements["volume_slider"].value()
            endVolume = 0
    
            fadeOut_thread = FaderThread(self.media_player, startVolume, endVolume, self.ui_elements["fade_duration_spinbox"].value())
            fadeOut_thread.fade_finished.connect(self.fade_finished)
            fadeOut_thread.start()
            self.fader_threads.append(fadeOut_thread)
        self.stop_file()

        
    def fade_out(self):
        startVolume = self.media_player.audio_get_volume()
        endVolume = 0   # self.ui_elements["volume_slider"].value()
#        self.media_player.audio_set_volume(startVolume)
#        self.media_player.audio_get_volume()
        self.volume_fade(startVolume, endVolume, self.ui_elements["fade_duration_spinbox"].value())
#        self.media_player.stop()
        self.stop_file()



    def volume_fade(self, start_volume, end_volume, fade_duration):
        if 0 <= start_volume <= 100 and 0 <= end_volume <= 100:
            step = 1 if start_volume < end_volume else -1
            for volume in range(start_volume, end_volume + step, step):
                self.media_player.audio_set_volume(volume)
                time.sleep(fade_duration / abs(end_volume - start_volume))
    
    def get_duration(self):
        return self.media.get_duration() / 1000  # Duration in seconds



    def debug(self, message):
        print("[DEBUG]:", message)

    def fade_finished(self):
        finished_threads = [thread for thread in self.fader_threads if not thread.isRunning()]
        for thread in finished_threads:
            thread.quit()
            thread.wait()
            self.fader_threads.remove(thread)



# Definisci la classe principale dell'app
class MultiThreadedApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.instance = vlc.Instance('--no-xlib')  # Inizializza l'istanza VLC senza supporto GUI
        self.media_players = []
        self.fader_threads = []  # Store FaderThread instances
        self.mp3_files = []
        self.init_ui()

    def init_ui(self):
        # Configura la finestra principale
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        
        open_action = QAction('Apri MP3', self)
        open_action.triggered.connect(self.open_mp3)
        file_menu.addAction(open_action)

        exit_action = QAction('Esci', self)
        exit_action.triggered.connect(self.close)  # Collega l'azione alla chiusura dell'app
        file_menu.addAction(exit_action)

        # Crea il layout principale
        self.setWindowTitle('MultiPlayer Eden Edition')
        self.setGeometry(100, 100, 700, 200)

        # Crea la barra dei menu
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

        for idx, file_name in enumerate(file_names):
            mp3_file = MP3File(self, file_name)
#            self.loaded_mp3_files.append(mp3_file)
#            self.create_file_frame(mp3_file, idx)
            self.mp3_files.append(mp3_file)  # Aggiungi l'oggetto MP3File a una lista o dizionario
            self.create_file_frame(mp3_file, idx)


    def create_file_frame(self, mp3_file, idx):
        ui_elements = {}
        file_frame = QFrame()
        # Imposta lo stile del frame con l'ombreggiatura leggera
        frame_style = "QFrame { background-color: #4A5662; border: 1px solid #5D6D7E; border-radius: 5px; }"
        file_frame.setStyleSheet(frame_style)

        file_frame_layout = QGridLayout()  # Utilizza un layout a griglia per i pulsanti

        label = QLabel(f"{os.path.basename(mp3_file.file_name)}")
        waveform_image_path = mp3_file.generate_waveform()
        progress_bar = self.create_progress_bar(waveform_image_path)
        button_play_pause = QPushButton()
        button_play_pause.setIcon(QIcon.fromTheme("media-playback-start"))  # Aggiungi un'icona di play
        button_fadeIn = QPushButton("FadeIn")
        
        fade_duration_spinbox = QDoubleSpinBox()
        fade_duration_spinbox.setRange(0, 10)  # Imposta il range dei valori consentiti
        fade_duration_spinbox.setValue(0.0)  # Imposta il valore predefinito a 0
        fade_duration_spinbox.setSingleStep(0.5) 
        
        button_fadeOut = QPushButton("FadeOut")            
        button_stop = QPushButton()
        button_stop.setIcon(QIcon.fromTheme("media-playback-stop"))  # Aggiungi un'icona di stop
        button_remove = QPushButton()
        button_remove.setIcon(QIcon.fromTheme("user-trash"))  # Aggiungi un'icona del cestino

        # Crea uno slider per il controllo del volume
        volume_slider = QSlider(Qt.Vertical)
        volume_slider.setMinimum(0)
        volume_slider.setMaximum(99)
        volume_slider.setValue(99)  # Imposta il valore iniziale del volume

        volume_slider.valueChanged.connect(mp3_file.update_volume)  # Passa l'indice esplicitamente))
#        volume_slider.valueChanged.connect(lambda value: mp3_file.update_volume(value))  # Passa l'indice esplicitamente))
        
        # Crea una QLabel per visualizzare il valore del volume
        volume_label = QLabel("99")  # Imposta il valore iniziale sulla label
        volume_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)  # Allinea il testo a destra

        # Imposta il volume predefinito al 100%
        media = self.instance.media_new(mp3_file.file_name)
        media_player = self.instance.media_player_new()
        media_player.set_media(media)
        media_player.audio_set_volume(99)
        
        file_frame_layout.addWidget(button_remove, 0, 0)
        file_frame_layout.addWidget(label, 0, 1, 1, 4)
        file_frame_layout.addWidget(button_play_pause, 0, 5)
        file_frame_layout.addWidget(button_fadeIn, 0, 6)
        file_frame_layout.addWidget(fade_duration_spinbox, 0, 7)  # Aggiungi il campo di inserimento numerico
        file_frame_layout.addWidget(button_fadeOut, 0, 8)            
        file_frame_layout.addWidget(button_stop, 0, 9)
        file_frame_layout.addWidget(volume_slider, 0, 10, 3, 1)  # Aggiungi lo slider del volume
        file_frame_layout.addWidget(volume_label, 0, 10)  # Aggiungi la label del volume
        file_frame_layout.addWidget(progress_bar, 1, 0, 1, 10)
        
        file_frame.setLayout(file_frame_layout)
        self.file_frames.addWidget(file_frame)

        ui_elements["button_play_pause"] = button_play_pause
        ui_elements["button_stop"] = button_stop
        ui_elements["progress_bar"] = progress_bar
        ui_elements["volume_slider"] = volume_slider
        ui_elements["fade_duration_spinbox"] = fade_duration_spinbox
        
        mp3_file.ui_elements = ui_elements
        
        #button_play_pause.clicked.connect(lambda _, mp3_file=mp3_file: mp3_file.play_pause_file())

        #button_play_pause.clicked.connect(mp3_file.play_pause_file(idx))  # Collega il pulsante Play a mp3_file.play()

        button_play_pause.clicked.connect(mp3_file.play_pause_file)
        button_stop.clicked.connect(mp3_file.stop_file)  # Collega il pulsante Stop a mp3_file.stop()

        button_fadeIn.clicked.connect(mp3_file.fade_in_thread)  # Esegui come prima
        button_fadeOut.clicked.connect(mp3_file.fade_out_thread)  # Esegui come prima

#        button_fadeIn.clicked.connect(lambda _, idx=idx: mp3_file.fade_in(idx, fade_duration_spinbox.value()))  # Esegui come prima
#        button_fadeOut.clicked.connect(lambda _, idx=idx: mp3_file.fade_out(idx, fade_duration_spinbox.value()))  # Esegui come prima

        self.debug(f"Loaded volume media: {mp3_file.media_player.audio_get_volume()}")
        print(vars(mp3_file.media_player))



    def remove_file(self, idx):
        mp3_file = self.loaded_mp3_files[idx]
        if mp3_file.media_player:
            mp3_file.media_player.release()
        if mp3_file.fade_thread:
            mp3_file.fade_thread.quit()
        os.remove(mp3_file.waveform_image_path)
        self.file_frames.removeWidget(mp3_file.frame)
        mp3_file.frame.deleteLater()
        del self.loaded_mp3_files[idx]  
    
    def create_progress_bar(self, waveform_image_path):
        progress_bar_style = f"""
        QProgressBar {{
            border: 1px solid grey;
            background-color: transparent;
            border-image: url({waveform_image_path}) 0 0 0 0 stretch stretch;
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
        progress_bar.setMaximum(1000)
        return progress_bar



    def update_progress_bars(self):
        for mp3_file in self.loaded_mp3_files:
            if mp3_file.media_player:
                position = mp3_file.media_player.get_time()
                duration = mp3_file.media_player.get_length()
                if duration > 0:
                    progress = (position / duration) * 1000
                    mp3_file.progress_bar.setValue(int(progress))
                    mp3_file.progress_bar.repaint()


    def debug(self, message):
        print("[DEBUG]:", message)


#    def fade_in(self, idx, fade_duration):
#        mp3_file = self.loaded_mp3_files[idx]
#        media_players = [mp3_file.media_player]
#        self.debug(f"FadeIn of:{mp3_file.file_name}, ToVolume:{mp3_file.volume_slider.value()}, Durata:{fade_duration}")
#        fade_thread = FaderThread(idx, media_players, 0, mp3_file.volume_slider.value(), fade_duration)
#        fade_thread.fade_finished.connect(self.fade_finished)
#        fade_thread.start()
#        self.fader_threads.append(fade_thread)
#
#    def fade_out(self, idx, fade_duration):
#        mp3_file = self.loaded_mp3_files[idx]
#        media_players = [mp3_file.media_player]
#        fade_thread = FaderThread(idx, media_players, mp3_file.media_player.audio_get_volume(), 0, fade_duration)
#        fade_thread.fade_finished.connect(self.fade_finished)
#        fade_thread.start()
#        self.fader_threads.append(fade_thread)
#
#    def fade_finished(self):
#        finished_threads = [thread for thread in self.fader_threads if not thread.isRunning()]
#        for thread in finished_threads:
#            thread.quit()
#            thread.wait()
#            self.fader_threads.remove(thread)


# Esegui l'app
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MultiThreadedApp()
    window.show()
    sys.exit(app.exec_())