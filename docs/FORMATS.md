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

Both `EBOOT.BIN` files start with the magic `~PSP` (`0x5053507E`). The
container is a **PSP module header**: the PSP firmware reads the fields
below to find and unlock the payload.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `~PSP` |
| 0x04 | 2 | u16 attribute |
| 0x06 | 2 | u16 comp_attribute; bit 0 marks a compressed payload |
| 0x08 | 2 | u16 module version, `0x0101` on the pinned target |
| 0x0A | 28 | the module name, NUL padded: `dax`, `updater` |
| 0x26 | 1 | u8 version |
| 0x27 | 1 | u8 segment count |
| 0x28 | 4 | u32 elf_size |
| 0x2C | 4 | u32 psp_size, the size of the whole container |
| 0x30 | 4 | u32 entry point |
| 0x34 | 4 | u32 offset of the module info |
| 0x38 | 4 | u32 bss_size |
| 0x3C | 8 | u16 segment alignment, four entries |
| 0x44 | 16 | u32 segment address, four entries |
| 0x54 | 16 | u32 segment size, four entries |
| 0x64 | 20 | u32 reserved, five entries |
| 0x78 | 4 | u32 devkit version |
| 0x7C | 4 | u32 decrypt mode |
| 0x80 | 48 | key data 0 |
| 0xB0 | 4 | s32 comp_size |
| 0xB4 | 12 | reserved |
| 0xC0 | 16 | key data 1 |
| 0xD0 | 4 | u32 **the PRX tag** |
| 0xD4 | 88 | the scheck: the SHA-1 and the signature |
| 0x12C | 4 | u32 key data 2 |
| 0x130 | 4 | u32 oe_tag |
| 0x134 | 28 | key data 3 |

Read on the pinned disc:

| Field | Disc executable | Update executable |
| --- | --- | --- |
| module name | `dax` | `updater` |
| elf_size | 4 949 041 | 3 951 368 |
| psp_size | 4 949 392 | 3 951 712 |
| decrypt mode | 9 | 3 |
| **tag** | **`0xC0CB167C`** | `0x02000000` |

### The decryption

The payload behind the header is encrypted with the KIRK engine of the PSP.
`tools/decrypt_psp.py` reproduces it; `tools/psp_crypto.py` holds the key
material. The steps, for the type 0 and type 1 PRX:

1. look the tag up in the tag table; it gives a 144-byte seed and a KIRK
   key slot;
2. for a type 1 PRX, decrypt 0xA0 bytes of the **rearranged** header with
   the key of that slot: the SHA-1, the unused block and the first 0x70
   bytes of the kirk block are adjacent in the file but not in the
   rearranged header, so they have to be assembled before they can be
   decrypted;
3. check the SHA-1 of the header against the one in the file — this is
   what tells a correct decryption from a wrong one;
4. unlock the 0x70-byte KIRK command 1 header with the seed;
5. run the KIRK command 1: recover the per-module AES and CMAC keys from
   the header with the KIRK1 key, check the two CMAC hashes over the header
   and over the payload, and decrypt the payload.

The pinned target is a **type 1** PRX. The type is decided by the hash
matching, not by the decrypt mode: the disc executable's mode is 9 and the
update's is 3, and both are type 1 and type 0 respectively.

### `BOOT.BIN` is the destination buffer

`BOOT.BIN` is 4 949 041 bytes — **exactly the `elf_size` of the
executable** — and it is **entirely zeroed**: not one non-zero byte in the
whole file. It is not an older version of the executable, and it is not a
compressed one. It is the buffer the firmware decrypts the executable into,
shipped on the disc so the PSP does not have to allocate one.

This is the answer to the question the first version of this document left
open, and it is worth recording because the file's name invites the wrong
guess.

### The `UPDATE` folder is the firmware updater, not a game patch

`PSP_GAME/SYSDIR/UPDATE/` holds the **PSP system firmware updater** that
ships on the disc, not a later revision of *Daxter*:

* its parameter file has `DISC_ID = MSTKUPDATE`, `CATEGORY = MG` and
  `TITLE = "PSP® Update ver 2.60"`;
