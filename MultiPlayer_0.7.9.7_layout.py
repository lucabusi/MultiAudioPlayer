##################################################################################
#        MultiPlayer                                                             #
#                                                                                #
# Ver: 0.6                                                                       #
# Date: 2024/08/22                                                               #
# Note:                                                                          #
# 0.5.4: basic implementation of seekbar                                         #
# 0.5.5: show total and elapsed time                                             # 
# 0.6.0: complete refactoring                                                    #
# 0.7.1: a lot of new stuff                                                      #
# 0.7.2: ProgressBar update in a different thread     (ToFix)                    #
# 0.7.6: read file_duration from vlc instead of libRosa                          #
# 0.7.7: waveform generated with librosa, waveform reflects real file amplitude  #
# 0.7.8.2: added some exception                                                  #
# 0.7.9: waveform creation with pillow library                                   #
# 0.7.9.2: merged different versions                                             #
# 0.7.9.3: added some exception handler, added Logger                            #
# 0.7.9.4: synced elapsed and remaining time labels                              #
# 0.7.9.5: some cleaning                                                         #
# 0.7.9.6: synced volume on fading function with slider                          #
# 0.7.9.7: added Save/Load project functionality                                 #
# 0.7.9.7_layout: added selectable layout functionality (alpha)                  #
# Fix: eliminare variabili e metodi non usati                                    #
##################################################################################

import sys
import vlc
import os
import librosa
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QMenu, QMessageBox, QSizePolicy, QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QGridLayout, QSlider, QFrame, QLabel, QPushButton, QProgressBar, QAction, QScrollArea, QDoubleSpinBox
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon
from PIL import Image, ImageDraw
import logging
import json
from datetime import datetime
from enum import Enum
from functools import partial


class ClickableProgressBar(QProgressBar):
    clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)   

    def mousePressEvent(self, event):
        # Calcola la posizione cliccata rispetto alla progress bar
        if event.button() == Qt.LeftButton:
            click_position = event.x()  # Ottieni la posizione del click sull'asse X
            total_width = self.width()  # Larghezza totale della progress bar

            # Calcola il nuovo valore in base alla posizione cliccata
            new_value = int(click_position / total_width * (self.maximum() - self.minimum()) + self.minimum())

            # Aggiorna il valore della progress bar
            self.setValue(new_value)
            # Emits signal for seeking
            self.clicked.emit(new_value/self.maximum())

        # Chiamare l'evento originale per garantire il comportamento standard
        super().mousePressEvent(event)



class Mp3File:
    def __init__(self, file_name):
        self.logger = logging.getLogger(__name__)

        try:
            self.player = vlc.MediaPlayer(file_name)
            self.file_name = file_name

            self.media = vlc.Media(file_name)
            self.player.set_media(self.media)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize player: {e}")
            raise
        
        # retrieve MP3 metadata        
        self.L_player_obj = self.player.get_media()
        self.L_player_obj.parse()
        self.mp3_total_duration = self.L_player_obj.get_duration()
        self.state = self.get_state()
        self.actual_volume = 100
        self.set_volume(100)

        # print(self.actual_volume)

    def get_state(self):
        self.state = self.player.get_state() 
        # print("state_init: ", state)

        return self.state

    def play_pause(self):
        try:
            if self.player.is_playing():
                self.player.pause()
            else:
                self.player.play()
        except Exception as e:
            self.logger.error(f"Play/Pause failed: {e}")
            raise

    def stop(self):
        try:
            self.player.stop()
        except Exception as e:
            self.logger.error(f"Stop failed: {e}")
            raise


    def fade_in(self, duration, end_volume):
        if not self.player.is_playing():
            self.player.play()
        
        self.fade_thread = FadeThread(duration, 0, end_volume)
        self.fade_thread.update_volume.connect(self.set_volume)
        self.fade_thread.start()

    def fade_out(self, duration, start_volume, end_volume):
        self.fade_thread = FadeThread(duration, start_volume, end_volume)
        self.fade_thread.update_volume.connect(self.set_volume)

        # Collegare il metodo stop al termine del fading
        self.fade_thread.finished.connect(self.stop)
        self.fade_thread.finished.connect(lambda: self.set_volume(start_volume))

        self.fade_thread.start()

    def set_volume(self, volume):
        self.actual_volume = volume
        self.player.audio_set_volume(self.actual_volume)

    def get_volume(self):
        return self.actual_volume
    
    def set_position(self, position):
        #It takes float value from 0 to 1 as argument 
        self.player.set_position(position)
        print("position: ", position)
    
    def get_position(self):
        return self.player.get_position()
        #Using get_position() returns a value between 0.0 and 1.0, essentially a percentage of the current position measured against the total running time.
        #Instead you can use get_time() which returns the current position in 1000ths of a second.

    def cleanup(self):
        self.stop()
        self.player.release()

