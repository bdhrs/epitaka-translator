# Upstream log

Upstream: https://github.com/dhammanana/epitaka_translator (remote `upstream`).
Fork point: `a7f67a8`.

## Last checked

`5d463fb` (2026-10-17), checked 2026-11-09. Run the next study from `5d463fb..upstream/main`.

## Decisions

| Date | Upstream commit | Item | Decision | Reason |
|---|---|---|---|---|
| 2026-11-09 | 5d463fb | Blank model reply counts as a failed try | Ported | The fork's compat transports already retry empty replies. Only whitespace slipped through. |
| 2026-11-09 | 5d463fb | Stop a book after repeated failed chunks | Ported, default 5 | A dead quota otherwise pays for one doomed prompt per chunk. Setting: `MAX_CONSECUTIVE_FAILED_CHUNKS`. |
| 2026-11-09 | 5d463fb | Shared Pāli script map and `to_pali_script` | Ported, used by export only | Prompts do not use it (next row). Lao, Khmer, Tibetan and Assamese exports now convert too. |
| 2026-11-09 | 5d463fb | Pāli in target script inside prompts | Skipped | Run logs: 221 of 247,829 Kannada and 176 of 251,796 Telugu sentences dropped for Roman letters (about 0.08 percent), and dropped lines are retried. Revisit if the rate rises. |
| 2026-11-09 | 5d463fb | Retry count 10 to 3, env knob | Skipped | The fork's key pool and off-peak waits need the 10. Nobody asked for a knob. |
| 2026-11-09 | 5d463fb | `description_builder.py` | Skipped | Gemini-only and English-centric. Nothing in the fork reads its output. Revisit when the web reader needs section descriptions. |
