# Evening Review HTML Design Spec

Render `morning-briefs/YYYY-MM-DD-evening.html` — same magazine design language as the morning brief but with **outcome cards** instead of trade-recommendation cards.

### Differences from the morning HTML

- **Masthead subtitle** reads `EVENING REVIEW · [DAY] EDITION · [DATE] · Vol. [#]`
- **Ticker bar** color: deeper indigo (`#1a3a6e`) instead of red — visually distinct from the
  morning so a printed stack is easy to sort
- **Outcome cards** (replace trade cards):
    - Each card shows: ticker tag, EOD price + day %, outcome badge, P/L estimate, thesis check,
      lesson (if any), diagnosis category (if any), status update (if any), partial-review flag (if
      true)
- **Proposals section** (replaces "implied move watch"):
    - Each proposal renders with `recurrence_count_14d` prominently
    - Proposals where `action_threshold_met: true` get a distinct red "ACT NOW" header
    - Proposals at recurrence 1–2 show as "watch — accumulating"
- **Visible EOD quote table** at top (just like morning's Step 1 Part E table)
- **Meta Review block** (dark bg, indigo accent — analog to morning's Meta Signal)
- **Tomorrow Focus block** (light surface card, summarizing what tomorrow's brief should pay
  attention to)

Otherwise: same fonts (Bebas Neue / Playfair Display / Source Serif 4), same triple-rule dividers,
same `@media print` discipline, same standalone HTML.
