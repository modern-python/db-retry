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
`just --list`, or read it. Two things it does not say: a `ty` suppression is written `# ty: ignore`,
never `# type: ignore`; and `just test` is Docker-only, so without a Docker daemon, point `DB_DSN`
at any reachable PostgreSQL and run `uv run pytest` directly.

## Architecture

Every module under `db_retry/` is named for what it does and is short enough to read whole. Read
them.

## Workflow

Real work **not scheduled** becomes a GitHub issue.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches.
Nothing enforces that docstring shape; it is read at review time.
