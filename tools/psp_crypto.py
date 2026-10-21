#!/usr/bin/env python3
"""The KIRK primitives of the PlayStation Portable, and the key material.

This module holds the three things the ``~PSP`` decryption needs:

* the **key vault**, the 128 AES-128 keys of the KIRK engine, indexed by key
  slot;
* the **KIRK1 key**, the key that wraps the per-module AES key inside a
  KIRK command 1 header;
* the **tag keys**, the per-tag 144-byte seed blocks that the PRX decrypter
  expands into the xor buffer of a decryption.

and the two primitives built on them: AES-128-CBC with a zero IV, which is
what ``kirk7`` is, and AES-CMAC, which the command 1 header is checked with.

Provenance
----------

The key material and the layout of the PRX header come from **PPSSPP**, the
open-source reference implementation of the PSP, and were first published by
the JPCSP and PSARDUMPER projects. PPSSPP is GPL-2.0-or-later; this file is
distributed under the GPL-3.0-or-later of this repository, which the
GPL-2.0-or-later licence of PPSSPP permits. See ``THIRD_PARTY_NOTICES.md``.

The decryption *algorithm* in ``tools/decrypt_psp.py`` is this project's own
work, written from the published description of the format.

Requirements
------------

``pycryptodome`` for AES. See ``requirements.txt``.
"""

from __future__ import annotations

from Crypto.Cipher import AES

