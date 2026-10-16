"""Execute the real appended inspector under a delayed CommonJS export in Node.

Prepared for the next consolidated verification. These fixtures exercise the
module-loading fault and event subscription recovery, not a copy of hookFx.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


LAUNCHER = Path(__file__).resolve().parents[1]
DESCRIPTOR = LAUNCHER / "shared" / "bbee-inspector" / "mod.json"

NODE_FIXTURE = r"""
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = JSON.parse(fs.readFileSync(0, "utf8")).source;
const scenario = process.argv[1];

function fixture(options = {}) {
  const clock = { wall: 100000 };
  const calls = { add: 0, fp: 0, singleton: 0, callbacks: [], fail: options.fail || 0 };
  const moduleExports = { U: undefined };
  const effectManager = {
    add_PreprocessEffect(callback) {
      calls.add++;
      if (calls.fail > 0) { calls.fail--; throw new Error("fixture subscription rejected"); }
      calls.callbacks.push(callback);
    }
  };
  const managerType = { Instance: options.managerReady === false ? null : effectManager };
  const player = {
    BaseID: 100101, UniqueId: 1, Position: { x: 0, y: 0 }, Dir: 1,
    ActorModel: { transform: { root: { name: "fixture-player" } } },
    ActionMgr: { ActionChangeAutoId: 1, CurrentActionName: "stand", Time: { number: 0 },
                 CurrentActionDuration: { number: 1 }, CurrentActionType: 0 },
    SkillMgr: { get_Item() { return null; } },
    Input: { GetCmdStatus() { return null; } },
    BuffMgr: { BuffAttr: { Stun: false, LockInputAttack: false }, Find() { return null; } },
    Attr: { GetMP() { return { number: 50 }; }, GetMPMax() { return { number: 100 }; } }
  };
  const battle = { PlayerSelf: player, BattleTimeFp: { number: 123 }, TimeScale: 1 };
  class FixtureDate extends Date { static now() { return clock.wall; } }
  const context = vm.createContext({
    Date: FixtureDate, Util_1: moduleExports,
    csharp_1: {
      GamePlay: { BattleBase: { Cur: battle } },
      NOAH: { VFX: { VFXManager: managerType } },
      UnityEngine: { KeyCode: {}, Input: { GetKeyDown() { return false; } } },
      System: { IO: { File: { Exists() { return false; } } } }
    }
  });
  // Deliberately evaluate the entire production IIFE before Core/Util assigns U.
  vm.runInContext(source, context, { filename: "bbee-inspector-production.js" });
  assert.equal(typeof context.BBI_Tick, "function");
  function provideUtil() {
    moduleExports.U = {
      GetSingleton(type) { calls.singleton++; return type.Instance; },
      FpToFloat(value) { calls.fp++; return value.number; }
    };
  }
  function tick(elapsed = 0) { clock.wall += elapsed; context.BBI_Tick(1 / 60, { R: {} }); }
  function effects() { return context.BBI.hist.filter(event => event.k === "fx+"); }
  function installed() { return context.BBI.hist.filter(event => event.msg === "effect hook installed"); }
  function emitEffect() {
    const hub = { Param: { name: "fixture/effect", bind: true, dontStop: false,
                          target: { root: { name: "fixture-player" }, name: "hand" } },
                  gameObject: { activeInHierarchy: true } };
    for (const callback of calls.callbacks) callback(hub);
  }
  return { context, clock, calls, provideUtil, managerType, effectManager,
           tick, effects, installed, emitEffect };
}

