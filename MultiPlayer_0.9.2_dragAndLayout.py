#################################################################################################
#        MultiPlayer                                                                            #
#                                                                                               #
# Date: 2024/08/22                                                                              #
# Note:                                                                                         #
# 0.5.4: basic implementation of seekbar                                                        #
# 0.5.5: show total and elapsed time                                                            # 
# 0.6.0: complete refactoring                                                                   #
# 0.7.1: a lot of new stuff                                                                     #
# 0.7.2: ProgressBar update in a different thread     (ToFix)                                   #
# 0.7.6: read file_duration from vlc instead of libRosa                                         #
# 0.7.7: waveform generated with librosa, waveform reflects real file amplitude                 #
# 0.7.8.2: added some exception                                                                 #
# 0.7.9: waveform creation with pillow library                                                  #
# 0.7.9.2: merged different versions                                                            #
# 0.7.9.3: added some exception handler, added Logger                                           #
# 0.7.9.4: synced elapsed and remaining time labels                                             #
# 0.7.9.5: some cleaning                                                                        #
# 0.7.9.6: synced volume on fading function with slider                                         #
# 0.7.9.7: added Save/Load project functionality                                                #
# 0.7.9.8: added color style on play/stop/pause button and Fade button symbol                   #
# 0.8.0.0: moved to timers instead of sleep() for fading function. add signals for fading state #
# 0.8.0.1: added preset button for fade spinbox and renamed some variables                      #
# 0.9.0.0: added drag&drop, grid layout, and project save/load with widget positions            #  
# 0.9.1.0: added dynamic layout selection for each widget                                       #
# 0.9.2.0: clean and fix some layout issues                                                     #
# Fix: eliminare variabili e metodi non usati                                                   #
# ToDo: aggiungere segnali dove possibile per pulire                                            #
# ToDo: implementare layout multipli                                                            #
# ToDo: rimpicciolire pulsanti Remove e label del volume                                        #
#################################################################################################
#https://www.pythonguis.com/tutorials/pyqt-layouts/

#scroll_area(QScrollArea)
# 	container_widget(QWidget)
# 		grid_layout(QGridLayout)   <-- MODIFIED FROM QVBoxLayout
# 			mp3_widget(QWidget) at (row, col)
# 			mp3_widget(QWidget) at (row, col)


import sys
import vlc
import os
import librosa
import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QToolButton, QMenu, QMessageBox, QSizePolicy, QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSlider, QFrame, QLabel, QPushButton, QProgressBar, QAction, QScrollArea, QDoubleSpinBox
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint, QMimeData #, QByteArray
from PyQt5.QtGui import QIcon, QDrag, QPixmap, QPainter
from PIL import Image, ImageDraw
import logging
import json
from datetime import datetime
import time
from enum import Enum


class WidgetLayout(Enum):
    COMPACT = 1
    TOUCH = 2
    STANDARD = 3


class Mp3WidgetMimeData(QMimeData):
    def __init__(self):
        super().__init__()
        self.widget = None

    def setWidget(self, widget):
        self.widget = widget

    def getWidget(self):
        return self.widget



class ClickableProgressBar(QProgressBar):
    clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)   

    def mousePressEvent(self, event):
        # Calcola la posizione cliccata rispetto alla progress bar
        if event.button() == Qt.LeftButton:
            click_position = event.x() 
            total_width = self.width()

            # Calculate new value based on clicked position            
            new_value = int(click_position / total_width * (self.maximum() - self.minimum()) + self.minimum())

            self.setValue(new_value)
            # Emits signal for seeking
            self.clicked.emit(new_value/self.maximum())

        # Call original event to keep standard behaviour
        super().mousePressEvent(event)


class playerStatus(Enum): # Not used
    fadein = "1"
    fadeout = "2"
    play = "3"
    pause = "4"
    stop = "5"