# Add this class before Mp3Widget
class WidgetLayout(Enum):
    STANDARD = "Standard"
    COMPACT = "Compact"
    EXPANDED = "Expanded"
    MINIMAL = "Minimal"


class Mp3Widget(QWidget):
    def __init__(self, mp3_audio_file: Mp3File):
        super().__init__()
        self.mp3file = mp3_audio_file
        self.volume_slider_value = self.mp3file.actual_volume
        self.fade_time = 5
        self.elapsed_time = 0
        self.remaining_time = 0
        self.file_duration = self.mp3file.mp3_total_duration
        self.logger = logging.getLogger(__name__)
        self.current_layout = WidgetLayout.STANDARD

        self.init_ui()
        
        # Imposta la politica di ridimensionamento
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Espande in orizzontale ma rimane fissa in verticale

        # Adatta l'altezza del widget al contenuto
        self.adjustSize()

    def w_play_pause(self):
        self.mp3file.play_pause()
        return

    def w_stop(self):
        self.mp3file.stop()
        return
    

    def init_ui(self):
        # Create all widgets first
        self.create_widgets()
        # Apply the default layout
        self.apply_layout(WidgetLayout.STANDARD)
        
        # Start the timer for progress bar
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress_bar)
        self.timer.start(50)

    def create_widgets(self):
        # Create the main frame
        self.widget_main_frame = QFrame()
        widget_main_frame_style = "QFrame { background-color: #4A5662; border: 1px solid #5D6D7E; border-radius: 5px; }"
        self.widget_main_frame.setStyleSheet(widget_main_frame_style)
        
        # Create the layout selector
        self.layout_selector = QPushButton("Layout")
        layout_menu = QMenu(self)
        for layout_type in WidgetLayout:
            action = layout_menu.addAction(layout_type.value)
            action.triggered.connect(partial(self.apply_layout, layout_type))
        self.layout_selector.setMenu(layout_menu)

        # Create all the widgets (moved from original init_ui)
        self.filename_label = QLabel(f"{os.path.basename(self.mp3file.file_name)}")
        self.progress_bar = self.create_progress_bar()
        
        self.play_button = QPushButton("Play/Pause")
        self.play_button.setIcon(QIcon.fromTheme("media-playback-start"))
        self.play_button.clicked.connect(self.w_play_pause)
        
        self.fade_in_button = QPushButton("FadeIn")
        self.fade_in_button.clicked.connect(self.fade_in)
        
        self.fade_time_spinbox = QDoubleSpinBox()
        self.fade_time_spinbox.setRange(0, 10)
        self.fade_time_spinbox.setValue(self.fade_time)
        self.fade_time_spinbox.setSingleStep(0.5)
        self.fade_time_spinbox.valueChanged.connect(self.update_fade_time)
        
        self.fade_out_button = QPushButton("Fade Out")
        self.fade_out_button.clicked.connect(self.fade_out)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.w_stop)
        self.stop_button.setIcon(QIcon.fromTheme("media-playback-stop"))
        
        self.remove_button = QPushButton("Remove")
        self.remove_button.setIcon(QIcon.fromTheme("user-trash"))
        self.remove_button.clicked.connect(self.w_remove_file)
        
        self.volume_slider = QSlider(Qt.Vertical)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(self.volume_slider_value)
        self.volume_slider.valueChanged.connect(self.update_volume)
        
        self.volume_label = QLabel("100")
        self.volume_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        self.elapsed_time_label = QLabel("Elapsed time: 00:00")
        self.elapsed_time_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        
        self.remaining_time_label = QLabel(f"Remaining time: {self.seconds_to_min_sec(int(self.file_duration/1000))}")
        
        # Create the main layout that will hold the current layout
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

    def apply_layout(self, layout_type: WidgetLayout):
        # Store the current layout type
        self.current_layout = layout_type
        
        # Clear the current layout without deleting widgets
        if self.main_layout.count():
            while self.main_layout.count():
                item = self.main_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
        
        # Create new frame and layout for the selected layout type
        frame_layout = QGridLayout()
        frame_layout.setSpacing(6)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        
        # Reset size policies and constraints
        widgets = [
            self.layout_selector, self.filename_label, 
            self.play_button, self.stop_button, 
            self.fade_in_button, self.fade_out_button, 
            self.progress_bar, self.volume_slider
        ]
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        
        # Apply the selected layout
        if layout_type == WidgetLayout.STANDARD:
            self.apply_standard_layout(frame_layout)
        elif layout_type == WidgetLayout.COMPACT:
            self.apply_compact_layout(frame_layout)
        elif layout_type == WidgetLayout.EXPANDED:
            self.apply_expanded_layout(frame_layout)
        elif layout_type == WidgetLayout.MINIMAL:
            self.apply_minimal_layout(frame_layout)
        
        # Set the layout to the frame
        self.widget_main_frame.setLayout(frame_layout)
        
        # Clear and re-add the frame to main layout
        self.main_layout.addWidget(self.widget_main_frame)
        
        # Force layout update
        self.widget_main_frame.updateGeometry()
        self.updateGeometry()

    def apply_standard_layout(self, layout):
        # Original layout
        self.setMinimumHeight(100)  # Adjust value as needed

        layout.addWidget(self.layout_selector, 0, 0)
        layout.addWidget(self.remove_button, 0, 1)
        layout.addWidget(self.filename_label, 0, 2, 1, 4)
        layout.addWidget(self.play_button, 0, 6)
        layout.addWidget(self.fade_in_button, 0, 7)
        layout.addWidget(self.fade_time_spinbox, 0, 8)
        layout.addWidget(self.fade_out_button, 0, 9)
        layout.addWidget(self.stop_button, 0, 10)
        layout.addWidget(self.volume_slider, 0, 12, 4, 1)
        layout.addWidget(self.volume_label, 0, 11)
        layout.addWidget(self.progress_bar, 1, 0, 2, 10)
        layout.addWidget(self.remaining_time_label, 1, 10, 1, 2)
        layout.addWidget(self.elapsed_time_label, 2, 10, 1, 2)

    def apply_compact_layout(self, layout):
        # Compact layout with minimal controls
        layout.addWidget(self.layout_selector, 0, 0)
        layout.addWidget(self.filename_label, 0, 1, 1, 4)
        layout.addWidget(self.play_button, 0, 5)
        layout.addWidget(self.stop_button, 0, 6)
        layout.addWidget(self.volume_slider, 0, 8, 2, 1)
        layout.addWidget(self.progress_bar, 1, 0, 1, 7)
        layout.addWidget(self.elapsed_time_label, 1, 7)

    def apply_expanded_layout(self, layout):
        # Set minimum sizes for the buttons to make them bigger
        button_min_size = QSize(120, 40)  # Increased button size
        
        # Configure buttons with minimum size
        self.play_button.setMinimumSize(button_min_size)
        self.stop_button.setMinimumSize(button_min_size)
        self.fade_in_button.setMinimumSize(button_min_size)
        self.fade_out_button.setMinimumSize(button_min_size)
        self.remove_button.setMinimumSize(button_min_size)
        
        # Make the spinbox taller to match buttons
        self.fade_time_spinbox.setMinimumHeight(40)
        
        # Configure the volume slider to be taller
        self.volume_slider.setMinimumHeight(150)
        
        # Make the progress bar taller
        self.progress_bar.setFixedHeight(60)  # Increased from 48
        
        # Expanded layout with larger controls and bigger spacing
        layout.addWidget(self.layout_selector, 0, 0)
        layout.addWidget(self.remove_button, 0, 1)
        layout.addWidget(self.filename_label, 0, 2, 1, 6)
        layout.addWidget(self.volume_label, 0, 8)
        layout.addWidget(self.volume_slider, 0, 9, 4, 1)
        
        # Add spacing between rows
        layout.setVerticalSpacing(10)
        
        # Add the control buttons in their own row with more prominence
        layout.addWidget(self.play_button, 1, 0, 1, 2)
        layout.addWidget(self.stop_button, 1, 2, 1, 2)
        layout.addWidget(self.fade_in_button, 1, 4)
        layout.addWidget(self.fade_time_spinbox, 1, 5)
        layout.addWidget(self.fade_out_button, 1, 6)
        
        # Progress bar and time labels
        layout.addWidget(self.progress_bar, 2, 0, 1, 8)
        layout.addWidget(self.remaining_time_label, 2, 8)
        layout.addWidget(self.elapsed_time_label, 3, 8)
        
        # Set column stretch factors to ensure proper spacing
        layout.setColumnStretch(2, 2)  # Give more stretch to the filename column
        layout.setColumnStretch(6, 1)  # Give some stretch to the last control column
        
        # Add some margin around the entire layout
        layout.setContentsMargins(10, 10, 10, 10)    
    
    def apply_minimal_layout(self, layout):
        # Minimal layout with only essential controls
        layout.addWidget(self.layout_selector, 0, 0)
        layout.addWidget(self.filename_label, 0, 1, 1, 3)
        layout.addWidget(self.play_button, 0, 4)
        layout.addWidget(self.progress_bar, 1, 0, 1, 5)

    def get_current_layout(self) -> WidgetLayout:
        return self.current_layout

    # Add to save_state method if you have one, or create it
    def save_state(self) -> dict:
        return {
            'file_path': self.mp3file.file_name,
            'volume': self.mp3file.get_volume(),
            'fade_time': self.fade_time,
            'layout': self.current_layout.value
        }

    # Add to load_state method if you have one, or create it
    def load_state(self, state: dict):
        if 'layout' in state:
            self.apply_layout(WidgetLayout(state['layout']))
        if 'volume' in state:
            self.volume_slider.setValue(state['volume'])
        if 'fade_time' in state:
            self.fade_time_spinbox.setValue(state['fade_time'])

    def w_remove_file(self):
        self.mp3file.cleanup()
        self.deleteLater()  # Mark widget for deletion
    

    def update_volume(self):
        volume = self.volume_slider.value()
        self.mp3file.set_volume(volume)
        self.volume_label.setText(str(volume))

    def update_fade_time(self):
        self.fade_time = self.fade_time_spinbox.value()

    def fade_in(self):
        print("start Fade_in", self.mp3file.get_volume())
        self.mp3file.fade_in(self.fade_time, self.mp3file.get_volume())

    def fade_out(self):
        print("start Fade_out", self.mp3file.get_volume())
        self.mp3file.fade_out(self.fade_time, self.mp3file.get_volume(), 0)
        

    def update_playback_position(self, new_position):
            # Qui aggiorni la posizione di riproduzione del player
        self.mp3file.set_position(new_position)

    def seconds_to_min_sec(self, seconds):
        return f"{seconds // 60:02}:{seconds % 60:02}"

    def update_progress_bar(self):

