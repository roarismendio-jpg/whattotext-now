# learnings (newest first)

## open tests from batch01 (pre-registered)
- format-P1 / P2 / P3: the same situation as a typing reel vs a copy carousel. Hypothesis: carousels win on saves and follows, reels win on reach. Decide at 48h with ≥500 reach each.
- hook pattern: `text_to_send_when` vs `how_to` across the batch (bandit arms). Hypothesis: "the text to send when…" earns more sends because it names the recipient.
- deletion moment: every typing reel types a bad first draft and deletes it. Once trials are on, test reels without the deletion to see if the hesitation actually holds people (skip rate).

## platform facts (Nov 2026)
- Trial reels need a public professional account with ~200 followers. API: trial_params with graduation_strategy MANUAL or SS_PERFORMANCE (we use SS_PERFORMANCE).
- reels_skip_rate (share of viewers who skip in the first 3s) is available in the API and is our hook metric.
- Hashtags are capped at 5 per post; we use 3.
- Original content only: aggregator-style accounts lose recommendations (April 2026).