class Mp3File(QObject):
    fadeInFinished = pyqtSignal()
    fadeOutFinished = pyqtSignal()

    def __init__(self, file_name):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.fade_controller = None

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
        pass

    def get_state(self):
        #maps specific player status to universal status, usefull if differentt player will be supported 
        self.vlcState = self.player.get_state() # vlc status

        # if (self.vlcState == 3) and self.fadingIn:
        #     self.state = 10 # FadingIn
        # elif (self.vlcState == 3) and self.fadingOut:
        #     self.state = 11 # fadingOut
        # else:
        #     self.state = self.vlcState

        # print("state_init: ", state)

    #     _enum_names_ = {0: 'NothingSpecial', 1: 'Opening', 2: 'Bufferi...
    #     Buffering = vlc.State.Buffering
    #     Ended = vlc.State.Ended
    #     Error = vlc.State.Error
    #     NothingSpecial = vlc.State.NothingSpecial
    #     Opening = vlc.State.Opening
    #     Paused = vlc.State.Paused
    #     Playing = vlc.State.Playing
    #     Stopped = vlc.State.Stopped
        
    #   {0: 'NothingSpecial',
    #   1: 'Opening',
    #   2: 'Buffering',
    #   3: 'Playing',
    #   4: 'Paused',
    #   5: 'Stopped',
    #   6: 'Ended',
    #   7: 'Error'}
        return self.vlcState


    def play_pause(self):
        try:
            if (self.get_state() == 3):  #playing  #self.player.is_playing():
                self.player.pause()
            else:
                self.player.play()
                time.sleep(0.1) 
                self.set_volume(self.actual_volume)
        except Exception as e:
            self.logger.error(f"Play/Pause failed: {e}")
            raise
        pass

    def stop(self):
        try:
            self.player.stop()
        except Exception as e:
            self.logger.error(f"Stop failed: {e}")
            raise
        pass

    def fade_in(self, duration, end_volume):
        if not self.player.is_playing():
            self.player.play()
            self.fade_controller = FadeController(duration, 0, end_volume)
            self.fade_controller.update_volume.connect(self.set_volume)
            self.fade_controller.finished.connect(lambda: self.fadeInFinished.emit())
            self.fade_controller.start()
        pass

    def fade_out(self, duration, start_volume, end_volume):
        self.fade_controller = FadeController(duration, start_volume, end_volume)
        self.fade_controller.update_volume.connect(self.set_volume)
        self.fade_controller.finished.connect(lambda: self.fadeOutFinished.emit())
        self.fade_controller.finished.connect(self.stop)
        self.fade_controller.finished.connect(lambda: self.set_volume(start_volume))
        self.fade_controller.start()
        pass

    def set_volume(self, volume):
        self.actual_volume = volume
        self.player.audio_set_volume(self.actual_volume)
        self.logger.error(f"set_volume method: {self.actual_volume}, mp3file-get_volume: {self.get_volume()}")
        pass

    def get_volume(self):
        return self.actual_volume
    
    def set_position(self, position):
        #It takes float value from 0 to 1 as argument 
        self.player.set_position(position)
        print("position: ", position)
        pass

    def get_position(self):
        return self.player.get_position()
        #Using get_position() returns a value between 0.0 and 1.0, essentially a percentage of the current position measured against the total running time.
        #Instead you can use get_time() which returns the current position in 1000ths of a second.


    def cleanup(self):
        self.stop()
        self.player.release()
        pass


