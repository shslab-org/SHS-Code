---
name: cpp
description: C++: modern C++, STL, CMake, RAII, templates
version: 1.0.0
tags: ['cpp', 'stl', 'cmake', 'modern']
required_config: []
platform: []
---

# C++ Skill

## When to Use
Modern C++: STL, RAII, templates, CMake projects.

## Protocol
1. RAII everywhere; smart pointers (unique_ptr default).
2. CMake with targets and properties, not global flags.
3. std::string_view/span at API boundaries.
4. -Wall -Wextra -Werror locally before committing.

## Verification
CMake configure+build succeeds; unit tests run clean.
