from pathlib import Path

STYLE = '''
QWidget { background: #0b0b0c; color: #f4f4f5; font-family: "Segoe UI"; font-size: 14px; }
QMainWindow { background: #0b0b0c; }
QFrame#header { border-bottom: 1px solid #27272a; }
QFrame#rail { background: #101011; border-right: 1px solid #27272a; }
QFrame#inspector { background: #101011; border-left: 1px solid #27272a; }
QFrame#footer { border-top: 1px solid #27272a; }
QLabel { background: transparent; }
QLabel#brand { font-size: 22px; font-weight: 650; letter-spacing: -0.5px; }
QLabel#muted { color: #a1a1aa; font-size: 13px; }
QLabel#section { font-size: 13px; font-weight: 650; }
QLabel#eyebrow { font-size: 10px; font-weight: 600; letter-spacing: 1.6px; color: #929299; }
QLabel#chip { background: #1c1c1f; color: #d4d4d8; border: 1px solid #303034; border-radius: 6px; padding: 4px 8px; font-size: 11px; }
QLabel#release-stage { color: #a1a1aa; font-size: 12px; padding-left: 3px; }
QPushButton { background: #19191b; border: 1px solid #36363b; border-radius: 7px; padding: 9px 12px; font-weight: 550; }
QPushButton:hover { background: #29292d; border-color: #626269; }
QPushButton:pressed { background: #38383e; }
QPushButton:checked { background: #f4f4f5; border-color: #f4f4f5; color: #111113; }
QPushButton:disabled { background: #18181b; border-color: #27272a; color: #63636b; }
QPushButton#primary { background: #fafafa; color: #09090b; border-color: #fafafa; font-weight: 650; padding: 10px 18px; }
QPushButton#primary:hover { background: #dedee3; }
QPushButton#primary:disabled { background: #303034; border-color: #303034; color: #88888f; }
QPushButton#ghost { border: none; background: transparent; color: #b7b7c0; padding: 7px; }
QPushButton#ghost:hover { background: #27272a; color: white; }
QFrame#media { border: 1px dashed #43434b; background: #171719; border-radius: 10px; }
QFrame#media:hover, QFrame#media:focus { border-color: #d4d4d8; background: #202023; }
QFrame#media[loaded="true"] { border-style: solid; border-color: #35353b; }
QTabWidget::pane { border: none; background: #101011; }
QTabBar { background: #101011; }
QTabBar::tab { background: #101011; color: #a1a1aa; padding: 13px 15px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #fafafa; border-bottom: 2px solid #fafafa; }
QTabBar::tab:hover { color: #fafafa; background: #1b1b1e; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: #101011; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px; }
QScrollBar::handle:vertical { background: #424249; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #19191c; border: 1px solid #3c3c44; border-radius: 6px; padding: 7px 8px; selection-background-color: #66666f; min-height: 19px; }
QComboBox { padding-right: 22px; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background: #202023; color: #f4f4f5; border: 1px solid #44444b; selection-background-color: #45454e; padding: 4px; }
QSlider::groove:horizontal { border: none; height: 6px; background: #44444d; border-radius: 3px; }
QSlider::add-page:horizontal { background: #44444d; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #d4d4d8; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; background: #fafafa; border: 2px solid #d4d4d8; margin: -6px 0; border-radius: 9px; }
QSlider::handle:horizontal:hover { border-color: white; background: white; }
QSlider:disabled::handle:horizontal { background: #64646b; border-color: #64646b; }
QSlider { min-height: 28px; background: transparent; }
QCheckBox { spacing: 9px; padding: 6px 0; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #71717a; border-radius: 4px; background: #19191c; }
QCheckBox::indicator:checked { background: #fafafa; border: 1px solid #fafafa; image: url(__CHECK__); }
QGroupBox { background: transparent; border: 1px solid #303036; border-radius: 8px; margin-top: 10px; padding-top: 18px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #d4d4d8; }
QProgressBar { background: #26262c; border: none; border-radius: 3px; min-height: 5px; max-height: 5px; }
QProgressBar::chunk { background: #ededf0; border-radius: 3px; }
QToolTip { background: #fafafa; color: #101011; border: none; padding: 7px; }
QSplitter::handle { background: #29292e; width: 1px; }
'''

STYLE += """
QSlider#timeline { min-height: 36px; }
QSlider#timeline::groove:horizontal { height: 4px; margin: 16px 0; background: #44444d; }
QSlider#timeline::add-page:horizontal, QSlider#timeline::sub-page:horizontal { height: 4px; }
QSlider#timeline::handle:horizontal { width: 12px; height: 12px; margin: -5px 0; border-radius: 7px; }
QPushButton#transport { padding: 0; background: transparent; border: 1px solid transparent; }
QPushButton#transport:hover { background: #27272a; border-color: #3c3c44; }
QPushButton#disclosure { text-align: left; padding: 10px; }
QPushButton#disclosure:checked { background: #202023; border-color: #626269; color: #f4f4f5; }
QCheckBox::indicator:hover, QGroupBox::indicator:hover { border-color: #fafafa; }
QCheckBox::indicator:disabled, QGroupBox::indicator:disabled { border-color: #44444b; background: #27272a; }
QCheckBox:focus { color: white; }
QGroupBox::indicator { width: 17px; height: 17px; border: 1px solid #71717a; border-radius: 4px; background: #19191c; }
QGroupBox::indicator:checked { background: #fafafa; border-color: #fafafa; image: url(__CHECK__); }
QComboBox::down-arrow { image: url(__CHEVRON__); width: 16px; height: 16px; }
"""
for token, filename in [('__CHECK__', 'check.svg'), ('__CHEVRON__', 'chevron.svg')]:
    STYLE = STYLE.replace(token, (Path(__file__).with_name('assets') / filename).as_posix())
