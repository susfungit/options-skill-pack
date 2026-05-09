# Morning Brief HTML Design Spec (v3.4)

Render `morning-briefs/YYYY-MM-DD.html` as a complete standalone document matching this spec.

### Design spec (unchanged from v3.4 prompt)

**Masthead**

- Black background (`#0f0f0f`)
- "THE MORNING BRIEF" in Bebas Neue
- Subtitle: `Options & Pre-Market Intelligence | [DAY] Edition | [DATE] · Vol. [#]`
- Red ticker bar (`#c41e3a`) below

**Typography (cdn.jsdelivr.net imports)**

- Headlines: Playfair Display
- Body: Source Serif 4
- Labels: Bebas Neue

**Color palette**

- Page: `#faf7f0` · Ink: `#0f0f0f` · Red accent: `#c41e3a`
- Bull green: `#1a7a3a` · Bear red: `#c41e3a` · Amber: `#b8860b`
- Body: `#2a2a2a` · Muted: `#888` · Surface: `#f0ede4`

**Section dividers** — triple rule between sections:

```
3px solid #0f0f0f / 1px solid #c41e3a / 0.5px solid #0f0f0f
```

**v3.4 visible element** — the Step 1 Part E quote table renders as its own visible block at the
top of the brief, just below the market snapshot. Reader must be able to verify every sourced
price before trusting any recommendation.

**Market-closed banner** — when `market_status` is `closed_weekend` or `closed_holiday`, render a
prominent banner immediately under the masthead:

> **MARKETS CLOSED — [Saturday | Memorial Day | …]. Quotes from [last_trading_day] close. Brief is for planning only.**

The banner uses the amber accent color (`#b8860b`) — same family as the carry-forward card so it
reads as "informational, not a tradable signal." When `market_status` is `early_close`, render a
smaller note: **"EARLY CLOSE — 1:00 PM ET. Same-day trades scaled accordingly."**

**Open Positions Carry-Forward block** — amber-accent card (`#b8860b` border) distinguishing it
from new-trade cards. Show ENTRY date, DTE remaining, current status vs strikes, MANAGEMENT ACTION
prominently.

**Stock / strategy card** — section label + ticker tag + move badge + headline + strategy box +
validation line + **v3.4 "Source:" citation line below live price** + conviction line.

**Conviction display**

- HIGH → green dot
- MEDIUM → amber dot
- LOW → red dot

**Footer** — black (`#0f0f0f`) with disclaimer.

**HTML file requirements**

- Full DOCTYPE, standalone HTML
- All CSS inline
- Three cdn.jsdelivr.net font imports
- `@media print` styles
- Saved to `morning-briefs/YYYY-MM-DD.html`
