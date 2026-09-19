# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

`db-retry` is a library of retry, connection, and transaction helpers for PostgreSQL applications
built on SQLAlchemy's asyncio extension and asyncpg; [`CONTEXT.md`](CONTEXT.md) opens with what it
does and owns the vocabulary — read it before naming a concept in code, a test name, or an issue
title. The words most easily got wrong here are the ones this package shares with PostgreSQL and
with tenacity: what "retriable" covers, what a "retry" counts, and what "primary" does not mean.

## Commands

`just` (task runner) and `uv` (package manager). The [`justfile`](justfile) is the source of truth —
`just --list`, or read it. The one thing it does not say: `just test` is Docker-only, so without a
Docker daemon, point `DB_DSN` at any reachable PostgreSQL and run `uv run pytest` directly.

## Architecture

Every module under `db_retry/` is named for what it does and is short enough to read whole. Read
them.

## Workflow

Every link in `README.md` must be absolute: `https://github.com/modern-python/<repo>/blob/main/<path>`,
or `.../tree/main/<path>` for a directory. Never a relative path: `README.md` is also the PyPI long
description, and PyPI does not rewrite relative links, so a relative one 404s on the package page.

## Agent skills

### Issue tracker

GitHub issues on `modern-python/db-retry`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