#: The key vault: 128 AES-128 keys, indexed by key slot. Slot 0x5D is the
#: one the retail executables of the 2.xx firmware use.
KEYVAULT: tuple[bytes, ...] = (
    bytes.fromhex("2C 92 E5 90 2B 86 C1 06 B7 2E EA 6C D4 EC 72 48"),
    bytes.fromhex("05 8D C8 0B 33 A5 BF 9D 56 98 FA E0 D3 71 5E 1F"),
    bytes.fromhex("B8 13 C3 5E C6 44 41 E3 DC 3C 16 F5 B4 5E 64 84"),
    bytes.fromhex("98 02 C4 E6 EC 9E 9E 2F FC 63 4C E4 2F BB 46 68"),
    bytes.fromhex("99 24 4C D2 58 F5 1B CB B0 61 9C A7 38 30 07 5F"),
    bytes.fromhex("02 25 D7 BA 63 EC B9 4A 9D 23 76 01 B3 F6 AC 17"),
    bytes.fromhex("60 99 F2 81 70 56 0E 5F 74 7C B5 20 C0 CD C2 3C"),
    bytes.fromhex("76 36 8B 43 8F 77 D8 7E FE 5F B6 11 59 39 88 5C"),
    bytes.fromhex("14 A1 15 EB 43 4A 1B A4 90 5E 03 B6 17 A1 5C 04"),
    bytes.fromhex("E6 58 03 D9 A7 1A A8 7F 05 9D 22 9D AF 54 53 D0"),
    bytes.fromhex("BA 34 80 B4 28 A7 CA 5F 21 64 12 F7 0F BB 73 23"),
    bytes.fromhex("72 AD 35 AC 9A C3 13 0A 77 8C B1 9D 88 55 0B 0C"),
    bytes.fromhex("84 85 C8 48 75 08 43 BC 9B 9A EC A7 9C 7F 60 18"),
    bytes.fromhex("B5 B1 6E DE 23 A9 7B 0E A1 7C DB A2 DC DE C4 6E"),
    bytes.fromhex("C8 71 FD B3 BC C5 D2 F2 E2 D7 72 9D DF 82 68 82"),
    bytes.fromhex("0A BB 33 6C 96 D4 CD D8 CB 5F 4B E0 BA DB 9E 03"),
    bytes.fromhex("32 29 5B D5 EA F7 A3 42 16 C8 8E 48 FF 50 D3 71"),
    bytes.fromhex("46 F2 5E 8E 4D 2A A5 40 73 0B C4 6E 47 EE 6F 0A"),
    bytes.fromhex("5D C7 11 39 D0 19 38 BC 02 7F DD DC B0 83 7D 9D"),
    bytes.fromhex("51 DD 65 F0 71 A4 E5 EA 6A AF 12 19 41 29 B8 F4"),
    bytes.fromhex("03 76 3C 68 65 C6 9B 0F FE 8F D8 EE A4 36 16 A0"),
    bytes.fromhex("7D 50 B8 5C AF 67 69 F0 E5 4A A8 09 8B 0E BE 1C"),
    bytes.fromhex("72 68 4B 32 AC 3B 33 2F 2A 7A FC 9E 14 D5 6F 6B"),
    bytes.fromhex("20 1D 31 96 4A D9 9F BF 32 D5 D6 1C 49 1B D9 FC"),
    bytes.fromhex("F8 D8 44 63 D6 10 D1 2A 44 8E 96 90 A6 BB 0B AD"),
    bytes.fromhex("5C D4 05 7F A1 30 60 44 0A D9 B6 74 5F 24 4F 4E"),
    bytes.fromhex("F4 8A D6 78 59 9C 22 C1 D4 11 93 3D F8 45 B8 93"),
    bytes.fromhex("CA E7 D2 87 A2 EC C1 CD 94 54 2B 5E 1D 94 88 B2"),
    bytes.fromhex("DE 26 D3 7A 39 95 6C 2A D8 C3 A6 AF 21 EB B3 01"),
    bytes.fromhex("7C B6 8B 4D A3 8D 1D D9 32 67 9C A9 9F FB 28 52"),
    bytes.fromhex("A0 B5 56 B4 69 AB 36 8F 36 DE C9 09 2E CB 41 B1"),
    bytes.fromhex("93 9D E1 9B 72 5F EE E2 45 2A BC 17 06 D1 47 69"),
    bytes.fromhex("A4 A4 E6 21 38 2E F1 AF 7B 17 7A E8 42 AD 00 31"),
    bytes.fromhex("C3 7F 13 E8 CF 84 DB 34 74 7B C3 A0 F1 9D 3A 73"),
    bytes.fromhex("2B F7 83 8A D8 98 E9 5F A5 F9 01 DA 61 FE 35 BB"),
    bytes.fromhex("C7 04 62 1E 71 4A 66 EA 62 E0 4B 20 3D B8 C2 E5"),
    bytes.fromhex("C9 33 85 9A AB 00 CD CE 4D 8B 8E 9F 3D E6 C0 0F"),
    bytes.fromhex("18 42 56 1F 2B 5F 34 E3 51 3E B7 89 77 43 1A 65"),
    bytes.fromhex("DC B0 A0 06 5A 50 A1 4E 59 AC 97 3F 17 58 A3 A3"),
    bytes.fromhex("C4 DB AE 83 E2 9C F2 54 A3 DD 37 4E 80 7B F4 25"),
    bytes.fromhex("BF AE EB 49 82 65 C5 7C 64 B8 C1 7E 19 06 44 09"),
    bytes.fromhex("79 7C EC C3 B3 EE 0A C0 3B D8 E6 C1 E0 A8 B1 A4"),
    bytes.fromhex("75 34 FE 0B D6 D0 C2 8D 68 D4 E0 2A E7 D5 D1 55"),
    bytes.fromhex("FA B3 53 26 97 4F 4E DF E4 C3 A8 14 C3 2F 0F 88"),
    bytes.fromhex("EC 97 B3 86 B4 33 C6 BF 4E 53 9D 95 EB B9 79 E4"),
    bytes.fromhex("B3 20 A2 04 CF 48 06 29 B5 DD 8E FC 98 D4 17 7B"),
    bytes.fromhex("5D FC 0D 4F 2C 39 DA 68 4A 33 74 ED 49 58 A7 3A"),
    bytes.fromhex("D7 5A 54 22 CE D9 A3 D6 2B 55 7D 8D E8 BE C7 EC"),
    bytes.fromhex("6B 4A EE 43 45 AE 70 07 CF 8D CF 4E 4A E9 3C FA"),
    bytes.fromhex("2B 52 2F 66 4C 2D 11 4C FE 61 31 8C 56 78 4E A6"),
    bytes.fromhex("3A A3 4E 44 C6 6F AF 7B FA E5 53 27 EF CF CC 24"),
    bytes.fromhex("2B 5C 78 BF C3 8E 49 9D 41 C3 3C 5C 7B 27 96 CE"),
    bytes.fromhex("F3 7E EA D2 C0 C8 23 1D A9 9B FA 49 5D B7 08 1B"),
    bytes.fromhex("70 8D 4E 6F D1 F6 6F 1D 1E 1F CB 02 F9 B3 99 26"),
    bytes.fromhex("0F 67 16 E1 80 69 9C 51 FC C7 AD 6E 4F B8 46 C9"),
    bytes.fromhex("56 0A 49 4A 84 4C 8E D9 82 EE 0B 6D C5 7D 20 8D"),
    bytes.fromhex("12 46 8D 7E 1C 42 20 9B BA 54 26 83 5E B0 33 03"),
    bytes.fromhex("C4 3B B6 D6 53 EE 67 49 3E A9 5F BC 0C ED 6F 8A"),
    bytes.fromhex("2C C3 CF 8C 28 78 A5 A6 63 E2 AF 2D 71 5E 86 BA"),
    bytes.fromhex("83 3D A7 0C ED 6A 20 12 D1 96 E6 FE 5C 4D 37 C5"),
    bytes.fromhex("C7 43 D0 67 42 EE 90 B8 CA 75 50 35 20 AD BC CE"),
    bytes.fromhex("8A E3 66 3F 8D 9E 82 A1 ED E6 8C 9C E8 25 6D AA"),
    bytes.fromhex("7F C9 6F 0B B1 48 5C A5 5D D3 64 B7 7A F5 E4 EA"),
    bytes.fromhex("91 B7 65 78 8B CB 8B D4 02 ED 55 3A 66 62 D0 AD"),
    bytes.fromhex("28 24 F9 10 1B 8D 0F 7B 6E B2 63 B5 B5 5B 2E BB"),
    bytes.fromhex("30 E2 57 5D E0 A2 49 CE E8 CF 2B 5E 4D 9F 52 C7"),
    bytes.fromhex("5E E5 04 39 62 32 02 FA 85 39 3F 72 BB 77 FD 1A"),
    bytes.fromhex("F8 81 74 B1 BD E9 BF DD 45 E2 F5 55 89 CF 46 AB"),
    bytes.fromhex("7D F4 92 65 E3 FA D6 78 D6 FE 78 AD BB 3D FB 63"),
    bytes.fromhex("74 7F D6 2D C7 A1 CA 96 E2 7A CE FF AA 72 3F F7"),
    bytes.fromhex("1E 58 EB D0 65 BB F1 68 C5 BD F7 46 BA 7B E1 00"),
    bytes.fromhex("24 34 7D AF 5E 4B 35 72 7A 52 27 6B A0 54 74 DB"),
    bytes.fromhex("09 B1 C7 05 C3 5F 53 66 77 C0 EB 36 77 DF 83 07"),
    bytes.fromhex("CC BE 61 5C 05 A2 00 33 37 8E 59 64 A7 DD 70 3D"),
    bytes.fromhex("0D 47 50 BB FC B0 02 81 30 E1 84 DE A8 D4 84 13"),
    bytes.fromhex("0C FD 67 9A F9 B4 72 4F D7 8D D6 E9 96 42 28 8B"),
    bytes.fromhex("7A D3 1A 8B 4B EF C2 C2 B3 99 01 A9 FE 76 B9 87"),
    bytes.fromhex("BE 78 78 17 C7 F1 6F 1A E0 EF 3B DE 4C C2 D7 86"),
    bytes.fromhex("7C D8 B8 91 91 0A 43 14 D0 53 3D D8 4C 45 BE 16"),
    bytes.fromhex("32 72 2C 88 07 CF 35 7D 4A 2F 51 19 44 AE 68 DA"),
    bytes.fromhex("7E 6B BF F6 F6 87 B8 98 EE B5 1B 32 16 E4 6E 5D"),
    bytes.fromhex("08 EA 5A 83 49 B5 9D B5 3E 07 79 B1 9A 59 A3 54"),
    bytes.fromhex("F3 12 81 BF E6 9F 51 D1 64 08 25 21 FF BB 22 61"),
    bytes.fromhex("AF FE 8E B1 3D D1 7E D8 0A 61 24 1C 95 92 56 B6"),
    bytes.fromhex("92 CD B4 C2 5B F2 35 5A 23 09 E8 19 C9 14 42 35"),
    bytes.fromhex("E1 C6 5B 22 6B E1 DA 02 BA 18 FA 21 34 9E F9 6D"),
    bytes.fromhex("14 EC 76 CE 97 F3 8A 0A 34 50 6C 53 9A 5C 9A B4"),
    bytes.fromhex("1C 9B C4 90 E3 06 64 81 FA 59 FD B6 00 BB 28 70"),
    bytes.fromhex("43 A5 CA CC 0D 6C 2D 3F 2B D9 89 67 6B 3F 7F 57"),
    bytes.fromhex("00 EF FD 18 08 A4 05 89 3C 38 FB 25 72 70 61 06"),
    bytes.fromhex("EE AF 49 E0 09 87 9B EF AA D6 32 6A 32 13 C4 29"),
    bytes.fromhex("8D 26 B9 0F 43 1D BB 08 DB 1D DA C5 B5 2C 92 ED"),
    bytes.fromhex("57 7C 30 60 AE 6E BE AE 3A AB 18 19 C5 71 68 0B"),
    bytes.fromhex("11 5A 5D 20 D5 3A 8D D3 9C C5 AF 41 0F 0F 18 6F"),
    bytes.fromhex("0D 4D 51 AB 23 79 BF 80 3A BF B9 0E 75 FC 14 BF"),
    bytes.fromhex("99 93 DA 3E 7D 2E 5B 15 F2 52 A4 E6 6B B8 5A 98"),
    bytes.fromhex("F4 28 30 A5 FB 0D 8D 76 0E A6 71 C2 2B DE 66 9D"),
    bytes.fromhex("FB 5F EB 7F C7 DC DD 69 37 01 97 9B 29 03 5C 47"),
    bytes.fromhex("02 32 6A E7 D3 96 CE 7F 1C 41 9D D6 52 07 ED 09"),
    bytes.fromhex("9C 9B 13 72 F8 C6 40 CF 1C 62 F5 D5 92 DD B5 82"),
    bytes.fromhex("03 B3 02 E8 5F F3 81 B1 3B 8D AA 2A 90 FF 5E 61"),
    bytes.fromhex("BC D7 F9 D3 2F AC F8 47 C0 FB 4D 2F 30 9A BD A6"),
    bytes.fromhex("F5 55 96 E9 7F AF 86 7F AC B3 3A E6 9C 8B 6F 93"),
    bytes.fromhex("EE 29 70 93 F9 4E 44 59 44 17 1F 8E 86 E1 70 FC"),
    bytes.fromhex("E4 34 52 0C F0 88 CF C8 CD 78 1B 6C CF 8C 48 C4"),
    bytes.fromhex("C1 BF 66 81 8E F9 53 F2 E1 26 6B 6F 55 0C C9 CD"),
    bytes.fromhex("56 0F FF 8F 3C 96 49 14 45 16 F1 BC BF CE A3 0C"),
    bytes.fromhex("24 08 DC 75 37 60 A2 9F 05 54 B5 F2 43 85 73 99"),
    bytes.fromhex("DD D5 B5 6A 59 C5 5A E8 3B 96 67 C7 5C 2A E2 DC"),
    bytes.fromhex("AA 68 67 72 E0 2D 44 D5 CD BB 65 04 BC D5 BF 4E"),
    bytes.fromhex("1F 17 F0 14 E7 77 A2 FE 4B 13 6B 56 CD 7E F7 E9"),
    bytes.fromhex("C9 35 48 CF 55 8D 75 03 89 6B 2E EB 61 8C A9 02"),
    bytes.fromhex("DE 34 C5 41 E7 CA 86 E8 BE A7 C3 1C EC E4 36 0F"),
    bytes.fromhex("DD E5 FF 55 1B 74 F6 F4 E0 16 D7 AB 22 31 1B 6A"),
    bytes.fromhex("B0 E9 35 21 33 3F D7 BA B4 76 2C CB 4D 80 08 D8"),
    bytes.fromhex("38 14 69 C4 C3 F9 1B 96 33 63 8E 4D 5F 3D F0 29"),
    bytes.fromhex("FA 48 6A D9 8E 67 16 EF 6A B0 87 F5 89 45 7F 2A"),
    bytes.fromhex("32 1A 09 12 50 14 8A 3E 96 3D EA 02 59 32 E1 8F"),
    bytes.fromhex("4B 00 BE 29 BC B0 28 64 CE FD 43 A9 6F D9 5C ED"),
    bytes.fromhex("57 7D C4 FF 02 44 E2 80 91 F4 CA 0A 75 69 FD A8"),
    bytes.fromhex("83 53 36 C6 18 03 E4 3E 4E B3 0F 6B 6E 79 9B 7A"),
    bytes.fromhex("5C 92 65 FD 7B 59 6A A3 7A 2F 50 9D 85 E9 27 F8"),
    bytes.fromhex("9A 39 FB 89 DF 55 B2 60 14 24 CE A6 D9 65 0A 9D"),
    bytes.fromhex("8B 75 BE 91 A8 C7 5A D2 D7 A5 94 A0 1C BB 95 91"),
    bytes.fromhex("95 C2 1B 8D 05 AC F5 EC 5A EE 77 81 23 95 C4 D7"),
    bytes.fromhex("B9 A4 61 64 36 33 FA 5D 94 88 E2 D3 28 1E 01 A2"),
    bytes.fromhex("B8 B0 84 FB 9F 4C FA F7 30 FE 73 25 A2 AB 89 7D"),
    bytes.fromhex("5F 8C 17 9F C1 B2 1D F1 F6 36 7A 9C F7 D3 D4 7C"),
)

