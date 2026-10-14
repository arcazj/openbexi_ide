# SPELL procedures

Open `spell_menu.py`, keep **Python** selected in the browser desktop, then Run
or Debug. Enter a choice in the console and press **Send** or **Enter**.

- Choices **1–11** exercise PY, COMMON, TIME, DATA, FILES, FLOW, UI, OBS, CMD,
  LIMIT and SPECIAL, where the selected runtime supports them.
- **12** browses all 763 language-reference entries by family or `ALL`.
- **13** runs every non-command demonstration. Each result is `PASS`, `FAIL`,
  or `UNAVAILABLE`; unavailable features never count as passed.
- **14–15** run successive native prompts and a native parent/child workflow.
- **16** sends exactly one CMD1 to the local DSS simulator only after you type
  `SEND CMD1`. It is excluded from Run all. A cancelled confirmation sends nothing.
- **0** exits. Results are saved as `spell_menu_results.json` in the project.

The browser SDK supports the six PY/COMMON/TIME/UI/OBS/CMD demonstrations; its
telemetry and command catalogue use the bundled DSS. DATA/FILES/FLOW need the
original native backend. LIMIT/SPECIAL and native DSS connection setup remain
outside this desktop profile. The catalogue records a historical native
qualification checkpoint, not 763 passing tests in this menu. Full native
language conformance remains incomplete.

| Procedure | Purpose | Runtime |
| --- | --- | --- |
| `test_spell.py` | Display, TIME and wait; extended native checks when available | SDK or native |
| `spell_sdk_telemetry.py` | Read TM1 and verify its range without sending commands | Browser SDK |
| `spell_native_data.py` | Typed data, variables, shared data and cleanup | Native |
| `spell_native_time.py` | UTC arithmetic and timed waiting | Native |
| `spell_native_prompt.py` | Two answers, saved to JSON | Native |
| `spell_native_parent.py` | Child prompt followed by parent prompt | Child-capable native host |
| `spell_native_child.py` | Child procedure, also runnable alone | Native |

Native YES_NO prompts use **0=Yes** and **1=No**. The native backend runs the
original `spell.lib` in its separately installed runtime; the browser SDK is a
smaller profile. Select the actual native backend to run the `spell_native_*`
files. The language menu displays the profile at startup.
