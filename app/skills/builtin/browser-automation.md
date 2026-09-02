---
name: browser-automation
description: Browser automation: scraping, testing, Playwright/Selenium
version: 1.0.0
tags: ['browser', 'scraping', 'playwright', 'selenium']
required_config: []
platform: []
---

# Browser Automation Skill

## When to Use
Scraping, automated testing, browser scripting.

## Protocol
1. Check robots/ToS and rate-limit politely.
2. Wait for conditions (selectors, network idle), never fixed sleeps.
3. Selectors: prefer semantic (aria, data-*) over brittle paths.
4. Headless-first; screenshot on failure for diagnosis.

## Verification
Script completes without timeout flake; extracted data validates against schema.