#        if (self.mp3file.get_state() == "State.Playing") or (self.mp3file.get_state() == "State.Paused"):
        if (self.mp3file.get_state() == 3) or (self.mp3file.get_state() == 4):
            try:
                # Ottieni il tempo corrente in millisecondi
                current_time_ms = self.mp3file.player.get_time()
                
                if current_time_ms >= 0:
                    # Calcola la posizione per la progress bar
                    position = current_time_ms / self.file_duration
                    progress_value = int(position * self.progress_bar.maximum())
                    
                    # Converti i millisecondi in secondi INTERI per evitare discrepanze
                    total_seconds = self.file_duration // 1000  # Durata totale in secondi
                    current_seconds = current_time_ms // 1000   # Tempo corrente in secondi
                    remaining_seconds = total_seconds - current_seconds  # Tempo rimanente in secondi
                    
                    # Aggiorna tutti gli elementi UI usando gli stessi valori interi
                    self.progress_bar.setValue(progress_value)
                    self.elapsed_time_label.setText(f"Elapsed Time: {self.seconds_to_min_sec(current_seconds)}")
                    self.remaining_time_label.setText(f"Remaining Time: {self.seconds_to_min_sec(remaining_seconds)}")
     
            except Exception as e:
                self.logger.error(f"Error updating progress bar: {e}")

        else:
            # Se il player non è in riproduzione, reset dei valori
            self.progress_bar.setValue(0)
            self.elapsed_time_label.setText("Elapsed Time: 00:00")
            self.remaining_time_label.setText(f"Remaining Time: {self.seconds_to_min_sec(round(self.file_duration/1000))}")
        return


    def generate_waveform(self):
        target_sr = 11025 #1378  # 689 #44100 #22050
        audio, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
        plt.figure(figsize=(10, 0.5))
        plt.box(False)
        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)
        plt.plot(np.linspace(0, self.file_duration, len(audio)), audio, color='b', linewidth=0.1)
        plt.ylim(-1, 1)

        mp3WaveformImagePath = f'{os.path.basename(self.mp3file.file_name)}.jpg'
        plt.savefig(mp3WaveformImagePath, format='jpeg', dpi=150)
        print(f"{self.mp3file.file_name}: Max: {audio.max():.4f}, Min: {audio.min():.4f}, Media: {audio.mean()*1000:.8f}")

        plt.close()
