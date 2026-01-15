from PySide6 import QtWidgets, QtWebEngineWidgets
import sys
import map

def show_map(map):
    app = QtWidgets.QApplication(sys.argv)
    view = QtWebEngineWidgets.QWebEngineView()
    view.setHtml(map.get_root().render())
    view.resize(800, 600)
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    show_map(map.build_map_html())