class Mp3Widget(QWidget):
    def __init__(self, mp3_audio_file: Mp3File, layout: WidgetLayout = WidgetLayout.TOUCH):
        super().__init__()
        self.mp3file = mp3_audio_file
        self.mp3file.fadeInFinished.connect(lambda: self.changeButtonStyle(self.btnFadeIn, "") )
        self.mp3file.fadeOutFinished.connect(lambda: self.changeButtonStyle(self.btnFadeOut, ""))
        self.mp3file.fadeOutFinished.connect(lambda: self.changeButtonStyle(self.btnPlay, ""))

        self.volume_slider_value = self.mp3file.actual_volume
        self.fade_time = 5
        self.elapsed_time = 0
        self.remaining_time = 0
        self.file_duration = self.mp3file.mp3_total_duration
        self.logger = logging.getLogger(__name__)
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name
        self.playerState = self.mp3file.get_state()
        
        self.drag_start_position = QPoint()
        
        self.create_ui_elements() 
        self.apply_layout() 
        
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) 
        self.defaultBtnStyle = "border: 1px solid; border-radius: 5px;"
        self.btnChangeLayout.setText(self.current_layout_name)

    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        
        # Use custom MimeData to pass a reference to the widget itself
        mime_data = Mp3WidgetMimeData()
        mime_data.setWidget(self)
        drag.setMimeData(mime_data)

        # Create a semi-transparent pixmap for visual feedback
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        painter = QPixmap(pixmap.size())
        painter.setDevicePixelRatio(self.devicePixelRatioF())
        painter.fill(Qt.transparent)
        p = QPainter(painter)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, pixmap)
        p.end()

        drag.setPixmap(painter)
        drag.setHotSpot(event.pos())
        
        # Start the drag operation
        drag.exec_(Qt.MoveAction)


    def create_ui_elements(self):
        """Creates all UI widgets. This is called only once."""
        self.widget_main_frame = QFrame()
        # Frame style with shadow
        widget_main_frame_style = ("""
        QFrame { background-color: #4A5662; border: 1px solid #5D6D7E; border-radius: 5px; }
        QLabel { color: white; font-weight: bold; }
        QDoubleSpinBox { color: black; }
        QPushButton {background-color: #a5adb6; border: 1px solid; border-radius: 5px;}
        QToolButton {background-color: #8c97a5; border: 1px solid; border-radius: 5px;}
        """)

        self.widget_main_frame.setStyleSheet(widget_main_frame_style)

        self.widget_file_frame_layout = QGridLayout()
        self.widget_main_frame.setLayout(self.widget_file_frame_layout)

        self.filename_label = QLabel(f"{os.path.basename(self.mp3file.file_name)}")
        self.progress_bar = self.create_progress_bar()
        self.btnPlay = QPushButton("Play/Pause")
        self.btnPlay.setIcon(QIcon.fromTheme("media-playback-start"))
        self.btnPlay.clicked.connect(self.w_play_pause)
        self.btnFadeIn = QPushButton("FadeIn")
        self.btnFadeIn.setIcon(QIcon.fromTheme("go-up"))
        self.btnFadeIn.clicked.connect(self.w_fade_in)
        self.spinboxFadeTime = QDoubleSpinBox() 
        self.spinboxFadeTime.setRange(0, 10) 
        self.spinboxFadeTime.setValue(self.fade_time)
        self.spinboxFadeTime.setSingleStep(0.5) 
        self.spinboxFadeTime.valueChanged.connect(self.update_fade_time)
        self.btnFadeOut = QPushButton("Fade Out")
        self.btnFadeOut.setIcon(QIcon.fromTheme("go-down"))
        self.btnFadeOut.clicked.connect(self.w_fade_out)
        self.btnStop = QPushButton("Stop")
        self.btnStop.clicked.connect(self.w_stop)
        self.btnStop.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.btnRemove = QPushButton("Remove")
        self.btnRemove.setIcon(QIcon.fromTheme("user-trash"))
        self.btnRemove.clicked.connect(self.w_remove_file) 
        self.slidVolume = QSlider(Qt.Vertical)
        self.slidVolume.setMinimum(0)
        self.slidVolume.setMaximum(100)
        self.slidVolume.setValue(self.volume_slider_value)
        self.slidVolume.valueChanged.connect(self.update_volume) 
        self.lblVolume = QLabel("100") 
        self.lblVolume.setAlignment(Qt.AlignHCenter | Qt.AlignTop) 
        self.lblElapsedTime = QLabel("Elapsed time: 00:00") 
        self.lblElapsedTime.setAlignment(Qt.AlignHCenter | Qt.AlignTop) 
        self.lblRemainingTime = QLabel(f"Remaining time: {self.seconds_to_min_sec(int(self.file_duration/1000))}")
        self.btnFadePreset1 = QPushButton("1")
        self.btnFadePreset1.clicked.connect(lambda: self.spinboxFadeTime.setValue(1))
        self.btnFadePreset2 = QPushButton("3")
        self.btnFadePreset2.clicked.connect(lambda: self.spinboxFadeTime.setValue(3))
        self.btnFadePreset3 = QPushButton("5")
        self.btnFadePreset3.clicked.connect(lambda: self.spinboxFadeTime.setValue(5))

        # --- Create the preset container ONCE and store it ---
        fade_preset_layout = QHBoxLayout()
        fade_preset_layout.setContentsMargins(0, 0, 0, 0)
        fade_preset_layout.setSpacing(0)
        fade_preset_layout.addWidget(self.btnFadePreset1)
        fade_preset_layout.addWidget(self.btnFadePreset2)
        fade_preset_layout.addWidget(self.btnFadePreset3)
        self.fade_preset_widget = QWidget() # Store as instance attribute
        self.fade_preset_widget.setLayout(fade_preset_layout)

        # --- Layout Change Button ---
        self.btnChangeLayout = QToolButton()
        self.btnChangeLayout.setIcon(QIcon.fromTheme("document-properties"))
        self.btnChangeLayout.setPopupMode(QToolButton.InstantPopup)
        layout_menu = QMenu(self)
        
        action_compact = QAction("Compact", self)
        action_compact.triggered.connect(lambda: self.set_layout(WidgetLayout.COMPACT))
        layout_menu.addAction(action_compact)
        
        action_touch = QAction("Touch", self)
        action_touch.triggered.connect(lambda: self.set_layout(WidgetLayout.TOUCH))
        layout_menu.addAction(action_touch)
        
        action_standard = QAction("Standard", self)
        action_standard.triggered.connect(lambda: self.set_layout(WidgetLayout.STANDARD))
        layout_menu.addAction(action_standard)
        
        self.btnChangeLayout.setMenu(layout_menu)
        
        # --- Final main layout setup ---
        self.widget_layout = QVBoxLayout()
        self.widget_layout.setContentsMargins(0, 0, 0, 0)
        self.widget_layout.addWidget(self.widget_main_frame)
        self.setLayout(self.widget_layout)

    def set_layout(self, layout: WidgetLayout):
        """Sets the new layout and applies it."""
        self.widgetLayout = layout
        self.current_layout_name = self.widgetLayout.name 
        self.btnChangeLayout.setText(self.current_layout_name)
        self.apply_layout()

    def apply_layout(self):
        """Clears and re-populates the internal grid layout based on self.widgetLayout."""

        while self.widget_file_frame_layout.count():
            item = self.widget_file_frame_layout.takeAt(0)
            if item.widget():
                # The widget is now detached from the layout but still exists
                # as a child of widget_main_frame. It will be re-added below.
                pass

        layout = self.widget_file_frame_layout
        
        if self.widgetLayout == WidgetLayout.COMPACT:
            layout.addWidget(self.btnRemove, 0, 0)
            layout.addWidget(self.btnChangeLayout, 0, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5)
            layout.addWidget(self.btnFadeIn, 0, 6)
            layout.addWidget(self.spinboxFadeTime, 0, 7)
            layout.addWidget(self.btnFadeOut, 0, 8)
            layout.addWidget(self.btnStop, 0, 9)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 1, 0, 2, 9)
            layout.addWidget(self.lblRemainingTime, 1, 9, 1, 2)
            layout.addWidget(self.lblElapsedTime, 2, 9, 1, 2)
        
        elif self.widgetLayout == WidgetLayout.TOUCH:
            for i in range(12): layout.setColumnStretch(i, 0)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(10, 1)
            for i in range(1, 10): layout.setColumnStretch(i, 2)

            # NOTE: self.fade_preset_widget is already created
            for btn in [self.spinboxFadeTime, self.btnRemove, self.btnPlay, self.btnFadeIn, self.btnFadeOut, self.btnStop, self.btnChangeLayout, self.fade_preset_widget]:
                btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            
            layout.addWidget(self.btnRemove, 0, 0, 2, 1)
            layout.addWidget(self.btnChangeLayout, 0, 1, 1, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5, 2, 1)
            layout.addWidget(self.btnFadeIn, 0, 6, 2, 1)
            layout.addWidget(self.spinboxFadeTime, 0, 7, 1, 1)
            layout.addWidget(self.fade_preset_widget, 1, 7, 1, 1)
            layout.addWidget(self.btnFadeOut, 0, 8, 2, 1)
            layout.addWidget(self.btnStop, 0, 9, 2, 1)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 2, 0, 2, 11)
            layout.addWidget(self.lblRemainingTime, 1, 3, 1, 2)
            layout.addWidget(self.lblElapsedTime, 1, 1, 1, 2)

        else:  # Standard Layout (WidgetLayout.STANDARD)
            for btn in [self.spinboxFadeTime, self.btnRemove, self.btnPlay, self.btnFadeIn, self.btnFadeOut, self.btnStop, self.btnChangeLayout]:
                btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

            layout.addWidget(self.btnRemove, 0, 0, 2, 1)
            layout.addWidget(self.btnChangeLayout, 0, 1, 1, 1)
            layout.addWidget(self.filename_label, 0, 2, 1, 3)
            layout.addWidget(self.btnPlay, 0, 5, 2, 1)
            layout.addWidget(self.btnFadeIn, 0, 6, 2, 1)
            layout.addWidget(self.spinboxFadeTime, 0, 7, 1, 1)
            layout.addWidget(self.fade_preset_widget, 1, 7, 1, 1)
            layout.addWidget(self.btnFadeOut, 0, 8, 2, 1)
            layout.addWidget(self.btnStop, 0, 9, 2, 1)
            layout.addWidget(self.slidVolume, 0, 11, 4, 1)
            layout.addWidget(self.lblVolume, 0, 10)
            layout.addWidget(self.progress_bar, 2, 0, 2, 11)
            layout.addWidget(self.lblRemainingTime, 1, 3, 1, 2)
            layout.addWidget(self.lblElapsedTime, 1, 1, 1, 2)
        
        self.adjustSize()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress_bar)
        self.timer.start(50)
        pass


    def changeButtonStyle(self, btn, color):
        btn.setStyleSheet(f"QPushButton {{background-color: {color}; {self.defaultBtnStyle} }} ")  # Stile pausa
        pass

    def w_play_pause(self):
        if (self.mp3file.get_state() == 3) :
            self.changeButtonStyle(self.btnPlay, "red")
        else:
            self.changeButtonStyle(self.btnPlay, "green")
        self.mp3file.play_pause()
        pass

    def w_stop(self):
        self.changeButtonStyle(self.btnPlay, "")
        self.mp3file.stop()
        pass
    
    def w_remove_file(self):
        self.mp3file.cleanup()
        # The parent (MainApp) will handle removing it from the layout and lists
        self.parent().remove_widget(self)
        self.deleteLater()
        pass    

    def update_volume(self):
        volume = self.slidVolume.value()
        self.mp3file.set_volume(volume)
        self.lblVolume.setText(str(volume))
        pass

    def update_fade_time(self):
        self.fade_time = self.spinboxFadeTime.value()
        pass

    def w_fade_in(self):
        #   print("start Fade_in", self.mp3file.get_volume())
        self.changeButtonStyle(self.btnPlay, "green")
        self.changeButtonStyle(self.btnFadeIn, "green")
        self.mp3file.fade_in(self.fade_time, self.mp3file.get_volume())
        pass

    def w_fade_out(self):
        #   print("start Fade_out", self.mp3file.get_volume())
        self.changeButtonStyle(self.btnFadeOut, "green")
        self.mp3file.fade_out(self.fade_time, self.mp3file.get_volume(), 0)
        pass        

    def update_playback_position(self, new_position):
        self.mp3file.set_position(new_position)
        pass

    def seconds_to_min_sec(self, seconds):
        return f"{seconds // 60:02}:{seconds % 60:02}"
        pass

    def update_progress_bar(self):
        if (self.mp3file.get_state() == 3) or (self.mp3file.get_state() == 4):
            try:
                current_time_ms = self.mp3file.player.get_time()  # use get_time to get current time in ms
                if current_time_ms >= 0:
                    # position for progress bar update
                    position = current_time_ms / self.file_duration
                    progress_value = int(position * self.progress_bar.maximum())
                    # Converti i millisecondi in secondi INTERI per evitare discrepanze
                    total_seconds = self.file_duration // 1000
                    current_seconds = current_time_ms // 1000
                    remaining_seconds = total_seconds - current_seconds
                    self.progress_bar.setValue(progress_value)
                    self.lblElapsedTime.setText(f"Elapsed Time: {self.seconds_to_min_sec(current_seconds)}")
                    self.lblRemainingTime.setText(f"Remaining Time: {self.seconds_to_min_sec(remaining_seconds)}")
            except Exception as e:
                self.logger.error(f"Error updating progress bar: {e}")
        else:
            # Se il player non è in riproduzione, reset dei valori
            self.progress_bar.setValue(0)
            self.lblElapsedTime.setText("Elapsed Time: 00:00")
            self.lblRemainingTime.setText(f"Remaining Time: {self.seconds_to_min_sec(round(self.file_duration/1000))}")
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


    def generate_waveform_pillow(self):     # Genera la forma d'onda usando Pillow.
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


    def generate_waveform_rosa(self):   # Genera la forma d'onda usando LibRosa.
        target_sr = 11025 #689 #44100 #22050
        try:
            audio, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
        except Exception as e:
            self.logger.error(f"Error loading audio file {self.mp3file.file_name}: {e}")
            raise

       # matplotlib config for performance optim.
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


