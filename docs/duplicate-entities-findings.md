# Duplicate entities: findings (2026-10-26, task t_98db8d54)

Repo: HomeAssistant-Cast-Metadata-Controls @ main 66d6f30 (v8.4.0). No functional code changed.
Evidence also from the earlier live-HA repro/backup tasks (t_08478232, t_ba9f4a55).

## Verdict
No true duplicate entities are created by this integration's code. What looks like duplication is
overlap between *different* integrations, plus two naming defects.

## Findings

| # | Symptom | Root cause | Where | Proposed fix |
|---|---------|-----------|-------|--------------|
| 1 | 4 media_players for one TV | 4 distinct integrations, each with its own entity: `braviatv`, `cast`, `dlna_dmr`, and this integration's `UnifiedMediaController` (unique_id `<UID_VERSION>\|<group>\|media_player\|controller`). Not a registry duplicate. | `media_player.py:184-191` | In HA UI, disable (not delete) the redundant `cast` / `dlna_dmr` media_player entities; keep `braviatv` + Controller. No code change. |
| 2 | 3 sensor sets per TV | By design: one `MetadataSensor` set per underlying *source* (state / snapshot / attributes). IDs are source-stable `v2\|<source_id>\|<kind>[\|<attr>]`, guarded by `if unique_id in self._sensors` so repeated setup cannot re-add them. | `util.py:34-41`, `sensor.py:170-181` | None. Optionally hide sources the user does not want via integration options. |
| 3 | Suspected orphan `v1\|` registry entries | Checked live registry: none left. Migration removes them (`v1\|` sensors + old-domain entities) at config-entry v9; stale group entities are pruned on setup. | `__init__.py:80-100`, `__init__.py:340-356` | None. |
| 4 | Device/friendly name "BRAVIA 4K UR3" on `ke_55xh8096` ids | `_preferred_group_name` takes the first non-generic of `device_name`, `name`, `model` by source priority, so the native model string beats the user's name; entity_ids keep the old slug. | `grouping.py:309-319`, `runtime.py:146-165` (`name=group.name`) | Prefer the user-set device name / configured group name over `model` in `_preferred_group_name`; then rename entity_ids in HA registry. |
| 5 | Area/floor suffixes in entity_ids | HA derives entity_id from device name + `has_entity_name`; names come from the device registry, so renaming/area moves after first creation leave suffixed ids. Not an integration bug. | `sensor.py:208`, `media_player.py:184` | Rename entity_ids once in HA UI (or via `ha_set_entity`) after fixing #4. |

## Not checked
Disabled/hidden registry entries; the Unified-TV-Card repo.

## Needs Tomás
1. Fix choice: (a) disable redundant cast/dlna_dmr entities in HA only, (b) patch naming in `grouping.py`, or both.
2. Main has unrelated uncommitted edits (ad_skip.py, strings.json, en/pt translations); left untouched, this branch was created via `git worktree`.
