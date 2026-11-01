# Folder Organizer (Windows)

Organizer file berbasis aturan: audit → preview → apply → undo. Tidak ada file yang dihapus; duplikat dipindah ke
`_to_delete\` untuk direview manual. GUI gaya Windows 11, dwibahasa (English default / Bahasa Indonesia).

*English: [README.md](README.md)*

## Install
**Installer (disarankan):** jalankan `FolderOrganizer-Setup-<versi>.exe` dari halaman
[Releases](https://github.com/antahbrantahhh/folder-organizer/releases). Install per-user, tanpa hak admin, ada
menu Start dan uninstaller. `rules.yaml` dan riwayat lu tetap ada saat upgrade maupun uninstall.

**Portable:** extract `FolderOrganizer-<versi>-portable.zip` ke mana saja, jalankan `Folder Organizer.exe`.

> .exe belum di-code-sign, jadi SmartScreen bisa menampilkan "Windows protected your PC" saat pertama jalan:
> klik **More info → Run anyway**.

**Dari source:** install Python 3.11+ dari python.org (centang **Add python.exe to PATH**), extract folder ini
(mis. `C:\Tools\folder-organizer\`), lalu double-click `Folder Organizer GUI.bat`. Dependensi diinstall otomatis.

### Build sendiri
1. `build_exe.bat` → `dist\Folder Organizer\Folder Organizer.exe` (±1–2 menit, versi persis dari
   `requirements.lock`). Di Task Manager & taskbar tampil sebagai **Folder Organizer** dengan ikonnya sendiri.
2. Opsional: `build_installer.bat` → `installer\Output\FolderOrganizer-Setup-<versi>.exe`
   (butuh [Inno Setup 6](https://jrsoftware.org/isinfo.php), mis. `winget install JRSoftware.InnoSetup`).

## Cara pakai
| Halaman | Shortcut | Isi |
|---|---|---|
| Overview | Ctrl+1 | Scan: jumlah file, ukuran, file basi, duplikat, tipe file, file terbesar |
| Organize | Ctrl+2 | Preview rencana, pilih item, rapikan |
| Duplicates | Ctrl+3 | Duplikat berdasarkan isi, pilih yang disimpan |
| History | Ctrl+4 | Semua batch + undo batch terakhir |
| Folder labels | Ctrl+5 | Terapkan / hapus deskripsi folder |
| Automation | Ctrl+6 | Rapikan file baru otomatis selama app terbuka |
| Rules | Ctrl+7 | Editor aturan visual + YAML |
| Settings | Ctrl+8 | Tema, bahasa, lama simpan riwayat, update, info app |

**Ctrl+O** ganti folder target · **F5** jalankan ulang scan/preview · **Esc** batalkan proses. Proses panjang
menampilkan progres, estimasi sisa waktu, dan tombol **Cancel**; membatalkan saat memindahkan aman (bisa di-undo).

**CLI** dan menu terminal (`organizer.bat`): lihat [README.md](README.md#using-it).

## Aturan (`rules.yaml`)
Aturan dicek dari atas ke bawah; aturan pertama yang cocok yang dipakai. Kondisi: `category`, `ext`, `name_regex`,
`older_than_days`, `newer_than_days`, `min_size_mb`, `max_size_mb`. `enabled: false` = aturan dimatikan.
`dest: "."` = biarkan di tempat. `{period}` = folder tanggal sesuai `date_format` (default `2026-10`).
- **Project lu:** aturan folder *Known projects* adalah contoh yang nonaktif. Isi `name_regex` dengan nama
  project lu lalu aktifkan (switch *Enabled* di form aturan).
- **Komentar tetap ada** saat menyimpan dari GUI; versi sebelumnya dibackup ke `rules.yaml.bak`.
- **Diedit di luar app?** Kalau `rules.yaml` diubah di Notepad saat app terbuka, tombol Save menanyakan: timpa
  atau muat ulang dari file.

## Label folder
Deskripsi ditulis ke `desktop.ini` (tooltip di Explorer) dan `_README.txt`. Nilainya bisa teks biasa atau
`{en: ..., id: ...}`; app menulis bahasa yang sedang dipakai, dan editor label hanya mengubah bahasa aktif.

## Keamanan & data
- **Satu proses per folder:** GUI, CLI, dan mode watch tidak pernah memindahkan file di folder yang sama
  bersamaan. Lock sisa crash diambil alih otomatis.
- Riwayat undo di `%APPDATA%\FolderOrganizer\state\`, disimpan 90 hari (Settings → History); 20 batch terbaru
  selalu disimpan.
- Log: `%APPDATA%\FolderOrganizer\logs\app.log`.
- **Cek update:** Settings → Updates membandingkan versi lu dengan rilis terbaru di GitHub. Tidak ada yang
  diunduh/diinstall otomatis.

Detail lengkap (kategori, yang otomatis dilewati, struktur kode, development, rilis): [README.md](README.md).
