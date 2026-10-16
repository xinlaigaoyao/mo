# 本工作台入口

此副本已改为独立物理游戏目录、显式 build/存档绑定和严格事务安装。请先读 [工作台说明](../README.md)；下面保留的原包说明只作历史参考，其 Steam 启动和旧安装流程不适用于此工程副本。

# The Zenith Terminal 0.3.0 (alpha): setup guide

The Zenith Terminal is a mod loader for **BlazBlue Entropy Effect** on Steam. One window shows the mods you have, installs the ones you switch on and takes them out again.

**Unofficial fan project.** It isn't made, endorsed or supported by 91Act or Arc System Works. It unlocks no paid content. It holds no files of BlazBlue Entropy Effect: mods are built on your PC from your own copy of the game.

Two of the characters that come with it are alpha builds that carry files of other games, so that you don't need those games: Ruby Rose carries the BlazBlue Cross Tag Battle files she is built from, and DELTARUNE: Party carries the DELTARUNE sprites, sounds and font it uses and its portrait artwork. Those files belong to their owners (see Credits).

KittySkin builds the loader. The window is part of Redux, the mod project Soulve directs.

## What you need

- **Windows 10 or 11**, 64-bit.
- **BlazBlue Entropy Effect on Steam**, at build **25627491**. The Terminal shows the build you have. A newer build needs a newer Terminal (see "After a game update").
- About **1 GB** of free disk space on your system drive.
- Nothing else. Python and the three characters come inside the Terminal, so there is nothing to install and nothing to add.

## First start

1. **Close the game.**
2. Double-click **`ZenithTerminal-0.3.0-alpha.exe`**, the file you downloaded.
   - Windows may show "Windows protected your PC", because the file isn't signed. Choose **More info**, then **Run anyway**.
   - The first time, it unpacks the Terminal into **`C:\ZenithTerminal`** (about 420 MB) and then opens its window. On a PC where that folder can't be made it uses `ZenithTerminal` in your local app data folder instead. The setup window names the folder.
   - After that, the same file opens the Terminal. Keep it wherever you like. `ZenithTerminal.exe` inside the folder opens it too.
   - **Don't move or rename that folder while mods are installed.** Ruby's and Kris's sounds are loaded from it.
3. Press **SET UP AND INSTALL**, the large button at the bottom. It does five things:
   - finds the game through Steam;
   - reads the game's data, which is needed once;
   - makes Ruby Rose's moves, art and sounds on your PC (**Prepare your mods**), which is needed once for each version of her;
   - copies your save into `Launcher\save_backups`;
   - builds the mods that are switched on from your own game files, and installs them.

   The first time takes several minutes.
4. When it has finished, the button says **PLAY**. It starts the game through Steam. Nine, Ruby and Kris are at the end of the Prototype list.

Play **single player only**. Don't take a modded game into multiplayer.

## What comes with it

Three characters, all switched on. To leave one out, switch it off in the Library before you install.

- **Nine the Phantom 0.9.0** (alpha). How she plays: `Launcher\docs\NINE_GUIDE.md`. If BlazBlue Centralfiction is installed through Steam on the same account, two of her moves use her Centralfiction animations, read from your own copy. Without it nothing is missing.
- **Ruby Rose 0.9.0** (alpha), the feedback update: Ruby as she appears in BlazBlue Cross Tag Battle, as a playable character. You don't need Cross Tag Battle. What is new and what is unfinished: `RUBY_ROSE_GUIDE.md` in the Terminal's folder. Until her first install her entry in the Library shows a letter where her picture goes: the picture is made with her.
- **DELTARUNE: Party 0.6.4** (alpha test): Kris from DELTARUNE as a playable character, with Susie and Ralsei fighting beside them. You don't need DELTARUNE. How they play and what is unfinished: `DELTARUNE_PARTY_GUIDE.md` in the Terminal's folder.
- The shared files that added characters run on, and the F9 report recorder. They go into the game by themselves.

## Adding a mod

The three characters above are already in the Library: there is nothing to add for them. A mod made for the Terminal that you get later is added like this.

1. Leave its zip zipped.
2. Open **Library** and press **ADD A MOD**, lower left. Pick the zip.
3. It appears in the list, switched on. Press the large button. It says **INSTALL**, or **APPLY CHANGES** when mods are already in the game.
4. Press **PLAY**.

Ruby also comes as `RubyRose-0.9.0-alpha.zip`, a folder with `.bat` files that installs her without the Terminal. Use one or the other, not both.

## Switching off, uninstalling, deleting

- **Switch a mod off or on** in the Library, then press **APPLY CHANGES**.
- **UNINSTALL**, in the Library, takes the selected mod out of the game. Its files stay in the Library.
- **DELETE FILES**, in the Library, moves a mod that isn't in the game to the Recycle Bin. To get it back, restore its folder from the Recycle Bin.
- **Options > General > UNINSTALL EVERY MOD** takes everything out and cleans your save so the normal game loads it.

Two things to know about your save:

- **Uninstall before you delete the Terminal's folder.** While a mod character is installed, your save holds that character's Evotypes and records. The normal game can't load a save that names a character it doesn't have.
- **Taking a character out removes that character's data from your save**: the Evotypes, the records and a run in progress. Everything else stays. The Terminal copies your whole save first, every time.

