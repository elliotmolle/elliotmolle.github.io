# Nexus cross-device handoff

Use this branch as the handoff point for the other laptop. `AGENT_HANDOFF.md` may be deleted after integration and verification are complete.

## 1. What owns Nexus now

1. `collector.py` at the repo root is the active collector.
2. `nexus/index.html` is the dependency-free shell.
3. `nexus/styles.css` owns styling.
4. `nexus/app.js` owns runtime behavior and fetches `./news_data.json`.
5. `nexus/news_data.json` is the public feed output.
6. `nexus/collector_sources.json` is the public Energy source config.
7. `nexus/news_quality_contract.json` is the current validation contract and source registry.
8. Old compiled Vite assets under `nexus/assets/` are not the source of truth.

Field names to keep straight:

- Public feed items use `source_tier` and `primary_source`.
- The contract source registry uses `tier` and `primary_source`.
- `collector.py` accepts config aliases like `sourceTier` and `isPrimarySource`, then normalizes them.

## 2. Verified public Energy source configuration

1. The checked-in config is `nexus/collector_sources.json`.
2. Every enabled source is public and scoped to `Energy`.
3. Current enabled feeds are:
   - ISO New England Newswire
   - PJM Board Public Disclosures
   - ANS Nuclear Newswire
   - NucNet
   - Duke Energy Newsroom
   - Entergy Newsroom
   - NextEra Energy Newsroom
   - GE Vernova Newsroom
4. The collector skips `Admin` and `Personal` topics so they can live in a separate collector later.

## 3. CLI help

Run these from the repo root:

```powershell
python .\collector.py --help
python .\scripts\news_quality_pipeline.py --help
```

Collector help includes `--write`, `--dry-run`, `--merge-existing` on by default, `--no-merge-existing`, `--backup-existing`, source and item limits, retries, and validation thresholds.

Quality pipeline help includes `--feed`, `--contract`, and `--json`.

## 4. Dry-run and write commands

1. Change to the repo root:

```powershell
Set-Location C:\Users\M05282\elliotmolle.github.io
```

2. Dry run without writing:

```powershell
python .\collector.py --dry-run --verbose
```

3. Write atomically:

```powershell
python .\collector.py --write --backup-existing --verbose
```

4. To ignore existing feed records, disable merge:

```powershell
python .\collector.py --write --no-merge-existing
```

## 5. Merge-existing behavior and quality gates

1. `--merge-existing` is the default.
2. The collector reads `nexus/news_data.json`, normalizes valid existing records, merges them with fresh items, dedupes, then applies source and host limits.
3. Invalid or stale existing records are dropped during normalization.
4. Writing is blocked if `min_success_sources` or `min_items` is not met, if no valid items remain, or if contract validation fails.
5. `--dry-run` never writes a file.
6. Collector exit codes are meaningful:
   - `0` success or dry run
   - `2` config error
   - `3` collection error
   - `4` quality gate failure
   - `5` contract validation failure
   - `6` write failure

## 6. Backups and atomic writes

1. `--backup-existing` creates a timestamped backup before writing.
2. Writes go to a temp file in the destination directory.
3. The temp file is swapped into place with an atomic replace.
4. This avoids partially written public JSON on GitHub Pages.

## 7. How to validate output

1. Run the collector in dry-run or write mode.
2. Validate the feed:

```powershell
python .\scripts\news_quality_pipeline.py --feed .\nexus\news_data.json
```

3. Add `--json` if you want machine-readable findings.
4. Serve the repo root locally:

```powershell
python -m http.server 8000
```

5. Open:
   - `http://localhost:8000/nexus/index.html`
6. Verify:
   - feed loads
   - search works
   - topic, category, impact, and sort filters work
   - detail panel opens
   - source links open
   - timestamps render
   - no console errors
7. Re-run the quality pipeline after any data change.
8. Check `git status --short` before handoff.

## 8. Recommended local and manual scheduling

1. Keep scheduling local first, either from PowerShell or Task Scheduler.
2. A simple Windows Task Scheduler action can run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Set-Location C:\Users\M05282\elliotmolle.github.io; python .\collector.py --write --backup-existing --verbose; python .\scripts\news_quality_pipeline.py --feed .\nexus\news_data.json"
```

3. Example GitHub Actions design, without adding a workflow yet:

```yaml
on:
  schedule:
    - cron: "0 12 * * *"
```

Then run checkout, set up Python, run `python .\collector.py --write --backup-existing --verbose`, run the quality pipeline, and commit only if `nexus/news_data.json` changed.

## 9. Windows commands

1. `Set-Location C:\Users\M05282\elliotmolle.github.io`
2. `git status --short`
3. `git diff --check`
4. `python .\collector.py --help`
5. `python .\scripts\news_quality_pipeline.py --feed .\nexus\news_data.json`

## 10. How the other laptop should compare or integrate its old collector

1. Keep the new root `collector.py` as the baseline.
2. Compare the old collector against the current config, contract, and feed output.
3. Port only useful source entries or normalization rules.
4. Do not overwrite `nexus/index.html`, `nexus/styles.css`, or `nexus/app.js`.
5. Do not blindly replace the new root collector.
6. Do not overwrite `nexus/news_data.json` with old output unless you have diffed the item-by-item changes and mean to accept them.
7. If the old collector is still useful, bring it across in a separate file or branch, then merge by hand.

## 11. Handling feed endpoint failures

1. The collector retries transient HTTP failures.
2. Retryable responses include common 429 and 5xx cases.
3. If a source still fails, it is skipped and the rest of the run continues.
4. If failures reduce successful sources below `min_success_sources`, writing is blocked.
5. If a feed is flaky, increase `--retries`, adjust `--timeout-seconds`, or disable that source in `nexus/collector_sources.json`.

## 12. Public GitHub Pages data safety

1. `nexus/news_data.json` is public.
2. Do not add secrets, internal URLs, credentials, private notes, or nonpublic source material.
3. GitHub Pages cannot be made private through client-side authentication.
4. Personal-interest and admin feeds must later use a separate config and separate output file, or an authenticated backend.
5. They must never be merged into the public `nexus/news_data.json`.

## 13. Original admin mode and future restoration checklist

The original admin mode should come back only as a separate private path, not inside the public feed.

Checklist:

1. Restore an admin-only collector or backend.
2. Use a separate admin config file.
3. Write to a separate private output file.
4. Protect private data with server-side auth, not client-side checks.
5. Keep the public Energy collector unchanged.
6. Verify the public feed still passes quality and loads on GitHub Pages.

## 14. Contract and quality tool notes

1. `nexus/news_quality_contract.json` defines required fields, optional fields, allowed values, freshness limits, and source registry entries.
2. Required feed fields are `id`, `title`, `summary`, `source`, `url`, `timestamp`, `topic`, `category`, `impact`, and `sentiment`.
3. Optional feed fields are `source_tier`, `primary_source`, `claims`, `citations`, `tickers`, `entities`, `data_as_of`, and `editorial_notes`.
4. The quality pipeline is read-only. It reports findings and does not modify the feed.

## Completion checklist

- [ ] Collector merged without overwriting the new frontend
- [ ] Public feed matches the contract
- [ ] Quality tool returns `0`
- [ ] Nexus works over HTTP
- [ ] No console errors
- [ ] Only intended files changed
- [ ] `AGENT_HANDOFF.md` is no longer needed
