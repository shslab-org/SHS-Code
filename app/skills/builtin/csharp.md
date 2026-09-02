---
name: csharp
description: C#/.NET: ASP.NET Core, LINQ, async/await
version: 1.0.0
tags: ['csharp', 'dotnet', 'aspnet']
required_config: []
platform: []
---

# C#/.NET Skill

## When to Use
.NET services, ASP.NET Core APIs, LINQ pipelines.

## Protocol
1. dotnet new templates; target LTS .NET unless specified.
2. async/await all the way down — never .Result.
3. DI registrations grouped in Program/Startup.
4. LINQ for transforms; keep queries readable.

## Verification
dotnet build zero warnings; endpoint smoke test returns 2xx.