#        print(mp3WaveformImagePath, self.file_duration)

        return mp3WaveformImagePath

    def generate_waveform_pillow(self): #samples, width, height):
    # Genera la forma d'onda usando Pillow.
        target_sr = 11025 #689 #44100 #22050
        samples, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
        width = 1500
        height = 75

        step = len(samples) // width
        samples = samples[: step * width]
        samples = samples.reshape(-1, step)
        min_vals = samples.min(axis=1)
        max_vals = samples.max(axis=1)
    
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        center = height // 2
    
        for x, (min_val, max_val) in enumerate(zip(min_vals, max_vals)):
            y1 = int(center + min_val * center)
            y2 = int(center + max_val * center)
            draw.line([(x, y1), (x, y2)], fill="blue")
        
        mp3WaveformImagePath = f'{os.path.basename(self.mp3file.file_name)}.jpg'
        img.save(mp3WaveformImagePath,'JPEG')

        return mp3WaveformImagePath


    def generate_waveform_rosa(self):
        target_sr = 11025 #689 #44100 #22050
        try:
            audio, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
        except Exception as e:
            self.logger.error(f"Error loading audio file {self.mp3file.file_name}: {e}")
            raise

       # Configura matplotlib per prestazioni ottimali
        plt.style.use('fast')
        plt.rcParams['agg.path.chunksize'] = 10000
        plt.figure(figsize=(10, 0.5), dpi=150)
        plt.box(False)

        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)
