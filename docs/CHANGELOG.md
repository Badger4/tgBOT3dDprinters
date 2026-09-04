# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-13

### Added
- Telegram Bot & WebApp SPA for Bambu Lab 3D printer farm management
- Real-time MQTT telemetry monitoring (nozzle/bed temps, progress, layers, AMS slots)
- Direct FTPS file upload (3MF/G-Code) with filament weight parsing
- Automated filament consumption tracking per AMS slot
- Server-Sent Events (SSE) live dashboard
- Commercial print cost calculator with flexible presets
- Print history with PDF export
- User access control with admin approval system
- Maintenance hour tracking per printer component
- OrcaSlicer post-processing hook integration

### Security
- Strict CORS origin whitelist (Telegram WebApp, WEBAPP_URL, localhost)
- CSP with separate script-src/style-src/font-src directives (no unsafe-inline for scripts)
- 3-tier IP rate limiting (uploads: 30/min, control: 20/min, telemetry: 300/min)
- SensitiveDataFilter on all loggers (root, aiohttp.access, aiogram)
- Safe math evaluator replacing eval() for filament weight input
- Access code masking in REST API responses

### Developer Experience
- GitHub Actions CI with Pytest, Mypy strict type checking, and pip-audit CVE scanning
- mypy.ini with strict configuration (disallow_untyped_defs, no_implicit_optional)
- Comprehensive test suite (108 unit tests)
