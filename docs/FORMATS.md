# Disc formats of Daxter for PSP

Everything in this document was measured on the pinned disc
(`config/target.json`): *Daxter* (USA), title id `UCUS98618`, disc version
1.00, disc SHA-1 `6a54c86d201ad5adaec109b84ffa3798c06282cb`.

Every offset below was read from the disc and can be re-derived with
`tools/psp_formats.py`. Nothing here is copied from a leaked source or from
proprietary documentation; the readers are in `tools/psp_formats.py` and are
tested on synthetic data in `tests/test_tools.py`.

---

## 1. The disc layout

```
Daxter.iso                                   ISO 9660, 1 405 845 504 bytes
├── UMD_DATA.BIN                              48 bytes
└── PSP_GAME/
    ├── PARAM.SFO                             472 bytes
    ├── ICON0.PNG, ICON1.PMF, PIC1.PNG, SND0.AT3
    ├── SYSDIR/
    │   ├── EBOOT.BIN                         4 949 392 bytes   ~PSP   (the target)
    │   ├── BOOT.BIN                          4 949 041 bytes   opaque
    │   └── UPDATE/
    │       ├── EBOOT.BIN                     3 951 712 bytes   ~PSP   module "update"
    │       ├── DATA.BIN                      14 809 632 bytes  PSAR
    │       └── PARAM.SFO
    └── USRDIR/
        ├── module/*.prx                      18 PSP runtime modules
        ├── music/*.at3, movies/*.pmf, dialogs/<lang>/*.at3
        └── data/
            ├── *.bin                          342 Pack containers (assets)
            └── <lang>/*.bin                  7 locales x 45 Pack containers
```

The executable is **not** at the root of `PSP_GAME` as on some UMD layouts:
it is in `PSP_GAME/SYSDIR/`. Both `BOOT.BIN` and `EBOOT.BIN` are present,
and they are almost the same size (4 949 041 and 4 949 392 bytes, 351 bytes
apart). `BOOT.BIN` starts with 0x30 zero bytes and is not an ELF; the
relationship between the two files is **not established** and is listed as an
open question in `docs/STATE.md`.

---

## 2. `PARAM.SFO` — the parameter file

The disc parameter file and the update parameter file use the same layout.
The header is 20 bytes:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `00 50 53 46` (`"\0PSF"`) |
| 0x04 | 4 | u32 format version, `0x00000101` |
| 0x08 | 4 | u32 offset of the key table |
| 0x0C | 4 | u32 offset of the data table |
| 0x10 | 4 | u32 number of index entries |

The index follows the header, 16 bytes per entry:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 2 | u16 offset of the key in the key table |
| 0x02 | 2 | u16 format: `0x0204` UTF-8, `0x0404` int32 |
| 0x04 | 2 | u16 length of the value |
| 0x06 | 2 | u16 reserved |
| 0x08 | 4 | u32 size of the value slot, padded |
| 0x0C | 4 | u32 offset of the value in the data table |

The value sits at `data_table_offset + offset`; the slot size is padded to a
multiple of four, which is why a 10-byte string occupies a 16-byte slot.
The keys are NUL-terminated and packed in the key table in index order.

> **Correction worth recording.** The obvious reading — that the value offset
> is implied by accumulating the padded sizes — is wrong for this file: the
> padded sizes are stored at `0x08` and the explicit offsets at `0x0C`. The
> first reader written for this project accumulated the sizes and read every
> string from the wrong place; the explicit offset field is what the disc
> actually uses.

Values read from the disc parameter file:

| Key | Value |
| --- | --- |
| `BOOTABLE` | 1 |
| `CATEGORY` | `UG` |
| `DISC_ID` | `UCUS98618` |
| `DISC_NUMBER` | 1 |
| `DISC_TOTAL` | 1 |
| `DISC_VERSION` | `1.00` |
| `PARENTAL_LEVEL` | 4 |
| `PSP_SYSTEM_VER` | `2.60` |
| `REGION` | `0x8000` (America) |
| `TITLE` | `Daxter` |

The update parameter file has `DISC_ID = MSTKUPDATE`, `CATEGORY = MG` and
`TITLE = "PSP® Update ver 2.60"`.

---

## 3. `~PSP` — the encrypted executable

Both `EBOOT.BIN` files start with the magic `~PSP` (`0x5053507E`).

| Offset | Size | Disc executable | Update executable |
| --- | --- | --- | --- |
| 0x00 | 4 | `~PSP` | `~PSP` |
| 0x04 | 4 | `0x00000000` | `0x00000800` |
| 0x08 | 2 | `0x0101` | `0x0101` |
| 0x0A | n | module name `dax` | module name `update` |

The payload behind the header is encrypted with a key derived from the disc
identifier, and the offset at `0x04` differs between the two files, so the
header parameter is not a common payload offset. **The exact boundary of the
encrypted payload is not established here**; recovering the ELF is done with
a PSP implementation, not with a header offset.

Decryption is delegated to a local PPSSPP build, which exports:

```c
int pspDecryptPRX(const unsigned char *encrypted, unsigned char *output,
                   unsigned int size, const unsigned char *key);
```