#        plt.plot(np.linspace(0, self.file_duration, len(audio)), audio, color='b', linewidth=0.1)

        # fig, ax = plt.subplots()
        librosa.display.waveshow(audio, sr=target_sr, axis=None, color='b', linewidth=0.1) #, sr=target_sr, ax=ax)
        plt.ylim(-1, 1)
        # y, sr = librosa.load(librosa.ex('choice'), duration=10)
        #fig, ax = librosa.display.waveshow(audio, sr=target_sr)

#        plt.show()
        mp3WaveformImagePath = f'{os.path.basename(self.mp3file.file_name)}.jpg'
        plt.savefig(mp3WaveformImagePath, format='jpeg', dpi=150)
        print(f"{self.mp3file.file_name}: Max: {audio.max():.4f}, Min: {audio.min():.4f}, Media: {audio.mean()*1000:.8f}")

        plt.close()
#        print(mp3WaveformImagePath, self.file_duration)

        return mp3WaveformImagePath



    def generate_waveform_mem(self):   # non viene caricata nella progressbar, la lascio qui per promemoria
        target_sr = 689 #44100 #22050
        audio, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
        duration = len(audio) / target_sr
#        self.debug(f"Audio Len: {len(audio)}")

        plt.figure(figsize=(10, 0.5))
        plt.box(False)
        plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
        plt.margins(0,0)
        plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)
        plt.plot(np.linspace(0, duration, len(audio)), audio, color='b', linewidth=0.1)

        # Salva l'immagine in un buffer di memoria
        buf = io.BytesIO()
        plt.savefig(buf, format='jpg', dpi=150)
        buf.seek(0)
        plt.close()
 
        # Converti l'immagine in base64
        image_data = base64.b64encode(buf.read()).decode('utf-8')

        return image_data


    def create_progress_bar(self):

        waveform_image_path=self.generate_waveform_rosa()