if (scenario === "late-util") {
  const f = fixture();
  f.tick();
  assert.equal(f.context.BBI.hooked, false, "an unavailable export is not a successful hook");
  assert.equal(f.calls.add, 0);
  assert.equal(f.context.BBI.warn.length, 1, "the missing export remains diagnosable");
  for (let i = 0; i < 20; i++) f.tick(10);
  assert.equal(f.context.BBI.warn.length, 1, "frames do not spam the same failure");
  f.tick(1000);
  assert.equal(f.context.BBI.warn.length, 1, "retrying the same cause does not repeat a warning");
  f.provideUtil();
  f.tick(1000);
  assert.equal(f.context.BBI.hooked, true);
  assert.equal(f.calls.add, 1);
  assert.equal(f.calls.callbacks.length, 1);
  assert.equal(f.installed().length, 1);
  assert.equal(f.context.BBI.clock, "battle", "Fp conversion also reads the late export");
  assert.ok(f.calls.fp > 0);
  assert.equal(f.context.BBI.mp, 50);
  assert.equal(f.context.BBI.warn.length, 1, "recovery does not erase the failure history");
  for (let i = 0; i < 20; i++) f.tick(1000);
  assert.equal(f.calls.add, 1, "successful subscription is not installed again");
  f.emitEffect(); f.tick();
  assert.equal(f.effects().length, 1, "the real callback still records an owned effect");
  assert.equal(f.context.BBI.err, undefined, "unrelated inspector work stays usable");
} else if (scenario === "subscription-error") {
  const f = fixture({ fail: 1 });
  f.provideUtil(); f.tick();
  assert.equal(f.calls.add, 1);
  assert.equal(f.context.BBI.hooked, false);
  assert.equal(f.installed().length, 0, "a thrown subscription never reports success");
  assert.ok(f.context.BBI.warn[0].msg.includes("fixture subscription rejected"));
  for (let i = 0; i < 20; i++) f.tick(10);
  assert.equal(f.calls.add, 1, "subscription exceptions are rate limited");
  f.tick(1000);
  assert.equal(f.context.BBI.hooked, true);
  assert.equal(f.calls.add, 2);
  assert.equal(f.calls.callbacks.length, 1);
  assert.equal(f.installed().length, 1);
  assert.equal(f.installed()[0].attempts, 2);
  assert.equal(f.context.BBI.warn.length, 1);
  f.emitEffect(); f.tick();
  assert.equal(f.effects().length, 1);
  f.tick(1000);
  assert.equal(f.calls.add, 2);
} else if (scenario === "late-manager") {
  const f = fixture({ managerReady: false });
  f.tick();
  f.provideUtil(); f.tick(1000);
  assert.equal(f.context.BBI.hooked, false);
  assert.equal(f.calls.add, 0);
  assert.equal(f.context.BBI.warn.length, 2, "a changed failure cause is preserved");
  assert.ok(f.context.BBI.warn[1].msg.includes("VFXManager effect event is not ready"));
  f.tick(1000);
  assert.equal(f.context.BBI.warn.length, 2);
  f.managerType.Instance = f.effectManager;
  f.tick(1000);
  assert.equal(f.context.BBI.hooked, true);
  assert.equal(f.calls.callbacks.length, 1);
  assert.equal(f.installed().length, 1);
  assert.equal(f.context.BBI.warn.length, 2);
} else {
  throw new Error("unknown fixture scenario");
}
process.stdout.write(JSON.stringify({ scenario, passed: true }));
"""


class InspectorLoadingCycleTests(unittest.TestCase):
    def run_node_fixture(self, scenario):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Pinned Node runtime is required for inspector regression")
        descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8-sig"))
        source = next(item["append"] for item in descriptor["content"]["js"] if item.get("append"))
        result = subprocess.run(
            [node, "-e", NODE_FIXTURE, scenario], input=json.dumps({"source": source}),
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"scenario": scenario, "passed": True})

    def test_late_util_export_recovers_without_duplicate_subscription(self):
        self.run_node_fixture("late-util")

    def test_subscription_exception_recovers_and_keeps_failure_history(self):
        self.run_node_fixture("subscription-error")

    def test_late_singleton_and_changed_cause_stay_diagnosable(self):
        self.run_node_fixture("late-manager")


if __name__ == "__main__":
    unittest.main()
