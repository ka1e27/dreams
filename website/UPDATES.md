# Weekly updates

<!--
HOW TO ADD AN UPDATE (anyone on the team, or a Claude Code session)
- Newest week goes at the TOP, right under this comment.
- Start each week with a "## Week of <Mon> <day>, <year>" heading (the Monday of that week).
- One bullet per thing you worked on, starting with your name in bold: - **Kyle:** what you did
- Keep bullets short and true: what was built, tested, decided or broken, and what's next.
- The full story and photos go in a separate file, updates/<the week's Monday>.md (for example updates/2026-10-12.md).
  Once that file exists, the week on the Updates page links to its own page. Write it as:
    # A headline for the week
    One or two sentences that sum the week up.
    ## Sections, with text and bullets
    ![What the photo shows](img/your-photo.jpg)
  Photos on lines next to each other sit side by side; click one on the site to see it full size.
- Photos: put them in img/ with their location data removed (phones often save GPS). tools/build_images.py does that.
- On GitHub: open this file, click the pencil icon, edit, then "Commit changes". The website's Updates page reads this file, so it goes live in about a minute.
-->

## Week of Oct 12, 2026

- **Kyle:** PCBWay is now sponsoring our circuit boards.
- **Kyle:** Designed a new PCB, V3.1, to get the boat on the water before the full V3 board and to try out the Pico-based electronics planned for it. It pairs the Raspberry Pi 5 with a Raspberry Pi Pico 2 in place of the Teensy, runs from one 10S Li-ion pack, and has CAN for the motor controllers, RC control, GPS and hull leak sensors. Then moved the full V3 board to two Pico 2s as well: one runs the motors, winch and RC, the other the sensors, GPS and the pod link. They talk to the Pi over its GPIO pins, so its USB ports stay free for cameras. All three boards now share one KiCad parts library, and each board's layout rules are written up beside it.
- **Kyle:** Gave every week on the website's Updates page its own page, with the full story and photos.
- **Kyle:** Picked the drive motors: two Flipsky 5048 200 KV sensored outrunners, each on a Flipsky VESC-based controller that talks to the boat's board over CAN.

## Week of Oct 5, 2026

- **Kyle:** Launched the D.R.E.A.M.S website with a build log.
- **Nolan:** Drew the new D.R.E.A.M.S logo.
- **Kyle:** Nolan Ting and Caleb Kong joined the team.
- **Kyle:** Sized V3's drive at about 200–300 W per side, with belt-driven motors on deck.
- **Kyle:** Started reaching out to sponsors.

## Week of Sep 28, 2026

- **Kyle:** Finished the V3 carrier board, rev D: 130.6 × 101.5 mm, 4 layers, 126 parts, with design-rule and schematic checks all passing.
- **Kyle:** Updated the sensor-pod board to rev B after a design review.
