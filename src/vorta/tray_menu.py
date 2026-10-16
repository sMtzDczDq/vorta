import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCursor, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from vorta.store.models import BackupProfileModel
from vorta.utils import get_asset


class TrayMenu(QSystemTrayIcon):
    def __init__(self, parent: QApplication = None):
        QSystemTrayIcon.__init__(self, parent)
        self.app = parent
        self.set_tray_icon()
        self.menu = QMenu()

        # Workaround to get `activated` signal on Unity: https://stackoverflow.com/a/43683895/3983708
        self.menu.aboutToShow.connect(self.build_menu)

        if sys.platform != 'darwin':
            self.setContextMenu(self.menu)

        self.build_menu()

        self.activated.connect(self.on_activation)
        self._palette_connection = self.app.paletteChanged.connect(lambda p: self.set_tray_icon())
        self.destroyed.connect(self._on_destroyed)
        self.setVisible(True)
        self.show()

    def on_activation(self, reason):
        """
        XDG-compliant tray behavior: right click to open a context menu, and left click to
        restore the application.

        If XDG_CURRENT_DESKTOP isn't set, always open the tray menu (macOS)
        """
        if sys.platform == 'darwin':
            self._show_menu()
        elif reason in [
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ] and os.environ.get('XDG_CURRENT_DESKTOP'):
            self.app.toggle_main_window_visibility()

    def _show_menu(self):
        """
        Show the tray menu manually on macOS.

        We deliberately do not use setContextMenu() on macOS: that makes Qt observe
        the native NSStatusItem menu tracking and read -[NSEvent clickCount] on a
        non-mouse event, raising NSInternalInconsistencyException and aborting the
        app on macOS 26+/27. Popping the menu up ourselves avoids that code path.
        """
        if self.menu.isVisible():
            self.menu.hide()
            return
        # Pop up one event-loop turn later, so the pending mouse-up that triggered
        # the activation does not immediately dismiss the menu again.
        QTimer.singleShot(0, self._popup_menu)

    def _popup_menu(self):
        icon_rect = self.geometry()
        self.menu.popup(icon_rect.bottomLeft() if icon_rect.isValid() else QCursor.pos())

    def build_menu(self):
        """Build system tray menu based on current state."""

        menu = self.menu
        menu.clear()

        open_action = menu.addAction(self.tr('Vorta for Borg Backup'))
        open_action.triggered.connect(self.app.open_main_window_action)

        menu.addSeparator()

        next_task_time = self.app.scheduler.next_job()
        status = menu.addAction(next_task_time)
        status.setEnabled(False)

        if self.app.jobs_manager.is_worker_running():
            status.setText(self.tr('Task in progress'))
            cancel_action = menu.addAction(self.tr('Cancel Backup'))
            cancel_action.triggered.connect(self.app.backup_cancelled_event.emit)
        else:
            status.setText(self.tr('Next Task: %s') % next_task_time)
            profiles = BackupProfileModel.select()
            if profiles.count() > 1:
                profile_menu = menu.addMenu(self.tr('Backup Now'))
                for profile in sorted(profiles, key=lambda p: (p.name.casefold(), p.name)):
                    new_item = profile_menu.addAction(profile.name)
                    new_item.triggered.connect(lambda state, i=profile.id: self.app.create_backup_action(i))
            else:
                profile = profiles.first()
                profile_menu = menu.addAction(self.tr('Backup Now'))
                profile_menu.triggered.connect(lambda state, i=profile.id: self.app.create_backup_action(i))

        menu.addSeparator()

        exit_action = menu.addAction(self.tr('Quit'))
        exit_action.triggered.connect(self.app.quit)

    def set_tray_icon(self, active=False):
        """
        Use white tray icon, when on Gnome or in dark mode.
        Use mask tray icon when on macOS.
        Otherwise use dark icon.
        """
        if sys.platform == 'darwin':
            icon_name = f"icons/hdd-o{'-active' if active else ''}-mask.svg"
            icon = QIcon(QPixmap(QImage.fromData(open(get_asset(icon_name), 'rb').read()).scaledToHeight(128)))
            icon.setIsMask(True)
        else:
            icon_name = f"icons/hdd-o{'-active' if active else ''}.png"
            icon = QIcon(get_asset(icon_name))
        self.setIcon(icon)

    def _on_destroyed(self):
        try:
            self.app.paletteChanged.disconnect(self._palette_connection)
        except (TypeError, RuntimeError):
            pass