## Your save

- A full copy of your save goes into `Launcher\save_backups` before every install and every uninstall. **Options > Saves and reports > BACK UP** makes one at any time.
- An install also removes from your save the data of mod characters that aren't switched on in the Terminal. If you already play a Redux character from one of the `.bat` packages, read the next section before your first install.
- **REPAIR**, on the same page, is for a save the normal game won't load because it still holds a mod character.
- If Steam asks about a cloud save conflict after an uninstall or a repair, choose the **local** save.

## Coming from a .bat package (Nine 0.7 to 0.9, Ruby 0.7, DELTARUNE: Party 0.6)

Only one loader's mods are in the game at a time, so the Terminal's install replaces what those packages installed. You don't need to uninstall the old version first.

- **Your characters' Evotypes and records stay** as long as the character is switched on in the Terminal when you press SET UP AND INSTALL. Nine, Ruby and DELTARUNE: Party come switched on.
- **A character you switch off is removed from your save** by the install, after the backup.
- Afterwards, don't run the old folder's `.bat` files again. Once the game loads your save and your characters are in the Prototype list, you can delete the old folder. Move its `save_backups` folder somewhere first if you want to keep those copies.

## Updating the Terminal

Close the Terminal and the game, then open the new version's file. It replaces the Terminal's own files in the same folder, and the characters that come with it. The mods you added, the list of what is switched on and your save backups stay as they are. The new version's guide says what to do after that.

## Removing the Terminal

1. **Options > General > UNINSTALL EVERY MOD.** Start the game once and check that your save loads.
2. Close the Terminal.
3. Move `Launcher\save_backups` somewhere else if you want to keep those copies. Then delete the Terminal's folder and the file you downloaded. The setup makes no shortcuts and installs nothing else.

## After a game update

A Steam update puts the game's own files back, which switches mods off. **The normal game can't load a save that still names a mod character.** It reports the save as corrupted. Your progress is still there.

This release works with game build **25627491**. After the game updates, before you play:

1. If the game says the save is corrupted, close the game. Don't choose anything that resets, deletes or overwrites the save.
2. Then do one of these:
   - **Keep playing your mods:** get the Terminal's release for the new build. This one stops at **SET UP AND INSTALL** with "no schema snapshot for game build ...", because the game is newer than it.
   - **Play without mods for now:** **Options > Saves and reports > REPAIR**. It copies your save, then takes the mod characters out of it so the normal game loads it.

If Steam updates games automatically, the update can arrive the moment you close the game.

## Known limits

- The window has one size, **1280 x 720**, and is used with the mouse. On a screen with less room than that, for example a small laptop at 150 % display scaling, the bottom of the window is off screen. Until the window can be resized, lower the display scaling while you use the Terminal.
- An install uses about 2 GB of memory while it builds. Close heavy programs first if your PC is short.
- Single player only.

## If something goes wrong

- **The game says your save is corrupted, or won't load.** Your progress is still there: the game has met a save that names a character it doesn't have. Close the game without choosing anything that resets, deletes or overwrites the save. Then open the Terminal and either install again with the large button, or use **REPAIR** to play without mods.
- **The setup window says STOPPED: The Zenith Terminal is open.** A newer version can't replace files that are in use. Close the Terminal's window, then open the file again.
- **The setup window says the download is incomplete.** Download the file again.
- **Windows or your antivirus won't run the file.** The download also comes as `ZenithTerminal-0.3.0-alpha.zip`, the same folder zipped. Unzip it to a place you will keep, not `Program Files` and not the game's folder, and open `ZenithTerminal.exe` in it. If that is blocked too, `Start The Zenith Terminal.bat` in the same folder opens the same window.
- **Ruby, Kris or the party have no voice or sound.** The Terminal's folder was moved or renamed after the install. Put it back where it was.
- **An install stops with BUILD ABORTED.** Nothing in the game was changed. The window shows the line that says why. Make a report (below) and send it.
- **A `.bat` file in the `Launcher` folder stops with `missing mod 'char-ruby'`.** Those are the loader's own console files, and they don't make Ruby. Install once with the window's large button: it makes her, and the `.bat` files work after that.

## Reporting a problem

**Options > Saves and reports > MAKE REPORT** zips your latest F9 reports, the mods' log and your mod versions into `Launcher\feedback`. Nothing is uploaded: send the zip with your notes to the place you got the download from. In the game, **F9** records a report at the moment something goes wrong.

More help: `Launcher\docs\TROUBLESHOOTING.md`.

## Credits

BlazBlue Entropy Effect © 91Act. BlazBlue, BlazBlue Cross Tag Battle and their characters © Arc System Works. Ruby Rose and RWBY belong to RWBY's rights holders. DELTARUNE, its characters, sprites, sounds and font belong to Toby Fox and the DELTARUNE team; the portraits are DELTARUNE's official artwork by Temmie Chang. This is an unofficial fan project, and none of them made or endorsed it.

- The mod loader: KittySkin.
- Redux, its characters and the window: Soulve.
- Open-source parts and their licences: `NOTICES.md`.

The Terminal is free. Its Support page links to both of our Ko-fi pages. A tip buys or unlocks nothing.