#     def generate_waveform_mem(self):   #non usata, non viene caricata nella progressbar, la lascio qui per promemoria
#         target_sr = 689 #44100 #22050
#         audio, _ = librosa.load(self.mp3file.file_name, sr=target_sr, mono=True)
#         duration = len(audio) / target_sr
# #        self.debug(f"Audio Len: {len(audio)}")

#         plt.figure(figsize=(10, 0.5))
#         plt.box(False)
#         plt.subplots_adjust(top = 1, bottom = 0, right = 1, left = 0, hspace = 0, wspace = 0)
#         plt.margins(0,0)
#         plt.tick_params(left = False, right = False , labelleft = False, labelbottom = False, bottom = False)
#         plt.plot(np.linspace(0, duration, len(audio)), audio, color='b', linewidth=0.1)

#         # Salva l'immagine in un buffer di memoria
#         buf = io.BytesIO()
#         plt.savefig(buf, format='jpg', dpi=150)
#         buf.seek(0)
#         plt.close()
 
#         # Converti l'immagine in base64
#         image_data = base64.b64encode(buf.read()).decode('utf-8')

#         return image_data


    def create_progress_bar(self):
        waveform_image_path = self.generate_waveform_rosa()
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

        self.progress_bar = ClickableProgressBar()
        self.progress_bar.setFixedHeight(48)
        self.progress_bar.setStyleSheet(progress_bar_style)
        self.progress_bar.setMaximum(1000)
        self.progress_bar.clicked.connect(self.update_playback_position)
        return self.progress_bar

