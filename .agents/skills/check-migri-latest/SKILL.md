---
name: check-migri-latest
description: Inspect the latest available Migri appointment using an externally supplied shared-browser skill, without booking.
---
Read the external browser SKILL.md specified in the request. Use its long-lived controller; never copy or modify that skill. Parameters in the request are authoritative.

Use the dedicated profile and command/response files in the supplied runtime directory. First probe an existing controller using a unique integer ID and title command. Reuse it if responsive. Otherwise start the external controller detached with logs in the runtime directory, URL=about:blank, the supplied profile and command files. This preserves an existing browser page. Reuse the existing Migri tab; navigate to https://migri.vihta.com/ only if needed. Never close the dedicated browser after a check. Use supplied PLAYWRIGHT_MODULE or locate an existing installation; do not install dependencies.

Inspect visible page state before acting. Switch to English and verify category, service, office, people count, and family checkbox against the request. Retain correct selections. Refresh availability with Search availability on every run. Never use direct Migri HTTP requests or select an appointment.

Wait a uniformly random duration between the supplied minimum and maximum before each click. Move the pointer gradually using Playwright mouse.move with steps through the existing CDP connection before clicking; if the external controller lacks this capability, use a temporary CDP helper with the existing Playwright installation. Do not rewrite the external controller. Serialize all browser actions.

Use Last week to establish the booking horizon. Verify whether later weeks can be reached. Find the latest actual available appointment, scanning backward if necessary and expanding More for its day. Derive year and timestamp from full accessible appointment labels; use Europe/Helsinki. Do not confuse the last calendar day with an available slot. If the complete search cannot be established within the time budget, report error rather than a partial result. Stop on challenges or blocks without retries.

Return only the requested JSON result. status is available, no_availability, or error. Echo observed filters, not merely requested filters. latest_at must include a timezone offset when available; otherwise null. horizon is the observed final calendar date or null. evidence explains the UI observations or failure. No booking or notification actions are authorized in this skill. Leave repository files unchanged. Stop any helper performing browser actions before returning.

Desktop and mobile controls may coexist in the DOM. Restrict click locators to visible elements and verify uniqueness; on ambiguous selectors inspect and refine the locator rather than abandoning the check. In successful results map observed labels to the supplied canonical city/category/service slugs.
