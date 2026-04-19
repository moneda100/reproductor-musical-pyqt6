class ThemeManager:
    """Administra los temas de estilo (QSS) de la aplicación con estética premium."""
    
    # --- VARIABLES DE DISEÑO (Simuladas en QSS) ---
    COMMON_STYLE = """
    * { font-family: 'Segoe UI', 'Inter', sans-serif; }
    /* Paneles y Layouts */
    QMainWindow { background-color: {BG}; }
    QSplitter::handle { background: transparent; }
    QWidget#ControlPanel { 
        background-color: {BG_LIST}; 
        border-top: 1px solid {BORDER_SUBTLE};
    }
    
    /* Etiquetas */
    QLabel { color: {TEXT_MAIN}; font-size: 13px; }
    QLabel#TitleLabel { font-size: 22px; font-weight: 800; color: {TEXT_MAIN}; }
    QLabel#MutedLabel { color: {TEXT_MUTED}; font-size: 15px; }
    QLabel#StatusLabel { color: {PRIMARY}; font-size: 11px; font-weight: bold; }
    
    /* Botones Pro */
    QPushButton { 
        background-color: {PRIMARY}; 
        color: {BTN_TEXT}; 
        border-radius: 12px; 
        font-weight: 600; 
        padding: 8px 16px; 
        border: none; 
        font-size: 13px;
    }
    QPushButton:hover { background-color: {PRIMARY_LIGHT}; }
    QPushButton:pressed { background-color: {PRIMARY_DARK}; }
    
    QPushButton#SecondaryBtn { 
        background-color: {SECONDARY}; 
        color: {TEXT_MUTED}; 
    }
    QPushButton#SecondaryBtn:hover { 
        background-color: {SECONDARY_HOVER}; 
        color: {TEXT_MAIN}; 
    }
    
    /* Botones de Reproducción Especiales */
    QPushButton#PlayBtn { 
        background-color: {PRIMARY}; 
        color: white; 
        font-size: 28px; 
        border-radius: 35px; 
        min-width: 70px; 
        min-height: 70px;
    }
    QPushButton#ControlBtn { 
        background-color: transparent; 
        color: {TEXT_MUTED}; 
        font-size: 18px;
        border-radius: 20px;
    }
    QPushButton#ControlBtn:hover { 
        background-color: {SECONDARY_HOVER}; 
        color: {TEXT_MAIN};
    }
    QPushButton#ToggleBtn:checked { 
        color: {PRIMARY}; 
        background-color: {SECONDARY_HOVER};
    }

    /* Listas y Contenedores */
    QListWidget { 
        background-color: {BG_LIST}; 
        color: {TEXT_MUTED}; 
        border: none; 
        border-radius: 12px; 
        padding: 10px;
        outline: none;
    }
    QListWidget::item { 
        padding: 12px; 
        border-radius: 8px; 
        margin-bottom: 4px;
        border-bottom: 1px solid {BORDER_SUBTLE};
    }
    QListWidget::item:hover { background-color: {ITEM_HOVER}; }
    QListWidget::item:selected { 
        background-color: {ITEM_SELECTED}; 
        color: {PRIMARY}; 
        font-weight: bold;
    }

    /* Tabs Modernos */
    QTabWidget::pane { border: none; top: -1px; background: transparent; }
    QTabBar::tab {
        background: transparent;
        color: {TEXT_MUTED};
        padding: 10px 20px;
        font-weight: 600;
        border-bottom: 2px solid transparent;
    }
    QTabBar::tab:selected {
        color: {PRIMARY};
        border-bottom: 2px solid {PRIMARY};
    }
    QTabBar::tab:hover { color: {TEXT_MAIN}; }

    /* Inputs y Sliders */
    QLineEdit { 
        background-color: {BG_INPUT}; 
        color: {TEXT_MAIN}; 
        border: 1px solid {BORDER_SUBTLE}; 
        border-radius: 18px; 
        padding: 8px 15px; 
        selection-background-color: {PRIMARY};
    }
    QLineEdit:focus { border: 1px solid {PRIMARY}; }

    QSlider::groove:horizontal { 
        border: none; 
        height: 4px; 
        background: {SECONDARY}; 
        border-radius: 2px; 
    }
    QSlider::sub-page:horizontal { background: {PRIMARY}; border-radius: 2px; }
    QSlider::handle:horizontal { 
        background: {TEXT_MAIN}; 
        width: 14px; 
        height: 14px; 
        margin: -5px 0; 
        border-radius: 7px; 
    }
    
    /* ScrollBars */
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: {SECONDARY};
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    """

    DARK_TOKENS = {
        "BG": "#0F0F0F",
        "BG_LIST": "#161616",
        "BG_INPUT": "#1E1E1E",
        "PRIMARY": "#1DB954",
        "PRIMARY_LIGHT": "#1ED760",
        "PRIMARY_DARK": "#15883E",
        "SECONDARY": "#282828",
        "SECONDARY_HOVER": "#3E3E3E",
        "TEXT_MAIN": "#FFFFFF",
        "TEXT_MUTED": "#B3B3B3",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#252525",
        "ITEM_HOVER": "#2A2A2A",
        "ITEM_SELECTED": "#282828"
    }

    LIGHT_TOKENS = {
        "BG": "#F2F3F5",
        "BG_LIST": "#FFFFFF",
        "BG_INPUT": "#E3E5E8",
        "PRIMARY": "#5865F2",
        "PRIMARY_LIGHT": "#6773F3",
        "PRIMARY_DARK": "#4752C4",
        "SECONDARY": "#EBEDEF",
        "SECONDARY_HOVER": "#D1D3D6",
        "TEXT_MAIN": "#060607",
        "TEXT_MUTED": "#4E5058",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#EBEDEF",
        "ITEM_HOVER": "#F2F3F5",
        "ITEM_SELECTED": "#E3E5E8"
    }

    CYBERPUNK_TOKENS = {
        "BG": "#050505",
        "BG_LIST": "#0A0A0A",
        "BG_INPUT": "#121212",
        "PRIMARY": "#FF0055",
        "PRIMARY_LIGHT": "#FF3377",
        "PRIMARY_DARK": "#CC0044",
        "SECONDARY": "#1A1A1A",
        "SECONDARY_HOVER": "#2A2A2A",
        "TEXT_MAIN": "#00FFEA",
        "TEXT_MUTED": "#00AA9A",
        "BTN_TEXT": "white",
        "BORDER_SUBTLE": "#333",
        "ITEM_HOVER": "#121212",
        "ITEM_SELECTED": "#1A1A1A"
    }

    @staticmethod
    def get_theme(name: str = "dark") -> str:
        name = name.lower()
        if name == "light":
            tokens = ThemeManager.LIGHT_TOKENS
        elif name == "cyberpunk":
            tokens = ThemeManager.CYBERPUNK_TOKENS
        else:
            tokens = ThemeManager.DARK_TOKENS
            
        style = ThemeManager.COMMON_STYLE
        for key, val in tokens.items():
            style = style.replace("{" + key + "}", val)
        return style
