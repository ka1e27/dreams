# Weekly updates

<!--
HOW TO ADD AN UPDATE (anyone on the team, or a Claude Code session)
- Newest week goes at the TOP, right under this comment.
- Start each week with a "## Week of <Mon> <day>, <year>" heading (the Monday of that week).
- One bullet per thing you worked on, starting with your name in bold: - **Kyle:** what you did
- Keep bullets short and true: what was built, tested, decided or broken, and what's next.
- Optional: add a photo on its own line with ![description](img/your-photo.jpg) after putting the file in img/.
- On GitHub: open this file, click the pencil icon, edit, then "Commit changes". The website's Updates page reads this file, so it goes live in about a minute.
-->

## Week of Oct 12, 2026

- **Kyle:** Designed V3.1, an interim starter carrier board to get the boat on the water before the full V3. It pairs the Raspberry Pi 5 with one Raspberry Pi Pico 2 instead of the Teensy, runs from one 10S Li-ion pack, and has a CAN chain for the VESCs, RC control, GPS, hull leak sensors and the pod tether.
- **Kyle:** Shrank V3.1 to 98 × 67 mm by tucking the Pico and the 5 V converter under the Pi, which mounts face down on standoffs, and moving the small surface-mount parts and the SHT41 hull-air sensor to the underside. Design-rule and schematic checks all pass.

## Week of Oct 5, 2026

- **Kyle:** Launched the D.R.E.A.M.S website, with the build log, the V3 board in 3D and the V2 command-center demo.
- **Kyle:** Drew the new D.R.E.A.M.S logo: the word is the hull, and the D is the bow.
- **Kyle:** Nolan Ting and Caleb Kong joined the team.
- **Kyle:** Sized V3's drive. A 3 ft catamaran needs about 200–300 W per side at survey speed, so we're planning belt-driven 5065-size motors mounted on deck.
- **Kyle:** Started reaching out to sponsors for parts, PCB fabrication and machining.

## Week of Sep 28, 2026

- **Kyle:** Finished the V3 carrier board, rev D: 130.6 × 101.5 mm, 4 layers, 126 parts, with design-rule and schematic checks all passing.
- **Kyle:** Updated the sensor-pod board to rev B after a design review.
