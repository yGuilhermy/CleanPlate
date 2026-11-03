"""Standalone Qt desktop application. No editor integration or network listener."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from fractions import Fraction
import json
from pathlib import Path
import queue
import threading
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QUrl
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QIcon, QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSlider, QDoubleSpinBox, QAbstractSpinBox, QComboBox,
    QCheckBox, QTabWidget, QScrollArea, QFileDialog, QColorDialog, QProgressBar,
    QSizePolicy, QSplitter, QGroupBox, QMessageBox, QStyle)
from .engine import Settings, Background, matte, composite, flatten_rgba, blurred_background
from .media import probe, read_frame, build_background, export_video, Cancelled
from .preview import calculate
from .desktop_theme import STYLE
from .branding import APP_NAME, RELEASE_STAGE, application_icon, configure_windows_identity


def label(text, role=None, wrap=False):
    value = QLabel(text)
    if role:
        value.setObjectName(role)
    value.setWordWrap(wrap)
    return value


def button(text, callback, role=None):
    value = QPushButton(text)
    if role:
        value.setObjectName(role)
    value.setCursor(Qt.PointingHandCursor)
    value.clicked.connect(callback)
    return value


def image_pixmap(array):
    array = np.ascontiguousarray(array, dtype=np.uint8)
    image = QImage(array.data, array.shape[1], array.shape[0], array.strides[0], QImage.Format_RGB888).copy()
    return QPixmap.fromImage(image)


class Monitor(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.error = ''
        self.setMinimumSize(300, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#080809'))
        if self.pixmap:
            size = self.pixmap.size().scaled(self.size() - QSize(24, 24), Qt.KeepAspectRatio)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap((self.width()-size.width())//2, (self.height()-size.height())//2,
                               size.width(), size.height(), self.pixmap)
        else:
            painter.setPen(QColor('#ededf0'))
            painter.setFont(QFont('Segoe UI', 21, QFont.DemiBold))
            painter.drawText(self.rect().adjusted(24, -30, -24, -30), Qt.AlignCenter, 'Prévia do vídeo')
            painter.setFont(QFont('Segoe UI', 10))
            painter.setPen(QColor('#909098'))
            painter.drawText(self.rect().adjusted(24, 115, -24, 0), Qt.AlignCenter,
                             'Adicione o vídeo e uma imagem do cenário vazio para começar.')
        if self.error:
            painter.fillRect(12, 12, self.width()-24, 58, QColor('#303034'))
            painter.setPen(QColor('#fafafa'))
            painter.setFont(QFont('Segoe UI', 10))
            painter.drawText(self.rect().adjusted(24, 12, -24, -self.height()+70), Qt.TextWordWrap, self.error)


class MediaCard(QFrame):
    fileDropped = Signal(str)
    activated = Signal()

    def __init__(self, title, hint, callback):
        super().__init__()
        self.setObjectName('media')
        self.setMinimumHeight(184)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        box = QVBoxLayout(self)
        box.setContentsMargins(13, 13, 13, 13)
        box.setSpacing(8)
        self.thumbnail = QLabel('+')
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setFixedHeight(84)
        self.thumbnail.setStyleSheet('background: #1e1e22; border-radius: 6px; color: #b2b2bb; font-size: 27px;')
        self.name = label(title, 'section', True)
        self.hint = label(hint, 'muted', True)
        for child in (self.thumbnail, self.name, self.hint):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
            box.addWidget(child)
        self.activated.connect(callback)
        self.fileDropped.connect(callback)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.activated.emit()
        else:
            super().keyPressEvent(event)

    def set_file(self, path, frame, detail):
        self.setProperty('loaded', True)
        self.name.setText(Path(path).name)
        self.setToolTip(str(path) + '\nClique para substituir')
        self.hint.setText(detail)
        pixmap = image_pixmap(frame)
        self.thumbnail.setPixmap(pixmap.scaled(170, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.fileDropped.emit(event.mimeData().urls()[0].toLocalFile())
        event.acceptProposedAction()


class Timeline(QSlider):
    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setFixedHeight(36)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        x = 7 + QStyle.sliderPositionFromValue(self.minimum(), self.maximum(),
                                              self.value(), max(1, self.width()-14))
        y = self.height() / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#44444d'))
        painter.drawRoundedRect(7, int(y-2), max(1, self.width()-14), 4, 2, 2)
        painter.setBrush(QColor('#d4d4d8'))
        painter.drawRoundedRect(7, int(y-2), max(0, x-7), 4, 2, 2)
        painter.setBrush(QColor('#fafafa'))
        painter.drawEllipse(x-6, int(y-6), 12, 12)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor('#a1a1aa'))
            painter.drawEllipse(x-9, int(y-9), 18, 18)

    def seek_at(self, event):
        self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
            round(event.position().x())-7, max(1, self.width()-14)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus()
            self.setSliderDown(True)
            self.seek_at(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.seek_at(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.seek_at(event)
            self.setSliderDown(False)


class Parameter(QWidget):
    changed = Signal(float)

    def __init__(self, title, value, low, high, step=1, hint=''):
        super().__init__()
        self.factor = 1 / step
        self.setStyleSheet('background: transparent;')
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 4, 0, 8)
        box.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(label(title))
        self.number = QDoubleSpinBox()
        self.number.setRange(low, high)
        self.number.setDecimals(0 if step == 1 else 1 if step >= .1 else 2)
        self.number.setSingleStep(step)
        self.number.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.number.setFixedWidth(72)
        self.number.setKeyboardTracking(False)
        row.addWidget(self.number)
        box.addLayout(row)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(round(low*self.factor), round(high*self.factor))
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setAccessibleName(title)
        self.number.setAccessibleName(title+' valor')
        box.addWidget(self.slider)
        if hint:
            box.addWidget(label(hint, 'muted', True))
        self.slider.valueChanged.connect(lambda v: self.set_value(v/self.factor, True))
        self.number.valueChanged.connect(lambda v: self.set_value(v, True))
        self.set_value(value)

    def set_value(self, value, emit=False):
        self.number.blockSignals(True)
        self.slider.blockSignals(True)
        self.number.setValue(value)
        self.slider.setValue(round(value*self.factor))
        self.number.blockSignals(False)
        self.slider.blockSignals(False)
        if emit:
            self.changed.emit(self.number.value())


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP_NAME} · {RELEASE_STAGE}')
        self.resize(1440, 920)
        self.setMinimumSize(1100, 740)
        self.setWindowIcon(application_icon())
        self.source = self.reference = None
        self.info = self.model = None
        self.settings = Settings(outline=4, shadow=.5, glow=.35,
            refine_foreground=True, edge_refinement=3, hole_area=600, feather=0,
            outline_enabled=False, shadow_enabled=False, glow_enabled=False)
        self.reference_interval = (0, 3)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cleanplate')
        self.inflight = None
        self.queued_action = None
        self.progress_events = queue.Queue()
        self.cancel_event = threading.Event()
        self.generation = 0
        self.dirty = False
        self.closing = False
        self.parameters = {}
        self.effect_checks = {}
        self.current_time = 0
        self.frame_cache = None
        self.latest_rgba = None
        self.latest_preview = None
        self.last_output = None
        self.output_color = '#00ff00'
        self.busy_buttons = []
        self.build_ui()
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.dispatch_preview)
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll)
        self.poller.start(35)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(160)
        self.play_timer.timeout.connect(self.play_tick)
        QShortcut(QKeySequence('Ctrl+O'), self, activated=self.open_video)
        QShortcut(QKeySequence('Ctrl+S'), self, activated=self.save_project)

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 17, 24, 17)
        brand_icon = QLabel()
        brand_icon.setPixmap(application_icon().pixmap(28, 28))
        brand_icon.setFixedSize(28, 28)
        row.addWidget(brand_icon)
        row.addWidget(label('Clean Plate', 'brand'))
        row.addWidget(label('STUDIO', 'chip'))
        self.release_label = label(RELEASE_STAGE, 'release-stage')
        self.release_label.setToolTip('Versão em desenvolvimento; recursos e resultados podem mudar.')
        row.addWidget(self.release_label)
        row.addStretch()
        for title, callback in [('Abrir projeto', self.load_project), ('Salvar projeto', self.save_project)]:
            value = button(title, callback, 'ghost')
            row.addWidget(value)
            self.busy_buttons.append(value)
        self.export_button = button('Renderizar vídeo', self.export, 'primary')
        self.export_button.setEnabled(False)
        row.addWidget(self.export_button)
        outer.addWidget(header)
        work = QSplitter(Qt.Horizontal)
        work.setChildrenCollapsible(False)
        outer.addWidget(work, 1)
        rail = QFrame()
        rail.setObjectName('rail')
        rail.setMinimumWidth(190)
        rail.setMaximumWidth(240)
        files = QVBoxLayout(rail)
        files.setContentsMargins(18, 22, 18, 16)
        files.setSpacing(14)
        files.addWidget(label('SEU PROJETO', 'eyebrow'))
        files.addWidget(label('01  Cenário vazio', 'section'))
        self.ref_card = MediaCard('Adicionar referência', 'Imagem ou take do fundo', self.open_reference)
        files.addWidget(self.ref_card)
        files.addWidget(label('02  Vídeo original', 'section'))
        self.video_card = MediaCard('Adicionar vídeo', 'Clique ou arraste um arquivo', self.open_video)
        files.addWidget(self.video_card)
        files.addStretch()
        self.busy_buttons.extend([self.ref_card, self.video_card])
        work.addWidget(rail)
        center = QWidget()
        view_box = QVBoxLayout(center)
        view_box.setContentsMargins(20, 16, 20, 18)
        view_box.setSpacing(10)
        monitor_bar = QHBoxLayout()
        monitor_bar.addWidget(label('MONITOR', 'eyebrow'))
        monitor_bar.addStretch()
        self.view = QComboBox()
        self.view.addItems(['Recorte', 'Comparar', 'Matte', 'Original', 'Diferença'])
        self.view.setMinimumWidth(130)
        self.view.currentTextChanged.connect(self.schedule_preview)
        monitor_bar.addWidget(self.view)
        view_box.addLayout(monitor_bar)
        self.monitor = Monitor()
        view_box.addWidget(self.monitor, 1)
        info_row = QHBoxLayout()
        self.video_info = label('Nenhum vídeo carregado', 'muted')
        info_row.addWidget(self.video_info)
        info_row.addStretch()
        self.preview_info = label('Prévia adaptativa', 'muted')
        info_row.addWidget(self.preview_info)
        view_box.addLayout(info_row)
        transport = QHBoxLayout()
        self.play = button('', self.toggle_play)
        self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
        self.play.setAccessibleName('Reproduzir / pausar')
        self.play.setFixedSize(36, 36)
        transport.setSpacing(8)
        self.play.setToolTip('Prévia sequencial sem áudio; velocidade depende do processamento')
        transport.addWidget(self.play)
        previous = button('', lambda: self.step(-1), 'transport')
        previous.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'previous.svg')))
        previous.setFixedSize(32, 36)
        previous.setToolTip('Frame anterior')
        transport.addWidget(previous)
        self.position = Timeline()
        self.position.setRange(0, 0)
        self.position.setObjectName('timeline')
        self.position.setAccessibleName('Posição do vídeo')
        self.position.valueChanged.connect(self.seek)
        transport.addWidget(self.position, 1)
        next_frame = button('', lambda: self.step(1), 'transport')
        next_frame.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'next.svg')))
        next_frame.setFixedSize(32, 36)
        next_frame.setToolTip('Próximo frame')
        transport.addWidget(next_frame)
        self.time_label = label('00:00.000', 'muted')
        self.time_label.setFixedWidth(82)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        transport.addWidget(self.time_label)
        view_box.addLayout(transport)
        hints = QHBoxLayout()
        hints.addWidget(label('Comparar: original à esquerda, recorte à direita.', 'muted'))
        hints.addStretch()
        self.png_button = button('Salvar frame', self.save_frame, 'ghost')
        self.png_button.setEnabled(False)
        hints.addWidget(self.png_button)
        view_box.addLayout(hints)
        work.addWidget(center)
        inspector = QFrame()
        inspector.setObjectName('inspector')
        inspector.setMinimumWidth(310)
        inspector.setMaximumWidth(400)
        inspector_box = QVBoxLayout(inspector)
        inspector_box.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        inspector_box.addWidget(self.tabs)
        pages = {}
        for name in ['Recorte', 'Efeitos', 'Saída']:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            content = QWidget()
            layout = QVBoxLayout(content)
            layout.setContentsMargins(18, 20, 18, 20)
            layout.setSpacing(10)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, name)
            pages[name] = layout
        cut = pages['Recorte']
        cut_header = QHBoxLayout()
        cut_header.addWidget(label('Recorte', 'section'), 1)
        self.reset_cut_button = button('Default', self.reset_matte, 'ghost')
        self.reset_cut_button.setToolTip('Restaurar recorte, alinhamento e limpeza')
        cut_header.addWidget(self.reset_cut_button)
        cut.addLayout(cut_header)
        cut.addWidget(label('Comece pela tolerância. Confira o contorno no modo Matte.', 'muted', True))
        self.refine = QCheckBox('Refinar por cores e contornos')
        self.refine.setChecked(self.settings.refine_foreground)
        self.refine.setToolTip('Melhora o recorte de objetos sólidos usando as cores e os contornos de cada frame. '
                              'A análise aumenta o tempo de prévia e renderização. '
                              'Transparências e cores iguais ao fundo podem exigir outro ajuste.')
        self.refine.toggled.connect(lambda value: self.change('refine_foreground', value))
        cut.addWidget(self.refine)
        cut.addWidget(label('Com o refinamento, a análise de cada frame pode demorar mais.', 'muted', True))
        for spec in [('threshold', 'Tolerância', 0, 255, 1), ('softness', 'Transição', .1, 255, .1),
                     ('feather', 'Suavidade da borda · px', 0, 30, .1), ('expand', 'Expandir / contrair · px', -30, 30, 1)]:
            self.add_parameter(cut, *spec)
        self.align_button = button('Alinhar referência automaticamente', self.auto_align)
        cut.addWidget(self.align_button)
        self.busy_buttons.append(self.align_button)
        advanced_toggle = QPushButton('Alinhamento e limpeza')
        self.advanced_toggle = advanced_toggle
        advanced_toggle.setObjectName('disclosure')
        advanced_toggle.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'right.svg')))
        advanced_toggle.setCheckable(True)
        cut.addWidget(advanced_toggle)
        advanced = QWidget()
        adv = QVBoxLayout(advanced)
        adv.setContentsMargins(0, 6, 0, 0)
        self.add_parameter(adv, 'refine_radius', 'Alcance do refino · px', 1, 100, 1,
                           'Distância em torno do recorte inicial que pode ser corrigida. '
                           'Valores maiores podem incluir partes do cenário.')
        self.add_parameter(adv, 'edge_refinement', 'Refino da borda · px', 0, 20, .5,
                           'Ajusta o contorno aos detalhes da imagem. Use 0 para desligar.')
        self.add_parameter(adv, 'hole_area', 'Pequenas falhas · px²', 0, 20000, 1,
                           'Preenche apenas buracos internos até esta área na resolução original. '
                           'Use 0 para desligar; reduza para preservar vãos pequenos.')
        for spec in [('noise', 'Variação do fundo', 0, 10, .1), ('cleanup', 'Limpar pontos', 0, 5, 1),
                     ('offset_x', 'Posição horizontal · px', -500, 500, 1), ('offset_y', 'Posição vertical · px', -500, 500, 1),
                     ('scale', 'Escala da referência · %', 50, 200, .1), ('rotation', 'Rotação · °', -15, 15, .1)]:
            self.add_parameter(adv, *spec)
        self.light = QCheckBox('Compensar mudança global de luz')
        self.light.toggled.connect(lambda value: self.change('compensate_light', value))
        adv.addWidget(self.light)
        self.fit_reference = QCheckBox('Redimensionar referência para o vídeo')
        self.fit_reference.setToolTip('Use se o enquadramento for igual. Proporções diferentes deformam a referência.')
        self.fit_reference.toggled.connect(self.schedule_preview)
        adv.addWidget(self.fit_reference)
        self.extrapolate = QCheckBox('Estender bordas da referência')
        self.extrapolate.setToolTip('Aproxima regiões fora da foto pela cor da borda. Pode falhar em fundos detalhados.')
        self.extrapolate.toggled.connect(lambda value: self.change('extrapolate_reference', value))
        adv.addWidget(self.extrapolate)
        self.largest = QCheckBox('Manter apenas o maior objeto')
        self.largest.setToolTip('Remove regiões separadas. Pode apagar objetos ou partes desconectadas que você queira manter.')
        self.largest.toggled.connect(lambda value: self.change('keep_largest', value))
        adv.addWidget(self.largest)
        self.holes = QCheckBox('Preencher todos os buracos')
        self.holes.setToolTip('Ignora o limite de pequenas falhas e preenche todos os espaços internos. '
                             'Pode manter fundo entre braços, dedos e no aro de um fone. '
                             'Prefira o preenchimento de pequenas falhas quando houver esses vãos.')
        self.holes.toggled.connect(lambda value: self.change('fill_holes', value))
        adv.addWidget(self.holes)
        cut.addWidget(advanced)
        advanced.hide()
        advanced_toggle.toggled.connect(advanced.setVisible)
        advanced_toggle.toggled.connect(lambda expanded: advanced_toggle.setIcon(
            QIcon(str(Path(__file__).with_name('assets') / ('down.svg' if expanded else 'right.svg')))))
        reference_group = QGroupBox('Take vazio como referência')
        ref_box = QVBoxLayout(reference_group)
        self.ref_start = QDoubleSpinBox()
        self.ref_duration = QDoubleSpinBox()
        for title, field, default in [('Início · segundos', self.ref_start, 0), ('Duração · segundos', self.ref_duration, 3)]:
            field.setRange(.1 if field is self.ref_duration else 0, 36000)
            field.setValue(default)
            line = QHBoxLayout()
            line.addWidget(label(title))
            line.addWidget(field)
            ref_box.addLayout(line)
        self.reanalyze = button('Reanalisar referência', self.reanalyze_reference)
        self.busy_buttons.append(self.reanalyze)
        ref_box.addWidget(self.reanalyze)
        adv.addWidget(reference_group)
        cut.addStretch()
        fx = pages['Efeitos']
        fx_header = QHBoxLayout()
        fx_header.addWidget(label('Efeitos', 'section'), 1)
        self.reset_fx_button = button('Default', self.reset_effects, 'ghost')
        self.reset_fx_button.setToolTip('Restaurar valores e desligar os efeitos')
        fx_header.addWidget(self.reset_fx_button)
        fx.addLayout(fx_header)
        fx.addWidget(label('Os efeitos são opcionais e começam desligados.', 'muted', True))
        fx.addWidget(button('Desligar todos', self.disable_effects, 'ghost'))
        for name, title, specs in [
            ('outline', 'Borda externa', [('outline', 'Espessura · px', 0, 30, 1)]),
            ('shadow', 'Sombra', [('shadow', 'Opacidade', 0, 1, .01), ('shadow_blur', 'Desfoque · px', 0, 50, .5),
                                ('shadow_x', 'Horizontal · px', -100, 100, 1), ('shadow_y', 'Vertical · px', -100, 100, 1)]),
            ('glow', 'Glow', [('glow', 'Intensidade', 0, 1, .01), ('glow_blur', 'Difusão · px', 0, 50, .5)])]:
            group = QGroupBox(title)
            group.setCheckable(True)
            group.setChecked(False)
            inner = QVBoxLayout(group)
            for spec in specs:
                self.add_parameter(inner, *spec)
            group.toggled.connect(lambda value, key=name: self.change(key+'_enabled', value))
            self.effect_checks[name] = group
            fx.addWidget(group)
        self.effect_color = button('Cor da borda / glow  ·  #ffffff', self.choose_effect_color)
        fx.addWidget(self.effect_color)
        fx.addStretch()
        out = pages['Saída']
        out.addWidget(label('Exportação', 'section'))
        out.addWidget(label('O fundo selecionado aparece na prévia e será aplicado ao vídeo final.', 'muted', True))
        out.addWidget(label('Formato de saída'))
        self.output_mode = QComboBox()
        self.output_mode.addItems(['Transparência · MOV', 'Fundo sólido · MP4', 'Matte preto e branco · MP4', 'Fundo desfocado · MP4'])
        self.output_mode.currentIndexChanged.connect(self.output_changed)
        out.addWidget(self.output_mode)
        self.color_box = QWidget()
        colors = QVBoxLayout(self.color_box)
        colors.setContentsMargins(0, 12, 0, 10)
        colors.addWidget(label('Cor do fundo', 'section'))
        for name, color in [('Preto', '#000000'), ('Branco', '#ffffff'), ('Verde chroma', '#00ff00')]:
            colors.addWidget(button(name, lambda checked=False, c=color: self.set_output_color(c)))
        self.custom_color = button('Cor personalizada…', self.choose_output_color)
        colors.addWidget(self.custom_color)
        self.color_label = label('#00FF00', 'chip')
        colors.addWidget(self.color_label)
        out.addWidget(self.color_box)
        self.blur_box = QWidget()
        blur_layout = QVBoxLayout(self.blur_box)
        blur_layout.setContentsMargins(0, 12, 0, 10)
        self.add_parameter(blur_layout, 'background_blur', 'Desfoque do fundo · px', 0, 100, 1,
                           '0 mantém o cenário nítido; valores maiores desfocam mais. O objeto permanece em primeiro plano.')
        out.addWidget(self.blur_box)
        self.audio = QCheckBox('Manter áudio original')
        self.audio.setChecked(True)
        out.addWidget(self.audio)
        out.addWidget(label('Qualidade do MP4'))
        self.quality = QComboBox()
        self.quality.addItems(['Alta · arquivo maior', 'Equilibrada', 'Compacta · arquivo menor'])
        out.addWidget(self.quality)
        self.output_hint = label('', 'muted', True)
        out.addWidget(self.output_hint)
        out.addWidget(label('Prévia sem áudio. Exportação com áudio quando ativado.\n\nA mídia deve estar em SDR. Use o mesmo enquadramento na referência e no vídeo.', 'muted', True))
        out.addStretch()
        work.addWidget(inspector)
        work.setSizes([215, 860, 350])
        work.setStretchFactor(1, 1)
        self.output_changed()
        footer = QFrame()
        footer.setObjectName('footer')
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(24, 10, 24, 12)
        foot.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        foot.addWidget(self.progress)
        status_row = QHBoxLayout()
        self.status = label('Adicione a referência e o vídeo para começar.', 'muted')
        status_row.addWidget(self.status, 1)
        self.open_output = button('Abrir pasta do resultado', self.reveal_output, 'ghost')
        self.open_output.hide()
        status_row.addWidget(self.open_output)
        self.cancel_button = button('Cancelar', self.cancel_event.set)
        self.cancel_button.hide()
        status_row.addWidget(self.cancel_button)
        foot.addLayout(status_row)
        outer.addWidget(footer)

    def add_parameter(self, layout, key, title, low, high, step, hint=''):
        parameter = Parameter(title, getattr(self.settings, key), low, high, step, hint)
        parameter.changed.connect(lambda value, name=key, integer=step==1:
                                  self.change(name, int(value) if integer else value))
        layout.addWidget(parameter)
        self.parameters[key] = parameter

    def change(self, name, value):
        setattr(self.settings, name, value)
        self.schedule_preview()

    def reset_matte(self):
        defaults = Settings(refine_foreground=True, edge_refinement=3, hole_area=600, feather=0)
        for name in ('threshold', 'softness', 'feather', 'expand', 'noise', 'cleanup',
                     'refine_foreground', 'refine_radius', 'edge_refinement', 'hole_area',
                     'keep_largest', 'fill_holes', 'offset_x', 'offset_y', 'scale', 'rotation',
                     'compensate_light', 'extrapolate_reference'):
            setattr(self.settings, name, getattr(defaults, name))
        self.fit_reference.setChecked(False)
        self.sync_controls()
        self.schedule_preview()

    def reset_effects(self):
        defaults = Settings(outline=4, shadow=.5, glow=.35,
                            outline_enabled=False, shadow_enabled=False, glow_enabled=False)
        for name in ('outline', 'outline_color', 'shadow', 'shadow_blur', 'shadow_x',
                     'shadow_y', 'glow', 'glow_blur', 'outline_enabled', 'shadow_enabled', 'glow_enabled'):
            setattr(self.settings, name, getattr(defaults, name))
        self.sync_controls()
        self.schedule_preview()

    def disable_effects(self):
        for name, group in self.effect_checks.items():
            group.setChecked(False)
            setattr(self.settings, name+'_enabled', False)
        self.schedule_preview()

    def sync_controls(self):
        for name, control in self.parameters.items():
            control.set_value(getattr(self.settings, name))
        for name, control in self.effect_checks.items():
            control.blockSignals(True)
            control.setChecked(getattr(self.settings, name+'_enabled'))
            control.blockSignals(False)
        self.light.blockSignals(True)
        self.light.setChecked(self.settings.compensate_light)
        self.light.blockSignals(False)
        self.extrapolate.blockSignals(True)
        self.extrapolate.setChecked(self.settings.extrapolate_reference)
        self.extrapolate.blockSignals(False)
        for field, key in [(self.largest, 'keep_largest'), (self.holes, 'fill_holes'),
                           (self.refine, 'refine_foreground')]:
            field.blockSignals(True)
            field.setChecked(getattr(self.settings, key))
            field.blockSignals(False)
        self.effect_color.setText('Cor da borda / glow  ·  '+self.settings.outline_color)

    def choose_effect_color(self):
        color = QColorDialog.getColor(QColor(self.settings.outline_color), self, 'Cor do efeito')
        if color.isValid():
            self.settings.outline_color = color.name()
            self.sync_controls()
            self.schedule_preview()

    def set_output_color(self, color):
        parsed = QColor(str(color))
        if not parsed.isValid():
            raise ValueError('Cor de saída inválida')
        color = parsed.name()
        self.output_color = color
        self.color_label.setText(color.upper())
        self.color_label.setStyleSheet(f'background: {color}; color: {"#000000" if QColor(color).lightness() > 125 else "#ffffff"}; padding: 8px; border-radius: 6px;')
        self.schedule_preview()

    def choose_output_color(self):
        color = QColorDialog.getColor(QColor(self.output_color), self, 'Cor do fundo final')
        if color.isValid():
            self.set_output_color(color.name())

    def output_changed(self, *_):
        index = self.output_mode.currentIndex()
        self.color_box.setVisible(index == 1)
        self.blur_box.setVisible(index == 3)
        self.audio.setEnabled(index != 2)
        self.quality.setEnabled(index != 0)
        self.output_hint.setText([
            'MOV / ProRes 4444 com alpha. Fundo transparente; arquivo maior.',
            'MP4 / H.264 com fundo opaco. Verde pode ser removido por chroma key no seu editor.',
            'MP4 em preto e branco, sem áudio, para usar como máscara no editor.',
            'MP4 com o cenário desfocado e o objeto em primeiro plano. Intensidade ajustável; áudio opcional.'][index])
        if hasattr(self, 'debounce'):
            self.schedule_preview()

    def start_job(self, kind, operation, callback):
        if self.inflight:
            return False
        self.cancel_event.clear()
        self.inflight = (kind, self.executor.submit(operation), callback)
        if kind != 'preview':
            self.play_timer.stop()
            self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
            for control in self.busy_buttons:
                control.setEnabled(False)
            self.export_button.setEnabled(False)
            self.progress.setValue(0)
            self.progress.show()
            self.cancel_button.show()
        return True

    def poll(self):
        try:
            latest = None
            while True:
                latest = self.progress_events.get_nowait()
        except queue.Empty:
            if latest is not None:
                self.progress.setValue(round(latest*100))
        if self.inflight and self.inflight[1].done():
            kind, future, callback = self.inflight
            self.inflight = None
            if kind != 'preview':
                for control in self.busy_buttons:
                    control.setEnabled(True)
                self.cancel_button.hide()
                self.progress.hide()
            try:
                result = future.result()
                callback(result)
            except Cancelled:
                self.status.setText('Operação cancelada. Arquivos originais preservados.')
            except Exception as error:
                self.status.setText(str(error))
                self.status.setToolTip(str(error))
                self.monitor.error = str(error)
                self.monitor.update()
                self.play_timer.stop()
                self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
            self.export_button.setEnabled(self.source is not None and self.model is not None)
            if self.closing:
                self.close()
                return
        if self.inflight is None and self.queued_action:
            action, self.queued_action = self.queued_action, None
            action()
            return
        if self.dirty and self.inflight is None and not self.debounce.isActive():
            self.dispatch_preview()

    def schedule_preview(self, *_):
        self.generation += 1
        self.dirty = True
        if hasattr(self, 'debounce'):
            self.debounce.start(120)

    @staticmethod
    def fitted_model(model, shape, fit):
        if model is None or model.mean.shape == shape:
            return model
        if not fit:
            raise ValueError('Resoluções diferentes. Ative “Redimensionar referência” nos ajustes avançados.')
        size = (shape[1], shape[0])
        def resize(array):
            return np.stack([np.asarray(Image.fromarray(array[..., channel]).resize(size, Image.Resampling.BILINEAR))
                             for channel in range(3)], axis=2)
        return Background(resize(model.mean), resize(model.deviation), model.samples)

    def dispatch_preview(self):
        if self.inflight or not self.source:
            return
        self.dirty = False
        generation = self.generation
        source, info, model = self.source, self.info, self.model
        seconds = self.current_time
        settings = replace(self.settings)
        fit = self.fit_reference.isChecked()
        view = self.view.currentText()
        output = self.output_mode.currentIndex()
        backdrop = self.output_color if output == 1 else 'Desfocado' if output == 3 else 'Transparência'
        if output == 2 and view == 'Recorte':
            view = 'Matte'
        if model is not None and view != 'Original':
            self.status.setText('Analisando cores e contornos deste frame… A prévia pode demorar mais.'
                                if settings.refine_foreground else 'Calculando prévia do recorte…')
        cache = self.frame_cache
        def operation():
            if cache is not None and cache[0] == source and abs(cache[1]-seconds) < .00001:
                frame = cache[2]
            else:
                frame = read_frame(source, seconds, info)
            background = self.fitted_model(model, frame.shape, fit)
            start = time.monotonic()
            image, rgba = calculate(frame, background, settings, view, backdrop, limit=1280)
            return generation, image, rgba, frame, (time.monotonic()-start)*1000
        def done(result):
            version, image, rgba, frame, elapsed = result
            self.frame_cache = (source, seconds, frame)
            if version != self.generation:
                return
            self.latest_preview, self.latest_rgba = image, rgba
            self.monitor.pixmap = image_pixmap(image)
            self.monitor.error = ''
            self.monitor.update()
            self.preview_info.setText(f'{image.shape[1]} × {image.shape[0]} · {elapsed:.0f} ms')
            self.png_button.setEnabled(model is not None)
            self.status.setText('Prévia pronta. O formato e o fundo escolhidos serão aplicados à exportação.'
                                if model is not None else 'Adicione uma referência do cenário vazio para gerar o recorte.')
        self.start_job('preview', operation, done)

    def open_video(self, path=None):
        if self.inflight:
            self.status.setText('Aguarde a tarefa atual antes de trocar o vídeo.')
            return
        if not isinstance(path, str):
            path = QFileDialog.getOpenFileName(self, 'Adicionar vídeo ou imagem', '',
                    'Mídia (*.mp4 *.mov *.mkv *.avi *.webm *.png *.jpg *.jpeg *.tif *.bmp);;Todos (*.*)')[0]
        if not path:
            return
        path = str(Path(path).resolve())
        self.status.setText('Abrindo vídeo…')
        def operation():
            info = probe(path)
            return info, read_frame(path, info=info)
        def done(result):
            info, frame = result
            self.source, self.info = path, info
            self.current_time = 0
            self.frame_cache = (path, 0, frame)
            self.position.blockSignals(True)
            self.position.setRange(0, max(0, round((info['duration']-1/float(Fraction(info['fps'])))*1000)))
            self.position.setValue(0)
            self.position.blockSignals(False)
            self.time_label.setText('00:00.000')
            detail = f'{info["width"]} × {info["height"]} · {info["duration"]:.1f}s'
            self.video_info.setText(detail)
            self.video_card.set_file(path, frame, detail)
            self.schedule_preview()
        self.start_job('load', operation, done)

    def open_reference(self, path=None):
        if self.inflight:
            self.status.setText('Aguarde a tarefa atual antes de trocar a referência.')
            return
        if not isinstance(path, str):
            path = QFileDialog.getOpenFileName(self, 'Cenário vazio · imagem ou take', '',
                    'Referência (*.png *.jpg *.jpeg *.tif *.bmp *.webp *.mp4 *.mov *.mkv);;Todos (*.*)')[0]
        if not path:
            return
        path = str(Path(path).resolve())
        start, duration = self.ref_start.value(), self.ref_duration.value()
        self.status.setText('Analisando referência…')
        def operation():
            return build_background(path, start, duration, cancel=self.cancel_event, progress=self.progress_events.put)
        def done(model):
            self.reference, self.model = path, model
            self.reference_interval = start, duration
            self.ref_card.set_file(path, np.uint8(np.clip(model.mean, 0, 255)), f'{model.samples} amostra(s) · cenário vazio')
            self.schedule_preview()
        self.start_job('load', operation, done)

    def reanalyze_reference(self):
        if self.reference:
            self.open_reference(self.reference)
        else:
            self.open_reference()

    def auto_align(self):
        if self.inflight:
            if self.inflight[0] == 'preview':
                self.play_timer.stop()
                self.dirty = False
                self.debounce.stop()
                self.queued_action = self.auto_align
            return
        if not self.source or self.model is None:
            self.status.setText('Carregue o vídeo e a referência antes de alinhar.')
            return
        source, info, seconds, model = self.source, self.info, self.current_time, self.model
        def operation():
            from .alignment import estimate_alignment
            frame = read_frame(source, seconds, info)
            background = self.fitted_model(model, frame.shape, True)
            return estimate_alignment(background.mean, frame)
        def done(result):
            transform, count = result
            for name, value in transform.items():
                setattr(self.settings, name, value)
            self.settings.extrapolate_reference = True
            self.fit_reference.setChecked(True)
            self.sync_controls()
            self.status.setText(f'Alinhamento estimado com {count} pontos. Bordas da referência estendidas; confira a prévia.')
            self.schedule_preview()
        self.status.setText('Buscando pontos correspondentes no cenário…')
        self.start_job('align', operation, done)

    def seek(self, milliseconds):
        self.current_time = milliseconds/1000
        self.time_label.setText(f'{int(self.current_time//60):02d}:{self.current_time%60:06.3f}')
        self.schedule_preview()

    def step(self, direction):
        if self.info and not self.info['image']:
            self.position.setValue(self.position.value()+round(direction*1000/float(Fraction(self.info['fps']))))

    def toggle_play(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
        elif self.info and not self.info['image'] and (self.inflight is None or self.inflight[0]=='preview'):
            self.play_timer.start()
            self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'pause.svg')))

    def play_tick(self):
        if self.inflight or self.dirty:
            return
        if self.position.value() >= self.position.maximum():
            self.play_timer.stop()
            self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
            return
        self.position.setValue(min(self.position.maximum(), self.position.value()+160))

    def export(self):
        if not self.source or self.model is None:
            return
        if self.inflight:
            if self.inflight[0] == 'preview':
                self.play_timer.stop()
                self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
                self.dirty = False
                self.debounce.stop()
                self.queued_action = self.export
                self.status.setText('Preparando exportação…')
            return
        mode = ['cutout', 'solid', 'matte', 'blur'][self.output_mode.currentIndex()]
        suffix = '.mov' if mode=='cutout' else '.mp4'
        if self.info['image']:
            suffix = '.png'
        suggested = str(Path(self.source).with_name(Path(self.source).stem+'_cleanplate'+suffix))
        destination = QFileDialog.getSaveFileName(self, 'Renderizar resultado', suggested, f'Arquivo {suffix} (*{suffix})')[0]
        if destination:
            self.begin_export(destination, mode)

    def begin_export(self, destination, mode=None):
        if self.inflight or not self.source or self.model is None:
            return False
        mode = mode or ['cutout', 'solid', 'matte', 'blur'][self.output_mode.currentIndex()]
        destination = str(Path(destination).resolve())
        if Path(destination) in (Path(self.source), Path(self.reference)):
            self.status.setText('Escolha uma saída diferente dos originais.')
            return False
        if Path(destination).exists():
            self.status.setText('O arquivo já existe. Escolha outro nome para preservá-lo.')
            return False
        source, info = self.source, self.info
        settings = replace(self.settings).validate()
        original_model, fit = self.model, self.fit_reference.isChecked()
        if original_model.mean.shape != (info['height'], info['width'], 3) and not fit:
            self.status.setText('Resoluções diferentes. Ative “Redimensionar referência” nos ajustes avançados.')
            return False
        color = self.output_color
        audio = self.audio.isChecked()
        quality = [16, 20, 24][self.quality.currentIndex()]
        self.generation += 1
        self.dirty = False
        self.debounce.stop()
        self.play_timer.stop()
        self.play.setIcon(QIcon(str(Path(__file__).with_name('assets') / 'play.svg')))
        self.status.setText('Renderizando vídeo…')
        self.open_output.hide()
        def operation():
            model = self.fitted_model(original_model, (info['height'], info['width'], 3), fit)
            if info['image']:
                if Path(destination).suffix.lower() != '.png':
                    raise ValueError('Use PNG para exportar imagens')
                frame = read_frame(source, info=info)
                alpha, _ = matte(frame, model, settings)
                rgba = composite(frame, alpha, settings)
                result = np.uint8(alpha*255) if mode=='matte' else flatten_rgba(rgba, color) if mode=='solid' else blurred_background(frame, rgba, model, settings) if mode=='blur' else rgba
                Image.fromarray(result).save(destination)
                return 1
            return export_video(source, destination, model, settings, mode,
                self.cancel_event, self.progress_events.put, background_color=color, quality=quality, audio=audio)
        def done(count):
            self.last_output = destination
            self.status.setText(f'Pronto · {count} frames · {Path(destination).name}')
            self.status.setToolTip(destination)
            self.open_output.show()
        return self.start_job('export', operation, done)

    def save_frame(self):
        if self.inflight or not self.source or self.model is None:
            self.status.setText('Aguarde a prévia para salvar o frame.')
            return
        path = QFileDialog.getSaveFileName(self, 'Salvar frame em PNG', 'frame.png', 'PNG (*.png)')[0]
        if not path:
            return
        if Path(path).exists():
            self.status.setText('Escolha um nome novo para preservar o arquivo existente.')
            return
        # Render full resolution, independent of the reduced preview and monitor view mode.
        source, seconds, info = self.source, self.current_time, self.info
        settings, model = replace(self.settings), self.model
        fit, mode, color = self.fit_reference.isChecked(), self.output_mode.currentIndex(), self.output_color
        def operation():
            frame = read_frame(source, seconds, info)
            background = self.fitted_model(model, frame.shape, fit)
            alpha, _ = matte(frame, background, settings)
            rgba = composite(frame, alpha, settings)
            result = np.uint8(alpha*255) if mode==2 else flatten_rgba(rgba, color) if mode==1 else blurred_background(frame, rgba, background, settings) if mode==3 else rgba
            Image.fromarray(result).save(path)
            return path
        self.start_job('frame', operation, lambda result: self.status.setText('Frame salvo: '+result))

    def project_data(self):
        return {'version': 3, 'source': self.source, 'reference': self.reference,
            'settings': self.settings.to_dict(), 'reference_start': self.reference_interval[0],
            'reference_duration': self.reference_interval[1], 'fit_reference': self.fit_reference.isChecked(),
            'output': {'mode': self.output_mode.currentIndex(), 'color': self.output_color,
                       'quality': self.quality.currentIndex(), 'audio': self.audio.isChecked()}}

    def save_project(self):
        if not self.source or not self.reference:
            self.status.setText('Carregue referência e vídeo antes de salvar o projeto.')
            return
        path = QFileDialog.getSaveFileName(self, 'Salvar projeto', 'projeto.cleanplate.json', 'Projeto (*.json)')[0]
        if path:
            try:
                Path(path).write_text(json.dumps(self.project_data(), indent=2, ensure_ascii=False), encoding='utf-8')
                self.status.setText('Projeto salvo. Preserve os arquivos de mídia originais.')
            except OSError as error:
                self.status.setText(str(error))

    def load_project(self, path=None):
        if self.inflight:
            return
        if not isinstance(path, str):
            path = QFileDialog.getOpenFileName(self, 'Abrir projeto', '', 'Projeto (*.json)')[0]
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if data.get('version') not in (1, 2, 3):
                raise ValueError('Versão de projeto não suportada')
            settings = Settings(**data['settings']).validate()
            base = Path(path).resolve().parent
            source = str((base / data['source']).resolve())
            reference = str((base / data['reference']).resolve())
            for media in (source, reference):
                if not Path(media).is_file():
                    raise ValueError('Mídia ausente: '+str(media))
        except Exception as error:
            self.status.setText(str(error))
            return
        self.status.setText('Abrindo projeto…')
        def operation():
            info = probe(source)
            frame = read_frame(source, info=info)
            model = build_background(reference, data.get('reference_start', 0), data.get('reference_duration', 3),
                                     cancel=self.cancel_event, progress=self.progress_events.put)
            return info, frame, model
        def done(result):
            self.info, frame, self.model = result
            self.source, self.reference, self.settings = source, reference, settings
            self.frame_cache = (source, 0, frame)
            self.current_time = 0
            self.reference_interval = data.get('reference_start', 0), data.get('reference_duration', 3)
            self.ref_start.setValue(self.reference_interval[0])
            self.ref_duration.setValue(self.reference_interval[1])
            self.fit_reference.setChecked(bool(data.get('fit_reference', False)))
            self.sync_controls()
            output = data.get('output', {})
            self.output_mode.setCurrentIndex(max(0, min(3, int(output.get('mode', 0)))))
            self.set_output_color(output.get('color', '#00ff00'))
            self.quality.setCurrentIndex(max(0, min(3, int(output.get('quality', 0)))))
            self.audio.setChecked(bool(output.get('audio', True)))
            detail = f'{self.info["width"]} × {self.info["height"]} · {self.info["duration"]:.1f}s'
            self.video_info.setText(detail)
            self.video_card.set_file(source, frame, detail)
            self.ref_card.set_file(reference, np.uint8(np.clip(self.model.mean, 0, 255)), f'{self.model.samples} amostra(s)')
            self.position.blockSignals(True)
            self.position.setRange(0, max(0, round((self.info['duration']-1/float(Fraction(self.info['fps'])))*1000)))
            self.position.setValue(0)
            self.position.blockSignals(False)
            self.time_label.setText('00:00.000')
            self.schedule_preview()
        self.start_job('load', operation, done)

    def reveal_output(self):
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output).parent)))

    def closeEvent(self, event):
        if self.inflight:
            self.closing = True
            self.queued_action = None
            self.cancel_event.set()
            self.play_timer.stop()
            self.dirty = False
            self.debounce.stop()
            self.status.setText('Finalizando tarefa antes de fechar…')
            event.ignore()
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Clean Plate Studio · aplicativo Windows independente')
    parser.add_argument('--project')
    parser.add_argument('--verify-package', help=argparse.SUPPRESS)
    args = parser.parse_args()
    configure_windows_identity()
    application = QApplication.instance() or QApplication([])
    application.setApplicationName(APP_NAME)
    application.setWindowIcon(application_icon())
    application.setStyle('Fusion')
    application.setStyleSheet(STYLE)
    window = Studio()
    window.show()
    if args.project:
        QTimer.singleShot(0, lambda: window.load_project(args.project))
    if args.verify_package:
        import sys
        report = Path(args.verify_package).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        verification = {'phase': 0}
        timer = QTimer(application)
        def finish(data):
            timer.stop()
            report.write_text(json.dumps(data, indent=2), encoding='utf-8')
            window.cancel_event.set()
            window.close()
        def verify():
            try:
                if time.monotonic()-started > 90:
                    raise RuntimeError('Verificação excedeu o tempo: '+window.status.text())
                if window.inflight or window.dirty or window.debounce.isActive():
                    return
                if window.model is None or window.latest_preview is None:
                    raise RuntimeError('Projeto ou prévia não carregados: '+window.status.text())
                if verification['phase'] == 0:
                    import cv2
                    verification['opencv'] = cv2.__version__
                    window.output_mode.setCurrentIndex(3)
                    window.tabs.setCurrentIndex(2)
                    verification['phase'] = 1
                elif verification['phase'] == 1:
                    destination = report.with_name(report.stem+'-video.mp4')
                    if destination.exists():
                        raise RuntimeError('Arquivo de teste já existe; escolha outro relatório')
                    if not window.begin_export(str(destination), 'blur'):
                        raise RuntimeError(window.status.text())
                    verification['phase'] = 2
                else:
                    from .media import run, executable
                    if not window.last_output:
                        raise RuntimeError('Exportação não concluiu: '+window.status.text())
                    info = probe(window.last_output)
                    pixel = read_frame(window.last_output)[0, 0].tolist()
                    window.grab().save(str(report.with_suffix('.png')))
                    finish({'success': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                            'opencv': verification['opencv'], 'width': info['width'], 'height': info['height'],
                            'pixel_background': pixel, 'duration': info['duration'],
                            'output_mode': 'blur', 'background_blur': window.settings.background_blur,
                            'ffmpeg_bundled': str(Path(executable('ffmpeg')).parent).endswith('bin')})
            except Exception as error:
                finish({'success': False, 'error': str(error)})
        timer.timeout.connect(verify)
        timer.start(100)
    application.exec()


if __name__ == '__main__':
    main()
