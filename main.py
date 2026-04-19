import sys
import os

# Asegurar que el directorio actual está en el path de Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    # Crear la aplicación PyQt6
    app = QApplication(sys.path)
    
    # Crear y mostrar la ventana principal
    window = MainWindow()
    window.show()
    
    # Iniciar el bucle de eventos
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
