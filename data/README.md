# Offline Component Database (`easyeda-std.elib`)

Kaibridge includes sub-millisecond offline component sourcing support powered by an SQLite database (`easyeda-std.elib`) indexing over 16,600 pre-verified JLCPCB parts with manufacturer part numbers (MPNs), packages, and LCSC C-Part IDs.

---

## Download & Setup

Because the uncompressed SQLite database is **~467 MB** (exceeding GitHub's 100 MB commit limit), it is hosted as a compressed asset under GitHub Releases.

### 1. Direct Download Link
* **Release Asset:** [easyeda-std.elib.zip](https://github.com/ShahMdAbid/Kaibridge/releases/download/v2.1.0/easyeda-std.elib.zip) (~142 MB compressed)
* **Release Tag:** [`v2.1.0`](https://github.com/ShahMdAbid/Kaibridge/releases/tag/v2.1.0)

### 2. Extraction Instructions
1. Download `easyeda-std.elib.zip`.
2. Extract the archive directly into this directory:
   ```text
   Kaibridge/
   └── data/
       ├── README.md
       └── easyeda-std.elib   <-- Place extracted database here
   ```
3. Kaibridge's path resolver (`kaibridge.core.paths.find_easyeda_db()`) will automatically detect and query it in `< 1ms`.

---

## Automatic Fallbacks (Zero-Setup)

If `data/easyeda-std.elib` is not present, Kaibridge automatically and seamlessly falls back through the following hierarchy:
1. **Local EasyEDA Pro Installations:** Scans standard desktop installation directories (`%LOCALAPPDATA%\Programs\easyeda-pro\...`, `C:\Program Files\easyeda-pro\...`, etc.).
2. **Golden Master Part Cache:** Uses the in-memory SQLite catalog embedded in `kaibridge.sourcing.parts_db` for zero-fee JLCPCB basic passives and standard ICs.
3. **On-Demand LCSC Downloads:** Downloads missing symbols, footprints, and 3D models headlessly via `easyeda2kicad --lcsc_id <ID>`.