class FadeController(QObject):
    update_volume = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, duration, start_volume, end_volume, parent=None):
        super().__init__(parent)
        self.start_volume = start_volume
        self.end_volume = end_volume
        self.duration = duration  # in seconds
        self.steps = int(duration * 10)
        self.step_index = 0
        self.volume_step = (end_volume - start_volume) / self.steps if self.steps > 0 else 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def start(self):
        self.timer.start(100)
        pass

    def update(self):
        if self.step_index >= self.steps:
            self.update_volume.emit(int(self.end_volume))
            self.timer.stop()
            self.finished.emit()
            return
        volume = int(self.start_volume + self.volume_step * self.step_index)
        self.update_volume.emit(volume)
        self.step_index += 1

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.mp3_audio_files = []
        self.mp3_widgets = []
        self.logger = logging.getLogger(__name__)
        
        self.initial_rows = 5
        self.initial_cols = 2
        
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('MultiPlayer Eden Edition')
        self.setGeometry(100, 100, 1080, 600)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        open_file_action = QAction("Open MP3 Files", self)
        open_file_action.triggered.connect(self.open_files)
        file_menu.addAction(open_file_action)
        save_project_action = QAction("Save Project", self)
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        load_project_action = QAction("Load Project", self)
        load_project_action.triggered.connect(self.load_project)
        file_menu.addAction(load_project_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- START: Grid Layout Setup ---
        self.container_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        
        # Initialize grid with empty space
        for r in range(self.initial_rows): self.grid_layout.setRowStretch(r, 1)
        for c in range(self.initial_cols): self.grid_layout.setColumnStretch(c, 1)

        self.container_widget.setLayout(self.grid_layout)

        # Enable dropping on the container widget
        self.container_widget.setAcceptDrops(True)
        # --- END: Grid Layout Setup ---


        scroll_area = QScrollArea()
        scroll_area.setWidget(self.container_widget)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setWidgetResizable(True)
        self.setCentralWidget(scroll_area)
        # We need to install event filters to handle drops on the container
        
        self.container_widget.dragEnterEvent = self.dragEnterEvent
        self.container_widget.dropEvent = self.dropEvent

        self.show()
    
    # --- START: Drag&Drop Event Handlers for the container ---
    def dragEnterEvent(self, event):
        # We only accept drops if they contain our custom mime data
        if isinstance(event.mimeData(), Mp3WidgetMimeData):
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if not isinstance(event.mimeData(), Mp3WidgetMimeData):
            event.ignore()
            return

        source_widget = event.mimeData().getWidget()
        # Find the target cell in the grid
        target_pos = event.pos()
        target_row, target_col = self.get_cell_at_pos(target_pos)
        if target_row == -1: # Dropped outside a valid cell
            event.ignore()
            return

        # Check if the target cell is occupied
        item = self.grid_layout.itemAtPosition(target_row, target_col)
        
        if item and item.widget() != source_widget:
            # The cell is occupied by another widget, we need to move it
            displaced_widget = item.widget()
            self.logger.info(f"Cell ({target_row}, {target_col}) is occupied by {os.path.basename(displaced_widget.mp3file.file_name)}. Finding new spot.")
            # Find the nearest free cell for the displaced widget
            new_row, new_col = self.find_nearest_free_cell(target_row, target_col)
            if new_row != -1:
                self.logger.info(f"Moving displaced widget to ({new_row}, {new_col}).")
                # Detach and re-attach the displaced widget
                self.grid_layout.removeWidget(displaced_widget)
                self.grid_layout.addWidget(displaced_widget, new_row, new_col)
            else:
                self.logger.warning("Could not find a free cell for the displaced widget. Aborting drop.")
                event.ignore()
                return

        # Now move the source widget to the target cell
        self.logger.info(f"Moving {os.path.basename(source_widget.mp3file.file_name)} to ({target_row}, {target_col}).")
        self.grid_layout.removeWidget(source_widget)
        self.grid_layout.addWidget(source_widget, target_row, target_col)
        event.acceptProposedAction()
    # --- END: Drag&Drop Event Handlers ---

    def open_files(self):
        options = QFileDialog.Options()
        file_names, _ = QFileDialog.getOpenFileNames(self, "Open MP3 Files", "", "MP3 Files (*.mp3)", options=options)
        for file_name in file_names:
            if file_name:
                row, col = self.find_next_available_cell()
                if row == -1:
                    QMessageBox.warning(self, "Grid Full", "The layout grid is full. Cannot add more files.")
                    break
                
                mp3_audio_file = Mp3File(file_name)
                mp3_widget = Mp3Widget(mp3_audio_file) # Uses default layout

                self.mp3_widgets.append(mp3_widget)
                self.grid_layout.addWidget(mp3_widget, row, col)


    def save_project(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Project Files (*.mpp)", options=options)
        
        if file_name:
            if not file_name.endswith('.mpp'):
                file_name += '.mpp'
            
            geometry = self.geometry()
            window_state = {'x': geometry.x(), 'y': geometry.y(), 'width': geometry.width(), 'height': geometry.height()}
                
            project_data = {
                'version': '1.2', # Updated version for layout support
                'saved_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'window_state': window_state,
                'grid_state': {
                    'rows': self.grid_layout.rowCount(),
                    'cols': self.grid_layout.columnCount()
                },
                'files': []
            }
            
            # Iterate through the grid layout to get widget positions
            for i in range(self.grid_layout.count()):
                item = self.grid_layout.itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    row, col, _, _ = self.grid_layout.getItemPosition(i)
                    file_data = {
                        'file_path': widget.mp3file.file_name,
                        'volume': widget.mp3file.get_volume(),
                        'fade_time': widget.fade_time,
                        'row': row,
                        'col': col,
                        'layout': widget.widgetLayout.name # Save layout as string (e.g., "TOUCH")
                    }
                    project_data['files'].append(file_data)
            
            try:
                with open(file_name, 'w') as f:
                    json.dump(project_data, f, indent=4)
                self.logger.info(f"Project saved successfully to {file_name}")
            except Exception as e:
                self.logger.error(f"Error saving project: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save project: {str(e)}")


    def load_project(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Project Files (*.mpp)", options=options)
        
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    project_data = json.load(f)
                
                if 'version' not in project_data or 'files' not in project_data:
                    raise ValueError("Invalid project file format")
                
                self.clear_layout()
                
                if 'grid_state' in project_data:
                    grid_state = project_data['grid_state']
                    rows = grid_state.get('rows', self.initial_rows)
                    cols = grid_state.get('cols', self.initial_cols)
                    for r in range(rows): self.grid_layout.setRowStretch(r, 1)
                    for c in range(cols): self.grid_layout.setColumnStretch(c, 1)

                successful_loads = []
                for file_data in project_data['files']:
                    try:
                        if not os.path.exists(file_data['file_path']):
                            raise FileNotFoundError(f"File not found: {file_data['file_path']}")
                        
                        mp3_audio_file = Mp3File(file_data['file_path'])
                        
                        # Get layout from file, default to TOUCH if not present
                        layout_name = file_data.get('layout', 'TOUCH')
                        layout = WidgetLayout[layout_name] # Convert string back to Enum
                        
                        mp3_widget = Mp3Widget(mp3_audio_file, layout=layout)
                        
                        mp3_widget.slidVolume.setValue(file_data['volume'])
                        mp3_widget.spinboxFadeTime.setValue(file_data['fade_time'])
                        mp3_widget.update_volume()
                        
                        row = file_data.get('row', -1)
                        col = file_data.get('col', -1)
                        
                        successful_loads.append((mp3_widget, row, col))
                        
                    except Exception as e:
                        self.logger.error(f"Error loading file {file_data['file_path']}: {e}")
                        QMessageBox.warning(self, "Warning", f"Error loading file {os.path.basename(file_data['file_path'])}: {str(e)}")
                
                # Add new widgets to the grid at their saved positions
                for widget, row, col in successful_loads:
                    self.mp3_widgets.append(widget)
                    if row != -1 and col != -1:
                        self.grid_layout.addWidget(widget, row, col)
                    else: # Fallback for old projects or errors
                        r, c = self.find_next_available_cell()
                        self.grid_layout.addWidget(widget, r, c)
                
                self.logger.info(f"Project loaded successfully from {file_name}")

                if 'window_state' in project_data:
                    ws = project_data['window_state']
                    screen = QApplication.primaryScreen().geometry()
                    x = min(max(0, ws['x']), screen.width() - ws['width'])
                    y = min(max(0, ws['y']), screen.height() - ws['height'])
                    self.setGeometry(x, y, ws['width'], ws['height'])
            except Exception as e:
                self.logger.error(f"Error loading project data: {e}")
                QMessageBox.critical(self, "Error", f"Failed to load project: {str(e)}")

    
    def clear_layout(self):
        """Removes all widgets from the grid layout and internal lists."""
        for widget in self.mp3_widgets:
            widget.mp3file.cleanup()
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
        self.mp3_widgets.clear()
        
    def remove_widget(self, widget):
        """Removes a single widget when its 'Remove' button is clicked."""
        if widget in self.mp3_widgets:
            self.mp3_widgets.remove(widget)
            self.grid_layout.removeWidget(widget)
            self.logger.info(f"Removed widget for {os.path.basename(widget.mp3file.file_name)}.")
            
    def get_cell_at_pos(self, pos):
        """Finds the grid cell (row, col) for a given QPoint position."""
        for r in range(self.grid_layout.rowCount()):
            for c in range(self.grid_layout.columnCount()):
                cell_rect = self.grid_layout.cellRect(r, c)
                if cell_rect.contains(pos):
                    return r, c
        return -1, -1

    def find_next_available_cell(self):
        """Finds the first empty cell in the grid, scanning top-to-bottom, left-to-right."""
        for r in range(self.grid_layout.rowCount()):
            for c in range(self.grid_layout.columnCount()):
                if self.grid_layout.itemAtPosition(r, c) is None:
                    return r, c
        # If grid is full, expand it by adding a new row
        new_row = self.grid_layout.rowCount()
        self.grid_layout.setRowStretch(new_row, 1)
        return new_row, 0

    def find_nearest_free_cell(self, start_row, start_col):
        """Finds the nearest empty cell using a spiral search pattern."""
        max_search_dist = max(self.grid_layout.rowCount(), self.grid_layout.columnCount()) * 2
        for dist in range(1, max_search_dist):
            # Check cells in a square ring around the start position
            for i in range(-dist, dist + 1):
                # Top & Bottom edges of the ring
                cells_to_check = [
                    (start_row - dist, start_col + i), (start_row + dist, start_col + i),
                    (start_row + i, start_col - dist), (start_row + i, start_col + dist)
                ]
                for r, c in cells_to_check:
                    if 0 <= r < self.grid_layout.rowCount() and 0 <= c < self.grid_layout.columnCount():
                        if self.grid_layout.itemAtPosition(r, c) is None:
                            return r, c
        # If no cell is found, expand the grid
        new_row = self.grid_layout.rowCount()
        self.grid_layout.setRowStretch(new_row, 1)
        return new_row, 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = QApplication(sys.argv)
    main_app = MainApp()
    sys.exit(app.exec_())