* its executable is named `updater`;
* its archive is the `PSAR` of a firmware image.

So there is **one** target, not two: the disc executable, version 1.00.

---

## 4. `PSAR` — the update archive

`PSP_GAME/SYSDIR/UPDATE/DATA.BIN` starts with the magic `PSAR`.

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | magic `PSAR` |
| 0x04 | 1 | u8 version, `3` |
| 0x08 | 4 | u32 total length of the records |
| 0x10 | — | the records begin here |

The records are a flat sequence, each made of an encrypted block, an entry
description and the file contents, and the whole thing is encrypted with a
disc-derived key. The bytes at the recorded table offset have high entropy
and do not decode as offsets, sizes and names.

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

## 6. The decrypted executable

The ELF the decryption yields is 4 949 041 bytes, and it is a **PSP PRX**:

| Field | Value |
| --- | --- |
| e_type | `0xFFA0`, the type the PSP SDK gives to a PRX |
| e_machine | 8, MIPS |
| e_entry | `0x00000000` |
| e_phnum | 2 |
| e_shnum | 60 |
| module name | `dax` |
| SHA-1 | `4a348e91e45fb17c23f2e8b72ce67113e7c4e4c2` |
| SHA-256 | `df13fd9d044044e0c17198b2837bdf6aacd8a9d1ee85680670a40e00590d67d2` |

The two segments are:

| Segment | File offset | Virtual address | File size | Memory size | Flags |
| --- | --- | --- | --- | --- | --- |
| 0 | `0x74` | `0x00000000` | 3 553 940 | 3 553 940 | read, execute |
| 1 | `0x363B08` | `0x00363A98` | 304 772 | 568 288 | read, write |

The 60 sections are the usual PRX ones: `.text` of 3 335 156 bytes, an
`.eh_frame`, the `sceStub` sections, and the pairs of `SHT_PSPPCREL`
sections that hold the unrelocated data beside their relocated twins.

**There is no symbol table.** The ELF's symbol table section holds 16 bytes:
one null symbol and nothing else. The functions therefore have neither names
nor sizes, and the inventory has to be recovered from the code.

The only names in the file are in the **module info**, at `0x0032ED54`:
the module name and the list of the 25 libraries the game imports.

```
sceUtility        IoFileMgrForUser   LoadExecForUser    ModuleMgrForUser
StdioForUser      SysMemUserForUser  ThreadManForUser   UtilsForUser
sceSuspendForUser sceAudio           Kernel_Library     sceCtrl
sceDisplay        sceGe_user         scePower            sceUsb
sceMpeg           sceUmdUser         sceImpose           sceWlanDrv
sceNet            sceNetAdhoc        sceNetAdhocctl      sceSasCore
sceAtrac3plus
```

### The function candidates

`tools/function_inventory.py` scans the executable segment for the place
where the code opens a stack frame the way the Allegrex compiler does —
`addiu $sp, $sp, -N` — and reports **14 655 candidates**, of which **8 794**
save the return address within the next four instructions.

Those are candidates, not functions. A frame can be opened by a function
that never returns, by a jump table, or by a hand-written block, and the
inventory is the input of a review rather than its result. The table is
`config/boot/functions.tsv`.

The prologue of a function of the target, as read from the code, is the
usual one:

```
addiu $sp, $sp, -0x30
sw    $s1, 0x24($sp)
move  $s1, $a0
sw    $s0, 0x20($sp)
sw    $ra, 0x28($sp)
```

Note that the return address is saved *after* the callee-saved registers,
not immediately after the frame is opened — which is why the scan looks a
few instructions ahead.

---

## 7. What is still open

* the derivation of the disc key, and with it the members of the `PSAR`
  archive;
* the meaning of the five header words of `Pack`, and of the three words
  inside the `CfCm` header;
* the `.at3` audio and `.pmf` movie containers, which are the same on every
  PSP title and are therefore not a Daxter-specific problem;
* the boundary of each of the 14 655 function candidates: nothing has been
  reviewed yet, so no function is known to exist yet, let alone to be
  named.
