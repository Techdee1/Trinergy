# Hero images and clip: caption suggestions

All images are 16:9, no browser chrome, no scroll bars, no cursor. Real data from the local API (T2-016 and T2-017). Heirs red appears only on the highlight box, the current-stage ring and the primary button.
Regenerate with `node docs/capture-hero.mjs final` and `node docs/capture-hero.mjs clip`.

| File | Caption (one line) | Suits slide |
|---|---|---|
| `hero_a_trust_dark_4k.png`, `hero_a_trust_dark_1080p.png`, `hero_a_trust_light_4k.png`, `hero_a_trust_light_1080p.png` | Every answer carries its confidence, the real report page, the cited record and the checks it passed. | trust, demo |
| `hero_b_search_dark_4k.png`, `hero_b_search_dark_1080p.png`, `hero_b_search_light_4k.png`, `hero_b_search_light_1080p.png` | Four reports opened out of 32, the rest left closed, and every claim checked before it is shown. | architecture, demo |
| `hero_replay_t2016.mp4`, `hero_replay_t2016_poster.png` | One question, from the router to a verified answer, in 16 seconds. | demo |

## Notes for the presenter

- **Hero A, the red box.** The box is the highlight the API returns for the cited record `F1C-20140326-FLUID-01`. It sits on the Sample Time cell of the fluid sample column. The answer, 1.03, is in the row "Fluid Density (g/cm3)" of the same column, four rows lower. Say "the fluid sample record" and point at the density row. Do not say the red box is the density value.
- **Hero B, 2D not 3D.** The 3D view was tried and rejected for this image: the wells form a tall, thin column, so the scene fills about a fifth of the frame and its labels are unreadable at slide size. The 2D replay reads clearly. The verifier panel shows the flagged check in violet: the first draft cited a number the records did not support, and a larger model took over.
- **Hero B timing.** The frame is the verify stage with the checks partway ticked. Check animations are frozen at 950 ms with the Web Animations API so the moment can be reproduced. Nothing is added to the page.
- **Pixel size.** The report page image is stored at twice page size by the server, so its text is soft in the 4K versions. The interface text is sharp.
- **Clip.** `hero_replay_t2016.mp4` is 1920x1080, H.264, about 22 seconds: the replay (about 16 seconds at 1x) and a hold on the resolved answer. `hero_replay_t2016_poster.png` is the resolved frame.
