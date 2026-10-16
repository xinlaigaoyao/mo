/* Native simulation callbacks, appended to GamePlay/BattleActor/ActorFuncs.
 * No damage, input, cooldown or resource work runs from the HUD render tick.
 * Bindless ActorFuncs.ExternCall supplies (actorJs, evaluated params, native object).
 * Current build: 25627491. All values below are BBEE adaptations, not WS statistics.
 */
(function () {
  "use strict";
  var G = globalThis, A = 200901, BULLET = 20090101;
  var POLICY = G.BB_YWY_INPUT_POLICY;
  if (!POLICY || POLICY.schema !== 1) throw new Error("YWY native input policy was not prepared");
  var R = G.__bbYWY = G.__bbYWY || { states: new Map(), errors: {}, revision: 2 };
  R.visuals = R.visuals || new Map(); R.impacts = R.impacts || new Map();
  function U() { return require("Core/Util").U; }
  function CS() { return require("csharp"); }
  function fp(v) { return U().FloatToFp(v); }
  function f(v) { return U().FpToFloat(v); }
  function battle() { return CS().GamePlay.BattleBase.Cur; }
  function now() { return f(battle().BattleTimeFp); }
  function own(a) { return !!a && a.BaseID === A; }
  function owner(a) { return own(a) ? a : a && own(a.RootCaster) ? a.RootCaster : null; }
  function enemy(a, o) {
    return !!a && a.Faction !== o.Faction && !!a.TagMgr &&
      (a.TagMgr.HasTag("Monster") || a.TagMgr.HasTag("Boss")) &&
      !a.TagMgr.HasTag("TargetIgnore") && !a.TagMgr.HasTag("CantBeHit");
  }
  function error(k, e) {
    if (!R.errors[k]) { R.errors[k] = String(e); console.error("GamePlay", "[YWY] " + k + ": " + e); }
    return false;
  }
  function clear(a) {
    if (!a) return;
    R.states.delete(a.UniqueId);
    a.BuffMgr.Remove("ywy_shield");
  }
  function state(a) {
    if (!own(a)) return null;
    var s = R.states.get(a.UniqueId);
    if (!s || s.actor !== a || s.battle !== battle()) {
      s = { actor: a, battle: battle(), room: 0, shi: 0, lastStyle: "", lastWeave: -1e9,
        action: -1, hitPaid: -1, shieldUntil: 0, shieldRatio: 0, guardPaid: -1, guardUntil: 0,
        escapeReady: 0, counterReady: 0, wuxiangUntil: 0, pulseReady: 0,
        groundDashCount: 0, groundDashReady: 0, usedPress: {},
        dodgeUntil: 0, snapshot: 0, emit: {}, hits: 0, guards: 0, starts: 0 };
      R.states.set(a.UniqueId, s);
      a.Attr.SetMP(fp(100), 2);
      a.Attr.SetMP(fp(100), 3);
    }
    return s;
  }
  function has(a, n) { return !!a.TriggerMgr.FindTrigger((209000 + n) * 10 + 1); }
  function qi(a, v) { a.Attr.SetMP(fp(Math.max(0, Math.min(100, f(a.Attr.GetMP(2)) + v))), 2); }
  function ultra(a, v) { a.Attr.SetMP(fp(Math.max(0, Math.min(100, f(a.Attr.GetMP(3)) + v))), 3); }
  function shi(s, v) { s.shi = Math.max(0, Math.min(5, s.shi + v)); }
  function shield(a, s, layers) {
    var gift = Math.min(0.15, Math.max(0, layers * 0.03));
    if (!gift) return;
    var ratio = now() < s.shieldUntil ? Math.max(s.shieldRatio, gift) : gift;
    a.BuffMgr.AddBuff("ywy_shield", fp(3), fp(ratio), 1, a);
    a.BuffMgr.RefreshBuffAttrForce();
    a.Attr.SetShield(fp(Math.min(f(a.Attr.MaxShield), f(a.Attr.Shield) + f(a.Attr.MaxHp) * gift)));
    s.shieldRatio = ratio;
    s.shieldUntil = now() + 3;
  }
  function spawn(a, rowName, action, x, y, dx, dy, scale, target) {
    var row = a.SkillMgr.FindSkillByActionName(rowName);
    if (!row) throw new Error("projectile damage source row missing: " + rowName);
    var C = CS(), v = C.UnityEngine.Vector2;
    var b = battle().BulletMgr.CreateBulletByParams(a, BULLET,
      U().Vector2ToFp2(new v(x, y)), U().Vector2ToFp2(new v(dx, dy)), fp(scale || 1), action, row.SkillActivate, null);
    if (b && target) b.TargetMgr.SetTarget(target);
    return b;
  }
  function inputState(a, key) { return a.Input.GetCmdStatus(key); }
  function freshPress(a, s, key) {
    var st = inputState(a,key);
    if (!st) return false;
    var stamp = f(st.LastPressTimeStamp), elapsed = f(a.Input.GetTimeEllaps(st.LastPressTimeStamp));
    return elapsed >= 0 && elapsed <= POLICY.buffer && s.usedPress[key] !== stamp;
  }
  function acceptPress(a, s, key) {
    if (!key || !freshPress(a,s,key)) return;
    s.usedPress[key] = f(inputState(a,key).LastPressTimeStamp);
    // Consume an edge only after a real native action starts. This API does not
    // release the physical key: Pressing/LongPressing still enter the charge.
    a.Input.SetPressInputSatisfied(key,true);
  }
  function moveAllowed(a, s, p) {
    var cur = a.ActionMgr.CurrentActionName, age = f(a.ActionMgr.Time), target = p.move;
    if (a.IsDead || a.CinemaControl) return false;
    if (p.group === 8) {
      var attack = inputState(a,1);
      return cur === "ywy_charge" && !!attack && !attack.Pressing &&
        (target !== "ywy_circle_full" || age >= .5);
    }
    if (!p.input || !freshPress(a,s,p.input)) return false;
    if (p.group === 5) {
      if (cur === "dash" || cur === "dash2" || cur === "dashAir") {
        if (age < POLICY.dash_follow) return false;
      } else if (age < POLICY.dash_cancel) return false;
    } else {
      if (cur === "ywy_charge" && (p.group === 1 || p.group === 4)) return false;
      var recovery = POLICY.recovery[cur] || 0;
      if (p.group === 7 && recovery) recovery = POLICY.jump_cancel;
      if (/^(dash|dash2|dashAir|ywy_escape)$/.test(cur)) recovery = POLICY.dash_attack;
      if (age < recovery) return false;
    }
    if (target === "ywy_sword2" && cur !== "ywy_sword1") return false;
    if (target === "ywy_sword3" && cur !== "ywy_sword2") return false;
    if (target === "ywy_sword1" && (cur === "ywy_sword1" || cur === "ywy_sword2")) return false;
    if (target === "ywy_air2" && cur !== "ywy_air1") return false;
    if (target === "ywy_air1" && (cur === "ywy_air1" || cur === "ywy_air2")) return false;
    if (p.group === 7 && target === cur) return false;
    if (target === "ywy_zhenwu") {
      // InputDir=Any is the native neutral fallback. Do not silently turn an
      // unaffordable Up+Skill chase into the cheaper neutral projectile.
      var dir = inputState(a,p.input).LastStartPressingDir;
      if (dir && f(dir.y) !== 0) return false;
    }
    return true;
  }
  function start(a, p) {
    var s = state(a), id = a.ActionMgr.ActionChangeAutoId;
    if (!s || s.action === id) return true;
    s.action = id; s.hitPaid = -1; s.emit = {}; s.starts++;
    var k = p.kind || "", t = now();
    var key = p.input || (/^(sword1|sword2|sword3|air1|air2|launcher)$/.test(k) ? 1 :
      /^(fist|chase|zhenwu)$/.test(k) ? 3 : k === "ultra" ? 4 : /^(dash|escape)$/.test(k) ? 55 : 0);
    acceptPress(a,s,key);
    if (k === "charge") spawn(a,"ywy_sword1","ywy_fx_charge",a.Position.x,a.Position.y,a.Dir,0,1,a);
    if (k === "short" || k === "full") spawn(a,a.ActionMgr.CurrentActionName,"ywy_fx_circle",a.Position.x,a.Position.y,a.Dir,0,1,a);
    if (k === "ultra") spawn(a,"ywy_ultra","ywy_fx_ultra",a.Position.x,a.Position.y,a.Dir,0,1,a);
    if (k === "escape") {
      s.escapeReady = t + 7;
      // Ordinary hit reactions only. The ActionSwitch eligibility gate excludes death, grabs and cinema.
      a.BuffMgr.RemoveByTagMask(CS().GamePlay.Buff.TagMaskByTagName("Stun"));
      return true;
    }
    if (k === "dash") {
      var dashName = a.ActionMgr.CurrentActionName;
      if (dashName === "dash" || dashName === "dash2") {
        if (t >= s.groundDashReady) s.groundDashCount = 0;
        s.groundDashCount = Math.min(2,s.groundDashCount + 1);
        s.groundDashReady = t + 0.45;
      }
      if (has(a, 8)) s.dodgeUntil = t + 1.2;
      return true;
    }
    if (k === "fist") {
      s.guardUntil = t + (has(a, 5) ? 0.45 : 0.35);
      s.guardPaid = -1;
    }
    if (k === "chase" && has(a, 3)) {
      a.ActionCountDown.SetCountDown("jump2", fp(0));
      a.ActionCountDown.SetCountDown("dashAir", fp(0));
    }
    if (k === "short" || k === "full") {
      s.snapshot = s.shi;
      var used = has(a, 9) ? Math.min(2, s.shi) : s.shi;
      shi(s, -used); shield(a, s, s.snapshot);
      if (has(a, 4)) qi(a, 5);  // the follow-up is still a native projectile, not a damage tick
    }
    if (k === "ultra") {
      s.snapshot = s.shi; shi(s, -s.shi); shield(a, s, 5);
      if (has(a, 10)) s.escapeReady = t;
    }
    return true;
  }
  function hit(a, p, h) {
    var o = owner(a), s = state(o);
    if (!s || !h || !h.Attacker || h.Attacker.UniqueId !== a.UniqueId || !enemy(h.Target,o)) return false;
    var k = p.kind || "", id = o.ActionMgr.ActionChangeAutoId, t = now();
    s.hits++;
    if (a.BaseID === BULLET) {
      var touched = R.impacts.get(a.UniqueId);
      if (!touched) { touched = { battle:battle(), targets:new Set() }; R.impacts.set(a.UniqueId,touched); }
      if (!touched.targets.has(h.Target.UniqueId)) {
        touched.targets.add(h.Target.UniqueId);
        spawn(o,"ywy_zhenwu","ywy_fx_impact",h.Target.Position.x,h.Target.Position.y+.8,o.Dir,0,1,null);
      }
    }
    if (own(a) && s.hitPaid !== id) {
      s.hitPaid = id;
      var gains = { sword1: 6, sword2: 6, sword3: 10, air1: 6, air2: 10, launcher: 6 };
      qi(o, gains[k] || 0); ultra(o, k === "ultra" ? 0 : 5);
      var style = k === "fist" ? "fist" : k === "sword1" || k === "sword2" || k === "sword3" || k === "launcher" || k === "air1" || k === "air2" || k === "chase" || k === "short" || k === "full" ? "sword" : "";
      if (k === "sword3" || k === "air2") shi(s, 1);
      if (style && s.lastStyle && style !== s.lastStyle && t - s.lastWeave > 0.1) {
        shi(s, 1); s.lastWeave = t;
        if (has(o, 7)) { shield(o, s, 1); qi(o, 5); }
        if (has(o, 11)) { qi(o, 8); ultra(o, 4); }
        if (has(o, 12) && s.shi === 5 && t >= s.pulseReady) {
          s.pulseReady = t + 2; s.wuxiangUntil = t + 3;
          spawn(o, o.ActionMgr.CurrentActionName, "ywy_wuxiang", o.Position.x, o.Position.y + 0.8, o.Dir, 0, 1, null);
        }
      }
      if (style) s.lastStyle = style;
      if (k === "sword3" && has(o, 1)) {
        spawn(o, o.ActionMgr.CurrentActionName, "ywy_sword_echo", o.Position.x + o.Dir, o.Position.y + 0.8, o.Dir, 0, 1, null);
        spawn(o, o.ActionMgr.CurrentActionName, "ywy_sword_echo", o.Position.x + o.Dir * 2, o.Position.y + 0.8, o.Dir, 0, 0.7, null);
      }
    }
    if ((k === "short" || k === "full") && own(a)) {
      var key = "attached:" + h.Target.UniqueId;
      if (!s.emit[key]) {
        s.emit[key] = true;
        spawn(o, o.ActionMgr.CurrentActionName, "ywy_attached", h.Target.Position.x, h.Target.Position.y + 0.8, o.Dir, 0, 1, h.Target);
      }
    }
    return true;
  }
  function damage(a, p, h) {
    var o = owner(a), s = state(o);
    if (!s || !h || !h.Attacker || h.Attacker.UniqueId !== a.UniqueId) return false;
    var mul = 1, k = p.kind || "", t = now();
    if (k === "short" || k === "full" || k === "ultra") mul *= 1 + s.snapshot * 0.1;
    if (t < s.wuxiangUntil) mul *= 1.4;
    if (t < s.dodgeUntil && own(a)) mul *= 1.25;
    h.IncomingDamageScale = fp(f(h.IncomingDamageScale) * mul);
    return true;
  }
  function guard(a, p, h) {
    var s = state(a);
    if (!s || !h || !h.Target || h.Target.UniqueId !== a.UniqueId) return false;
    var t = now(), age = f(a.ActionMgr.Time);
    if (a.ActionMgr.CurrentActionName === "ywy_taiji_fist" && t < s.guardUntil) {
      h.IncomingDamageScale = fp(0); h.DestPassiveActionEnable = false;
      if (s.guardPaid !== s.action && t >= s.counterReady) {
        s.guardPaid = s.action; s.counterReady = t + 1; s.guards++;
        var precise = age <= 0.2;
        qi(a, precise ? 25 : 20); ultra(a, precise ? 12 : 8); shi(s, 1);
        if (has(a, 6)) {
          spawn(a, "ywy_taiji_fist", "ywy_taiji_counter", a.Position.x, a.Position.y + 0.8, a.Dir, 0, precise ? 1.5 : 1, null);
        }
      }
    } else if (a.ActionMgr.CurrentActionName === "ywy_taiji_fist" && age < 0.5) {
      h.IncomingDamageScale = fp(f(h.IncomingDamageScale) * 0.3);
    }
    return true;
  }
  function emit(a, p) {
    var s = state(a), k = p.kind, key = "emit:" + k;
    if (!s || s.emit[key]) return true;
    s.emit[key] = true;
    var x = a.Position.x + a.Dir * 0.7, y = a.Position.y + 0.9, row = a.ActionMgr.CurrentActionName;
    if (k === "zhenwu") {
      spawn(a, row, "ywy_zhenwu_bolt", x, y, a.Dir, 0, 1, null);
      if (has(a, 2)) {
        spawn(a, row, "ywy_zhenwu_bolt_up", x, y, a.Dir, 0.2, 0.75, null);
        spawn(a, row, "ywy_zhenwu_bolt_down", x, y, a.Dir, -0.2, 0.75, null);
      }
    } else if (k === "circle_follow" && has(a, 4)) {
      spawn(a, row, "ywy_sword_echo", x + a.Dir, y, a.Dir, 0, 1, null);
      spawn(a, row, "ywy_sword_echo", x + a.Dir * 2, y, a.Dir, 0, 1, null);
    } else if (k === "ultra") {
      spawn(a, row, "ywy_wuxiang", a.Position.x, y, a.Dir, 0, 1.5, null);
    }
    return true;
  }
  function gate(a, p) {
    var s = state(a); if (!s) return false;
    if (p.move && !moveAllowed(a,s,p)) return false;
    if (p.card) return has(a, p.card);
    if (p.dash === 1) return s.groundDashCount === 0 || now() >= s.groundDashReady;
    if (p.dash === 2) return s.groundDashCount === 1 && now() < s.groundDashReady;
    if (p.escape) return !a.IsDead && !a.CinemaControl && now() >= s.escapeReady &&
      /^(behit_up|behit_middle|push_back|push_back_2|push_down|push_down_2|knockdown|knockdown_loop)$/.test(a.ActionMgr.CurrentActionName);
    return true;
  }
  function visualBind(a, p) {
    var o=owner(a), s=o && R.states.get(o.UniqueId), v=R.visuals.get(a.UniqueId);
    if (!o || !s || s.battle!==battle() || o.IsDead) return false;
    var expected = p.bound === "charge" ? /^ywy_charge$/ : p.bound === "circle" ? /^ywy_circle_(short|full)$/ : /^ywy_ultra$/;
    if (!v) {
      if (!expected.test(o.ActionMgr.CurrentActionName)) return false;
      v={caster:o,battle:s.battle,room:s.room,action:o.ActionMgr.ActionChangeAutoId};
      R.visuals.set(a.UniqueId,v);a.TargetMgr.SetTarget(o);
    }
    return v.caster===o && v.battle===battle() && v.room===s.room &&
      v.action===o.ActionMgr.ActionChangeAutoId && expected.test(o.ActionMgr.CurrentActionName);
  }
  function wrap(name, fn) {
    pubfuncs[name] = function (js, p, obj) {
      try { return fn(js && js.Actor, p || {}, obj); }
      catch (e) { return error(name, e); }
    };
  }
  wrap("YwyStart", start); wrap("YwyHit", hit); wrap("YwyDamage", damage);
  wrap("YwyGuard", guard); wrap("YwyEmit", emit); wrap("YwyGate", gate);
  wrap("YwyVisualBind",visualBind);wrap("YwyVisualAlive",visualBind);
  wrap("YwyBulletDone",function(a){if(a){R.visuals.delete(a.UniqueId);R.impacts.delete(a.UniqueId);}return true;});
  wrap("YwyBorn", function (a) { clear(a); state(a); return true; });
  wrap("YwyReset", function (a) { clear(a); return true; });
  R.stage = function (a) {
    if (!own(a)) return false;
    try {
      var s = state(a); s.room++; s.shi = 0; s.lastStyle = ""; s.snapshot = 0;
      s.guardUntil = 0; s.wuxiangUntil = 0; s.dodgeUntil = 0; s.shieldUntil = 0; s.shieldRatio = 0;
      s.groundDashCount = 0; s.groundDashReady = 0; s.emit = {};
      a.BuffMgr.Remove("ywy_shield"); return true;
    } catch (e) { return error("stage", e); }
  };
  R.dodge = function (a) {
    if (!own(a)) return false;
    try { var s = state(a); qi(a, 10); ultra(a, 5); if (has(a, 8)) { shi(s, 1); s.dodgeUntil = now() + 1.2; } return true; }
    catch (e) { return error("dodge", e); }
  };
  R.talent = function (a, params) {
    try {
      if (!a || !params) return false;
      var level = Math.max(1, Math.min(5, f(params.GetFp("v0"))));
      a.BuffMgr.AddBuff("ywy_breath", fp(99999), fp(level), 1, a);
      return true;
    } catch (e) { return error("talent", e); }
  };
  R.view = function (a) {
    var s = own(a) ? R.states.get(a.UniqueId) : null;
    if (!s || s.actor !== a || s.battle !== battle() || a.IsDead) return null;
    return { qi: f(a.Attr.GetMP(2)), ultra: f(a.Attr.GetMP(3)), shi: s.shi,
      shield: f(a.Attr.Shield), escape: Math.max(0, s.escapeReady - now()),
      dashCharges: now()>=s.groundDashReady ? 2 : 2-s.groundDashCount,
      dashRecover: Math.max(0,s.groundDashReady-now()),
      hits: s.hits, guards: s.guards, starts: s.starts, errors: Object.keys(R.errors).length };
  };
  R.exitBattle = function (b) {
    R.states.forEach(function (s, key) {
      if (s.battle !== b) return;
      try { if (s.actor) s.actor.BuffMgr.Remove("ywy_shield"); }
      finally { R.states.delete(key); }
    });
    R.visuals.forEach(function(v,key){if(v.battle===b)R.visuals.delete(key);});
    R.impacts.forEach(function(v,key){if(v.battle===b)R.impacts.delete(key);});
    if (typeof R.disposeHUD === "function") R.disposeHUD();
  };
})();