#: The KIRK1 key, which wraps the AES and CMAC keys of a command 1 header.
KIRK1_KEY = bytes.fromhex("98 C9 40 97 5C 1D 10 E8 7F E6 0E A3 FD 03 A8 BA")

#: The per-tag seed blocks. Each entry is the tag, the 144-byte seed, the key
#: slot the seed is expanded with, and whether the seed is stored scrambled
#: and needs the kirk7 pass before use.
TAG_KEYS: dict[int, tuple[bytes, int, bool]] = {
    0xC0CB167C: (
        bytes.fromhex("FA 36 8E DA 47 74 D9 5D 74 98 C1 76 AF 7E E5 97 BD 09 AB 1C C6 BA 35 98 81 92 D3 03 CF 05 B2 03 34 E7 82 28 63 F6 14 E7 75 27 6E B9 C7 AF 8A BD 29 EC D3 1D 6C A1 A4 EC 87 EC 69 5F 92 1E 98 85 21 AE FC 7C 16 DD E9 BA 04 78 A9 E6 FC 02 EE 2E 3D 8A DF 61 64 05 31 DD 49 E1 97 96 3B 3F 45 C2 56 84 1D F9 C8 6B DA 39 F5 FE E5 B3 A3 93 C5 89 BC 8A 5C FB 12 72 0B 6C CB D3 0D E1 A8 B2 D0 98 47 18 D6 5F 57 23 DC F0 6A 16 01 77 68 3B 5C 0F"),
        0x5D, False),
    0x08000000: (
        bytes.fromhex("EF 69 CB 18 12 89 8E 15 BB 0E F9 DE 23 FB B0 4C 18 EE 87 36 6E 4A 8D 86 56 C7 B5 19 1D 55 16 EE 6C 2D CB E7 60 C6 47 97 3F 14 95 CE 77 F4 56 29 DE 4A 82 03 F1 9D 0C 21 24 EB 29 50 9F E6 DF 81 00 9B C8 39 91 8B 0C B0 C2 F9 2D EF FC 93 3A E1 A8 A4 94 8B 9D D0 1D 49 0D 40 6A 68 E4 C7 D4 CE C9 B7 C8 96 28 DC AA 1E 84 0B 17 A4 DC 5D 5D 50 CF C3 A6 5D 2D FA 5D 0E B5 19 79 6E C7 29 5E CE 94 DB AC AA DD 0C F7 45 25 37 A7 62 3D 56 E6 CC"),
        0x4B, False),
    0x0F000000: (
        bytes.fromhex("BC FE 81 A3 C9 D5 B9 99 8D 0A 56 6C 95 9F 30 30 CC 46 26 79 5E 4E B6 82 AD 51 39 1A C4 2E 18 0A B4 31 61 C4 8A 0C C5 77 C6 16 5F 32 2E 94 D1 02 C4 8A A3 0A C6 0A 94 2A 26 47 03 67 33 B1 2D E5 07 21 EF D2 90 1E C8 85 BA 64 D1 C8 1D CE 8D C3 75 A2 8B 94 03 46 B8 0D 37 36 47 E2 DA FC 74 CD 66 3D 8E 58 22 E8 28 6D 8B 54 1E 89 6D F5 3C F5 66 DB BD 0B AA 86 B2 C4 4B BC EB 2B F4 1F 26 FC 05 E7 B8 92 52 69 EE DC E5 42 04 5E 21 7F EB 8B"),
        0x52, False),
    0x862648D1: (
        bytes.fromhex("98 D6 BF 11 24 B3 F9 D7 27 49 52 DD 86 5B 21 16 6D C3 4A 50 17 B2 43 58 47 DA A0 E5 E7 A1 73 BB 35 DB 15 29 3A FD 5C 37 05 A9 70 BB CA EF 2B 27 91 07 96 2E BB 99 07 EA C8 E6 5A B8 73 F7 CA C9 41 E6 0E 25 9E 4A E7 06 5D 89 44 52 A5 55 67 46 53 AF 84 9A 74 41 02 E1 1E 03 BA EE CE B9 80 ED 72 5F 31 BC 7F 06 21 58 58 30 31 E8 06 E7 D0 D2 3E 93 D8 E6 B4 7F D1 D7 C4 96 50 50 3B 0B A5 FD 3D AE 35 46 8A 9C 48 EB 2D 76 2D 42 31 32 8B 5A"),
        0x52, False),
    0x0B000000: (
        bytes.fromhex("BF 3C 60 A5 41 24 48 D7 CC 64 57 F6 0B 06 90 1F 45 3E A7 4E 92 D1 51 E5 8A 5D B7 E7 6E 50 5A 46 22 10 FB 40 50 33 27 2C 44 DA 96 80 8E 19 47 99 77 EE 8D 27 2E 06 5D 74 45 FA 48 C1 AF 82 25 83 DA 86 DB 5F CE C4 15 CB 2F C6 24 25 B1 C3 2E 6C 9E E3 9B 36 C4 1F EB F7 1A CE 51 1E F4 36 05 D7 D8 39 4D C3 13 FB 18 74 E1 4D C8 E3 3C F0 18 B1 4E 8D 01 A2 0D 77 D8 E6 90 F3 20 57 41 63 F9 17 8F A6 A4 60 28 DD 27 13 64 4C 94 05 12 4C 2C 0C"),
        0x4E, False),
    0x0E000000: (
        bytes.fromhex("DE 57 B7 77 17 DD 62 EE 7B 78 03 5D 44 86 CA 59 20 8D F6 93 28 93 81 21 71 4E A7 86 CA 82 24 1B 58 AE 74 5F 6C 01 8D 56 32 88 4D 9A 72 43 A2 2E 84 F4 0C 82 B9 06 FC FC 6A FB 5B 8A D7 9C 9F BF 01 0D 85 15 BA 5F ED 39 93 83 C3 4C AF DE 3A ED BF 68 A7 1A 77 8A BD 89 65 41 56 46 D9 DB 33 73 81 6C E8 62 96 9B 29 03 5A AE AF 73 20 53 A0 40 E8 4B 66 10 99 6A B7 E5 70 DD E0 29 28 24 60 EA 30 AE 42 20 32 8D 6F 94 71 5F 9E A2 D5 7F 0C 7C"),
        0x51, True),
}