#        waveform_image_path=self.generate_waveform_pillow()

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
            background-color: rgba(0,255,0,100);
            width: 1px;
        }}
        """

        self.progress_bar = ClickableProgressBar() # QProgressBar()
        self.progress_bar.setFixedHeight(48)
        self.progress_bar.setStyleSheet(progress_bar_style)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.clicked.connect(self.update_playback_position)
        return self.progress_bar



class ProgressBarUpdateThread(QThread): # Not used
    progress_signal = pyqtSignal(int)

    def __init__(self, mp3_widget: Mp3Widget):
        super().__init__()
        self.mp3_widget = mp3_widget
        self.running = True
        self.seconds_to_min_sec = lambda seconds: f"{seconds // 60:02}:{seconds % 60:02}"
        self.logger = logging.getLogger(__name__)

    def run(self):
        while self.running:
            if (self.mp3_widget.mp3file.get_state() == 3) or (self.mp3_widget.mp3file.get_state() == 4):
                self.elapsed_time = self.mp3_widget.mp3file.player.get_time()   # Converti in ms
                self.file_duration = self.mp3_widget.file_duration 
                self.bar_position = (self.elapsed_time / self.file_duration) * self.mp3_widget.progress_bar.maximum()
                self.remaining_time = self.file_duration - self.elapsed_time

                # Update time label
                self.mp3_widget.elapsed_time_label.setText(f"Elapsed Time: {self.seconds_to_min_sec(int(self.elapsed_time/1000))}")
                self.mp3_widget.remaining_time_label.setText(f"Remaining Time: {self.seconds_to_min_sec(int(self.remaining_time/1000))}")

                self.progress_signal.emit(int(self.bar_position))  # Emit the progress value

#                print("Elapsed_time: ", self.elapsed_time)
#                print("Position: ", self.bar_position)
#                print("ProgresBar_Max:", self.mp3_widget.progress_bar.maximum())
                print("ProgresBar_value:", self.mp3_widget.progress_bar.value())
            else:
                self.file_duration = self.mp3_widget.file_duration 
                self.mp3_widget.elapsed_time_label.setText(f"Elapsed Time: 00:00")
                self.mp3_widget.remaining_time_label.setText(f"Remaining Time: {self.seconds_to_min_sec(int(self.file_duration/1000))}")

                self.progress_signal.emit(int(0))  # Emit the progress value
                print("progress ELSE")

            print("progress thread", self.mp3_widget.mp3file.file_name)    
            QThread.msleep(100)  # Sleep for 100ms before the next update

    def stop(self):
        self.running = False


class FadeThread(QThread):
    update_volume = pyqtSignal(int)

    def __init__(self, duration, start_volume, end_volume):
        super().__init__()
        self.end_volume = end_volume
        self.duration = duration
        self.start_volume = start_volume

    def run(self):
        steps = int(self.duration * 10)
        volume_step = (self.end_volume - self.start_volume) / steps

        for i in range(steps):
            volume = int(self.start_volume + volume_step * i)
            self.update_volume.emit(volume)
            QThread.msleep(100)

        
        if self.start_volume > self.end_volume:
            self.update_volume.emit(self.start_volume)
            print("fade_out thread",self.start_volume )
        else:
            self.update_volume.emit(self.end_volume)
            print("fade_in thread", self.end_volume)


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.mp3_audio_files = []
        self.mp3_widgets = []
        self.logger = logging.getLogger(__name__)

        self.init_ui()

    def init_ui(self):
        # Crea il layout principale
        self.setWindowTitle('MultiPlayer Eden Edition')
        self.setGeometry(100, 100, 1080, 300)

        # Crea la barra dei menu
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_file_action = QAction("Open MP3 Files", self)
        open_file_action.triggered.connect(self.open_files)
        file_menu.addAction(open_file_action)

        # Add Save/Load actions
        save_project_action = QAction("Save Project", self)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        
        load_project_action = QAction("Load Project", self)
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)

        # Add separator before Exit
        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)


        self.container_widget = QWidget()
        self.container_layout = QVBoxLayout()
        self.container_widget.setLayout(self.container_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.container_widget)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setWidgetResizable(True)

        self.setCentralWidget(scroll_area)


        self.show()

    def open_files(self):
        options = QFileDialog.Options()
        file_names, _ = QFileDialog.getOpenFileNames(self, "Open MP3 Files", "", "MP3 Files (*.mp3)", options=options)
        for file_name in file_names:
            if file_name:
                mp3_audio_file = Mp3File(file_name)
                self.mp3_audio_files.append(mp3_audio_file)
                mp3_widget = Mp3Widget(mp3_audio_file)
                self.mp3_widgets.append(mp3_widget)
                self.container_layout.addWidget(mp3_widget)

    def save_project(self):
        try:
            # Create a dialog to choose save location
            options = QFileDialog.Options()
            file_name, _ = QFileDialog.getSaveFileName(
                self,
                "Save Project",
                "",
                "Project Files (*.mpp);;All Files (*)",  # .mpp for MultiPlayer Project
                options=options
            )
            
            if file_name:
                # If user didn't add extension, add it
                if not file_name.endswith('.mpp'):
                    file_name += '.mpp'

                # Get window geometry
                geometry = self.geometry()
                window_state = {
                    'x': geometry.x(),
                    'y': geometry.y(),
                    'width': geometry.width(),
                    'height': geometry.height()
                }
                    
                # Create project data structure
                project_data = {
                    'version': '1.0',
                    'saved_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'window_state': window_state,
                    'files': []
                }
                
                # Collect data for each loaded MP3 file
                for widget in self.mp3_widgets:
                    file_data = {
                        'file_path': widget.mp3file.file_name,
                        'volume': widget.mp3file.get_volume(),
                        'fade_time': widget.fade_time,
                        'layout': widget.get_current_layout().value  # Add layout information
                    }
                    project_data['files'].append(file_data)
                
                # Save to file
                with open(file_name, 'w') as f:
                    json.dump(project_data, f, indent=4)
                    
                self.logger.info(f"Project saved successfully to {file_name}")
        except Exception as e:
            self.logger.error(f"Error saving project: {e}")
            # Show error dialog to user
            QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")

    def load_project(self):
        try:
            # Create dialog to choose file to load
            options = QFileDialog.Options()
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "Load Project",
                "",
                "Project Files (*.mpp);;All Files (*)",
                options=options
            )
            
            if file_name:
                try:
                    # Load and validate project data first
                    with open(file_name, 'r') as f:
                        project_data = json.load(f)
                    
                    if 'version' not in project_data or 'files' not in project_data:
                        raise ValueError("Invalid project file format")
                    
                    # Store current widgets for cleanup
                    old_widgets = self.mp3_widgets.copy()
                    old_files = self.mp3_audio_files.copy()
                    
                    # Clear lists but don't delete widgets yet
                    self.mp3_widgets = []
                    self.mp3_audio_files = []
                    
                    # Track successful loads
                    successful_loads = []
                    
                    # Load each file
                    for file_data in project_data['files']:
                        try:
                            # Validate file path
                            if not os.path.exists(file_data['file_path']):
                                raise FileNotFoundError(f"File not found: {file_data['file_path']}")
                            
                            # Create new MP3File instance
                            mp3_audio_file = Mp3File(file_data['file_path'])
                            
                            # Create widget
                            mp3_widget = Mp3Widget(mp3_audio_file)
                            if 'layout' in file_data:
                                try:
                                    layout_type = WidgetLayout(file_data['layout'])
                                    mp3_widget.apply_layout(layout_type)
                                except ValueError:
                                    self.logger.warning(f"Invalid layout type: {file_data['layout']}")
                            
                            # Apply settings
                            mp3_widget.volume_slider.setValue(file_data['volume'])
                            mp3_widget.fade_time_spinbox.setValue(file_data['fade_time'])
                            mp3_widget.update_volume()  # Ensure volume is actually set
                            
                            # Track successful creation
                            successful_loads.append((mp3_audio_file, mp3_widget))
                            
                        except Exception as e:
                            self.logger.error(f"Error loading file {file_data['file_path']}: {e}")
                            QMessageBox.warning(self, "Warning", 
                                f"Error loading file {os.path.basename(file_data['file_path'])}: {str(e)}")
                            continue
                    
                    # If we have any successful loads, cleanup old widgets
                    if successful_loads:
                        # Clean up old widgets
                        for widget in old_widgets:
                            try:
                                widget.mp3file.cleanup()
                                widget.deleteLater()
                            except Exception as e:
                                self.logger.error(f"Error cleaning up widget: {e}")
                        
                        # Clear the container layout
                        while self.container_layout.count():
                            item = self.container_layout.takeAt(0)
                            if item.widget():
                                item.widget().deleteLater()
                        
                        # Add new widgets
                        for mp3_file, widget in successful_loads:
                            self.mp3_audio_files.append(mp3_file)
                            self.mp3_widgets.append(widget)
                            self.container_layout.addWidget(widget)
                        
                        self.logger.info(f"Project loaded successfully from {file_name}")
                    else:
                        # If no files were loaded successfully, restore old state
                        self.mp3_widgets = old_widgets
                        self.mp3_audio_files = old_files
                        raise Exception("No files were loaded successfully")
                    
                    # Restore window geometry if available
                    if 'window_state' in project_data:
                        ws = project_data['window_state']
                        # Make sure the window is visible on the current screen setup
                        screen = QApplication.primaryScreen().geometry()
                        x = min(max(0, ws['x']), screen.width() - ws['width'])
                        y = min(max(0, ws['y']), screen.height() - ws['height'])
                        self.setGeometry(x, y, ws['width'], ws['height'])
      

                except Exception as e:
                    self.logger.error(f"Error loading project data: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")
                    
                    # Restore old state if loading failed
                    self.mp3_widgets = old_widgets
                    self.mp3_audio_files = old_files
                    
        except Exception as e:
            self.logger.error(f"Error in load_project: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_app = MainApp()
    sys.exit(app.exec_())
