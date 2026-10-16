# The Zenith Terminal: notices

The Zenith Terminal is an unofficial, fan-made mod loader for BlazBlue Entropy Effect. It is not made, endorsed or
supported by 91Act or Arc System Works. BlazBlue Entropy Effect and BlazBlue belong to their owners, and so do the
characters that mods add.

## People

- Redux, its characters, and this window's design and direction: Soulve.
- The mod loader the window runs: KittySkin.

## Open-source parts the window uses

| Part | Licence | Where its licence text is |
|---|---|---|
| Qt for Python (PySide6) and Qt 6, used unmodified as separate libraries | GNU Lesser General Public License v3 | `licences\LGPL-3.0.txt`, with the GNU General Public License v3 it builds on in `licences\GPL-3.0.txt` |
| Aldrich (typeface; copyright 2011 Matthew Desmond, MADType) | SIL Open Font License 1.1 | `zenith_gui\fonts\OFL-aldrich.txt` |
| Chakra Petch (typeface; copyright 2018 The Chakra Petch Project Authors) | SIL Open Font License 1.1 | `zenith_gui\fonts\OFL-chakrapetch.txt` |
| Share Tech Mono (typeface; copyright 2012 Carrois Type Design, Ralph du Carrois) | SIL Open Font License 1.1 | `zenith_gui\fonts\OFL-sharetechmono.txt` |

Qt and PySide6 are used as they are published. You can replace them with your own build: they are ordinary
packages in the Terminal's Python. Their source code is published by The Qt Company at <https://download.qt.io/>.

## Pictures

The window shows each mod's own pictures from that mod's folder. It carries none of its own, apart from the
Terminal's mark (`art\logo\`, made for the Terminal).

## The mods that come in this package

Nine (`Launcher\mods\char-nine`), Ruby Rose 0.9.0, an alpha (`Launcher\mods\char-ruby`), and DELTARUNE: Party 0.6.4,
an alpha test (`Launcher\mods\dr-party`), come with the Terminal, switched on. All three are unofficial fan works.
None of them holds a file of BlazBlue Entropy Effect: what they need of the game is read from your own copy
when they are installed.

Ruby Rose carries the BlazBlue Cross Tag Battle files she is built from (`Launcher\mods\char-ruby\bbtag_alpha`):
her sprites, animations, effects, voice and sounds, as that game stores them, and her sounds a second time in
the form the game plays. BlazBlue Cross Tag Battle belongs to Arc System Works; Ruby Rose and RWBY belong to
RWBY's rights holders. The mod isn't made or endorsed by 91Act, Arc System Works or RWBY's rights holders.

DELTARUNE: Party carries the DELTARUNE sprites, sounds and font it uses and its portrait artwork
(`Launcher\mods\dr-party\pack`), and the same sounds a second time in the form the game plays
(`Launcher\local_only\deltarune\audio\hca_cache`, encoded with VGAudio). They belong to DELTARUNE's owners
(Toby Fox and the DELTARUNE team; the portrait artwork is by Temmie Chang). The mod isn't made or endorsed
by 91Act, Arc System Works, Toby Fox or the DELTARUNE team.

## The Python that comes in this package

The `Interpreter` folder holds Python 3.14.8 as python.org publishes it, without its manual, C headers and
tests, and the packages below as they are published on PyPI. Each one's licence text is in the folder
named in the last column, under `Interpreter\pythoncore-3.14-64\Lib\site-packages`.

| Part | Licence, as the part declares it | Its licence files |
|---|---|---|
| Python 3.14.8 | Python Software Foundation License | `Interpreter\pythoncore-3.14-64\LICENSE.txt` |
| archspec 0.2.6 | Apache-2.0 OR MIT | `archspec-0.2.6.dist-info\` |
| astc-encoder-py 0.1.12 | MIT License | `astc_encoder_py-0.1.12.dist-info\` |
| attrs 26.1.0 | MIT | `attrs-26.1.0.dist-info\` |
| brotli 1.2.0 | MIT | `brotli-1.2.0.dist-info\` |
| etcpak 0.9.15 | MIT License | `etcpak-0.9.15.dist-info\` |
| fsspec 2026.7.0 | BSD-3-Clause | `fsspec-2026.7.0.dist-info\` |
| lz4 4.4.5 | BSD License | `lz4-4.4.5.dist-info\` |
| numpy 2.5.1 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | `numpy-2.5.1.dist-info\` |
| pillow 12.3.0 | MIT-CMU | `pillow-12.3.0.dist-info\` |
| PySide6 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | `licences\` beside this file |
| PySide6_Addons 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | `licences\` beside this file |
| PySide6_Essentials 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | `licences\` beside this file |
| shiboken6 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | `licences\` beside this file |
| texture2ddecoder 1.0.6 | MIT License | `texture2ddecoder-1.0.6.dist-info\` |
| tpk_ar 0.2.4 | MIT License | `tpk_ar-0.2.4.dist-info\` |
| UnityPy 1.25.3 | MIT License | `unitypy-1.25.3.dist-info\` |

PySide6 holds only the Qt modules the window uses (`PySide6\TRIMMED.txt`).

`fmod_toolkit`, UnityPy's audio helper, is not the published package. The published one loads FMOD's
own library, which is proprietary and is not in this package. The `fmod_toolkit` folder here is a
stand-in written for the Terminal: UnityPy starts with it, and converting Unity audio stops with a
message. No mod that comes with the Terminal converts Unity audio.
