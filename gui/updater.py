"""Update dari dalam app: cek otomatis (maks. sekali sehari), download + verifikasi installer, pasang senyap, buka lagi."""
import sys
import threading
import time
import webbrowser

import updates
from gui.common import (T, VERSION, UserError, open_path, org)
from gui.widgets import Dialog


class UpdaterMixin:
    UPDATE_START_DELAY_MS = 4000

    def _init_updater(self):
        self.update_info = None
        if "--updated" in sys.argv:
            self.root.after(800, lambda: self.infobar.show("success", T("upd_done", v=VERSION), timeout=8000))
        elif "--update-failed" in sys.argv:  # installer gagal/dibatalkan; versi lama tetap utuh
            log = org.log_dir() / "update-install.log"
            self.root.after(800, lambda: self.infobar.show(
                "error", T("upd_install_failed_title"), T("upd_install_failed", v=VERSION),
                action=(T("btn_open_log"), lambda: open_path(log if log.exists() else org.log_dir()))))
        self._update_job = self.root.after(self.UPDATE_START_DELAY_MS, self._auto_check_updates)

    # ── cek otomatis ──
    def _auto_check_updates(self):
        if not self.settings.get("auto_update_check", True):
            return
        now = time.time()
        if not updates.check_due(self.settings.get("last_update_check", 0), now):
            return

        def worker():
            try:
                info = updates.check(VERSION)
            except updates.UpdateError as e:
                org.log.info("auto update check: %s", e)  # offline dll.: dicoba lagi saat app dibuka berikutnya
                return
            self.q.put(lambda: self._checked(now))
            if info["newer"]:
                self.q.put(lambda: self._offer_update(info, auto=True))

        threading.Thread(target=worker, daemon=True).start()

    def _checked(self, when):
        self.settings["last_update_check"] = when
        self._save_settings()

    def _reoffer_update(self):
        """Tawaran update tidak hilang setelah UI dibangun ulang (tema, bahasa, pindah monitor)."""
        info = getattr(self, "update_info", None)
        if info and info.get("newer") and self.settings.get("skip_update_version") != info["version"]:
            self.root.after(300, lambda: self._offer_update(info, auto=True))

    def _offer_update(self, info, auto=False):
        self.update_info = info
        if auto and self.settings.get("skip_update_version") == info["version"]:
            return
        self.infobar.show("info", T("upd_available_title", v=info["version"]), T("upd_available_short", cur=VERSION),
                          action=(T("btn_update_now") if self._can_self_install(info) else T("btn_download"),
                                  lambda: self.start_update(info)))

    # ── cek manual (Settings) ──
    def check_updates(self):
        def job():
            try:
                return updates.check(VERSION)
            except updates.UpdateError as e:
                raise UserError(self._update_error_text(e))

        def done(info):
            self._checked(time.time())
            if not info["newer"]:
                self.infobar.show("success", T("upd_latest", v=VERSION), timeout=6000)
                return
            self.update_info = info
            buttons = ([("update", T("btn_update_now"), True)] if self._can_self_install(info) else []) + [
                ("page", T("btn_download"), not self._can_self_install(info)), ("skip", T("btn_skip_version"), False),
                (None, T("btn_later"), False)]
            notes = info["notes"].splitlines()[:30] or None
            msg = T("upd_available_msg_auto" if self._can_self_install(info) else "upd_available_msg", cur=VERSION)
            r = Dialog(self, T("upd_available_title", v=info["version"]), msg, buttons, notes).result
            if r == "update":
                self.start_update(info)
            elif r == "page":
                webbrowser.open(info["url"])
            elif r == "skip":
                self.settings["skip_update_version"] = info["version"]
                self._save_settings()

        self.run_bg(T("task_updates"), job, done, cancellable=False)

    def _can_self_install(self, info) -> bool:
        return bool(info.get("asset")) and updates.can_self_install(org.app_dir(), org.FROZEN)

    @staticmethod
    def _update_error_text(e) -> str:
        key = {"offline": "upd_offline", "no_release": "upd_no_release", "bad_hash": "upd_verify_failed",
               "bad_size": "upd_verify_failed", "bad_source": "upd_verify_failed"}.get(str(e), "upd_failed")
        return T(key, err=e)

    # ── download + install ──
    def start_update(self, info):
        if not self._can_self_install(info):
            webbrowser.open(info["url"])  # versi portable / dari source: unduh manual
            return
        if self.busy:
            self.infobar.show("info", T("busy"), timeout=3000)
            return
        if not self._rules_saved_or_discarded():
            return

        def job():
            self.phase(T("task_download_update", v=info["version"]))
            try:
                return updates.download(info["asset"], progress=self.bytes_progress(), cancel=self.cancel_event)
            except updates.UpdateCancelled:
                raise org.Cancelled()
            except updates.UpdateError as e:
                org.log.warning("update download failed: %s", e)
                raise UserError(self._update_error_text(e))

        def done(path):
            r = Dialog(self, T("upd_ready_title", v=info["version"]), T("upd_ready_msg"),
                       [("install", T("btn_install_restart"), True), (None, T("btn_later"), False)]).result
            if r == "install":
                self._install_update(path, info)

        self.run_bg(T("task_download_update", v=info["version"]), job, done)

    def _rules_saved_or_discarded(self) -> bool:
        if hasattr(self, "confirm_yaml_draft") and not self.confirm_yaml_draft():
            return False
        return not self.dirty or self._ask_save_rules()

    def _install_update(self, path, info):
        # aturan bisa saja diedit selama download berjalan → tanya lagi sebelum app ditutup
        if not self._rules_saved_or_discarded():
            return
        if not updates.verify(path, info["asset"]):  # file di disk diganti/rusak sejak diunduh
            org.log.error("update file changed after download: %s", path)
            self.infobar.show("error", T("err_title"), T("upd_verify_failed", err="changed on disk"))
            return
        if self.watch_active:
            self.watch_active = False
            self.watch_stop.set()
        log_file = org.log_dir() / "update-install.log"
        try:
            updates.launch_installer(path, log_file)
        except OSError as e:
            org.log.error("could not start installer %s", path, exc_info=True)
            self.infobar.show("error", T("err_title"), T("upd_failed", err=e))
            return
        org.log.info("installing update %s from %s", info["version"], path)
        self._shutdown()

    def _ask_save_rules(self) -> bool:
        r = Dialog(self, T("dlg_unsaved_title"), T("dlg_unsaved_msg"),
                   [("save", T("btn_save"), True), ("discard", T("btn_dont_save"), False),
                    (None, T("btn_cancel"), False)]).result
        if r is None:
            return False
        if r == "save":
            return self.save_rules()
        self.dirty = False
        return True
