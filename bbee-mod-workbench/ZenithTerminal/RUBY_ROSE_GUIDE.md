# Ruby Rose 0.9.0 (alpha), in The Zenith Terminal

Ruby Rose, as she appears in BlazBlue Cross Tag Battle, as a playable character in BlazBlue Entropy Effect. She is part of Cross Effect, one of the Redux mods. She comes with the Terminal, switched on, for game build **25627491**.

This is an unofficial fan-made mod. It isn't made, endorsed or supported by 91Act, Arc System Works or RWBY's rights holders. Play single player only.

**You don't need BlazBlue Cross Tag Battle.** This is an alpha, and the Terminal carries the Cross Tag Battle files Ruby is built from, in `Launcher\mods\char-ruby\bbtag_alpha`: her sprites, animations, effects, voice and sounds, as that game stores them. Please don't pass that folder on by itself. A later release is to read the same files from your own copy of Cross Tag Battle instead.

## Getting Ruby into the game

Press the Terminal's large button (SET UP AND INSTALL, INSTALL or APPLY CHANGES). Her first install has a step of its own, **Prepare your mods**: her moves, art and sounds are made on your PC from those files. It happens once for each version of her and takes a few minutes. Her picture in the Library is made in the same step, so until then her entry shows a letter in its place.

Ruby is at the end of the Prototype list. Her moves are in the game's own move list.

To leave Ruby out, switch **Ruby Rose** off in the Library and press the large button. Taking a character out removes that character's Evotypes, records and a run in progress from your save. The Terminal copies your whole save first.

Don't share the files the install makes: `mod.json` and the `gen` folder in `Launcher\mods\char-ruby`, and the `local_only`, `decoded`, `extracted_raw`, `inspect` and `patch_out` folders in `Launcher`. They are made from the games' files.

## What is new in 0.9.0

This version is built from three rounds of the testers' feedback on 0.7.

**She starts with less, and her Potentials give more**

- Gun Blast fires once. Chaining three is its card now.
- Rising Reap (Up + Attack) and Buzzsaw Blast (Down + Skill in the air) are Potentials.
- The air Skill is the Recoil Shot, a new move: a rifle round forward for 30 MP. The recoil carries her back and holds her height.

**Guns**

- Rifle Shot deals less, and an enemy flinches from her rounds at most once every 1.5 seconds. The damage always lands.
- Press Skill again while she is still aiming and she fires again from that pose.
- Sy-Pod Shot fires one heavy round. Keep Skill held and she fires again at a steady pace, 30 MP a round. Gun Blast leaves the plant at any time.
- The third air attack fires three rounds with recoil, and she no longer hangs in the air after it.
- With Gravity Dust loaded, her rounds open a gravity well where they hit.
- A new card, Jump: every jump fires a round straight down, and the recoil carries the jump higher.
- A new card, Gunswing: during a scythe attack, Skill fires a round from the muzzle without ending the attack. Each shot costs 8 MP, one shot a swing. A tester's idea.

**Moves**

- Reaper's Hook and Guillotine open with a cinematic start: the camera pushes in, time holds for a moment and the enemies on screen are held in place until her first strike lands. Bosses aren't held.
- Reaper's Hook swings from where she stands and pulls the hooked enemy in front of her. She no longer runs on the spot.
- Guillotine's last hit has a run-up, and Rising Reap in the air has a start of its own.
- Buzzsaw Blast is invincible for its first 0.2 seconds, has Super Armor through the dive, and Jump cancels it once it has hit. Hold Down to drop faster, or Up to rise a little first.
- In the air, Down + Dash is the dive and Forward + Dash is the forward blast.
- Clash Assault shows its backdrop only with its Potential's full-charge finish. A glint on her blade shows when Scythe Chain is ready. Her SP has a badge of its own.

**Red slashes**

- The red slashes of the power stages pass through walls and ledges.
- They are slimmer, and their break is over in under half a second.
- Each red slash lies the way its swing cuts: a level cut throws a flat crescent, an overhead chop an upright one that leans with the chop.
- Buzzsaw Blast draws a red ring round her on every turn of the saw at power stages 2 and 3. Its landing no longer throws a slash.
- Recoil Rush shows: after a Gun Blast, petals trail her while the stronger strike waits, and that strike lands with a flash and a ring.

**Fixed**

- Jump works during and after the third air attack.
- The effects of a blast fired while she faces left point the right way, and the backward blast no longer pulls her forward at its end.
- Three effects that promised MP back never paid it. They do now.
- The Lightning card's bolt and the rose gust of the fourth strike came once a battle. They come on every use.

The full list: `Launcher\mods\char-ruby\docs\CHANGELOG.md`.

## Known in this version

- **Petal Burst, Petal Dance and Red Reaper can't be used.** Their inputs are off while they are reworked, and their three Potentials aren't offered in a run. Her Ultra slot stays empty.
- **Stage 2 and stage 3 swings keep their stage 1 look.** What changes with the stages is what the swings throw: a small crescent at stage 2, the full slash projectile at stage 3.
- **Ice Dust and the down chain.** With Ice loaded, the down chain can Freeze the enemy at Rising Crescent. A Frozen enemy stops rising with her, so the air string after it misses.
- **Bosses** can't be held by Guillotine; the hits still land.
- **Buzzsaw Blast's red ring has no hit of its own.** The saw's own cuts are what hit.
- **Guillotine's last hit at stage 3 still throws its two standing crescents**, as in 0.7.
- **The cinematic start's dark backdrop** has not been checked on every stage: tell us where it looks wrong.
- **Her voice is English only.**
- **Not played yet from a Terminal install.** She is the same build as in her own package. Built and installed by the Terminal, she has been checked up to the install, not in a run.
- The rest: `Launcher\mods\char-ruby\docs\LIMITATIONS.md`. Its "Setting it up" part, and `README.md` beside it, are written for her own `.bat` package. In the Terminal, this guide and `SETUP_GUIDE.md` take their place.

## If something goes wrong

- **Ruby has no voice or sound.** Her sounds are loaded from the Terminal's folder. If it was moved or renamed after the install, put it back where it was.
- **The game says the save is corrupted, or won't load.** Close the game without choosing anything that resets the save. Then use **Options > Saves and reports > REPAIR** in the Terminal, or install again.
- **To send a report:** **Options > Saves and reports > MAKE REPORT**. With the zip, say the version (0.9.0), the Entropy you played at and which Potentials you had. In the game, **F9** records a report at the moment something goes wrong.

## Credits

Ruby Rose and RWBY belong to RWBY's rights holders. BlazBlue Cross Tag Battle and BlazBlue belong to Arc System Works. BlazBlue Entropy Effect belongs to 91Act. This mod is free and made by fans; none of them made or endorsed it.

Thank you to the alpha testers whose feedback this version is built from.
