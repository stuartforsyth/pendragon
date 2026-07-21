---
id: core.game-system.critical-bonus
book: core
chapter: "2 — The Game System"
pages: [28, 30, 31]
tags: [resolution, skill, trait, passion, critical, critical-bonus, fumble, opposed, mastery]
title: The Critical Bonus (Statistics over 20)
see_also: [data:combat.json#resolution, core.combat.resolution-matrix, core.combat.winners-outcome]
---

## The Critical Bonus

With the exception of **Characteristics**, no Statistic value may ever exceed 20.
Any points in a Skill, Trait, or Passion **above 20 become the critical bonus**,
written as `20 (+x)` where `x = value − 20`. The x-value is **always added to the
result of the d20 roll** for that Statistic.

Because the bonus is added to the roll, it **widens the critical range**: a
Statistic of `20 (+x)` scores a critical success on any natural roll **≥ 20 − x**.

- Example: a knight with **Sword 20 (+4)** who rolls 16 gets 16 + 4 = 20 — a
  critical. They critical on any roll **≥ 16**.
- So **Sword 22** is `20 (+2)`: it criticals on **18, 19, or 20**, and — being a
  value of 20 or more — **can never fail and can never fumble**.

The bonus also **improves opposed rolls even when the result is not a critical**,
since a higher roll beats a lower one.

**All criticals are equal.** A modified roll above 20 still counts simply as a
critical success with a value of **20**. If one combatant's modified roll is 21
and their opponent's is 30, both count as criticals of 20 — a **tie**.

### Temporary critical bonus from modifiers

Statistic modifiers or inspiration from Passions can create a **temporary**
critical bonus: if a modifier raises a value above 20, the difference over 20
becomes the bonus while it applies. E.g. Sword 18 with a +5 Height Advantage
becomes 23 → **20 (+3)** for as long as the advantage lasts.

### No fumble at 20+ (and its converse)

A **Statistic value of 20 has no chance of a fumble**; a natural 20 becomes a
**critical** instead (printed p.28). Thus a knight with Sword 16 (who normally
fumbles on a 20) who is bumped to **20 (+1)** by a +5 modifier can no longer
fumble. Conversely, a penalty that drops the effective value **below 20 makes
fumbles possible again**.

### Optional rule — mutual bonus reduction (opposed rolls)

When two characters make an opposed roll and **both** have a critical bonus,
reduce each bonus by the **lower** of the two. E.g. Sword `20 (+3)` vs `20 (+5)`
become `20` and `20 (+2)`. This puts equally-proficient characters on a more even
footing, yielding fewer criticals overall.

## Base outcomes (values ≤ 20, for context)

- **Critical:** natural roll exactly equals the Statistic value.
- **Success:** roll ≤ the value (roll-under).
- **Failure:** roll > the value.
- **Fumble:** a natural 20 — **unless** the value is 20+, in which case 20 is a
  critical and no fumble is possible.
- **Characteristics** are pass/fail only: no critical/fumble distinction, and
  they may exceed 20 (which simply means near-automatic success).