def aes_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    """Decrypt AES-128-CBC with a zero IV.

    The KIRK engine's own CBC mode has no IV register: the first block is
    decrypted without an xor, which is the same as a zero IV.
    """
    if len(data) % 16:
        raise ValueError("CBC data is not a multiple of the block size")
    return AES.new(key, AES.MODE_CBC, iv=b"\x00" * 16).decrypt(data)


def kirk7(key_slot: int, data: bytes) -> bytes:
    """Decrypt with the AES key of a KIRK key slot."""
    if not 0 <= key_slot < len(KEYVAULT):
        raise ValueError(f"no such KIRK key slot: 0x{key_slot:02X}")
    return aes_cbc_decrypt(KEYVAULT[key_slot], data)


def _cmac_shift_left(block: bytes) -> bytes:
    """Shift a 16-byte block one bit to the left, as AES-CMAC defines it.

    A bit shifted out of the top is replaced by the constant 0x87 in the
    low byte, which is what makes the CMAC subkeys different from a plain
    shift.
    """
    value = int.from_bytes(block, "big")
    carry = value >> 127
    value = ((value << 1) & ((1 << 128) - 1)) ^ (0x87 if carry else 0)
    return value.to_bytes(16, "big")


def aes_cmac(key: bytes, data: bytes) -> bytes:
    """Compute the AES-CMAC of ``data`` under ``key`` (RFC 4493).

    The MAC is a CBC-MAC over the *encryption* of the blocks, so the
    subkeys come from an encryption of the zero block, not a decryption.
    """
    cipher = AES.new(key, AES.MODE_ECB)
    k1 = _cmac_shift_left(cipher.encrypt(b"\x00" * 16))
    k2 = _cmac_shift_left(k1)

    length = len(data)
    if length and length % 16 == 0:
        # The message fills whole blocks: the last one is masked with K1.
        blocks = data[:-16] + bytes(a ^ b for a, b in zip(data[-16:], k1))
    else:
        # The message is padded with 0x80 and zeros, and the last block is
        # masked with K2.
        padding = 16 - (length % 16)
        padded = data + b"\x80" + b"\x00" * (padding - 1)
        blocks = padded[:-16] + bytes(a ^ b for a, b in zip(padded[-16:], k2))

    chain = b"\x00" * 16
    for offset in range(0, len(blocks), 16):
        block = blocks[offset:offset + 16]
        chain = cipher.encrypt(bytes(a ^ b for a, b in zip(chain, block)))
    return chain
