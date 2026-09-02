---
name: php
description: PHP: Composer, Laravel/Symfony, PSR standards
version: 1.0.0
tags: ['php', 'composer', 'laravel']
required_config: []
platform: []
---

# PHP Skill

## When to Use
PHP web apps, Composer packages, framework work.

## Protocol
1. Composer with version constraints; lockfile committed.
2. PSR-12 style; PSR-4 autoloading.
3. Validate all input; parameterized queries only.
4. Framework conventions (Laravel/Symfony) over bespoke wiring.

## Verification
php -l passes on changed files; framework tests green.
