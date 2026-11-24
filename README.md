# pestuns.github.io

Open `index.html` in a browser. The 100×100 viewport looks onto a sparse Life
world with no fixed edges. Use the arrow buttons or Shift-drag to pan.

The default circuit runs `00, 01, 10, 11` through the same EQ and NOT gates.
**Play** animates it; **Advance to next result** runs to the next NOT sample.
**Input streams** accepts two other four-bit sequences without changing the layout.

All data and clock pulses are part of the starting configuration. At input slot
`k` (generation `64k`, starting at zero), A is a glider or an empty slot and B is
a lightweight spaceship or an empty slot. Either input alone destroys an EQ clock
pulse. Both together annihilate each other, letting the EQ clock pulse pass just
as it does when both inputs are absent. The surviving pulse travels on to NOT,
where it destroys a second clock pulse.

The trace samples the EQ port at generation `60 + 64k` and the NOT port at
`104 + 64k`. Each probe checks the expected ship shape. The default trace reads
`1001` followed by its complement `0110`. Playback pauses after the fourth result.

Run `node --test tests/clocked-life.test.mjs` to verify all 256 input-stream pairs,
the physical connection between the gates, and evolution outside the viewport.
