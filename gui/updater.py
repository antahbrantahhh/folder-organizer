"""Update dari dalam app: cek otomatis (maks. sekali sehari), download + verifikasi installer, pasang senyap, buka lagi."""
import sys
import threading
import time
import webbrowser

import updates
from gui.common import (T, VERSION, UserError, org)
from gui.widgets import Dialog


class UpdaterMixin:
    UPDATE_START_DELAY_MS = 4000

    def _init_updater(self):
        self.update_info = None
        if "--updated" in sys.argv:
            self.root.after(800, lambda: self.infobar.show("success", T("upd_done", v=VERSION), timeout=8000))
        self._update_job = self.root.after(self.UPDATE_START_DELAY_MS, self._auto_check_updates)

    # ── cek otomatis ──
    def _auto_check_updates(self):
        if not self.settings.get("auto_update_check", True):
            return
        now = time.time()
        if not updates.check_due(self.settings.get("last_update_check", 0), now):
            return
        self.settings["last_update_check"] = now
        self._save_settings()

        def worker():
            try:
                info = updates.check(VERSION)
            except updates.UpdateError as e:
                org.log.info("auto update check: %s", e)
                return
            if info["newer"]:
                self.q.put(lambda: self._offer_update(info, auto=True))

        threading.Thread(target=worker, daemon=True).start()

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
            self.settings["last_update_check"] = time.time()
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
        if self.dirty and not self._ask_save_rules():
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

    def _install_update(self, path, info):
        if self.watch_active:
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