The same routine is used by the sibling project
[`anthonyhfm/daxter-recompiled`](https://github.com/anthonyhfm/daxter-recompiled)
and by `psprism`. The key is passed as `NULL`, which asks the implementation
to derive it from the module.

---

## 4. `PSAR` — the update archive

`PSP_GAME/SYSDIR/UPDATE/DATA.BIN` starts with the magic `PSAR`.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `PSAR` |
| 0x04 | 4 | u32 version, `3` |
| 0x08 | 4 | u32 offset of the member table |
| 0x0C | 4 | u32 member count, `1` |
| 0x10 | 16 | opaque signature |

The member table is recorded at offset `0x00E1FA10`, that is 16 bytes before
the end of the 14 809 632-byte file. **The bytes there have high entropy and
do not decode as offsets, sizes and names**: the tail of the file is
encrypted with a disc-derived key, exactly like the executable.

The reader therefore reports the header and leaves the member list empty
rather than inventing one. Recovering the members needs the same disc key
as the executable.

---

## 5. `Pack` — the asset container

Every file under `PSP_GAME/USRDIR/data` is a `Pack` container. This is the
format of the assets of the Insomniac engine, and it is **not** a code
container.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `Pack` |
| 0x04 | 2 | u16 version major, `3` |
| 0x06 | 2 | u16 version minor, `2` or `4` |
| 0x08 | 4 | u32, meaning not established |
| 0x0C | 4 | u32 entry count, **including** the header pseudo-entry |
| 0x10 | 20 | five header words, meaning not established |
| 0x24 | 4 | u32 end of the entry table, and the start of the blob area |
| 0x24+ | 16 | entries |

Each entry is 16 bytes:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | u32 offset of the blob in the file |
| 0x04 | 4 | u32 size of the blob |
| 0x08 | 4 | u32 type |
| 0x0C | 4 | u32 identifier |

The count at `0x0C` is one larger than the number of entries, because the
header itself is described by an entry. For `engine_assets.bin` the count is
7 and there are 6 entries.

The word at `0x24` is the offset of the blob area: on every container of
the disc it is also the offset of the first entry, which is how the reader
uses it. The word at `0x08` is **not** that offset — it holds `0x28`,
`0x7FD` and `0xAE0` on `daxter.bin`, `engine_assets.bin` and
`breezy_valley.bin` respectively, and no relation to the blob area has been
established.

Two versions are in use: `3.2` for the three shared containers
(`daxter.bin`, `engine_assets.bin`, `frontend_assets.bin`) and `3.4` for the
level and locale containers.

### Type codes and payload magics

The census over the 342 containers of the disc — **19 255 blobs** in all —
gives:

| Type | Blobs | Payload magic | Reading |
| --- | --- | --- | --- |
| 3 | 9 193 | `RADI` (8 831) | lighting / radiance block |
| 9 | 3 841 | `CfCm` | class mesh, textured |
| 5 | 2 691 | `CfCm` | class mesh, dense |
| 2 | 1 646 | `CfCm` | class mesh, primary |
| 43 | 1 415 | float data | vertex or point table |
| 23 | 283 | `GmTx` | texture block; the reading is provisional |
| 11 | 132 | `SBlk` | stream block |
| 4 | 52 | `CfCm` | class mesh, single block |
| 61 | 2 | raw | texture page |

By payload magic alone: `RADI` 8 831, `CfCm` 8 230, `GmTx` 283. The
remaining blobs carry no printable magic. Type 23 and the `GmTx` magic only
appear in the locale containers, not in the level containers.

The `CfCm` blobs share a 0x30-byte header:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `CfCm` |
| 0x04 | 4 | u32 section count, `0x0C` |
| 0x14 | 4 | u32 payload size |
| 0x18 | 4 | u32 `0x40`, the offset of the first payload section |
| 0x30+ | 24 | u32 section offsets, sizes and strides |

### These containers carry no code

This is the load-bearing measurement of the whole project, so it is worth
stating exactly what was done:

1. every `CfCm` blob of the 75 of `daxter.bin` was scanned for the Allegrex
   function prologue `addiu $sp, $sp, -N` (opcode `0x27BDxxxx`): **0 hits in
   75 blobs**;
2. the first 16 KiB of each of the three largest `CfCm` blobs was scanned for
   32-bit words in the PSP user range `0x08800000`–`0x08FFFFFF`: **0 to 1
   hits**, against the thousands of such words a code section would hold.

The code is therefore **only** in the executable. On the PS2 games of the
same studio the code sits in packed level overlays; on Daxter for PSP it
does not. The `Pack` containers are an asset research problem.

---

## 6. What is still open

* the payload boundary of the `~PSP` header, and the derivation of the disc
  key;
* the member table of the `PSAR` archive;
* the meaning of the five header words of `Pack`, and of the three words
  inside the `CfCm` header;
* the relation between `BOOT.BIN` and `EBOOT.BIN`;
* the `.at3` audio and `.pmf` movie containers, which are the same on every
  PSP title and are therefore not a Daxter-specific problem.
